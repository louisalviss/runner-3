import app from "./rss-article-fast-entry.js";

const VERSION = "rss-reader-read-fast-v1";
const READER_TOKEN_SHA256 = "a4efd86ada61ed4398ec259b7f46262f10d4e2f7fa4f123c5619eb6366d0dd18";
const READER_CATEGORIES = ["AI", "Tech", "Kinh tế", "Chính trị", "Khoa học", "Trading", "WordPress", "Khác"];

function json(value, status = 200, route = "read") {
  return Response.json(value, {
    status,
    headers: {
      "cache-control": "private, no-store",
      "x-r3-rss-read-fastpath": VERSION,
      "x-r3-rss-read-route": route,
    },
  });
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(String(text ?? "")));
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function authorized(request) {
  const auth = request.headers.get("Authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  return Boolean(supplied) && (await sha256Hex(supplied)) === READER_TOKEN_SHA256;
}

function cleanRow(row) {
  if (!row) return null;
  return {
    article_id: row.article_id,
    canonical_url: row.canonical_url,
    source_key: row.source_key,
    source_name: row.source_name,
    source_language: row.source_language,
    title: row.title,
    published_at: row.published_at,
    fetch_status: row.fetch_status,
    translation_status: row.translation_status,
    qa_state: row.qa_state,
    last_error: row.last_error,
    updated_at: row.updated_at,
    lifecycle: row.lifecycle || "active",
    featured: Number(row.featured || 0) === 1,
    category: row.category || null,
    preference: row.preference || null,
    last_opened_at: row.last_opened_at || null,
  };
}

async function getArticle(env, articleId) {
  return env.DB.prepare(`
    SELECT a.*,
           COALESCE(s.lifecycle, 'active') AS lifecycle,
           COALESCE(s.featured, 0) AS featured,
           s.category, s.preference, s.last_opened_at
    FROM rss_articles a
    LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
    WHERE a.article_id = ?
    LIMIT 1
  `).bind(articleId).first();
}

async function markOpened(env, articleId) {
  await env.DB.prepare(`
    INSERT INTO rss_reader_state (article_id, lifecycle, featured, last_opened_at, updated_at)
    VALUES (?, 'active', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ON CONFLICT(article_id) DO UPDATE SET
      last_opened_at = CURRENT_TIMESTAMP,
      updated_at = CURRENT_TIMESTAMP
  `).bind(articleId).run();
}

async function routeRead(request, env, url, ctx) {
  if (!url.pathname.startsWith("/reader/rss/")) return null;
  if (request.method !== "GET") return null;
  if (!env.DB) return json({ ok: false, error: "D1_NOT_BOUND" }, 503, "binding");
  if (!(await authorized(request))) return json({ ok: false, error: "UNAUTHORIZED" }, 401, "auth");

  if (url.pathname === "/reader/rss/categories") {
    try {
      const rows = await env.DB.prepare(`
        SELECT name, keywords, sort_order
        FROM rss_reader_categories
        ORDER BY sort_order, lower(name)
      `).all();
      const categories = (rows.results || []).map((row) => ({
        name: String(row.name || "").trim(),
        keywords: String(row.keywords || "").trim(),
        sort_order: Number(row.sort_order || 100),
        usage: 0,
      })).filter((item) => item.name);
      return json({ ok: true, categories }, 200, "categories");
    } catch (error) {
      return json({ ok: false, error: "CATEGORIES_READ_FAILED", detail: String(error?.message || error).slice(0, 300) }, 500, "categories");
    }
  }

  const match = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)(?:\/(vi|original))?$/);
  if (!match) return null;
  let articleId;
  try { articleId = decodeURIComponent(match[1]); }
  catch { return json({ ok: false, error: "INVALID_ARTICLE_ID" }, 400, "article"); }

  try {
    const article = await getArticle(env, articleId);
    if (!article) return json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404, "article");
    const kind = match[2] || "";
    if (!kind) return json({ ok: true, article: cleanRow(article), suggestedCategories: READER_CATEGORIES }, 200, "detail");

    if (!env.ARTIFACTS) return json({ ok: false, error: "R2_NOT_BOUND" }, 503, kind);
    let key = article.original_object_key;
    let nativeVi = false;
    if (kind === "vi") {
      if (article.source_language === "vi") nativeVi = true;
      else key = article.vi_object_key;
    }
    if (!key) {
      const code = kind === "vi" && article.source_language !== "vi" ? "TRANSLATION_NOT_READY" : "ORIGINAL_NOT_FETCHED";
      return json({ ok: false, error: code, article: cleanRow(article) }, 409, kind);
    }
    const object = await env.ARTIFACTS.get(key);
    if (!object) return json({ ok: false, error: "ARTIFACT_MISSING", article: cleanRow(article) }, 500, kind);
    const artifact = JSON.parse(await object.text());
    if (ctx?.waitUntil) ctx.waitUntil(markOpened(env, articleId).catch(() => {}));
    return json({ ok: true, article: cleanRow(article), view: kind, nativeVi, artifact }, 200, kind);
  } catch (error) {
    return json({ ok: false, error: "ARTICLE_READ_FAILED", detail: String(error?.message || error).slice(0, 300) }, 500, "article");
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await routeRead(request, env, url, ctx);
    if (response) return response;
    return app.fetch(request, env, ctx);
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
