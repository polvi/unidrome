export interface Env {
  PACK: R2Bucket;
  COUNTER: DurableObjectNamespace; // per-pack download counter
  USER_AGENT: string;
  REFRESH_TOKEN?: string; // secret guarding /admin/* and /<id>/refresh
}

// --- R2 key layout (one bucket, namespaced per content pack) ---
//   packs/<id>/...           the pack's file tree (zipped as <id>/...)
//   packs/<id>/manifest.json the ForeFlight manifest (part of the tree)
//   state/<id>.json          per-pack worker state (not in the zip)
//   static/<id>/...          per-pack seed inputs, e.g. nasr-coords.json (not in the zip)
export const packPrefix = (id: string) => `packs/${id}/`;
export const manifestKey = (id: string) => `packs/${id}/manifest.json`;
export const stateKey = (id: string) => `state/${id}.json`;
export const staticKey = (id: string, name: string) => `static/${id}/${name}`;

// nasr-coords.json shape: { IDENT: [lat, lon, label] }
export type CoordMap = Record<string, [string, string, string]>;

export interface FactsheetState {
  url: string;
  etag: string | null;
  size: number;
  updatedAt: string;
}

export interface State {
  idents: Record<string, FactsheetState>;
  lastRun: string | null;
  counts: { total: number; added: number; changed: number; removed: number };
}

export function emptyState(): State {
  return {
    idents: {},
    lastRun: null,
    counts: { total: 0, added: 0, changed: 0, removed: 0 },
  };
}
