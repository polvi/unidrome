#!/usr/bin/env python3
"""Build a ForeFlight content pack of North American airports of entry that
bundles the CBP General Aviation Airport Fact Sheets as per-airport documents.

What it does:
  1. Scrapes CBP's "General Aviation Airport Fact Sheets" index for every
     published fact-sheet PDF (one per port of entry, keyed by ICAO/ident).
  2. Downloads each PDF into the pack's navdata/ folder, named so ForeFlight
     attaches it to that airport's Documents tab. Airports without a CBP fact
     sheet simply get nothing (we only ship what CBP publishes).
  3. Copies the AOE map layers (US + Canada) into layers/.
  4. Writes manifest.json and zips the pack.

ForeFlight content pack format (Mobile Guide / support.foreflight.com):
  PackName/
    manifest.json
    layers/   -> KML/GeoJSON map layers
    navdata/  -> documents named "<WAYPOINT><DocName>.pdf" attach to <WAYPOINT>
"""

import csv
import json
import os
import re
import shutil
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor

CBP_BASE = "https://www.cbp.gov"
INDEX = CBP_BASE + "/newsroom/publications/general-aviation-airport-fact-sheets?page={}"
INDEX_PAGES = 28  # site paginates 0..27

PACK_DIR = "data/content-pack/na-airports-of-entry"
NASR = "data/us/faa/nasr/APT_BASE.csv"  # local FAA data: ident -> coordinates
DOC_NAME = "CBP GA Airport Fact Sheet"  # display name shown in ForeFlight

# ForeFlight links an associated file to a custom-layer waypoint when the file is
# named "<WAYPOINT> <Document Description>.pdf" (space-separated) AND a placemark
# named exactly <WAYPOINT> exists in a bundled map layer. So we ship a layer whose
# placemark names are the bare fact-sheet idents, and name PDFs to match.
FACTSHEET_LAYER = "CBP Fact Sheet Airports.kml"

# Canada AOE layer (no attachments) bundled alongside; produced by cbsa-aoe.py.
CANADA_SRC = "build/CA_AOE.kml"
CANADA_LAYER = "Canada Airports of Entry.kml"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def scrape_factsheets():
    """Return {ident: absolute_pdf_url} for every GA airport fact sheet."""
    sheets = {}
    pat = re.compile(r'href="([^"]+\.pdf)"', re.I)
    ga = re.compile(r'ga[ _]?airport[ _]?fact[ _]?sheet', re.I)
    for n in range(INDEX_PAGES):
        try:
            html = get(INDEX.format(n)).decode("utf-8", "replace")
        except Exception as e:
            print(f"  page {n}: {e}")
            continue
        for href in pat.findall(html):
            name = href.split("/")[-1].replace("%20", " ")
            if not ga.search(name):
                continue
            ident = re.split(r"[ _]", name)[0].upper()
            if not re.fullmatch(r"[A-Z0-9]{3,5}", ident):
                continue
            url = href if href.startswith("http") else CBP_BASE + href
            sheets[ident] = url  # dedupe by ident, newest page wins
    return sheets


def load_coords():
    """Map fact-sheet idents to (lat, lon, label) using local FAA NASR data.

    NASR records airports by FAA LID (ARPT_ID) and ICAO_ID; CBP fact sheets use
    ICAO-style idents (KSEA), so we try ICAO, then LID, then LID without the K.
    """
    by_icao, by_lid = {}, {}
    with open(NASR) as f:
        for r in csv.DictReader(f):
            lat, lon = r["LAT_DECIMAL"].strip(), r["LONG_DECIMAL"].strip()
            if not lat or not lon:
                continue
            rec = (lat, lon, f"{r['ARPT_NAME'].strip()} — "
                             f"{r['CITY'].strip()}, {r['STATE_CODE'].strip()}")
            if r.get("ICAO_ID", "").strip():
                by_icao[r["ICAO_ID"].strip().upper()] = rec
            by_lid[r["ARPT_ID"].strip().upper()] = rec

    def lookup(ident):
        if ident in by_icao:
            return by_icao[ident]
        if ident in by_lid:
            return by_lid[ident]
        if ident.startswith("K") and len(ident) == 4:
            return by_lid.get(ident[1:])
        return None
    return lookup


def build_factsheet_layer(idents, lookup, navdata_dir):
    """KML whose placemark names are the bare idents, so the navdata PDFs attach.

    Per the ForeFlight Mobile Guide 25.12.7, the map layer must live in the
    navdata/ folder (NOT layers/) for its waypoints to support associated files;
    layers/ treats KML as a plain chart with no attachments.

    Returns the set of idents that got a coordinate (others are dropped)."""
    kml_ns = "http://www.opengis.net/kml/2.2"
    ET.register_namespace("", kml_ns)
    kml = ET.Element(f"{{{kml_ns}}}kml")
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = "CBP Fact Sheet Airports"

    placed = set()
    for ident in sorted(idents):
        rec = lookup(ident)
        if not rec:
            print(f"  no local coords for {ident}, dropped from layer")
            continue
        lat, lon, label = rec
        pm = ET.SubElement(doc, "Placemark")
        ET.SubElement(pm, "name").text = ident  # must match the PDF prefix
        ET.SubElement(pm, "description").text = (
            f"{label}\n\nCBP General Aviation Airport Fact Sheet attached "
            f"(tap to open).")
        point = ET.SubElement(pm, "Point")
        ET.SubElement(point, "coordinates").text = f"{lon},{lat},0"
        placed.add(ident)

    tree = ET.ElementTree(kml)
    ET.indent(tree)
    tree.write(os.path.join(navdata_dir, FACTSHEET_LAYER),
               xml_declaration=True, encoding="UTF-8")
    return placed


def download(ident, url, navdata):
    dest = os.path.join(navdata, f"{ident} {DOC_NAME}.pdf")
    legacy = os.path.join(navdata, f"{ident}{DOC_NAME}.pdf")  # pre-space naming
    if os.path.exists(legacy) and not os.path.exists(dest):
        os.rename(legacy, dest)
    if os.path.exists(dest) and os.path.getsize(dest) > 1024:
        return ident, "cached"
    try:
        data = get(url)
    except Exception as e:
        return ident, f"FAIL {e}"
    if not data.startswith(b"%PDF"):
        return ident, "skip (not a PDF)"
    with open(dest, "wb") as f:
        f.write(data)
    return ident, "ok"


def main():
    navdata_dir = os.path.join(PACK_DIR, "navdata")
    os.makedirs(navdata_dir, exist_ok=True)
    # Everything (map layer + associated PDFs) lives in navdata/. A layers/
    # folder would treat the KML as a chart whose waypoints can't hold files,
    # so remove any leftover one from earlier builds.
    legacy_layers = os.path.join(PACK_DIR, "layers")
    if os.path.isdir(legacy_layers):
        for fn in os.listdir(legacy_layers):
            os.remove(os.path.join(legacy_layers, fn))
        os.rmdir(legacy_layers)
        print("removed legacy layers/ folder")

    # 1. scrape index, build the fact-sheet airport layer from local NASR coords.
    # Its waypoints are what the navdata PDFs attach to.
    sheets = scrape_factsheets()
    lookup = load_coords()
    placed = build_factsheet_layer(sheets.keys(), lookup, navdata_dir)
    print(f"layer: {FACTSHEET_LAYER} ({len(placed)} airports)")

    # Canada AOE layer (map layer only, no associated files)
    if os.path.exists(CANADA_SRC):
        shutil.copyfile(CANADA_SRC, os.path.join(navdata_dir, CANADA_LAYER))
        print(f"layer: {CANADA_LAYER}")
    else:
        print(f"{CANADA_SRC} missing — run cbsa-aoe.py first (skipping Canada layer)")

    # only ship PDFs that have a matching placemark to attach to
    sheets = {i: u for i, u in sheets.items() if i in placed}
    print(f"Found {len(sheets)} CBP fact sheets; downloading...")
    ok = cached = skipped = failed = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for ident, status in ex.map(lambda kv: download(kv[0], kv[1], navdata_dir),
                                    sheets.items()):
            if status == "ok": ok += 1
            elif status == "cached": cached += 1
            elif status.startswith("skip"): skipped += 1
            else:
                failed += 1
                print(f"  {ident}: {status}")
    print(f"fact sheets: {ok} downloaded, {cached} cached, "
          f"{skipped} skipped, {failed} failed")

    # drop any stray navdata file that isn't a current fact sheet or a layer
    keep = ({f"{i} {DOC_NAME}.pdf" for i in sheets}
            | {FACTSHEET_LAYER, CANADA_LAYER})
    for fn in os.listdir(navdata_dir):
        if fn not in keep:
            os.remove(os.path.join(navdata_dir, fn))
            print(f"removed stray navdata file: {fn}")

    # 3. manifest
    manifest = {
        "name": "North America Airports of Entry (CBP/CBSA)",
        "abbreviation": "NA.AOE",
        "version": 1.0,
        "effectiveDate": "20260615T000000",
        "expirationDate": "20270615T000000",
        "organizationName": "unidrome",
    }
    with open(os.path.join(PACK_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=4)

    # 4. zip
    zip_path = PACK_DIR + ".zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(PACK_DIR):
            for fn in files:
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, os.path.dirname(PACK_DIR)))
    print(f"Wrote {PACK_DIR}/ and {zip_path}")


if __name__ == "__main__":
    main()
