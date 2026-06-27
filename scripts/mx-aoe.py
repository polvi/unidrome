#!/usr/bin/env python3
"""Generate a ForeFlight KML layer of Mexican airports of entry (customs), for the
North America Airports of Entry content pack.

Static source: data/mx/afac/sistema.csv — the AFAC "Sistema Aeroportuario
Mexicano" list of concessioned airports. It has no customs column and no
coordinates, so:
  - airport of entry  := operation type (col 10) mentions "Internacional"
    (international service ⇒ customs/Aduana + immigration/INM). Domestic-only and
    private airports are dropped.
  - coordinates       := joined by ICAO (col 2, MM**) from OurAirports.

(The canonical AFAC source is behind a bot challenge and shifts structure, so a
live importer is deferred; this is the static stopgap.)
"""

import csv
import os
import xml.etree.ElementTree as ET

SISTEMA = "data/mx/afac/sistema.csv"
OURAIRPORTS = "data/world/ourairports/airports.csv"
OUTPUT = "build/MX_AOE.kml"  # gitignored build dir; seed input for the worker

# sistema.csv column indexes (5 header rows precede the data)
C_IATA, C_ICAO, C_NAME, C_APT_CITY, C_AERO_CITY = 1, 2, 3, 4, 5
C_STATE, C_MUNI, C_OPERATOR, C_GROUP, C_OPTYPE = 6, 7, 8, 9, 10


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def load_coords():
    """ICAO -> (lat, lon) from OurAirports (icao_code, then ident, then gps_code)."""
    coords = {}
    with open(OURAIRPORTS) as f:
        for r in csv.DictReader(f):
            lat, lon = r.get("latitude_deg", "").strip(), r.get("longitude_deg", "").strip()
            if not lat or not lon:
                continue
            for col in ("ident", "gps_code", "icao_code"):
                k = (r.get(col) or "").strip().upper()
                if k:
                    coords[k] = (lat, lon)  # icao_code last so it wins
    return coords


def load_airports():
    rows = list(csv.reader(open(SISTEMA, encoding="utf-8-sig")))
    out = []
    for r in rows[5:]:
        if len(r) <= C_OPTYPE:
            continue
        icao = r[C_ICAO].strip().upper()
        optype = r[C_OPTYPE].strip()
        if not icao or icao == "N/D":
            continue
        if "internacional" not in optype.lower():
            continue  # not an international airport of entry / no customs
        out.append({
            "iata": r[C_IATA].strip(),
            "icao": icao,
            "name": r[C_NAME].strip(),
            "city": (r[C_APT_CITY].strip() or r[C_AERO_CITY].strip()),
            "state": r[C_STATE].strip(),
            "muni": r[C_MUNI].strip(),
            "operator": r[C_OPERATOR].strip(),
            "group": r[C_GROUP].strip(),
            "optype": optype,
        })
    return out


def description_html(a):
    loc = ", ".join(p for p in (a["muni"] or a["city"], a["state"]) if p)
    parts = [f"<b>{esc(a['name'])}</b> ({esc(a['icao'])})"]
    if loc:
        parts.append(esc(loc))
    parts.append("<br/><b>Airport of Entry</b>")
    parts.append("International airport &mdash; customs (Aduana) &amp; immigration (INM)")
    operator = a["operator"] + (f" ({a['group']})" if a["group"] else "")
    if operator.strip():
        parts.append("<br/>Operator: " + esc(operator))
    return "<br/>".join(parts)


def main():
    coords = load_coords()
    airports = load_airports()

    placed, missing = [], []
    for a in airports:
        if a["icao"] in coords:
            a["lat"], a["lon"] = coords[a["icao"]]
            placed.append(a)
        else:
            missing.append(a["icao"])

    kml_ns = "http://www.opengis.net/kml/2.2"
    ET.register_namespace("", kml_ns)
    kml = ET.Element(f"{{{kml_ns}}}kml")
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = "Mexico Airports of Entry"

    descriptions = {}
    for a in sorted(placed, key=lambda x: (x["state"], x["name"])):
        pm = ET.SubElement(doc, "Placemark")
        ET.SubElement(pm, "name").text = f"{a['icao']} — {a['name']}"
        token = f"@@DESC{len(descriptions)}@@"
        descriptions[token] = description_html(a)
        ET.SubElement(pm, "description").text = token
        point = ET.SubElement(pm, "Point")
        ET.SubElement(point, "coordinates").text = f"{a['lon']},{a['lat']},0"

    ET.indent(ET.ElementTree(kml))
    xml = ET.tostring(kml, encoding="unicode")
    for token, html in descriptions.items():
        xml = xml.replace(token, f"<![CDATA[{html}]]>")
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("<?xml version='1.0' encoding='UTF-8'?>\n")
        f.write(xml)

    print(f"Wrote {len(placed)} Mexican AOE airports to {OUTPUT}")
    if missing:
        print(f"  no coords for: {', '.join(missing)}")


if __name__ == "__main__":
    main()
