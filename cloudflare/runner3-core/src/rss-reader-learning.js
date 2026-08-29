import { FEATURE_MODEL_VERSION, replaceAutoSemanticFeatures } from "./content-feature-enrichment.js";
import {
  isSupportedContentEvent,
  markProfileDirty,
  maybeRecomputePersonal as maybeRecomputePersonalShared,
} from "./content-personalization.js";

export const maybeRecomputePersonal = maybeRecomputePersonalShared;

function articleItemId(article) {
  return String(article?.canonical_url || article?.canonicalUrl || "").trim();
}

async function loadArticle(env, articleId) {
  return env.DB.prepare(`
    SELECT article_id, canonical_url, source_key, source_name, source_language, title, published_at
    FROM rss_articles WHERE article_id = ?
  `).bind(articleId).first();
}

async function ensureContentItem(env, article) {
  const itemId = articleItemId(article);
  if (!itemId) return { itemId: null, changed: 0, features: 0 };
  const sourceKey = String(article.source_key || article.sourceKey || "").trim() || null;
  const sourceName = String(article.source_name || article.sourceName || sourceKey || "").trim() || null;
  const title = String(article.title || "").trim() || null;
  const publishedAt = article.published_at || article.publishedAt || null;
  const language = String(article.source_language || article.language || "").trim().toLowerCase() || null;
  const result = await env.DB.prepare(`
    INSERT INTO content_items (
      item_id, canonical_url, source_type, source_name, source_key, title,
      published_at, captured_at, language, metadata_json, first_seen_at, last_seen_at
    ) VALUES (?, ?, 'rss', ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ON CONFLICT(item_id) DO UPDATE SET
      canonical_url = excluded.canonical_url,
      source_name = COALESCE(excluded.source_name, content_items.source_name),
      source_key = COALESCE(excluded.source_key, content_items.source_key),
      title = COALESCE(excluded.title, content_items.title),
      published_at = COALESCE(excluded.published_at, content_items.published_at),
      language = COALESCE(excluded.language, content_items.language),
      metadata_json = excluded.metadata_json,
      last_seen_at = CURRENT_TIMESTAMP
  `).bind(
    itemId, itemId, sourceName, sourceKey, title, publishedAt, language,
    JSON.stringify({ rss_reader_article_id: article.article_id || null, selection_gate: true, feature_model: FEATURE_MODEL_VERSION })
  ).run();

  const semantic = await replaceAutoSemanticFeatures(env, itemId, {
    canonical_url: itemId,
    source_key: sourceKey,
    source_name: sourceName,
    language,
    title,
    published_at: publishedAt,
  });
  return { itemId, changed: Number(result.meta?.changes || 0), features: semantic.applied };
}

async function recordEventOnce(env, article, eventType, context = null) {
  if (!isSupportedContentEvent(eventType)) return 0;
  const ensured = await ensureContentItem(env, article);
  if (!ensured.itemId) return 0;
  const renderId = `rss-reader:${eventType}:v3`;
  const result = await env.DB.prepare(`
    INSERT INTO user_content_events (
      item_id, render_id, event_type, assistant_recommended, assistant_rank,
      explicit_feedback, context_json, event_at
    )
    SELECT ?, ?, ?, 0, NULL, NULL, ?, CURRENT_TIMESTAMP
    WHERE NOT EXISTS (
      SELECT 1 FROM user_content_events WHERE item_id = ? AND event_type = ?
    )
  `).bind(
    ensured.itemId, renderId, eventType, JSON.stringify(context || {}),
    ensured.itemId, eventType
  ).run();
  const changed = Number(result.meta?.changes || 0);
  if (changed) await markProfileDirty(env, `rss_${eventType}`);
  return changed;
}

async function replaceReaderPreference(env, article, preference, articleId) {
  const ensured = await ensureContentItem(env, article);
  if (!ensured.itemId) return 0;
  const removed = await env.DB.prepare(`DELETE FROM user_content_events WHERE item_id=? AND event_type IN ('liked','disliked')`).bind(ensured.itemId).run();
  let changed = Number(removed.meta?.changes || 0);
  if (preference === "like" || preference === "dislike") {
    const eventType = preference === "like" ? "liked" : "disliked";
    const inserted = await env.DB.prepare(`
      INSERT INTO user_content_events(item_id,render_id,event_type,assistant_recommended,assistant_rank,explicit_feedback,context_json,event_at)
      VALUES(?,?,?,0,NULL,?, ?,CURRENT_TIMESTAMP)
    `).bind(
      ensured.itemId,
      `rss-reader:${eventType}:state-v3`,
      eventType,
      preference,
      JSON.stringify({ source: "rss_reader_state", article_id: articleId, state_semantics: "current_preference" }),
    ).run();
    changed += Number(inserted.meta?.changes || 0);
  }
  if (changed) await markProfileDirty(env, "rss_preference_state");
  return changed;
}

async function replaceReaderFeatured(env, article, featured, articleId) {
  const ensured = await ensureContentItem(env, article);
  if (!ensured.itemId) return 0;
  const removed = await env.DB.prepare(`DELETE FROM user_content_events WHERE item_id=? AND event_type='saved' AND render_id LIKE 'rss-reader:saved:%'`).bind(ensured.itemId).run();
  let changed = Number(removed.meta?.changes || 0);
  if (featured === true) {
    const inserted = await env.DB.prepare(`
      INSERT INTO user_content_events(item_id,render_id,event_type,assistant_recommended,assistant_rank,explicit_feedback,context_json,event_at)
      VALUES(?,?,'saved',0,NULL,'featured',?,CURRENT_TIMESTAMP)
    `).bind(
      ensured.itemId,
      "rss-reader:saved:featured-v3",
      JSON.stringify({ source: "rss_reader_state", article_id: articleId, state_semantics: "featured_only" }),
    ).run();
    changed += Number(inserted.meta?.changes || 0);
  }
  if (changed) await markProfileDirty(env, "rss_featured_state");
  return changed;
}

export async function reconcileLibraryLearning(response, env) {
  if (!response?.ok || !env.DB) return { ok: false, changed: 0 };
  const payload = await response.json().catch(() => null);
  const articles = Array.isArray(payload?.articles) ? payload.articles : [];
  let changed = 0;
  for (const article of articles) {
    changed += await recordEventOnce(env, article, "selected", {
      source: "rss_library_selection_gate",
      article_id: article.article_id || null,
    });
  }
  const recompute = changed ? await maybeRecomputePersonalShared(env) : { recomputed: false };
  return { ok: true, changed, articles: articles.length, recomputed: Boolean(recompute.recomputed) };
}

export async function handleRssReaderLearning(request, env, url, authorize) {
  if (request.method !== "POST") return null;
  const match = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/deep-read$/);
  if (!match) return null;
  if (!env.DB) return Response.json({ ok: false, error: "D1_NOT_BOUND" }, { status: 503 });
  let articleId;
  try { articleId = decodeURIComponent(match[1]); } catch { return Response.json({ ok: false, error: "INVALID_ARTICLE_ID" }, { status: 400 }); }

  const auth = await authorize(articleId);
  if (!auth?.ok) return auth?.response || Response.json({ ok: false, error: "UNAUTHORIZED" }, { status: 401 });
  const article = auth.payload?.article || await loadArticle(env, articleId);
  if (!article) return Response.json({ ok: false, error: "ARTICLE_NOT_FOUND" }, { status: 404 });

  const selected = await recordEventOnce(env, article, "selected", { source: "rss_reader_deep_read", article_id: articleId });
  const deepRead = await recordEventOnce(env, article, "deep_read", { source: "rss_reader_threshold_v2", article_id: articleId });
  const recompute = (selected || deepRead) ? await maybeRecomputePersonalShared(env) : { recomputed: false };
  return Response.json({ ok: true, selected_applied: selected, deep_read_applied: deepRead, profile_recomputed: Boolean(recompute.recomputed) });
}

export async function recordReaderStateLearning(env, articleId, body) {
  if (!env.DB || !body) return { ok: false, changed: 0 };
  const article = await loadArticle(env, articleId);
  if (!article) return { ok: false, changed: 0 };
  let changed = 0;
  changed += await recordEventOnce(env, article, "selected", { source: "rss_reader_state", article_id: articleId });

  if (Object.prototype.hasOwnProperty.call(body, "preference")) {
    changed += await replaceReaderPreference(env, article, body.preference, articleId);
  }
  if (Object.prototype.hasOwnProperty.call(body, "featured")) {
    changed += await replaceReaderFeatured(env, article, body.featured, articleId);
  }

  const recompute = changed ? await maybeRecomputePersonalShared(env) : { recomputed: false };
  return { ok: true, changed, recomputed: Boolean(recompute.recomputed) };
}
