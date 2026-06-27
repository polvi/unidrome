// Dynamic pack "oregon-seaplane": rebuild the Oregon power-boat (seaplane-capable)
// waters KML from the Oregon State Marine Board ArcGIS services and serve it as
// its own content pack. Ported from scripts/oregon-seaplane.py.
//
// Geometry is simplified + rounded server-side by ArcGIS (maxAllowableOffset +
// geometryPrecision), so the payload is ~4 MB (vs ~39 MB raw) and we don't need
// to run Douglas-Peucker in the worker. We still compute a centroid per waterbody
// for the tappable point that carries the label + rule notes.

import type { Env } from "./env";
import { manifestKey, packPrefix, stateKey } from "./env";
import { buildManifest } from "./manifest";

const ID = "oregon-seaplane";
const LAYER_FILE = "Oregon Power-Boat Waters (Seaplane).kml";
const KML_CT = "application/vnd.google-earth.kml+xml";

const WATERWAYS =
  "https://services.arcgis.com/uUvqNMGPm7axC2dD/arcgis/rest/services/Oregon_Boated_Waterways_Public/FeatureServer/0/query";
const REGS =
  "https://services.arcgis.com/uUvqNMGPm7axC2dD/arcgis/rest/services/Boating_Regulations_Public_0422/FeatureServer/0/query";
const WHERE = "Boated='yes' AND (MotorUse IS NULL OR MotorUse='Motors Allowed')";
const REG_WHERE =
  "Symbol_Class IN ('Motor Restriction','All Boats Prohibited','Speed Restriction','Slow No-Wake')";
const PAGE = 1000;
const COORD_DECIMALS = 5;

const layerKey = () => `${packPrefix(ID)}layers/${LAYER_FILE}`;

// --- ArcGIS fetch ---

interface RegRow {
  Name?: string;
  Waterway?: string;
  Restriction?: string;
  Symbol_Class?: string;
  Rule_Link?: string;
}
interface WwProps {
  Waterway_NM?: string;
  MotorUse?: string | null;
  MotorUseSub?: string | null;
  MotorUseCov?: string | null;
  AW_URL?: string | null;
  COUNTY?: string | null;
  Region?: string | null;
}
type Position = [number, number];
interface Feature {
  geometry: { type: "Polygon" | "MultiPolygon"; coordinates: Position[][] | Position[][][] } | null;
  properties: WwProps;
}

// The waterways layer disambiguates same-named lakes with a "(County)" suffix
// (e.g. "Elk Lake (Deschutes)") while the regulations layer uses the base name
// ("Elk Lake"), so strip parentheticals before normalizing to match them.
const normName = (s: string | null | undefined) =>
  (s ?? "").toLowerCase().replace(/\([^)]*\)/g, "").replace(/[^a-z0-9]/g, "");

// Words that mark a restriction as applying to a sub-zone (a swim area, marina,
// dam boom, an arm/cove, a river reach) rather than the whole waterbody.
const ZONE =
  /\b(within|feet|yards|arm|cove|inlet|bridge|upstream|downstream|above|below|boom|swim|marina|ramp|dam|channel|mouth|boundary|marked|buoyed|breakwater|narrows|slough|portion|enclosure|designated)\b/i;

/** True if a rule makes the WHOLE waterbody unusable for a seaplane (gas motor
 * needs to take off): a whole-lake speed/closure ("entire") or a whole-lake
 * motor ban (electric-only / no-motor with no sub-zone qualifier). */
function disqualifies(cls: string, text: string): boolean {
  const t = text.toLowerCase();
  if (/\bentire\b/.test(t)) return true;
  if (
    cls === "Motor Restriction" &&
    /(electric motors only|no motor use|motors prohibited)/.test(t) &&
    !ZONE.test(t)
  ) {
    return true;
  }
  return false;
}

async function getJson(url: string): Promise<any> {
  const res = await fetch(url, {
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(60000), // don't let a slow ArcGIS query hang the run
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.json();
}

/** normalized waterway name -> motor/closure rules */
async function fetchRegs(): Promise<Map<string, RegRow[]>> {
  const params = new URLSearchParams({
    where: REG_WHERE,
    outFields: "Name,Waterway,Rule_Type,Restriction,Symbol_Class,Rule_Link",
    returnGeometry: "false",
    f: "json",
  });
  const data = await getJson(`${REGS}?${params}`);
  const byName = new Map<string, RegRow[]>();
  for (const feat of data.features ?? []) {
    const a: RegRow = feat.attributes ?? {};
    const key = normName(a.Waterway);
    const list = byName.get(key);
    if (list) list.push(a);
    else byName.set(key, [a]);
  }
  return byName;
}

/** simplified power-boat waterbody polygons */
async function fetchWaterways(): Promise<Feature[]> {
  const features: Feature[] = [];
  let offset = 0;
  for (;;) {
    const params = new URLSearchParams({
      where: WHERE,
      outFields: "Waterway_NM,MotorUse,MotorUseSub,MotorUseCov,AW_URL,COUNTY,Region",
      outSR: "4326",
      f: "geojson",
      maxAllowableOffset: "0.0001", // ~11 m, matches the script's SIMPLIFY_EPS
      geometryPrecision: String(COORD_DECIMALS),
      resultOffset: String(offset),
      resultRecordCount: String(PAGE),
    });
    const data = await getJson(`${WATERWAYS}?${params}`);
    const batch: Feature[] = data.features ?? [];
    features.push(...batch);
    if (batch.length < PAGE) break;
    offset += PAGE;
  }
  return features;
}

// --- geometry helpers ---

/** signed-area-weighted centroid of one closed ring */
function ringAreaCentroid(ring: Position[]): { area: number; pt: Position } {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i + 1 < ring.length; i++) {
    const [x0, y0] = ring[i];
    const [x1, y1] = ring[i + 1];
    const cross = x0 * y1 - x1 * y0;
    a += cross;
    cx += (x0 + x1) * cross;
    cy += (y0 + y1) * cross;
  }
  a *= 0.5;
  if (a === 0) {
    const n = ring.length || 1;
    const sx = ring.reduce((s, p) => s + p[0], 0) / n;
    const sy = ring.reduce((s, p) => s + p[1], 0) / n;
    return { area: 0, pt: [sx, sy] };
  }
  return { area: Math.abs(a), pt: [cx / (6 * a), cy / (6 * a)] };
}

/** centroid of the largest outer ring across a (multi)polygon's parts */
function centroid(parts: Position[][][]): Position {
  let bestArea = -1;
  let best: Position = [0, 0];
  for (const rings of parts) {
    const { area, pt } = ringAreaCentroid(rings[0]);
    if (area > bestArea) {
      bestArea = area;
      best = pt;
    }
  }
  return best;
}

const round = (n: number) => Number(n.toFixed(COORD_DECIMALS));
const ringCoords = (ring: Position[]) =>
  ring.map(([x, y]) => `${round(x)},${round(y)},0`).join(" ");

// --- KML build ---

const esc = (s: string | null | undefined) =>
  (s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function descriptionHtml(props: WwProps, rules: RegRow[]): string {
  const name = props.Waterway_NM || "Unnamed waterway";
  const loc = [props.COUNTY, props.Region].filter(Boolean).join(", ");
  const mu = props.MotorUse || "Default: motors allowed unless a rule below applies";
  const cov = [props.MotorUseCov, props.MotorUseSub].filter(Boolean) as string[];

  const parts = [`<b>${esc(name)}</b>`];
  if (loc) parts.push(esc(loc));
  parts.push("Power boats allowed &mdash; seaplane-capable.");
  parts.push("Motor use: " + esc(mu) + (cov.length ? ` (${esc(cov.join(", "))})` : ""));

  if (rules.length) {
    parts.push("<br/><b>&#9888; Zone restrictions &mdash; keep landings/takeoffs clear of these areas</b>");
    for (const r of rules) {
      parts.push(`<b>${esc(r.Symbol_Class)}</b>: ${esc(r.Name)}`);
      if (r.Restriction) parts.push(esc(r.Restriction));
      if (r.Rule_Link) parts.push(`<a href="${esc(r.Rule_Link)}">Oregon OAR rule</a>`);
    }
  } else {
    parts.push("<br/>No posted motor/closure rule on file (verify locally before use).");
  }
  if (props.AW_URL) parts.push(`<br/><a href="${esc(props.AW_URL)}">Waterway details</a>`);
  return parts.join("<br/>");
}

function toParts(feat: Feature): Position[][][] {
  const g = feat.geometry;
  if (!g) return [];
  if (g.type === "Polygon") return [g.coordinates as Position[][]];
  if (g.type === "MultiPolygon") return g.coordinates as Position[][][];
  return [];
}

interface BuildResult {
  kml: string;
  total: number;
  flagged: number;
  excluded: number;
}

function buildKml(features: Feature[], regs: Map<string, RegRow[]>): BuildResult {
  const lines: string[] = [
    `<?xml version='1.0' encoding='UTF-8'?>`,
    `<kml xmlns="http://www.opengis.net/kml/2.2">`,
    `  <Document>`,
    `    <name>Oregon Power-Boat Waters (Seaplane)</name>`,
    // aabbggrr. Green = power boats allowed; orange flags waters with a state
    // motor/closure rule. Polygons draw the area; a centroid point (the only
    // tappable/labeled element in FF) carries the name + notes.
    `    <Style id="ok"><LineStyle><color>ff14b414</color><width>2.2</width></LineStyle><PolyStyle><color>6614b414</color></PolyStyle></Style>`,
    `    <Style id="restricted"><LineStyle><color>ff0073ff</color><width>3.0</width></LineStyle><PolyStyle><color>6614b414</color></PolyStyle></Style>`,
    `    <Style id="pt_ok"><IconStyle><color>ff14b414</color><scale>0.9</scale></IconStyle><LabelStyle><scale>0.8</scale></LabelStyle></Style>`,
    `    <Style id="pt_restricted"><IconStyle><color>ff0073ff</color><scale>0.9</scale></IconStyle><LabelStyle><scale>0.8</scale></LabelStyle></Style>`,
  ];

  let total = 0;
  let flagged = 0;
  let excluded = 0;
  for (const feat of features) {
    const parts = toParts(feat).filter((rings) => rings[0] && rings[0].length >= 4);
    if (!parts.length) continue;

    const props = feat.properties ?? {};
    const nm = props.Waterway_NM || "Unnamed waterway";
    const rules = regs.get(normName(props.Waterway_NM)) ?? [];

    // Drop waters with a whole-lake motor/closure/speed restriction — a seaplane
    // can't take off there (e.g. Waldo Lake & Elk Lake are electric-only).
    if (rules.some((r) => disqualifies(r.Symbol_Class ?? "", r.Restriction ?? ""))) {
      excluded++;
      continue;
    }
    if (rules.length) flagged++; // kept, but has sub-zone restrictions

    // shape placemark (fill/outline only; FF ignores its name/description)
    lines.push(`    <Placemark><styleUrl>#${rules.length ? "restricted" : "ok"}</styleUrl>`);
    const multi = parts.length > 1;
    if (multi) lines.push(`      <MultiGeometry>`);
    for (const rings of parts) {
      lines.push(`      <Polygon><outerBoundaryIs><LinearRing><coordinates>${ringCoords(rings[0])}</coordinates></LinearRing></outerBoundaryIs>`);
      for (const hole of rings.slice(1)) {
        if (hole.length < 4) continue;
        lines.push(`        <innerBoundaryIs><LinearRing><coordinates>${ringCoords(hole)}</coordinates></LinearRing></innerBoundaryIs>`);
      }
      lines.push(`      </Polygon>`);
    }
    if (multi) lines.push(`      </MultiGeometry>`);
    lines.push(`    </Placemark>`);

    // centroid waypoint: the tappable label + rule notes
    const [cx, cy] = centroid(parts);
    lines.push(
      `    <Placemark>`,
      `      <name>${esc(rules.length ? `⚠ ${nm}` : nm)}</name>`,
      `      <styleUrl>#${rules.length ? "pt_restricted" : "pt_ok"}</styleUrl>`,
      `      <description><![CDATA[${descriptionHtml(props, rules)}]]></description>`,
      `      <Point><coordinates>${round(cx)},${round(cy)},0</coordinates></Point>`,
      `    </Placemark>`,
    );
    total++;
  }

  lines.push(`  </Document>`, `</kml>`, ``);
  return { kml: lines.join("\n"), total, flagged, excluded };
}

// --- refresh ---

interface SeaplaneState {
  hash: string | null;
  lastRun: string | null;
  counts: { total: number; flagged: number } | null;
}

async function sha256Hex(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function refreshOregonSeaplane(env: Env): Promise<void> {
  const now = new Date();

  const [regs, features] = await Promise.all([fetchRegs(), fetchWaterways()]);
  const { kml, total, flagged, excluded } = buildKml(features, regs);
  const hash = await sha256Hex(kml);

  const stateObj = await env.PACK.get(stateKey(ID));
  const state: SeaplaneState = stateObj
    ? await stateObj.json<SeaplaneState>()
    : { hash: null, lastRun: null, counts: null };

  const layerExists = !!(await env.PACK.head(layerKey()));
  const manifestExists = !!(await env.PACK.head(manifestKey(ID)));
  const changed = state.hash !== hash || !layerExists || !manifestExists;

  if (changed) {
    await env.PACK.put(layerKey(), kml, { httpMetadata: { contentType: KML_CT } });
    await env.PACK.put(
      manifestKey(ID),
      buildManifest(now, "Oregon Power-Boat Waters (Seaplane)", "OR.SEAPL"),
      { httpMetadata: { contentType: "application/json" } },
    );
  }

  state.hash = hash;
  state.lastRun = now.toISOString();
  state.counts = { total, flagged };
  await env.PACK.put(stateKey(ID), JSON.stringify(state), {
    httpMetadata: { contentType: "application/json" },
  });

  console.log(
    `[${ID}] total=${total} flagged=${flagged} excluded=${excluded} changed=${changed}`,
  );
}
