// Control-plane deploy health is independent from workload success/failure state.
const EVENT_RETENTION_DAYS = 90;
const MAX_JSON_CHARS = 200000;
const MAX_KEY_CHARS = 200;
const MAX_ARTIFACT_KEY_CHARS = 900;

function requireDb(env) {
  if (!env.DB) {
    return Response.json({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });
  }
  return null;
}

function requireArtifacts(env) {
  if (!env.ARTIFACTS) {
    return Response.json({ ok: false, error: "R2_NOT_BOUND" }, { status: 503 });
  }
  return null;
}

function requireArtifactAuth(request, env) {
  const expected = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!expected) {
    return Response.json({ ok: false, error: "ARTIFACT_AUTH_NOT_CONFIGURED" }, { status: 503 });
  }
  const auth = request.headers.get("Authorization") || "";
  const prefix = "Bearer ";
  const supplied = auth.startsWith(prefix) ? auth.slice(prefix.length).trim() : "";
  if (!supplied || supplied !== expected) {
    return Response.json({ ok: false, error: "UNAUTHORIZED" }, { status: 401 });
  }
  return null;
}

function coreWriteAuthMode(env) {
  const raw = typeof env.RUNNER3_CORE_WRITE_AUTH === "string"
    ? env.RUNNER3_CORE_WRITE_AUTH.trim().toLowerCase()
    : "";
  return new Set(["required", "enforce", "1", "true"]).has(raw) ? "required" : "compat";
}

function requireCoreWriteAuth(request, env) {
  if (coreWriteAuthMode(env) !== "required") return null;

  const expected = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!expected) {
    return Response.json({ ok: false, error: "WRITE_AUTH_NOT_CONFIGURED" }, { status: 503 });
  }

  const auth = request.headers.get("Authorization") || "";
  const prefix = "Bearer ";
  const supplied = auth.startsWith(prefix) ? auth.slice(prefix.length).trim() : "";
  if (!supplied || supplied !== expected) {
    return Response.json({ ok: false, error: "UNAUTHORIZED" }, { status: 401 });
  }
  return null;
}

function cleanKey(value, name) {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) return { error: `${name} is required` };
  if (text.length > MAX_KEY_CHARS) return { error: `${name} too long` };
  return { value: text };
}

function cleanArtifactSegment(value, name) {
  const result = cleanKey(value, name);
  if (result.error) return result;
  if (result.value === "." || result.value === ".." || /[\\/\u0000-\u001f\u007f]/.test(result.value)) {
    return { error: `${name} contains invalid characters` };
  }
  return result;
}

function artifactKeyFromSegments(segments) {
  if (segments.length < 4) return { error: "artifact name is required" };
  const project = cleanArtifactSegment(segments[1], "project");
  const scope = cleanArtifactSegment(segments[2], "scope");
  if (project.error || scope.error) {
    return { error: project.error || scope.error };
  }

  const nameParts = [];
  for (let i = 3; i < segments.length; i += 1) {
    const part = cleanArtifactSegment(segments[i], `name[${i - 3}]`);
    if (part.error) return { error: part.error };
    nameParts.push(part.value);
  }

  const name = nameParts.join("/");
  const key = `core/${project.value}/${scope.value}/${name}`;
  if (key.length > MAX_ARTIFACT_KEY_CHARS) {
    return { error: `artifact key too long (max ${MAX_ARTIFACT_KEY_CHARS} chars)` };
  }
  return { project: project.value, scope: scope.value, name, key };
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

function artifactHeaders(object, artifact) {
  const headers = new Headers();
  if (typeof object.writeHttpMetadata === "function") {
    object.writeHttpMetadata(headers);
  }
  if (object.httpEtag) headers.set("ETag", object.httpEtag);
  if (Number.isFinite(object.size)) headers.set("Content-Length", String(object.size));
  headers.set("Cache-Control", "private, no-store");
  headers.set("X-Runner3-Artifact-Project", artifact.project);
  headers.set("X-Runner3-Artifact-Scope", artifact.scope);
  headers.set("X-Runner3-Artifact-Name", artifact.name);
  return headers;
}

async function handleArtifact(request, env, segments) {
  const r2Error = requireArtifacts(env);
  if (r2Error) return r2Error;
  const authError = requireArtifactAuth(request, env);
  if (authError) return authError;

  const artifact = artifactKeyFromSegments(segments);
  if (artifact.error) {
    return Response.json({ ok: false, error: artifact.error }, { status: 400 });
  }

  if (request.method === "PUT") {
    if (!request.body) {
      return Response.json({ ok: false, error: "artifact body is required" }, { status: 400 });
    }
    const contentType = request.headers.get("Content-Type") || "application/octet-stream";
    const source = (request.headers.get("X-Runner3-Source") || "unknown").slice(0, 200);
    const object = await env.ARTIFACTS.put(artifact.key, request.body, {
      httpMetadata: { contentType },
      customMetadata: {
        project: artifact.project,
        scope: artifact.scope,
        name: artifact.name,
        source,
      },
    });
    return Response.json({
      ok: true,
      artifact: {
        project: artifact.project,
        scope: artifact.scope,
        name: artifact.name,
        key: artifact.key,
        size: object?.size ?? null,
        etag: object?.httpEtag || object?.etag || null,
        uploaded: object?.uploaded ? object.uploaded.toISOString() : null,
        content_type: contentType,
      },
    });
  }

  if (request.method === "HEAD") {
    const object = await env.ARTIFACTS.head(artifact.key);
    if (!object) return new Response(null, { status: 404 });
    return new Response(null, { status: 200, headers: artifactHeaders(object, artifact) });
  }

  if (request.method === "GET") {
    const object = await env.ARTIFACTS.get(artifact.key);
    if (!object) {
      return Response.json({ ok: false, error: "ARTIFACT_NOT_FOUND" }, { status: 404 });
    }
    return new Response(object.body, {
      status: 200,
      headers: artifactHeaders(object, artifact),
    });
  }

  if (request.method === "DELETE") {
    const existing = await env.ARTIFACTS.head(artifact.key);
    if (!existing) {
      return Response.json({ ok: true, deleted: false, artifact: artifact.key });
    }
    await env.ARTIFACTS.delete(artifact.key);
    return Response.json({ ok: true, deleted: true, artifact: artifact.key });
  }

  return Response.json({ ok: false, error: "method_not_allowed" }, { status: 405 });
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
        r2: !!env.ARTIFACTS,
        artifact_auth: !!(typeof env.RUNNER3_CORE_TOKEN === "string" && env.RUNNER3_CORE_TOKEN.trim()),
        write_auth: coreWriteAuthMode(env),
        time: new Date().toISOString()
      });
    }

    if (segments[0] === "artifacts") {
      return handleArtifact(request, env, segments);
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
        const authError = requireCoreWriteAuth(request, env);
        if (authError) return authError;
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
        const authError = requireCoreWriteAuth(request, env);
        if (authError) return authError;
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
      const authError = requireCoreWriteAuth(request, env);
      if (authError) return authError;

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
