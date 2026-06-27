#!/usr/bin/env python3
"""Emit a compact ident -> coordinates lookup from local FAA NASR data, for the
Cloudflare worker that rebuilds the CBP fact-sheet content pack.

Output: nasr-coords.json = {IDENT: [lat, lon, "ARPT_NAME — CITY, ST"]}

The worker uses this to (a) keep only fact-sheet idents that have known coords
and (b) build the "CBP Fact Sheet Airports.kml" layer. The lookup mirrors
scripts/cbp-factsheets.py load_coords(): CBP fact sheets use ICAO-style idents
(KSEA), NASR records both ICAO_ID and the FAA LID (ARPT_ID), so we expose every
airport under its ICAO_ID and its ARPT_ID. The worker additionally tries an
ICAO ident with the leading "K" stripped (handled at lookup time there).
"""

import csv
import json
import os

NASR = "data/us/faa/nasr/APT_BASE.csv"
OUTPUT = "build/nasr-coords.json"  # gitignored build dir; seed input for the worker


def main():
    coords = {}
    with open(NASR) as f:
        for r in csv.DictReader(f):
            lat, lon = r["LAT_DECIMAL"].strip(), r["LONG_DECIMAL"].strip()
            if not lat or not lon:
                continue
            label = (f"{r['ARPT_NAME'].strip()} — "
                     f"{r['CITY'].strip()}, {r['STATE_CODE'].strip()}")
            rec = [lat, lon, label]
            # ARPT_ID (FAA LID) first so a real ICAO_ID overwrites it below.
            arpt_id = r["ARPT_ID"].strip().upper()
            if arpt_id:
                coords[arpt_id] = rec
            icao = r.get("ICAO_ID", "").strip().upper()
            if icao:
                coords[icao] = rec

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(coords, f, separators=(",", ":"))
    print(f"Wrote {len(coords)} idents to {OUTPUT}")


if __name__ == "__main__":
    main()
