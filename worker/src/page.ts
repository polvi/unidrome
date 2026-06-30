// HTML index for content-pack.barbless.net: one card per pack with a QR code and
// an "Add to ForeFlight" deep link. Scanning the QR (or tapping the link) on a
// device with ForeFlight opens the import via foreflight.com/content?downloadURL=.

import { qrSvg } from "./qr";

export interface PackView {
  id: string;
  title: string;
  description: string;
  dynamic: boolean;
  lastRun: string | null;
  counts: { total: number; added: number; changed: number; removed: number } | null;
  downloads: number;
}

const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** ForeFlight import deep link for a pack zip URL. */
export const foreflightUrl = (packUrl: string) =>
  `https://foreflight.com/content?downloadURL=${encodeURIComponent(packUrl)}`;

function card(origin: string, p: PackView): string {
  const packUrl = `${origin}/${p.id}.zip`;
  const ffUrl = foreflightUrl(packUrl);
  const meta: string[] = [p.dynamic ? "auto-updated daily" : "static"];
  if (p.counts) meta.push(`${p.counts.total} items`);
  if (p.lastRun) meta.push(`updated ${esc(p.lastRun.slice(0, 10))}`);

  return `
    <section class="card">
      <h2>${esc(p.title)}</h2>
      <p class="meta">${meta.join(" · ")}</p>
      <p class="desc">${esc(p.description)}</p>
      <a class="qr" href="${esc(ffUrl)}" aria-label="Add ${esc(p.title)} to ForeFlight">${qrSvg(ffUrl)}</a>
      <a class="btn" href="${esc(ffUrl)}">Add to ForeFlight</a>
      <p class="downloads"><b>${p.downloads.toLocaleString("en-US")}</b> downloads</p>
      <p class="dl"><a href="${esc(packUrl)}">download .zip</a></p>
    </section>`;
}

export function renderIndex(origin: string, packs: PackView[]): string {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Barbless content packs</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 16px/1.5 -apple-system, system-ui, Segoe UI, Roboto, sans-serif;
         margin: 0; padding: 2rem 1rem 4rem; background: #f6f7f9; color: #14171a; }
  @media (prefers-color-scheme: dark) { body { background:#0f1216; color:#e8eaed; } }
  header { max-width: 70rem; margin: 0 auto 1.5rem; }
  h1 { font-size: 1.4rem; margin: 0 0 .25rem; }
  header p { margin: 0; opacity: .7; }
  .grid { max-width: 70rem; margin: 0 auto; display: grid; gap: 1.25rem;
          grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr)); }
  .card { background: #fff; border: 1px solid #e3e6ea; border-radius: 14px;
          padding: 1.25rem; text-align: center; }
  @media (prefers-color-scheme: dark) { .card { background:#171b21; border-color:#262c34; } }
  .card h2 { font-size: 1.05rem; margin: 0 0 .25rem; }
  .meta { margin: 0 0 .75rem; font-size: .8rem; opacity: .6; }
  .desc { margin: 0 0 1rem; font-size: .85rem; line-height: 1.45; text-align: left; opacity: .85; }
  .qr { display: block; }
  .qr svg { width: 190px; height: 190px; border-radius: 8px; }
  .btn { display: inline-block; margin: 1rem 0 .25rem; padding: .6rem 1.1rem;
         background: #1f6feb; color: #fff; text-decoration: none; border-radius: 999px;
         font-weight: 600; font-size: .95rem; }
  .downloads { margin: .75rem 0 0; font-size: .85rem; opacity: .75; }
  .downloads b { font-size: 1.15rem; opacity: 1; }
  .dl { margin: .25rem 0 0; font-size: .8rem; }
  .dl a, .meta a { color: inherit; opacity: .65; }
  footer { max-width: 70rem; margin: 2.5rem auto 0; font-size: .8rem; opacity: .55; }
  code { font-size: .85em; }
  .help { max-width: 70rem; margin: 2.5rem auto 0; background: #fff;
          border: 1px solid #e3e6ea; border-radius: 14px; padding: 1.5rem;
          display: flex; gap: 2rem; flex-wrap: wrap; align-items: flex-start; }
  @media (prefers-color-scheme: dark) { .help { background:#171b21; border-color:#262c34; } }
  .help .steps { flex: 1 1 20rem; }
  .help h2 { font-size: 1.05rem; margin: 0 0 .6rem; }
  .help ol { margin: 0; padding-left: 1.2rem; }
  .help li { margin: .35rem 0; }
  .help .note { margin: .35rem 0 0; opacity: .8; }
  .arrow { display: inline-block; width: 1.15em; height: 1.15em; vertical-align: -.25em;
           background: #1f6feb; color: #fff; border-radius: 50%; text-align: center;
           line-height: 1.15em; font-size: .85em; font-weight: 700; }
  .help .video { flex: 0 0 auto; }
  .help .video iframe { width: 240px; height: 427px; border: 0; border-radius: 12px; }
  .help .video figcaption { font-size: .8rem; opacity: .6; margin-top: .4rem; text-align: center; }
</style>
</head>
<body>
  <header>
    <h1>Barbless content packs</h1>
    <p>Scan a QR code, or tap “Add to ForeFlight”, to import.</p>
  </header>
  <main class="grid">
    ${packs.map((p) => card(origin, p)).join("\n")}
  </main>
  <section class="help">
    <div class="steps">
      <h2>Install</h2>
      <ol>
        <li>Scan a pack’s QR code (or tap <b>Add to ForeFlight</b>) on your device.</li>
        <li>In ForeFlight, open <b>More → Custom Content</b>.</li>
        <li>Tap the blue download arrow <span class="arrow">↓</span> next to the pack to install.</li>
      </ol>
      <h2 style="margin-top:1.25rem">Update</h2>
      <p class="note">These packs update when you delete and re-add them. To pull the latest into an
      already-installed pack, open <b>Custom Content</b>, swipe left on the pack, press delete, then scroll to the bottom of the content pack list and tap the blue arrow
      <span class="arrow">↓</span> again — see the clip.</p>
    </div>
    <figure class="video">
      <iframe src="https://www.youtube.com/embed/S1ErbZHkWQ8" title="How to update a content pack in ForeFlight"
        loading="lazy" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen
        allow="accelerometer; encrypted-media; gyroscope; picture-in-picture; web-share"></iframe>
      <figcaption>Updating an installed pack</figcaption>
    </figure>
  </section>
  <footer>
    Each pack is also at <code>${esc(origin)}/&lt;id&gt;.zip</code>.
    QR codes link to <code>foreflight.com/content?downloadURL=…</code>.
  </footer>
</body>
</html>`;
}
