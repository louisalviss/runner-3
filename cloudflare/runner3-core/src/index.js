// Control-plane deploy health is independent from workload success/failure state.
const EVENT_RETENTION_DAYS = 90;

async function cleanupOldEvents(env) {
  if (!env.DB) {
    throw new Error("D1_NOT_BOUND");
  }

  // Keep the latest workflow_status for every source indefinitely so /status
  // still represents dormant workloads after historical telemetry is purged.
  const result = await env.DB.prepare(`
    DELETE FROM events
    WHERE created_at < datetime('now', '-${EVENT_RETENTION_DAYS} days')
      AND NOT (
        event_type = 'workflow_status'
        AND id IN (
          SELECT MAX(id)
          FROM events
          WHERE event_type = 'workflow_status'
          GROUP BY source
        )
      )
  `).run();

  return {
    retention_days: EVENT_RETENTION_DAYS,
    deleted: result.meta?.changes ?? null
  };
}

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

    if (url.pathname === "/status") {
      if (!env.DB) {
        return Response.json({ error: "D1_NOT_BOUND" }, { status: 503 });
      }

      const result = await env.DB.prepare(`
        SELECT e.id, e.source, e.event_type, e.payload, e.created_at
        FROM events e
        JOIN (
          SELECT source, MAX(id) AS max_id
          FROM events
          WHERE event_type = 'workflow_status'
          GROUP BY source
        ) latest ON latest.max_id = e.id
        ORDER BY e.source
      `).all();

      const sources = {};
      for (const row of result.results || []) {
        let payload = {};
        try {
          payload = JSON.parse(row.payload || "{}");
        } catch {
          payload = {};
        }

        sources[row.source] = {
          status: payload.status || "unknown",
          workflow: payload.workflow || null,
          run_id: payload.run_id || null,
          run_attempt: payload.run_attempt || null,
          sha: payload.sha || null,
          ref: payload.ref || null,
          event_id: row.id,
          created_at: row.created_at
        };
      }

      return Response.json({ ok: true, sources });
    }

    if (url.pathname === "/radar/latest") {
      return Response.json({
        status: "ready",
        message: "D1 event layer enabled"
      });
    }

    return new Response("Not Found", { status: 404 });
  },

  async scheduled(controller, env) {
    const result = await cleanupOldEvents(env);
    console.log("runner3-core retention cleanup", {
      cron: controller.cron,
      scheduled_time: new Date(controller.scheduledTime).toISOString(),
      ...result
    });
  }
};
