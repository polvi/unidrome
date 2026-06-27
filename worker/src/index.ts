// content-pack.barbless.net — multi-pack ForeFlight content-pack host.
//   scheduled() — daily, run refresh() for every dynamic pack
//   fetch()     — serve each pack's zip + status from R2, plus /admin seeding
//
// Routes:
//   GET    /                      index of available packs (+ download links)
//   GET    /<id>.zip              stream the pack zip (stable ForeFlight URL)
//   GET    /<id>/status           per-pack state JSON
//   POST   /<id>/refresh          run a dynamic pack's refresh (guarded)
//   PUT    /admin/<id>/pack/<p>   seed/update a pack file        (guarded)
//   PUT    /admin/<id>/static/<n> seed/update a pack seed input  (guarded)
//   DELETE /admin/<id>/pack/<p>   delete a pack file             (guarded)

import { handleAdmin } from "./admin";
import type { Env, State } from "./env";
import { stateKey } from "./env";
import { renderIndex, type PackView } from "./page";
import { getPack, PACKS } from "./packs";
import { streamPackZip } from "./zip";

export { Counter } from "./counter";

/** Read (and optionally increment) a pack's download count via its Durable Object. */
async function downloadCount(env: Env, id: string, incr = false): Promise<number> {
  const stub = env.COUNTER.get(env.COUNTER.idFromName(id));
  const res = await stub.fetch(`https://counter/${incr ? "?incr" : ""}`);
  return ((await res.json()) as { n: number }).n;
}

async function runAllRefreshers(env: Env): Promise<void> {
  for (const pack of PACKS) {
    if (!pack.refresh) continue;
    try {
      await pack.refresh(env);
    } catch (e) {
      console.error(`refresh ${pack.id} failed: ${e}`);
    }
  }
}

export default {
  async scheduled(_c: ScheduledController, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(runAllRefreshers(env));
  },

  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const segments = url.pathname.split("/").filter(Boolean).map(decodeURIComponent);

    // /admin/...
    const admin = await handleAdmin(request, env, segments);
    if (admin) return admin;

    // GET /  -> HTML index (QR + ForeFlight links); JSON via Accept or ?format=json
    if (request.method === "GET" && segments.length === 0) {
      const views: PackView[] = await Promise.all(
        PACKS.map(async (p) => {
          const obj = await env.PACK.get(stateKey(p.id));
          const state: Partial<State> = obj ? await obj.json() : {};
          return {
            id: p.id,
            title: p.title,
            description: p.description,
            dynamic: !!p.refresh,
            lastRun: state.lastRun ?? null,
            counts: state.counts ?? null,
            downloads: await downloadCount(env, p.id),
          };
        }),
      );

      const wantsJson =
        url.searchParams.get("format") === "json" ||
        (request.headers.get("accept") ?? "").includes("application/json");
      if (wantsJson) {
        return Response.json({
          host: "content-pack.barbless.net",
          packs: views.map((v) => ({ ...v, download: `${url.origin}/${v.id}.zip` })),
        });
      }
      return new Response(renderIndex(url.origin, views), {
        headers: { "Content-Type": "text/html; charset=utf-8" },
      });
    }

    // GET /<id>.zip
    if (request.method === "GET" && segments.length === 1 && segments[0].endsWith(".zip")) {
      const id = segments[0].slice(0, -4);
      if (!getPack(id)) return new Response("unknown pack", { status: 404 });
      // count the download without delaying the stream
      ctx.waitUntil(downloadCount(env, id, true).catch(() => {}));
      return streamPackZip(env, id);
    }

    // /<id>/status | /<id>/refresh
    if (segments.length === 2) {
      const [id, action] = segments;
      const pack = getPack(id);
      if (!pack) return new Response("unknown pack", { status: 404 });

      if (request.method === "GET" && action === "status") {
        const obj = await env.PACK.get(stateKey(id));
        const state: Partial<State> = obj ? await obj.json() : {};
        // Summary only — omit the full per-ident map.
        return Response.json({
          id,
          title: pack.title,
          dynamic: !!pack.refresh,
          lastRun: state.lastRun ?? null,
          counts: state.counts ?? null,
        });
      }

      if (request.method === "POST" && action === "refresh") {
        if (!env.REFRESH_TOKEN || request.headers.get("x-refresh-token") !== env.REFRESH_TOKEN) {
          return new Response("forbidden", { status: 403 });
        }
        if (!pack.refresh) return new Response("pack is static (no refresh)", { status: 400 });
        ctx.waitUntil(
          pack.refresh(env).catch((e) => console.error(`manual refresh ${id} failed: ${e}`)),
        );
        return Response.json({ ok: true, started: id });
      }
    }

    return new Response("not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
