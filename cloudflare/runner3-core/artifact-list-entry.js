import app from "./opaque-mailbox-entry-v2.js";

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "private, no-store",
    },
  });
}

function requireArtifactAuth(request, env) {
  const expected = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!expected) return json({ ok: false, error: "ARTIFACT_AUTH_NOT_CONFIGURED" }, 503);

  const auth = request.headers.get("Authorization") || "";
  const prefix = "Bearer ";
  const supplied = auth.startsWith(prefix) ? auth.slice(prefix.length).trim() : "";
  if (!supplied || supplied !== expected) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  return null;
}

function parseLimit(raw) {
  const value = Number.parseInt(raw || "100", 10);
  if (!Number.isFinite(value)) return 100;
  return Math.min(Math.max(value, 1), 1000);
}

async function handleArtifactList(request, env) {
  if (request.method !== "GET") {
    return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  }
  if (!env.ARTIFACTS) {
    return json({ ok: false, error: "R2_NOT_BOUND" }, 503);
  }
  const authError = requireArtifactAuth(request, env);
  if (authError) return authError;

  const url = new URL(request.url);
  const prefix = url.searchParams.get("prefix") || "";
  const cursor = url.searchParams.get("cursor") || undefined;
  const delimiter = url.searchParams.get("delimiter") || undefined;
  const limit = parseLimit(url.searchParams.get("limit"));

  const options = { prefix, limit };
  if (cursor) options.cursor = cursor;
  if (delimiter) options.delimiter = delimiter;

  const result = await env.ARTIFACTS.list(options);
  return json({
    ok: true,
    prefix,
    limit,
    truncated: Boolean(result.truncated),
    cursor: result.truncated ? (result.cursor || null) : null,
    delimited_prefixes: Array.isArray(result.delimitedPrefixes) ? result.delimitedPrefixes : [],
    objects: (result.objects || []).map((object) => ({
      key: object.key,
      size: Number.isFinite(object.size) ? object.size : null,
      etag: object.httpEtag || object.etag || null,
      uploaded: object.uploaded instanceof Date ? object.uploaded.toISOString() : (object.uploaded || null),
    })),
  });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/artifact-list") {
      return handleArtifactList(request, env);
    }
    return app.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") {
      return app.scheduled(controller, env, ctx);
    }
  },
};
