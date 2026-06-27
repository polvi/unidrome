// Build the "CBP Fact Sheet Airports.kml" layer. Mirrors the placemark format
// in scripts/cbp-factsheets.py build_factsheet_layer(): one Placemark per ident
// whose <name> is the bare ident (so the matching navdata PDF attaches), with a
// plain-text description and a Point at the airport's coordinates.

import type { CoordMap } from "./env";

function xmlEscape(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** ICAO, then LID, then ICAO with a leading "K" stripped (matches load_coords). */
export function lookupCoords(
  ident: string,
  coords: CoordMap,
): [string, string, string] | null {
  if (coords[ident]) return coords[ident];
  if (ident.startsWith("K") && ident.length === 4 && coords[ident.slice(1)]) {
    return coords[ident.slice(1)];
  }
  return null;
}

/** Idents (of those with known coords) that should appear in the layer/pack. */
export function placeableIdents(
  idents: Iterable<string>,
  coords: CoordMap,
): Set<string> {
  const placed = new Set<string>();
  for (const ident of idents) {
    if (lookupCoords(ident, coords)) placed.add(ident);
  }
  return placed;
}

/** Serialize the KML document for the given idents (sorted), 2-space indented. */
export function buildFactsheetKml(
  idents: Iterable<string>,
  coords: CoordMap,
): string {
  const sorted = [...idents].sort();
  const lines: string[] = [
    `<?xml version='1.0' encoding='UTF-8'?>`,
    `<kml xmlns="http://www.opengis.net/kml/2.2">`,
    `  <Document>`,
    `    <name>US CBP Fact Sheet Airports</name>`,
  ];
  for (const ident of sorted) {
    const rec = lookupCoords(ident, coords);
    if (!rec) continue;
    const [lat, lon, label] = rec;
    const desc =
      `${label}\n\nCBP General Aviation Airport Fact Sheet attached (tap to open).`;
    lines.push(
      `    <Placemark>`,
      `      <name>${xmlEscape(ident)}</name>`,
      `      <description>${xmlEscape(desc)}</description>`,
      `      <Point>`,
      `        <coordinates>${lon},${lat},0</coordinates>`,
      `      </Point>`,
      `    </Placemark>`,
    );
  }
  lines.push(`  </Document>`, `</kml>`, ``);
  return lines.join("\n");
}
