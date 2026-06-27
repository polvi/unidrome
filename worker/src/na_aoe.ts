// Dynamic pack "na-airports-of-entry": diff CBP's current fact sheets against
// our R2 state, fetch only what's new/changed, regenerate the US KML when the
// airport set changes, keep the manifest + static Canada layer in place, and
// persist state. Idempotent and resumable — state only advances on successful
// PUTs, so failures retry next run. Mirrors scripts/cbp-factsheets.py.

import { fetchPdf, scrapeFactsheets } from "./cbp";
import type { CoordMap, Env, State } from "./env";
import { emptyState, manifestKey, packPrefix, stateKey, staticKey } from "./env";
import { buildFactsheetKml, placeableIdents } from "./kml";
import { buildManifest } from "./manifest";

const ID = "na-airports-of-entry";
const DOC_NAME = "CBP GA Airport Fact Sheet";
const FACTSHEET_LAYER = "US CBP Fact Sheet Airports.kml";
const CANADA_LAYER = "Canada Airports of Entry.kml";
const KML_CT = "application/vnd.google-earth.kml+xml";

// Seeded offline (space-free keys; the worker writes the spaced pack filenames).
const COORDS_SEED = "nasr-coords.json";
const CANADA_SEED = "canada.kml";
const MEXICO_LAYER = "Mexico Airports of Entry.kml";
const MEXICO_SEED = "mexico.kml";

const pdfKey = (ident: string) =>
  `${packPrefix(ID)}navdata/${ident} ${DOC_NAME}.pdf`;
const navKey = (name: string) => `${packPrefix(ID)}navdata/${name}`;

export async function refreshNaAoe(env: Env): Promise<void> {
  const now = new Date();

  const coordsObj = await env.PACK.get(staticKey(ID, COORDS_SEED));
  if (!coordsObj) {
    throw new Error(
      `missing ${staticKey(ID, COORDS_SEED)} — seed it first (build-nasr-coords.py)`,
    );
  }
  const coords = await coordsObj.json<CoordMap>();

  const stateObj = await env.PACK.get(stateKey(ID));
  const state: State = stateObj ? await stateObj.json<State>() : emptyState();

  // Current CBP fact sheets, filtered to idents we have coordinates for (so
  // every shipped PDF has a matching placemark).
  const sheets = await scrapeFactsheets(env.USER_AGENT);
  const placeable = placeableIdents(Object.keys(sheets), coords);
  const desired: Record<string, string> = {};
  for (const ident of placeable) desired[ident] = sheets[ident];

  let added = 0;
  let changed = 0;
  let removed = 0;

  const saveState = () =>
    env.PACK.put(stateKey(ID), JSON.stringify(state), {
      httpMetadata: { contentType: "application/json" },
    });

  // Figure out which idents actually need a (re)download (sequential R2 heads).
  const todo: { ident: string; url: string; isNew: boolean }[] = [];
  for (const [ident, url] of Object.entries(desired)) {
    const prev = state.idents[ident];
    const missing = !prev || !(await env.PACK.head(pdfKey(ident)));
    if (prev && prev.url === url && !missing) continue; // unchanged
    todo.push({ ident, url, isNew: !prev });
  }

  // Download with bounded concurrency, persisting state periodically so a run
  // that gets cut off (fetch waitUntil budget) makes durable progress and the
  // next invocation resumes instead of redoing everything.
  const CONCURRENCY = 6;
  const SAVE_EVERY = 20;
  let cursor = 0;
  let sinceSave = 0;
  async function drainQueue(): Promise<void> {
    while (cursor < todo.length) {
      const { ident, url, isNew } = todo[cursor++];
      const pdf = await fetchPdf(url, env.USER_AGENT);
      if (!pdf) continue; // failed / not a PDF — keep old, retry next run
      await env.PACK.put(pdfKey(ident), pdf.bytes, {
        httpMetadata: { contentType: "application/pdf" },
      });
      if (isNew) added++;
      else changed++;
      state.idents[ident] = {
        url,
        etag: pdf.etag,
        size: pdf.bytes.length,
        updatedAt: now.toISOString(),
      };
      if (++sinceSave >= SAVE_EVERY) {
        sinceSave = 0;
        await saveState();
      }
    }
  }
  await Promise.all(
    Array.from({ length: Math.min(CONCURRENCY, todo.length) }, drainQueue),
  );

  for (const ident of Object.keys(state.idents)) {
    if (!desired[ident]) {
      await env.PACK.delete(pdfKey(ident));
      delete state.idents[ident];
      removed++;
    }
  }

  const setChanged = added > 0 || removed > 0;

  const layerKey = navKey(FACTSHEET_LAYER);
  if (setChanged || !(await env.PACK.head(layerKey))) {
    const kml = buildFactsheetKml(Object.keys(state.idents), coords);
    await env.PACK.put(layerKey, kml, { httpMetadata: { contentType: KML_CT } });
  }

  // Copy a seeded static layer (Canada, Mexico) into the pack if it's missing.
  // Returns true if it was just copied (so the manifest can bump).
  async function copyStaticLayer(layer: string, seed: string): Promise<boolean> {
    if (await env.PACK.head(navKey(layer))) return false;
    const src = await env.PACK.get(staticKey(ID, seed));
    if (!src) {
      console.log(`no ${staticKey(ID, seed)} seeded — ${layer} omitted`);
      return false;
    }
    await env.PACK.put(navKey(layer), src.body, {
      httpMetadata: { contentType: KML_CT },
    });
    return true;
  }
  const copiedCanada = await copyStaticLayer(CANADA_LAYER, CANADA_SEED);
  const copiedMexico = await copyStaticLayer(MEXICO_LAYER, MEXICO_SEED);

  const anyChange = added + changed + removed > 0 || copiedCanada || copiedMexico;
  if (anyChange || !(await env.PACK.head(manifestKey(ID)))) {
    await env.PACK.put(
      manifestKey(ID),
      buildManifest(now, "North America Airports of Entry (CBP/CBSA)", "NA.AOE"),
      { httpMetadata: { contentType: "application/json" } },
    );
  }

  state.lastRun = now.toISOString();
  state.counts = {
    total: Object.keys(state.idents).length,
    added,
    changed,
    removed,
  };
  await env.PACK.put(stateKey(ID), JSON.stringify(state), {
    httpMetadata: { contentType: "application/json" },
  });

  console.log(
    `[${ID}] total=${state.counts.total} added=${added} changed=${changed} removed=${removed}`,
  );
}
