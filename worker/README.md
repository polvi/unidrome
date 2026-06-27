# content-pack worker — content-pack.barbless.net

Multi-pack ForeFlight content-pack host on Cloudflare Workers + R2. Each pack is
served at `https://content-pack.barbless.net/<id>.zip` and is one of:

- **dynamic** — has a `refresh()` the daily cron runs to keep its R2 tree current
  (e.g. `na-airports-of-entry` pulls CBP fact sheets, records each sheet's source
  URL + ETag, downloads only what changed, regenerates the US KML on set change).
- **static** — no `refresh()`; seeded once and updated by re-uploading
  (e.g. `barbless-maps`, which carries the Oregon seaplane layer).

Publishing model: **R2 public URL only** — import into ForeFlight manually
(download + import / AirDrop). ForeFlight can't subscribe to an arbitrary URL.

## Routes

| route | purpose |
|-------|---------|
| `GET /` | HTML index: per-pack QR code + "Add to ForeFlight" deep link (`?format=json` or `Accept: application/json` for JSON) |
| `GET /<id>.zip` | stream the pack zip (stable URL), built live from R2 |
| `GET /<id>/status` | per-pack state |
| `POST /<id>/refresh` | run a dynamic pack's refresh (header `x-refresh-token`) |
| `PUT /admin/<id>/pack/<relpath>` | seed/update a pack file (guarded) |
| `PUT /admin/<id>/static/<name>` | seed/update a seed input (guarded) |
| `DELETE /admin/<id>/pack/<relpath>` | delete a pack file (guarded) |

The zip streams straight from R2 (never buffers the whole ~95 MB in memory).

## R2 layout (bucket `content-packs`)

```
packs/<id>/...            the pack's file tree (zipped as <id>/...)
packs/<id>/manifest.json  ForeFlight manifest (part of the tree)
state/<id>.json           per-pack worker state (dynamic packs)
static/<id>/...           per-pack seed inputs, not in the zip
```

> ⚠️ `wrangler r2 object put` URL-encodes spaces in **keys**. For files with
> spaces (most pack layers/PDFs), seed via the `/admin/...` endpoint instead —
> the worker writes keys from the decoded URL path, preserving spaces. The
> dynamic pack writes its own spaced filenames from JS. Only space-free keys
> (e.g. `static/<id>/nasr-coords.json`, `static/<id>/canada.kml`) are safe via
> the wrangler CLI.

## Adding a new pack

1. Append a `PackSpec` to `src/packs.ts` (with a `refresh` for dynamic packs).
2. Seed `packs/<id>/...` (and any `static/<id>/...`):
   - static pack — upload each built file via `/admin/<id>/pack/<relpath>`.
   - dynamic pack — seed its `static/<id>/...` inputs, then `POST /<id>/refresh`.

The Oregon seaplane pack is live as part of `barbless-maps` — built locally by
`../scripts/oregon-seaplane.py`, then uploaded with the seeding loop below.

## Deploy (already done for this account)

```sh
cd worker && npm install
npx wrangler r2 bucket create content-packs
npx wrangler secret put REFRESH_TOKEN          # guards /admin + /refresh
npx wrangler deploy                            # provisions content-pack.barbless.net + cron
```

### Seed the dynamic CBP/CBSA pack
```sh
# from repo root: build inputs (written to the gitignored build/ dir)
python3 scripts/build-nasr-coords.py           # -> build/nasr-coords.json
python3 scripts/cbsa-aoe.py                     # -> build/CA_AOE.kml (drain for full enrichment)

ID=na-airports-of-entry
npx wrangler r2 object put "content-packs/static/$ID/nasr-coords.json" --file build/nasr-coords.json
npx wrangler r2 object put "content-packs/static/$ID/canada.kml"       --file build/CA_AOE.kml
curl -X POST -H "x-refresh-token: $TOKEN" https://content-pack.barbless.net/$ID/refresh
# the daily cron (09:00 UTC) keeps it current thereafter
```

### Seed a static pack (e.g. barbless-maps)
```sh
TOKEN=...   # the REFRESH_TOKEN value
ID=barbless-maps
cd data/content-pack/$ID
find . -type f -not -name '*.zip' | sed 's|^\./||' | while read -r rel; do
  enc=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe='/'))" "$rel")
  curl -s -o /dev/null -w "%{http_code} $rel\n" -X PUT --data-binary @"$rel" \
    -H "x-refresh-token: $TOKEN" "https://content-pack.barbless.net/admin/$ID/pack/$enc"
done
```

## Local development

```sh
npx wrangler r2 object put "content-packs/static/na-airports-of-entry/nasr-coords.json" --file ../build/nasr-coords.json --local
npx wrangler r2 object put "content-packs/static/na-airports-of-entry/canada.kml" --file ../build/CA_AOE.kml --local
npx wrangler dev --test-scheduled
curl http://localhost:8787/__scheduled                       # run all refreshers once
curl -s http://localhost:8787/na-airports-of-entry.zip -o out.zip && unzip -l out.zip
```
