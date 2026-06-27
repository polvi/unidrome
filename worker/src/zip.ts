// Stream a content pack's zip directly from R2 using client-zip. We never hold
// the whole pack in memory: each object's body is piped through the zip stream
// as it's produced (Workers cap memory at 128 MB).

import { makeZip } from "client-zip";
import type { Env } from "./env";
import { packPrefix } from "./env";

interface ZipInput {
  name: string;
  input: ReadableStream<Uint8Array>;
  lastModified?: Date;
  size?: number;
}

/** Yield client-zip inputs for every object under packs/<id>/, named <id>/... */
async function* packEntries(env: Env, id: string): AsyncGenerator<ZipInput> {
  const prefix = packPrefix(id);
  const keys: string[] = [];
  let cursor: string | undefined;
  do {
    const page = await env.PACK.list({ prefix, cursor, limit: 1000 });
    for (const o of page.objects) keys.push(o.key);
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
  keys.sort();

  for (const key of keys) {
    const obj = await env.PACK.get(key);
    if (!obj) continue; // deleted between list and get
    yield {
      name: `${id}/${key.slice(prefix.length)}`,
      input: obj.body,
      size: obj.size,
      lastModified: obj.uploaded,
    };
  }
}

/** A streaming Response containing the full content pack zip. */
export function streamPackZip(env: Env, id: string): Response {
  const zip = makeZip(packEntries(env, id));
  return new Response(zip, {
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="${id}.zip"`,
      "Cache-Control": "no-store",
    },
  });
}
