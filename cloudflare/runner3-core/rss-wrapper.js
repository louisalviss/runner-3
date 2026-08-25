import core from "./src/index.js";

const RSS_MAX_LIMIT = 200;

function requireDb(env) {
  if (!env.DB) return Response.json({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });
  return null;
}

function requireR2(env) {
  if (!env.ARTIFACTS) return Response.json({ ok: false, error: "R2_NOT_BOUND" }, { status: 503 });
  return null;
}

function requireCoreAuth(request, env) {
  const expected = typeof env.RUNNER3_CORE_TOKEN === "string" ? env.RUNNER3_CORE_TOKEN.trim() : "";
  if (!expected) {
    return Response.json({ ok: false, error: "RSS_BODY_AUTH_NOT_CONFIGURED" }, { status: 503 });
  }
  const auth = request.headers.get("Authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!supplied || supplied !== expected) {
    return Response.json({ ok: false, error: "UNAUTHORIZED" }, { status: 401 });
  }
  return null;
}

function clampLimit(value) {
  const parsed = Number.parseInt(value || "50", 10);
  if (!Number.isFinite(parsed)) return 50;
  return Math.min(RSS_MAX_LIMIT, Math.max(1, parsed));
}

function ftsQuery(value) {
  return String(value || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 12)
    .map((part) => `"${part.replaceAll('"', '""')}"`)
    .join(" AND ");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function articleShape(row) {
  if (!row) return null;
  return {
    article_id: row.article_id,
    stable_key: row.stable_key,
    canonical_url: row.canonical_url,
    source_key: row.source_key,
    source_name: row.source_name,
    source_language: row.source_language,
    item_type: row.item_type,
    title: row.title,
    published_at: row.published_at,
    fetch_status: row.fetch_status,
    translation_status: row.translation_status,
    current_version_id: row.current_version_id,
    original_object_key: row.original_object_key,
    vi_object_key: row.vi_object_key,
    qa_state: row.qa_state,
    last_error: row.last_error,
    updated_at: row.updated_at,
  };
}

const RSS_COLUMNS = `
  a.article_id, a.stable_key, a.canonical_url, a.source_key, a.source_name,
  a.source_language, a.item_type, a.title, a.published_at, a.fetch_status,
  a.translation_status, a.current_version_id, a.original_object_key,
  a.vi_object_key, a.qa_state, a.last_error, a.updated_at
`;

async function listArticles(request, env, url) {
  if (request.method !== "GET") {
    return Response.json({ ok: false, error: "method_not_allowed" }, { status: 405 });
  }
  const dbError = requireDb(env);
  if (dbError) return dbError;

  const q = (url.searchParams.get("q") || "").trim();
  const source = (url.searchParams.get("source") || "").trim();
  const lang = (url.searchParams.get("lang") || "").trim();
  const limit = clampLimit(url.searchParams.get("limit"));
  const conditions = [];
  const binds = [];
  let from = "rss_articles a";

  if (q) {
    const match = ftsQuery(q);
    if (match) {
      from += " JOIN rss_articles_fts ON rss_articles_fts.rowid = a.rowid";
      conditions.push("rss_articles_fts MATCH ?");
      binds.push(match);
    }
  }
  if (source) {
    conditions.push("a.source_key = ?");
    binds.push(source);
  }
  if (lang) {
    conditions.push("a.source_language = ?");
    binds.push(lang);
  }

  const where = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
  const sql = `SELECT ${RSS_COLUMNS} FROM ${from} ${where} ORDER BY a.published_at DESC, a.article_id LIMIT ?`;
  binds.push(limit);

  try {
    const result = await env.DB.prepare(sql).bind(...binds).all();
    const articles = (result.results || []).map(articleShape);
    return Response.json({ ok: true, count: articles.length, articles });
  } catch (err) {
    return Response.json({ ok: false, error: "RSS_QUERY_FAILED", detail: String(err?.message || err) }, { status: 500 });
  }
}

async function getArticle(request, env, url) {
  if (request.method !== "GET") {
    return Response.json({ ok: false, error: "method_not_allowed" }, { status: 405 });
  }
  const dbError = requireDb(env);
  if (dbError) return dbError;
  const r2Error = requireR2(env);
  if (r2Error) return r2Error;
  const authError = requireCoreAuth(request, env);
  if (authError) return authError;

  const id = (url.searchParams.get("id") || "").trim();
  const lang = (url.searchParams.get("lang") || "original").trim().toLowerCase();
  if (!id) return Response.json({ ok: false, error: "id is required" }, { status: 400 });
  if (!new Set(["original", "vi"]).has(lang)) {
    return Response.json({ ok: false, error: "lang must be original or vi" }, { status: 400 });
  }

  const row = await env.DB.prepare(`
    SELECT ${RSS_COLUMNS}
    FROM rss_articles a
    WHERE a.article_id = ? OR a.stable_key = ?
    LIMIT 1
  `).bind(id, id).first();

  if (!row) return Response.json({ ok: false, error: "RSS_ARTICLE_NOT_FOUND" }, { status: 404 });

  const objectKey = lang === "original"
    ? row.original_object_key
    : (row.source_language === "vi" ? row.original_object_key : row.vi_object_key);

  let content = null;
  let contentAvailable = false;
  if (objectKey) {
    const object = await env.ARTIFACTS.get(objectKey);
    if (object) {
      content = await object.text();
      contentAvailable = true;
    }
  }

  return Response.json({
    ok: true,
    article: articleShape(row),
    requested_language: lang,
    object_key: objectKey || null,
    content_available: contentAvailable,
    content,
  }, { headers: { "Cache-Control": "private, no-store" } });
}

async function rssUi(request, env) {
  if (request.method !== "GET") return new Response("Method Not Allowed", { status: 405 });
  const dbError = requireDb(env);
  if (dbError) return dbError;

  const result = await env.DB.prepare(`
    SELECT ${RSS_COLUMNS}
    FROM rss_articles a
    ORDER BY a.published_at DESC, a.article_id
    LIMIT 100
  `).all();
  const rows = result.results || [];
  const body = rows.map((row) => `
    <tr>
      <td><a href="${escapeHtml(row.canonical_url)}" target="_blank" rel="noreferrer">${escapeHtml(row.title)}</a></td>
      <td>${escapeHtml(row.source_name)}</td>
      <td>${escapeHtml(row.source_language)}</td>
      <td>${escapeHtml(row.fetch_status)}</td>
      <td>${escapeHtml(row.translation_status)}</td>
      <td>${escapeHtml(row.published_at || "")}</td>
    </tr>`).join("");

  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Runner3 RSS Library</title>
<style>
body{font:14px system-ui,sans-serif;margin:24px;color:#111}h1{font-size:22px}table{border-collapse:collapse;width:100%}th,td{padding:9px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#fff}a{color:inherit}.meta{color:#666;margin-bottom:14px}@media(max-width:760px){th:nth-child(3),td:nth-child(3),th:nth-child(6),td:nth-child(6){display:none}}
</style></head><body>
<h1>Runner3 RSS Library</h1><div class="meta">${rows.length} catalog items · bodies remain in private R2</div>
<table><thead><tr><th>Title</th><th>Source</th><th>Lang</th><th>Fetch</th><th>Translation</th><th>Published</th></tr></thead><tbody>${body}</tbody></table>
</body></html>`;
  return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/v1/rss/articles") return listArticles(request, env, url);
    if (url.pathname === "/v1/rss/article") return getArticle(request, env, url);
    if (url.pathname === "/ui/rss") return rssUi(request, env);
    return core.fetch(request, env, ctx);
  },

  async scheduled(controller, env, ctx) {
    if (typeof core.scheduled === "function") return core.scheduled(controller, env, ctx);
  },
};
