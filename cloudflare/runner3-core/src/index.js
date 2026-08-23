// Control-plane deploy health is independent from workload success/failure state.
const EVENT_RETENTION_DAYS = 90;
const MAX_JSON_CHARS = 200000;
const MAX_KEY_CHARS = 200;

function requireDb(env) {
  if (!env.DB) {
    return Response.json({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });
  }
  return null;
}

function cleanKey(value, name) {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) return { error: `${name} is required` };
  if (text.length > MAX_KEY_CHARS) return { error: `${name} too long` };
  return { value: text };
}

function optionalText(value) {
  if (value == null) return null;
  return typeof value === "string" ? value : String(value);
}

function serializeJson(value, field) {
  if (value == null) return { text: null };
  const text = JSON.stringify(value);
  if (text.length > MAX_JSON_CHARS) {
    return { error: `${field} too large (max ${MAX_JSON_CHARS} chars)` };
  }
  return { text };
}

function parseJsonField(row, field) {
  if (!row || typeof row[field] !== "string") return row;
  try {
    return { ...row, [field]: JSON.parse(row[field]) };
  } catch {
    return row;
  }
}

function decodePath(pathname) {
  try {
    return pathname.split("/").filter(Boolean).map(decodeURIComponent);
  } catch {
    return null;
  }
}

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
    const segments = decodePath(url.pathname);
    if (!segments) {
      return Response.json({ ok: false, error: "invalid_path_encoding" }, { status: 400 });
    }

    if (url.pathname === "/health") {
      return Response.json({
        ok: true,
        service: "runner3-core",
        d1: !!env.DB,
        time: new Date().toISOString()
      });
    }

    if (segments[0] === "state" && segments.length === 2) {
      const dbError = requireDb(env);
      if (dbError) return dbError;

      const sourceResult = cleanKey(segments[1], "source");
      if (sourceResult.error) {
        return Response.json({ ok: false, error: sourceResult.error }, { status: 400 });
      }
      const source = sourceResult.value;

      if (request.method === "GET") {
        const row = await env.DB.prepare(
          "SELECT source, status, run_id, detail, updated_at FROM workflow_state WHERE source = ?"
        ).bind(source).first();
        return Response.json({ ok: true, state: row ? parseJsonField(row, "detail") : null });
      }

      if (request.method === "PUT") {
        try {
          const body = await request.json();
          const detail = serializeJson(body.detail, "detail");
          if (detail.error) {
            return Response.json({ ok: false, error: detail.error }, { status: 400 });
          }

          await env.DB.prepare(`
            INSERT INTO workflow_state (source, status, run_id, detail, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(source) DO UPDATE SET
              status = excluded.status,
              run_id = excluded.run_id,
              detail = excluded.detail,
              updated_at = CURRENT_TIMESTAMP
          `).bind(
            source,
            optionalText(body.status),
            optionalText(body.run_id),
            detail.text
          ).run();

          const row = await env.DB.prepare(
            "SELECT source, status, run_id, detail, updated_at FROM workflow_state WHERE source = ?"
          ).bind(source).first();
          return Response.json({ ok: true, state: parseJsonField(row, "detail") });
        } catch (err) {
          return Response.json({ ok: false, error: String(err?.message || err) }, { status: 400 });
        }
      }

      return Response.json({ ok: false, error: "method_not_allowed" }, { status: 405 });
    }

    if (segments[0] === "checkpoints" && segments.length === 3) {
      const dbError = requireDb(env);
      if (dbError) return dbError;

      const projectResult = cleanKey(segments[1], "project");
      const scopeResult = cleanKey(segments[2], "scope");
      if (projectResult.error || scopeResult.error) {
        return Response.json(
          { ok: false, error: projectResult.error || scopeResult.error },
          { status: 400 }
        );
      }
      const project = projectResult.value;
      const scope = scopeResult.value;

      if (request.method === "GET") {
        const row = await env.DB.prepare(`
          SELECT project, scope, source, status, position, dropbox_path, last_error, updated_at
          FROM checkpoints
          WHERE project = ? AND scope = ?
        `).bind(project, scope).first();
        return Response.json({ ok: true, checkpoint: row ? parseJsonField(row, "position") : null });
      }

      if (request.method === "PUT") {
        try {
          const body = await request.json();
          const sourceResult = cleanKey(body.source, "source");
          if (sourceResult.error) {
            return Response.json({ ok: false, error: sourceResult.error }, { status: 400 });
          }
          const position = serializeJson(body.position, "position");
          if (position.error) {
            return Response.json({ ok: false, error: position.error }, { status: 400 });
          }

          await env.DB.prepare(`
            INSERT INTO checkpoints (
              project, scope, source, status, position, dropbox_path, last_error, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(project, scope) DO UPDATE SET
              source = excluded.source,
              status = excluded.status,
              position = excluded.position,
              dropbox_path = excluded.dropbox_path,
              last_error = excluded.last_error,
              updated_at = CURRENT_TIMESTAMP
          `).bind(
            project,
            scope,
            sourceResult.value,
            optionalText(body.status),
            position.text,
            optionalText(body.dropbox_path),
            optionalText(body.last_error)
          ).run();

          const row = await env.DB.prepare(`
            SELECT project, scope, source, status, position, dropbox_path, last_error, updated_at
            FROM checkpoints
            WHERE project = ? AND scope = ?
          `).bind(project, scope).first();
          return Response.json({ ok: true, checkpoint: parseJsonField(row, "position") });
        } catch (err) {
          return Response.json({ ok: false, error: String(err?.message || err) }, { status: 400 });
        }
      }

      return Response.json({ ok: false, error: "method_not_allowed" }, { status: 405 });
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
