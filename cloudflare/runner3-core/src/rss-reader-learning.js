const EVENT_WEIGHTS = { shown: 0, selected: 1, deep_read: 2, liked: 4, disliked: -4, saved: 3 };

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
  if (!itemId) return { itemId: null, changed: 0 };
  const sourceKey = String(article.source_key || article.sourceKey || "").trim() || null;
  const sourceName = String(article.source_name || article.sourceName || sourceKey || "").trim() || null;
  const title = String(article.title || "").trim() || null;
  const publishedAt = article.published_at || article.publishedAt || null;
  const language = article.source_language || article.language || null;
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
      last_seen_at = CURRENT_TIMESTAMP
  `).bind(
    itemId, itemId, sourceName, sourceKey, title, publishedAt, language,
    JSON.stringify({ rss_reader_article_id: article.article_id || null, selection_gate: true })
  ).run();

  if (sourceKey) {
    await env.DB.prepare(`
      INSERT INTO content_features (
        item_id, feature_type, feature_key, feature_value, weight, confidence, model_version, updated_at
      ) VALUES (?, 'source', ?, NULL, 0.35, 1.0, 'reader-bridge-v1', CURRENT_TIMESTAMP)
      ON CONFLICT(item_id, feature_type, feature_key) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
    `).bind(itemId, sourceKey).run();
  }
  return { itemId, changed: Number(result.meta?.changes || 0) };
}

async function recordEventOnce(env, article, eventType, context = null) {
  if (!(eventType in EVENT_WEIGHTS)) return 0;
  const ensured = await ensureContentItem(env, article);
  if (!ensured.itemId) return 0;
  const renderId = `rss-reader:${eventType}:v1`;
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
  return Number(result.meta?.changes || 0);
}

function eventWeightSql() {
  return Object.entries(EVENT_WEIGHTS).map(([key, value]) => `WHEN '${key}' THEN ${value}`).join(" ");
}

async function recomputePersonal(env) {
  const cases = eventWeightSql();
  await env.DB.prepare("DELETE FROM interest_profile").run();
  await env.DB.prepare(`
    INSERT INTO interest_profile (
      feature_type, feature_key, weight, evidence_count, positive_count,
      negative_count, confidence, updated_at
    )
    SELECT f.feature_type, f.feature_key,
      SUM((CASE e.event_type ${cases} ELSE 0 END) * f.weight * f.confidence) / MAX(1.0, SQRT(COUNT(*))),
      COUNT(*),
      SUM(CASE WHEN (CASE e.event_type ${cases} ELSE 0 END) > 0 THEN 1 ELSE 0 END),
      SUM(CASE WHEN (CASE e.event_type ${cases} ELSE 0 END) < 0 THEN 1 ELSE 0 END),
      MIN(1.0, COUNT(*) / 6.0), CURRENT_TIMESTAMP
    FROM user_content_events e
    JOIN content_features f ON f.item_id = e.item_id
    WHERE e.event_type <> 'shown'
    GROUP BY f.feature_type, f.feature_key
  `).run();

  const model = "personal-v1";
  await env.DB.prepare("DELETE FROM content_scores WHERE score_type='personal_relevance' AND model_version=?").bind(model).run();
  await env.DB.prepare(`
    INSERT INTO content_scores (item_id, score_type, score, confidence, reason_json, model_version, scored_at)
    SELECT i.item_id, 'personal_relevance',
      MIN(100.0, MAX(0.0, 50.0 + 12.5 * COALESCE(SUM(p.weight * f.weight * f.confidence), 0))),
      MIN(1.0, COALESCE(MAX(p.confidence), 0)),
      json_object('matched_features', COUNT(p.feature_key)), ?, CURRENT_TIMESTAMP
    FROM content_items i
    LEFT JOIN content_features f ON f.item_id = i.item_id
    LEFT JOIN interest_profile p ON p.feature_type = f.feature_type AND p.feature_key = f.feature_key
    GROUP BY i.item_id
  `).bind(model).run();
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
  if (changed) await recomputePersonal(env);
  return { ok: true, changed, articles: articles.length };
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
  const deepRead = await recordEventOnce(env, article, "deep_read", { source: "rss_reader_threshold_v1", article_id: articleId });
  if (selected || deepRead) await recomputePersonal(env);
  return Response.json({ ok: true, selected_applied: selected, deep_read_applied: deepRead });
}

export async function recordReaderStateLearning(env, articleId, body) {
  if (!env.DB || !body) return { ok: false, changed: 0 };
  const article = await loadArticle(env, articleId);
  if (!article) return { ok: false, changed: 0 };
  let changed = 0;
  changed += await recordEventOnce(env, article, "selected", { source: "rss_reader_state", article_id: articleId });
  if (body.preference === "like") {
    changed += await recordEventOnce(env, article, "liked", { source: "rss_reader_state", article_id: articleId });
  } else if (body.preference === "dislike") {
    changed += await recordEventOnce(env, article, "disliked", { source: "rss_reader_state", article_id: articleId });
  }
  if (body.lifecycle === "archived" || body.featured === true) {
    changed += await recordEventOnce(env, article, "saved", { source: "rss_reader_state", article_id: articleId });
  }
  if (changed) await recomputePersonal(env);
  return { ok: true, changed };
}
