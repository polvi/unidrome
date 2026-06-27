// Per-pack download counter. One Durable Object instance per pack id (via
// idFromName) serializes its requests, so the read-modify-write below is atomic
// even under concurrent downloads — no lost increments.
//
//   GET /        -> { n }            read the count
//   GET /?incr   -> { n }            increment, then read

export class Counter {
  constructor(private state: DurableObjectState) {}

  async fetch(request: Request): Promise<Response> {
    let n = (await this.state.storage.get<number>("n")) ?? 0;
    if (new URL(request.url).searchParams.has("incr")) {
      n++;
      await this.state.storage.put("n", n);
    }
    return Response.json({ n });
  }
}
