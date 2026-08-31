import { handleRssLibrary } from "./rss-library.js";
import { markProfileDirty } from "./content-personalization.js";

const VERSION = "rss-library-save-v1";
const ALLOWED = new Set(["article", "render_id", "context"]);
const ARTICLE_ALLOWED = new Set([
  "article_id", "stable_key", "canonical_url", "source_key", "source_name",
  "source_language", "item_type", "title", "published_at"
]);

function json(value, status = 200) {
  return Response.json(value, { status, headers: { "cache-control": "private, no-store" } });
}

function authError(request, env) {
  const expected = String(env.RUNNER3_CORE_TOKEN || "").trim();
  const auth = request.headers.get("authorization") || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (!expected) return json({ ok: false, error: "RSS_SAVE_AUTH_NOT_CONFIGURED" }, 503);
  if (!supplied || supplied !== expected) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  return null;
}

function bounded(value, name, limit = 4096, required = false) {
  const out = String(value ?? "").trim();
  if (required && !out) throw new Error(`${name}_required`);
  if (out.length > limit) throw new Error(`${name}_too_long`);
  return out || null;
}

function normalize(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("body_must_be_object");
  const unknown = Object.keys(body).filter((k) => !ALLOWED.has(k));
  if (unknown.length) throw new Error(`unsupported_fields:${unknown.join(",")}`);
  const a = body.article;
  if (!a || typeof a !== "object" || Array.isArray(a)) throw new Error("article_required");
  const articleUnknown = Object.keys(a).filter((k) => !ARTICLE_ALLOWED.has(k));
  if (articleUnknown.length) throw new Error(`unsupported_article_fields:${articleUnknown.join(",")}`);
  const canonicalUrl = bounded(a.canonical_url, "canonical_url", 8192, true);
  let parsed;
  try { parsed = new URL(canonicalUrl); } catch { throw new Error("canonical_url_invalid"); }
  if (!new Set(["http:", "https:"]).has(parsed.protocol)) throw new Error("canonical_url_scheme_invalid");
  const article = {
    article_id: bounded(a.article_id, "article_id", 240, true),
    stable_key: bounded(a.stable_key, "stable_key", 500, true),
    canonical_url: canonicalUrl,
    source_key: bounded(a.source_key, "source_key", 160, true),
    source_name: bounded(a.source_name, "source_name", 300, true),
    source_language: bounded(a.source_language || "en", "source_language", 20, true),
    item_type: bounded(a.item_type || "article", "item_type", 40, true),
    title: bounded(a.title, "title", 4000, true),
    published_at: bounded(a.published_at, "published_at", 100, false),
  };
  return {
    article,
    render_id: bounded(body.render_id || `rss-save:${article.stable_key}`, "render_id", 300, true),
    context: body.context && typeof body.context === "object" && !Array.isArray(body.context) ? body.context : {},
  };
}

async function upsertArticle(env, article) {
  const existing = await env.DB.prepare(`
    SELECT article_id,stable_key,canonical_url,current_version_id,source_checksum,original_object_key
    FROM rss_articles
    WHERE article_id=? OR stable_key=? OR canonical_url=?
    LIMIT 1
  `).bind(article.article_id, article.stable_key, article.canonical_url).first();

  if (existing) {
    const sameIdentity = existing.article_id === article.article_id || existing.stable_key === article.stable_key || existing.canonical_url === article.canonical_url;
    if (!sameIdentity) throw new Error("article_identity_conflict");
    await env.DB.prepare(`
      UPDATE rss_articles SET
        stable_key=?, canonical_url=?, source_key=?, source_name=?, source_language=?,
        item_type=?, title=?, published_at=COALESCE(?,published_at), updated_at=CURRENT_TIMESTAMP
      WHERE article_id=?
    `).bind(
      article.stable_key, article.canonical_url, article.source_key, article.source_name,
      article.source_language, article.item_type, article.title, article.published_at, existing.article_id
    ).run();
    return { articleId: existing.article_id, created: false, before: existing };
  }

  await env.DB.prepare(`
    INSERT INTO rss_articles(
      article_id,stable_key,canonical_url,source_key,source_name,source_language,item_type,title,published_at,fetch_status,translation_status
    ) VALUES(?,?,?,?,?,?,?,?,?,'pending',?)
  `).bind(
    article.article_id, article.stable_key, article.canonical_url, article.source_key,
    article.source_name, article.source_language, article.item_type, article.title,
    article.published_at, article.source_language === "vi" ? "native_vi" : "pending"
  ).run();
  return { articleId: article.article_id, created: true, before: null };
}

async function fetchThroughCanonicalHandler(env, articleId) {
  const url = new URL(`https://rss-library.internal/api/rss/articles/${encodeURIComponent(articleId)}/fetch`);
  const request = new Request(url.toString(), {
    method: "POST",
    headers: { authorization: `Bearer ${String(env.RUNNER3_CORE_TOKEN || "")}` },
  });
  const response = await handleRssLibrary(request, env, url);
  if (!response) throw new Error("rss_fetch_handler_missing");
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.ok !== true) throw new Error(`full_fetch_failed:${payload?.error || response.status}`);
  return payload;
}

async function recordSelected(env, article, renderId, context, checksum) {
  const itemId = article.canonical_url;
  await env.DB.prepare(`
    INSERT INTO content_items(
      item_id,canonical_url,source_type,source_name,source_key,title,published_at,captured_at,language,raw_ref,content_hash,metadata_json,first_seen_at,last_seen_at
    ) VALUES(?,?, 'rss',?,?,?,?,CURRENT_TIMESTAMP,?,?,?, ?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
    ON CONFLICT(item_id) DO UPDATE SET
      canonical_url=excluded.canonical_url,source_name=excluded.source_name,source_key=excluded.source_key,
      title=excluded.title,published_at=COALESCE(excluded.published_at,content_items.published_at),
      language=excluded.language,content_hash=excluded.content_hash,metadata_json=excluded.metadata_json,last_seen_at=CURRENT_TIMESTAMP
  `).bind(
    itemId, article.canonical_url, article.source_name, article.source_key, article.title,
    article.published_at, article.source_language, `rss-library:${article.article_id}`, checksum,
    JSON.stringify({ rss_article_id: article.article_id, selected_via: "rss-library-save-v1" })
  ).run();

  const result = await env.DB.prepare(`
    INSERT INTO user_content_events(item_id,render_id,event_type,explicit_feedback,context_json,event_at)
    SELECT ?,?,'selected',NULL,?,CURRENT_TIMESTAMP
    WHERE NOT EXISTS(
      SELECT 1 FROM user_content_events WHERE item_id=? AND event_type='selected' AND COALESCE(render_id,'')=COALESCE(?,'')
    )
  `).bind(itemId, renderId, JSON.stringify({ source: "rss_library_save", ...context }), itemId, renderId).run();
  await markProfileDirty(env, "rss_library_selected");
  return Number(result.meta?.changes || 0);
}

export async function handleRssLibrarySave(request, env, url) {
  if (url.pathname !== "/api/rss/library/save") return null;
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!env.DB || !env.ARTIFACTS) return json({ ok: false, error: "RSS_BINDINGS_MISSING" }, 503);
  const auth = authError(request, env); if (auth) return auth;

  try {
    const normalized = normalize(await request.json());
    const identity = await upsertArticle(env, normalized.article);
    const fetched = await fetchThroughCanonicalHandler(env, identity.articleId);
    const row = await env.DB.prepare(`
      SELECT article_id,stable_key,canonical_url,fetch_status,translation_status,current_version_id,
             source_checksum,original_object_key,vi_object_key,qa_state,last_error
      FROM rss_articles WHERE article_id=?
    `).bind(identity.articleId).first();
    if (!row || row.fetch_status !== "fetched" || !row.source_checksum || !row.original_object_key) {
      throw new Error("durable_d1_readback_failed");
    }
    const object = await env.ARTIFACTS.head(row.original_object_key);
    if (!object) throw new Error("durable_r2_readback_failed");
    const selectedApplied = await recordSelected(env, { ...normalized.article, article_id: identity.articleId }, normalized.render_id, normalized.context, row.source_checksum);
    const versionCount = await env.DB.prepare("SELECT COUNT(*) AS n FROM rss_article_versions WHERE article_id=? AND source_checksum=?")
      .bind(identity.articleId, row.source_checksum).first();
    return json({
      ok: true,
      durable: true,
      version: VERSION,
      article_id: identity.articleId,
      article_created: identity.created,
      canonical_url: row.canonical_url,
      source_checksum: row.source_checksum,
      current_version_id: row.current_version_id,
      original_object_key: row.original_object_key,
      r2_readback: true,
      d1_readback: true,
      logical_version_count: Number(versionCount?.n || 0),
      selected_event_applied: selectedApplied,
      profile_status: "dirty",
      fetch: { chars: fetched.chars ?? null, native_vi: fetched.nativeVi ?? null },
      reader_path: `/rss/article/${encodeURIComponent(identity.articleId)}`,
      audio: "persistent-reader-audio-on-demand",
      translation_status: row.translation_status,
      qa_state: row.qa_state,
    });
  } catch (error) {
    return json({ ok: false, durable: false, version: VERSION, error: String(error?.message || error).slice(0, 1000) }, 400);
  }
}
