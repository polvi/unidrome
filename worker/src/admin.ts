// Seed/update a pack's files (and its static seed inputs) over HTTP, guarded by
// REFRESH_TOKEN. Used to populate static packs (e.g. barbless-maps) and the
// dynamic pack's seed inputs. The worker writes R2 keys from the decoded URL
// path, so spaces in filenames are preserved (unlike `wrangler r2 object put`,
// which URL-encodes spaces in keys).
//
//   PUT    /admin/<id>/pack/<relpath>     -> packs/<id>/<relpath>
//   PUT    /admin/<id>/static/<name>      -> static/<id>/<name>
//   DELETE /admin/<id>/pack/<relpath>     -> delete packs/<id>/<relpath>

import type { Env } from "./env";
import { packPrefix, staticKey } from "./env";

function authed(req: Request, env: Env): boolean {
  return (
    !!env.REFRESH_TOKEN &&
    req.headers.get("x-refresh-token") === env.REFRESH_TOKEN
  );
}

/** segments are the path parts after "/admin/". Returns null if not an admin route. */
export async function handleAdmin(
  req: Request,
  env: Env,
  segments: string[],
): Promise<Response | null> {
  if (segments[0] !== "admin") return null;
  if (!authed(req, env)) return new Response("forbidden", { status: 403 });

  const [, id, scope, ...rest] = segments; // admin / <id> / <scope> / <relpath...>
  const relpath = rest.join("/");
  if (!id || !scope || !relpath) {
    return new Response("usage: /admin/<id>/(pack|static)/<relpath>", {
      status: 400,
    });
  }

  let key: string;
  if (scope === "pack") key = packPrefix(id) + relpath;
  else if (scope === "static") key = staticKey(id, relpath);
  else return new Response("scope must be 'pack' or 'static'", { status: 400 });

  if (req.method === "PUT" || req.method === "POST") {
    if (!req.body) return new Response("missing body", { status: 400 });
    await env.PACK.put(key, req.body, {
      httpMetadata: req.headers.get("content-type")
        ? { contentType: req.headers.get("content-type")! }
        : undefined,
    });
    return Response.json({ ok: true, key });
  }
  if (req.method === "DELETE") {
    await env.PACK.delete(key);
    return Response.json({ ok: true, deleted: key });
  }
  return new Response("method not allowed", { status: 405 });
}
