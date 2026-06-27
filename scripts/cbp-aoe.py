#!/usr/bin/env python3
"""Generate a ForeFlight KML layer of U.S. airports where you can clear customs
flying an aircraft into the United States (CBP airports of entry).

Source: FAA NASR airport data (data/us/faa/nasr/APT_BASE.csv), the same dataset
pdc.py uses. NASR carries the FAA's customs designations per airport:

    CUST_FLAG        -> Customs Airport of Entry (AOE)
    LNDG_RIGHTS_FLAG -> Customs Landing Rights Airport (prior CBP permission)

An airport may carry both. This mirrors scripts/cbsa-aoe.py (Canada).

Note: NASR does not separately flag CBP "User Fee" airports; many of those are
recorded here as Landing Rights airports. For the authoritative/complete picture
always confirm against CBP before flying.
"""

import csv
import os
import xml.etree.ElementTree as ET

DATA_DIR = "data/us/faa/nasr"
OUTPUT = "build/US_AOE.kml"  # gitignored build dir

# Customs designations a pilot can use to clear into the U.S., mapped to a note.
# Keyed by the NASR column whose value is "Y".
AOE_FLAGS = {
    "CUST_FLAG":        "AOE: Customs Airport of Entry (customs available)",
    "LNDG_RIGHTS_FLAG": "LRA: Landing Rights Airport (prior CBP permission required)",
}
SHORT = {"CUST_FLAG": "AOE", "LNDG_RIGHTS_FLAG": "LRA"}


def main():
    airports = []
    with open(f"{DATA_DIR}/APT_BASE.csv") as f:
        for row in csv.DictReader(f):
            matched = [col for col in AOE_FLAGS if row.get(col, "").strip() == "Y"]
            if not matched:
                continue
            lat, lon = row["LAT_DECIMAL"].strip(), row["LONG_DECIMAL"].strip()
            if not lat or not lon:
                continue
            airports.append({
                "id": row["ARPT_ID"].strip(),
                "name": row["ARPT_NAME"].strip(),
                "city": row["CITY"].strip(),
                "state": row["STATE_CODE"].strip(),
                "lat": lat,
                "lon": lon,
                "codes": [SHORT[c] for c in matched],
                "notes": [AOE_FLAGS[c] for c in matched],
            })

    # Build KML
    kml_ns = "http://www.opengis.net/kml/2.2"
    ET.register_namespace("", kml_ns)
    kml = ET.Element(f"{{{kml_ns}}}kml")
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = "US Airports of Entry (CBP)"

    for apt in sorted(airports, key=lambda a: a["id"]):
        pm = ET.SubElement(doc, "Placemark")
        ET.SubElement(pm, "name").text = f"{apt['id']} - {apt['name']} ({'/'.join(apt['codes'])})"
        desc = f"{apt['city']}, {apt['state']}\n\n" + "\n".join(apt["notes"])
        ET.SubElement(pm, "description").text = desc
        point = ET.SubElement(pm, "Point")
        ET.SubElement(point, "coordinates").text = f"{apt['lon']},{apt['lat']},0"

    tree = ET.ElementTree(kml)
    ET.indent(tree)
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    tree.write(OUTPUT, xml_declaration=True, encoding="UTF-8")
    print(f"Wrote {len(airports)} U.S. AOE airports to {OUTPUT}")


if __name__ == "__main__":
    main()
