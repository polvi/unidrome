#!/usr/bin/env python3
"""Generate a KML file of FAA airports that support PDC (Pre-Departure Clearance)."""

import csv
import xml.etree.ElementTree as ET

DATA_DIR = "data/us/faa/nasr"
OUTPUT = "PDC.kml"

# Load PDC airport SITE_NOs from ATC_SVC
pdc_sites = set()
with open(f"{DATA_DIR}/ATC_SVC.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["CTL_SVC"].strip() == "PDC":
            pdc_sites.add(row["SITE_NO"].strip())

# Load airport info from APT_BASE and match
airports = []
with open(f"{DATA_DIR}/APT_BASE.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["SITE_NO"].strip() in pdc_sites:
            airports.append({
                "id": row["ARPT_ID"].strip(),
                "name": row["ARPT_NAME"].strip(),
                "city": row["CITY"].strip(),
                "state": row["STATE_CODE"].strip(),
                "lat": row["LAT_DECIMAL"].strip(),
                "lon": row["LONG_DECIMAL"].strip(),
            })

# Build KML
kml_ns = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", kml_ns)
kml = ET.Element(f"{{{kml_ns}}}kml")
doc = ET.SubElement(kml, "Document")
ET.SubElement(doc, "name").text = "FAA PDC Airports"

for apt in sorted(airports, key=lambda a: a["id"]):
    pm = ET.SubElement(doc, "Placemark")
    ET.SubElement(pm, "name").text = f"{apt['id']} - {apt['name']}"
    ET.SubElement(pm, "description").text = f"{apt['city']}, {apt['state']}"
    point = ET.SubElement(pm, "Point")
    ET.SubElement(point, "coordinates").text = f"{apt['lon']},{apt['lat']},0"

tree = ET.ElementTree(kml)
ET.indent(tree)
tree.write(OUTPUT, xml_declaration=True, encoding="UTF-8")
print(f"Wrote {len(airports)} PDC airports to {OUTPUT}")
