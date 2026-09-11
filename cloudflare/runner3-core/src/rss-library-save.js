import { handleRssLibrary, persistFetchedArticle } from "./rss-library.js";
import { markProfileDirty } from "./content-personalization.js";

const VERSION = "rss-library-save-v1";
const IMPORT_VERSION = "rss-library-import-v1";
const ALLOWED = new Set(["article", "render_id", "context"]);
const IMPORT_ALLOWED = new Set(["article", "context", "content", "media"]);
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

function normalizeImportMedia(value) {
  if (value === undefined) return null;
  if (!Array.isArray(value)) throw new Error("media_must_be_array");
  if (value.length > 80) throw new Error("media_too_many_items");
  return value.map((item, index) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) throw new Error(`media_${index}_invalid`);
    const sourceObjectKey = bounded(item.source_object_key, `media_${index}_source_object_key`, 1200, true);
    if (!sourceObjectKey.startsWith("core/facebook-archive/") || sourceObjectKey.includes("..")) {
      throw new Error(`media_${index}_source_object_key_invalid`);
    }
    const contentType = bounded(item.content_type, `media_${index}_content_type`, 120, true).toLowerCase();
    if (!contentType.startsWith("image/") || contentType === "image/svg+xml") throw new Error(`media_${index}_content_type_invalid`);
    const sha256 = bounded(item.sha256, `media_${index}_sha256`, 64, true).toLowerCase();
    if (!/^[a-f0-9]{64}$/.test(sha256)) throw new Error(`media_${index}_sha256_invalid`);
    const bytes = Math.max(0, Number.parseInt(item.bytes || 0, 10) || 0);
    if (!bytes || bytes > 12 * 1024 * 1024) throw new Error(`media_${index}_bytes_invalid`);
    return {
      source_object_key: sourceObjectKey,
      content_type: contentType,
      sha256,
      bytes,
      width: Math.max(0, Number.parseInt(item.width || 0, 10) || 0),
      height: Math.max(0, Number.parseInt(item.height || 0, 10) || 0),
      alt: bounded(item.alt, `media_${index}_alt`, 2000, false) || "",
      order: Number.isFinite(Number(item.order)) ? Number(item.order) : index,
      kind: bounded(item.kind || "photo", `media_${index}_kind`, 40, false) || "photo",
    };
  }).sort((a, b) => a.order - b.order);
}

async function sha256Bytes(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

function importedFacebookMediaUrl(env, sourceObjectKey) {
  const key = String(sourceObjectKey || "").trim();
  const match = key.match(/^core\/facebook-archive\/([A-Za-z0-9._-]+)\/media\/([A-Za-z0-9._-]+)\/([A-Za-z0-9._-]+)$/);
  if (!match) throw new Error(`media_source_key_invalid:${key.slice(0, 160)}`);
  const origin = readerPublicOrigin(env);
  return `${origin}/rss/facebook-media/${encodeURIComponent(match[1])}/${encodeURIComponent(match[2])}/${encodeURIComponent(match[3])}`;
}

function readerPublicOrigin(env) {
  return String(env.RSS_READER_PUBLIC_ORIGIN || "https://runner3-core.ducduy2411.workers.dev").trim().replace(/\/$/, "");
}

async function attachImportedMedia(env, article, row, media) {
  if (media === null) return { attached: null, count: null, readback: null };
  const totalExpected = media.reduce((sum, item) => sum + item.bytes, 0);
  if (totalExpected > 96 * 1024 * 1024) throw new Error("media_total_bytes_exceeded");
  const images = [];
  for (const item of media) {
    const source = await env.ARTIFACTS.get(item.source_object_key);
    if (!source) throw new Error(`media_source_missing:${item.source_object_key}`);
    const bytes = await source.arrayBuffer();
    if (bytes.byteLength !== item.bytes) throw new Error(`media_source_size_mismatch:${item.source_object_key}`);
    const hash = await sha256Bytes(bytes);
    if (hash !== item.sha256) throw new Error(`media_source_hash_mismatch:${item.source_object_key}`);
    const token = hash.slice(0, 32);
    const targetKey = `rss-media/${encodeURIComponent(article.article_id)}/${token}`;
    const existing = await env.ARTIFACTS.head(targetKey);
    if (!existing || Number(existing.size || 0) !== bytes.byteLength) {
      await env.ARTIFACTS.put(targetKey, bytes, {
        httpMetadata: { contentType: item.content_type, cacheControl: "public, max-age=31536000, immutable" },
        customMetadata: { articleId: article.article_id.slice(0, 160), sourceKey: article.source_key.slice(0, 80), sourceHash: hash, kind: "facebook-import" },
      });
    }
    const verify = await env.ARTIFACTS.head(targetKey);
    if (!verify || Number(verify.size || 0) !== bytes.byteLength) throw new Error(`media_target_readback_failed:${targetKey}`);
    const url = importedFacebookMediaUrl(env, item.source_object_key);
    images.push({
      url, source_url: url, alt: item.alt, caption: item.alt,
      width: item.width, height: item.height, kind: item.kind === "video_poster" ? "photo" : "photo",
      score: 10, inFigure: true, cache_status: "cached", cache_token: token,
      imported_from: item.source_object_key, order: item.order,
    });
  }
  const current = await env.ARTIFACTS.get(row.original_object_key);
  if (!current) throw new Error("article_artifact_missing_before_media_attach");
  const artifact = JSON.parse(await current.text());
  artifact.images = images;
  artifact.imageCount = images.length;
  artifact.mediaImport = { version: 1, source: "facebook-r2-verified", readbackVerified: true };
  await env.ARTIFACTS.put(row.original_object_key, JSON.stringify(artifact), {
    httpMetadata: { contentType: "application/json; charset=utf-8" },
    customMetadata: {
      articleId: String(article.article_id).slice(0, 160), sourceKey: String(article.source_key || "").slice(0, 80),
      checksum: String(row.source_checksum || "").slice(0, 64), kind: "rss-original",
      imageCount: String(images.length), cachedImageCount: String(images.length),
    },
  });
  const readback = await env.ARTIFACTS.get(row.original_object_key);
  if (!readback) throw new Error("article_artifact_media_readback_missing");
  const checked = JSON.parse(await readback.text());
  if (!Array.isArray(checked.images) || checked.images.length !== images.length || checked.mediaImport?.readbackVerified !== true) {
    throw new Error("article_artifact_media_readback_failed");
  }
  return { attached: true, count: images.length, readback: true };
}

function normalize(body, importMode = false) {
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("body_must_be_object");
  const allowed = importMode ? IMPORT_ALLOWED : ALLOWED;
  const unknown = Object.keys(body).filter((k) => !allowed.has(k));
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
    content: importMode ? bounded(body.content, "content", 500000, true) : null,
    media: importMode ? normalizeImportMedia(body.media) : null,
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
  const changed = Number(result.meta?.changes || 0);
  if (changed) await markProfileDirty(env, "rss_library_selected");
  return changed;
}

export async function handleRssLibrarySave(request, env, url) {
  const importMode = url.pathname === "/api/rss/library/import";
  if (!importMode && url.pathname !== "/api/rss/library/save") return null;
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!env.DB || !env.ARTIFACTS) return json({ ok: false, error: "RSS_BINDINGS_MISSING" }, 503);
  const auth = authError(request, env); if (auth) return auth;

  try {
    const normalized = normalize(await request.json(), importMode);
    const identity = await upsertArticle(env, normalized.article);
    const canonicalArticle = { ...normalized.article, article_id: identity.articleId };
    const fetched = importMode
      ? await persistFetchedArticle(env, canonicalArticle, {
          rawText: normalized.content,
          route: "facebook-r2-import",
          resolvedUrl: canonicalArticle.canonical_url,
          coverage: "full",
          truncated: false,
          chars: normalized.content.length,
          extractedTitle: canonicalArticle.title,
        })
      : await fetchThroughCanonicalHandler(env, identity.articleId);
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
    const mediaResult = importMode ? await attachImportedMedia(env, canonicalArticle, row, normalized.media) : { attached: null, count: null, readback: null };
    const selectedApplied = importMode ? 0 : await recordSelected(env, canonicalArticle, normalized.render_id, normalized.context, row.source_checksum);
    const versionCount = await env.DB.prepare("SELECT COUNT(*) AS n FROM rss_article_versions WHERE article_id=? AND source_checksum=?")
      .bind(identity.articleId, row.source_checksum).first();
    return json({
      ok: true,
      durable: true,
      version: importMode ? IMPORT_VERSION : VERSION,
      imported: importMode,
      article_id: identity.articleId,
      article_created: identity.created,
      canonical_url: row.canonical_url,
      source_checksum: row.source_checksum,
      current_version_id: row.current_version_id,
      original_object_key: row.original_object_key,
      r2_readback: true,
      d1_readback: true,
      media_attached: mediaResult.attached,
      media_count: mediaResult.count,
      media_readback: mediaResult.readback,
      logical_version_count: Number(versionCount?.n || 0),
      selected_event_applied: selectedApplied,
      profile_status: importMode ? "unchanged" : "dirty",
      fetch: { chars: fetched.chars ?? null, native_vi: fetched.nativeVi ?? null },
      reader_path: `/rss/article/${encodeURIComponent(identity.articleId)}`,
      audio: "persistent-reader-audio-on-demand",
      translation_status: row.translation_status,
      qa_state: row.qa_state,
    });
  } catch (error) {
    return json({ ok: false, durable: false, version: importMode ? IMPORT_VERSION : VERSION, error: String(error?.message || error).slice(0, 1000) }, 400);
  }
}
