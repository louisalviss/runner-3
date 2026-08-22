export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return Response.json({
        ok: true,
        service: "runner3-core",
        d1: !!env.DB,
        time: new Date().toISOString()
      });
    }

    if (url.pathname === "/events" && request.method === "POST") {
      if (!env.DB) {
        return Response.json({ error: "D1_NOT_BOUND" }, { status: 503 });
      }

      const body = await request.json();
      await env.DB.prepare(
        "INSERT INTO events (source, event_type, payload) VALUES (?, ?, ?)"
      )
        .bind(
          body.source || "unknown",
          body.event_type || "event",
          JSON.stringify(body.payload || body)
        )
        .run();

      return Response.json({ ok: true });
    }

    if (url.pathname === "/events/latest") {
      if (!env.DB) {
        return Response.json({ error: "D1_NOT_BOUND" }, { status: 503 });
      }

      const result = await env.DB.prepare(
        "SELECT * FROM events ORDER BY id DESC LIMIT 20"
      ).all();

      return Response.json(result.results || []);
    }

    if (url.pathname === "/radar/latest") {
      return Response.json({
        status: "ready",
        message: "D1 event layer enabled"
      });
    }

    return new Response("Not Found", { status: 404 });
  }
};
