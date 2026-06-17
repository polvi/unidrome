#!/usr/bin/env python3
"""Add an Oregon "power-boat (seaplane-capable) waters" layer to the Barbless
Maps ForeFlight content pack.

Source: Oregon State Marine Board boating GIS (the Experience app at
experience.arcgis.com/experience/72308dd6b893451690a14437cde89be8):
  - Oregon_Boated_Waterways  -> boatable waterbody polygons + MotorUse
  - Boating_Regulations      -> the actual rule text (motor restrictions, closures)

In Oregon motors are allowed by default unless restricted, so where power boats are
allowed a seaplane (gas engine) may operate. We keep boated waters that aren't
motor-prohibited/electric-only. The waterbody layer's MotorUse field is mostly
empty, though -- the real restrictions live in Boating_Regulations -- so we match
those rules to each waterbody by name, flag restricted ones (orange outline), and
put the state's rule text + OAR link in the clickable description so they can be
read in the field.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.setrecursionlimit(100000)  # detailed shoreline rings recurse deeply in RDP

LAYER = ("https://services.arcgis.com/uUvqNMGPm7axC2dD/arcgis/rest/services/"
         "Oregon_Boated_Waterways_Public/FeatureServer/0/query")
REGS = ("https://services.arcgis.com/uUvqNMGPm7axC2dD/arcgis/rest/services/"
        "Boating_Regulations_Public_0422/FeatureServer/0/query")
WHERE = "Boated='yes' AND (MotorUse IS NULL OR MotorUse='Motors Allowed')"
# Rule classes that bear on whether a seaplane can operate at all.
REG_WHERE = "Symbol_Class IN ('Motor Restriction','All Boats Prohibited')"
PAGE = 1000

CACHE = "data/us/or/oregon_powerboat_waters.geojson"
REG_CACHE = "data/us/or/oregon_boating_regulations.json"
OUT = "data/content-pack/barbless-maps/layers/Oregon Power-Boat Waters (Seaplane).kml"
PACK_DIR = "data/content-pack/barbless-maps"

KML_NS = "http://www.opengis.net/kml/2.2"

# Douglas-Peucker tolerance in degrees (~0.0001 deg ≈ 11 m) and coordinate
# rounding, to shrink the detailed shoreline polygons with no visible change.
SIMPLIFY_EPS = 0.0001
COORD_DECIMALS = 5


def fetch_geojson():
    """Page through the feature service and return a merged GeoJSON dict."""
    features = []
    offset = 0
    while True:
        params = {
            "where": WHERE,
            "outFields": "Waterway_NM,MotorUse,MotorUseSub,MotorUseCov,AW_URL,COUNTY,Region",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": PAGE,
        }
        url = LAYER + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=120) as r:
            data = json.loads(r.read())
        batch = data.get("features", [])
        features.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)
    return features


def norm_name(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def fetch_regulations():
    """Return {normalized waterway name: [rule, ...]} for motor/closure rules."""
    params = {
        "where": REG_WHERE,
        "outFields": "Name,Waterway,Rule_Type,Restriction,Symbol_Class,Rule_Link",
        "returnGeometry": "false",
        "f": "json",
    }
    url = REGS + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=120) as r:
        data = json.loads(r.read())
    os.makedirs(os.path.dirname(REG_CACHE), exist_ok=True)
    with open(REG_CACHE, "w") as f:
        json.dump(data, f)
    by_name = {}
    for feat in data.get("features", []):
        a = feat["attributes"]
        by_name.setdefault(norm_name(a.get("Waterway")), []).append(a)
    return by_name


def _rdp(pts, eps):
    """Douglas-Peucker simplification of a point list (planar lon/lat)."""
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]
    bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    norm = (dx * dx + dy * dy) ** 0.5
    dmax, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        if norm == 0:
            d = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
        else:
            d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        left = _rdp(pts[:idx + 1], eps)
        right = _rdp(pts[idx:], eps)
        return left[:-1] + right
    return [pts[0], pts[-1]]


def simplify_ring(ring):
    """Simplify a closed ring; return None if it collapses below a triangle."""
    s = _rdp(ring, SIMPLIFY_EPS)
    if s[0] != s[-1]:
        s.append(s[0])
    return s if len(s) >= 4 else None


def ring_coords(ring):
    r = COORD_DECIMALS
    return " ".join(f"{round(x, r)},{round(y, r)},0" for x, y in ring)


def _ring_area_centroid(ring):
    """Signed area and area-weighted centroid of a closed ring."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if a == 0:
        n = len(ring)
        return 0.0, (sum(x for x, _ in ring) / n, sum(y for _, y in ring) / n)
    return abs(a), (cx / (6 * a), cy / (6 * a))


def centroid(simplified):
    """Centroid of the largest outer ring across a (multi)polygon's parts.
    ForeFlight ignores shape names, so this point carries the label + notes."""
    best_area, best_pt = -1.0, None
    for rings in simplified:
        area, pt = _ring_area_centroid(rings[0])
        if area > best_area:
            best_area, best_pt = area, pt
    return best_pt


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def description_html(props, rules):
    """Clean CDATA HTML (ForeFlight guide §25.8.3.1 supports basic HTML:
    links, line breaks, headings). Surfaces the state's rule text + OAR link."""
    name = props.get("Waterway_NM") or "Unnamed waterway"
    loc = ", ".join(p for p in (props.get("COUNTY"), props.get("Region")) if p)
    mu = props.get("MotorUse") or "Default: motors allowed unless a rule below applies"
    cov = [c for c in (props.get("MotorUseCov"), props.get("MotorUseSub")) if c]

    parts = [f"<b>{esc(name)}</b>"]
    if loc:
        parts.append(esc(loc))
    parts.append("Power boats allowed &mdash; seaplane-capable.")
    parts.append("Motor use: " + esc(mu) + (f" ({esc(', '.join(cov))})" if cov else ""))

    if rules:
        parts.append("<br/><b>&#9888; Oregon boating rules on this waterway</b>")
        for r in rules:
            line = f"<b>{esc(r.get('Symbol_Class',''))}</b>: {esc(r.get('Name',''))}"
            parts.append(line)
            if r.get("Restriction"):
                parts.append(esc(r["Restriction"]))
            if r.get("Rule_Link"):
                parts.append(f'<a href="{esc(r["Rule_Link"])}">Oregon OAR rule</a>')
    else:
        parts.append("<br/>No motor/closure rule on file (verify locally before use).")

    if props.get("AW_URL"):
        parts.append(f'<br/><a href="{esc(props["AW_URL"])}">Waterway details</a>')
    return "<br/>".join(parts)


def build_kml(features, regs):
    ET.register_namespace("", KML_NS)
    kml = ET.Element(f"{{{KML_NS}}}kml")
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = "Oregon Power-Boat Waters (Seaplane)"

    # aabbggrr. Green = power boats allowed; orange flags waters that have a
    # state motor/closure rule (read the notes). Each waterbody gets a shape
    # (fill/outline) plus a centroid waypoint -- ForeFlight only makes points
    # tappable/labeled (guide §25.8.6), so the notes live on the point.
    def shape_style(sid, line, width):
        s = ET.SubElement(doc, "Style", id=sid)
        lse = ET.SubElement(s, "LineStyle")
        ET.SubElement(lse, "color").text = line
        ET.SubElement(lse, "width").text = width
        ET.SubElement(ET.SubElement(s, "PolyStyle"), "color").text = "6614b414"

    def point_style(sid, icon):
        s = ET.SubElement(doc, "Style", id=sid)
        ic = ET.SubElement(s, "IconStyle")
        ET.SubElement(ic, "color").text = icon
        ET.SubElement(ic, "scale").text = "0.9"
        ET.SubElement(ET.SubElement(s, "LabelStyle"), "scale").text = "0.8"

    shape_style("ok", "ff14b414", "2.2")        # green outline
    shape_style("restricted", "ff0073ff", "3.0")  # orange outline
    point_style("pt_ok", "ff14b414")
    point_style("pt_restricted", "ff0073ff")

    descriptions = {}
    kept = 0
    for feat in features:
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        props = feat.get("properties", {})
        if gtype == "Polygon":
            polys = [geom["coordinates"]]
        elif gtype == "MultiPolygon":
            polys = geom["coordinates"]
        else:
            continue

        # simplify rings; drop polygons/holes that collapse
        simplified = []
        for rings in polys:
            outer = simplify_ring(rings[0])
            if outer is None:
                continue
            holes = [h for h in (simplify_ring(r) for r in rings[1:]) if h]
            simplified.append([outer] + holes)
        if not simplified:
            continue

        rules = regs.get(norm_name(props.get("Waterway_NM")), [])
        nm = props.get("Waterway_NM") or "Unnamed waterway"

        # shape placemark (fill/outline only; ForeFlight ignores its name/desc)
        shape = ET.SubElement(doc, "Placemark")
        ET.SubElement(shape, "styleUrl").text = "#restricted" if rules else "#ok"
        geo_parent = shape
        if len(simplified) > 1:
            geo_parent = ET.SubElement(shape, "MultiGeometry")
        for rings in simplified:
            poly = ET.SubElement(geo_parent, "Polygon")
            outer = ET.SubElement(poly, "outerBoundaryIs")
            lr = ET.SubElement(outer, "LinearRing")
            ET.SubElement(lr, "coordinates").text = ring_coords(rings[0])
            for hole in rings[1:]:
                inner = ET.SubElement(poly, "innerBoundaryIs")
                lr = ET.SubElement(inner, "LinearRing")
                ET.SubElement(lr, "coordinates").text = ring_coords(hole)

        # centroid waypoint carries the tappable label + restriction notes
        cx, cy = centroid(simplified)
        pt = ET.SubElement(doc, "Placemark")
        ET.SubElement(pt, "name").text = ("⚠ " + nm) if rules else nm
        ET.SubElement(pt, "styleUrl").text = "#pt_restricted" if rules else "#pt_ok"
        token = f"@@DESC{len(descriptions)}@@"
        descriptions[token] = description_html(props, rules)
        ET.SubElement(pt, "description").text = token
        point = ET.SubElement(pt, "Point")
        r = COORD_DECIMALS
        ET.SubElement(point, "coordinates").text = f"{round(cx, r)},{round(cy, r)},0"
        kept += 1

    ET.indent(ET.ElementTree(kml))
    xml = ET.tostring(kml, encoding="unicode")
    for token, html in descriptions.items():
        xml = xml.replace(token, f"<![CDATA[{html}]]>")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("<?xml version='1.0' encoding='UTF-8'?>\n")
        f.write(xml)
    return kept


def rezip():
    import zipfile
    zpath = PACK_DIR + ".zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(PACK_DIR):
            for fn in files:
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, os.path.dirname(PACK_DIR)))
    return zpath


def main():
    feats = fetch_geojson()
    print(f"fetched {len(feats)} waterbody features")
    regs = fetch_regulations()
    print(f"fetched motor/closure rules for {len(regs)} waterways")
    kept = build_kml(feats, regs)
    flagged = sum(1 for f in feats
                  if regs.get(norm_name(f.get('properties', {}).get('Waterway_NM'))))
    print(f"wrote {kept} polygons to {OUT} ({flagged} flagged with restrictions)")
    print(f"rebuilt {rezip()}")


if __name__ == "__main__":
    main()
