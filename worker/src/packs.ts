// Registry of content packs hosted by this worker. Each pack is served at
// /<id>.zip (streamed from packs/<id>/ in R2). A pack may be:
//   - dynamic: has a refresh() that the daily cron runs to keep its R2 tree
//     current (e.g. na-airports-of-entry pulls CBP fact sheets), or
//   - static: no refresh(); its files are seeded once via /admin/<id>/<path>
//     and updated by re-uploading (e.g. barbless-maps).
//
// Add a new pack by appending an entry here and seeding packs/<id>/ in R2.

import type { Env } from "./env";
import { refreshNaAoe } from "./na_aoe";
import { refreshOregonSeaplane } from "./oregon_seaplane";

export interface PackSpec {
  id: string; // url slug + zip basename + zip root folder + R2 namespace
  title: string;
  description: string; // shown on the index; what the pack is + its layers
  refresh?: (env: Env) => Promise<unknown>;
}

export const PACKS: PackSpec[] = [
  {
    id: "na-airports-of-entry",
    title: "North America Airports of Entry",
    description:
      "Customs airports of entry across North America — where you can clear " +
      "customs flying in. Three map layers: U.S. CBP general-aviation airports " +
      "(each with its CBP fact-sheet PDF attached to the airport), Canada CBSA " +
      "airports of entry, and Mexico international airports.",
    refresh: refreshNaAoe,
  },
  {
    id: "oregon-seaplane",
    title: "Oregon Seaplane Waters",
    description:
      "Oregon waters where power boats — and therefore floatplanes — may " +
      "operate, from the Oregon State Marine Board boating GIS. Whole-lake " +
      "electric-only, no-motor, and speed-restricted waters are excluded; lakes " +
      "with sub-zone restrictions (swim areas, no-wake zones) are flagged orange " +
      "with the rule details.",
    refresh: refreshOregonSeaplane,
  },
];

export const getPack = (id: string): PackSpec | undefined =>
  PACKS.find((p) => p.id === id);
