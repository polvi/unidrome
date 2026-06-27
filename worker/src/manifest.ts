// Content pack manifest. The manifest is (re)written whenever the pack content
// changes, so all three time fields reflect the last update:
//   version        -> YYYYMMDD of the last update (readable "last updated" date)
//   effectiveDate  -> full timestamp of the last update
//   expirationDate -> one year out
// ForeFlight shows these in the content pack detail view.

function stamp(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}` +
    `T${p(d.getUTCHours())}${p(d.getUTCMinutes())}${p(d.getUTCSeconds())}`
  );
}

// YYYYMMDD as an integer, e.g. 2026-06-23 -> 20260623.
function dateVersion(d: Date): number {
  return d.getUTCFullYear() * 10000 + (d.getUTCMonth() + 1) * 100 + d.getUTCDate();
}

export function buildManifest(
  now: Date,
  name: string,
  abbreviation: string,
): string {
  const expires = new Date(now);
  expires.setUTCFullYear(expires.getUTCFullYear() + 1);
  const manifest = {
    name,
    abbreviation,
    version: dateVersion(now),
    effectiveDate: stamp(now),
    expirationDate: stamp(expires),
    organizationName: "unidrome",
  };
  return JSON.stringify(manifest, null, 4);
}
