import { handleRssReader } from "./src/rss-reader.js";
import { handleRssReaderPlus } from "./src/rss-reader-plus.js";
import { handleRssReaderAudio } from "./src/rss-reader-audio.js";
import { handleRssReaderLearning, recordReaderStateLearning, reconcileLibraryLearning } from "./src/rss-reader-learning.js";
import { preserveArticleImages, serveCachedReaderImage } from "./src/rss-image-enrich.js";

const VERSION = "rss-reader-read-fast-v3-isolated-stream";
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
    SELECT a.article_id, a.canonical_url, a.source_key, a.source_name, a.source_language,
           a.title, a.published_at, a.fetch_status, a.translation_status, a.qa_state,
           a.last_error, a.updated_at, a.original_object_key, a.vi_object_key,
           COALESCE(s.lifecycle, 'active') AS lifecycle,
           COALESCE(s.featured, 0) AS featured,
           s.category, s.preference, s.last_opened_at
    FROM rss_articles a
    LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
    WHERE a.article_id = ?
    LIMIT 1
  `).bind(articleId).first();
}

function streamArtifactEnvelope(article, kind, nativeVi, object) {
  if (!object?.body || typeof object.body.getReader !== "function") return null;
  const encoder = new TextEncoder();
  const prefix = `{"ok":true,"article":${JSON.stringify(cleanRow(article))},"view":${JSON.stringify(kind)},"nativeVi":${nativeVi ? "true" : "false"},"artifact":`;
  const suffix = "}";
  const source = object.body;
  const body = new ReadableStream({
    async start(controller) {
      const reader = source.getReader();
      try {
        controller.enqueue(encoder.encode(prefix));
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (value?.byteLength) controller.enqueue(value);
        }
        controller.enqueue(encoder.encode(suffix));
        controller.close();
      } catch (error) {
        controller.error(error);
      } finally {
        try { reader.releaseLock(); } catch {}
      }
    },
  });
  return new Response(body, {
    status: 200,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "private, no-store",
      "x-r3-rss-read-fastpath": VERSION,
      "x-r3-rss-read-route": kind,
      "x-r3-rss-artifact-stream": "1",
    },
  });
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

  const categoriesRoute = url.pathname === "/reader/rss/categories";
  const neighborMatch = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/neighbors$/);
  const articleMatch = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)(?:\/(vi|original))?$/);
  if (!categoriesRoute && !neighborMatch && !articleMatch) return null;

  if (!env.DB) return json({ ok: false, error: "D1_NOT_BOUND" }, 503, "binding");
  if (!(await authorized(request))) return json({ ok: false, error: "UNAUTHORIZED" }, 401, "auth");

  if (categoriesRoute) {
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

  if (neighborMatch) {
    let neighborId;
    try { neighborId = decodeURIComponent(neighborMatch[1]); }
    catch { return json({ ok: false, error: "INVALID_ARTICLE_ID" }, 400, "neighbors"); }
    try {
      const current = await env.DB.prepare(`
        SELECT a.article_id, a.published_at
        FROM rss_articles a
        LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
        WHERE a.article_id = ? AND COALESCE(s.lifecycle, 'active') != 'deleted'
        LIMIT 1
      `).bind(neighborId).first();
      if (!current) return json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404, "neighbors");
      const publishedAt = String(current.published_at || "");
      const [previous, next] = await env.DB.batch([
        env.DB.prepare(`
          SELECT a.article_id, a.title
          FROM rss_articles a
          LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
          WHERE COALESCE(s.lifecycle, 'active') != 'deleted'
            AND (a.published_at > ? OR (a.published_at = ? AND a.article_id > ?))
          ORDER BY a.published_at ASC, a.article_id ASC
          LIMIT 1
        `).bind(publishedAt, publishedAt, neighborId),
        env.DB.prepare(`
          SELECT a.article_id, a.title
          FROM rss_articles a
          LEFT JOIN rss_reader_state s ON s.article_id = a.article_id
          WHERE COALESCE(s.lifecycle, 'active') != 'deleted'
            AND (a.published_at < ? OR (a.published_at = ? AND a.article_id < ?))
          ORDER BY a.published_at DESC, a.article_id DESC
          LIMIT 1
        `).bind(publishedAt, publishedAt, neighborId),
      ]);
      return json({
        ok: true,
        previous: previous?.results?.[0] || null,
        next: next?.results?.[0] || null,
      }, 200, "neighbors");
    } catch (error) {
      return json({ ok: false, error: "NEIGHBORS_READ_FAILED", detail: String(error?.message || error).slice(0, 300) }, 500, "neighbors");
    }
  }

  const match = articleMatch;
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
    if (ctx?.waitUntil) ctx.waitUntil(markOpened(env, articleId).catch(() => {}));
    const streamed = streamArtifactEnvelope(article, kind, nativeVi, object);
    if (!streamed) return json({ ok: false, error: "ARTIFACT_STREAM_UNAVAILABLE" }, 500, kind);
    return streamed;
  } catch (error) {
    return json({ ok: false, error: "ARTICLE_READ_FAILED", detail: String(error?.message || error).slice(0, 300) }, 500, "article");
  }
}


function internalReaderRequest(request, articleId, suffix = "") {
  const target = new URL(request.url);
  target.pathname = `/reader/rss/articles/${encodeURIComponent(articleId)}${suffix}`;
  target.search = "";
  const headers = new Headers();
  const authorization = request.headers.get("authorization");
  if (authorization) headers.set("authorization", authorization);
  return { target, request: new Request(target.toString(), { method: "GET", headers }) };
}

async function authorizeReaderArticle(request, env, ctx, articleId) {
  const internal = internalReaderRequest(request, articleId);
  const response = await routeRead(internal.request, env, internal.target, ctx);
  if (!response?.ok) return { ok: false, response: response || json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404, "authorize") };
  const payload = await response.json().catch(() => null);
  if (!payload?.article) return { ok: false, response: json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404, "authorize") };
  return { ok: true, payload };
}

async function cleanReaderArticleView(request, env, ctx, articleId, view) {
  const internal = internalReaderRequest(request, articleId, `/${view === "original" ? "original" : "vi"}`);
  const response = await routeRead(internal.request, env, internal.target, ctx);
  if (!response?.ok) return { ok: false, response: response || json({ ok: false, error: "ARTICLE_AUDIO_SOURCE_FAILED" }, 502, "audio-source") };
  const payload = await response.json().catch(() => null);
  if (!payload?.artifact) return { ok: false, response: json({ ok: false, error: "READER_PAYLOAD_INVALID" }, 500, "audio-source") };
  return { ok: true, payload };
}

function stateArticleId(request, url) {
  if (request.method !== "POST") return "";
  const match = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/state$/);
  if (!match) return "";
  try { return decodeURIComponent(match[1]); } catch { return ""; }
}

function shouldPreserveImages(body) {
  if (!body || typeof body !== "object") return false;
  return body.preference === "like" || body.featured === true || body.lifecycle === "archived";
}

async function routeReaderExtended(request, env, url, ctx) {
  if (!url.pathname.startsWith("/reader/rss/")) return null;

  const plusResponse = await handleRssReaderPlus(request, env, url);
  if (plusResponse) {
    if (request.method === "GET" && url.pathname === "/reader/rss/library/v2" && plusResponse.ok) {
      const task = reconcileLibraryLearning(plusResponse.clone(), env).catch((error) => {
        console.warn("rss learning library reconcile failed", String(error?.message || error));
      });
      if (ctx?.waitUntil) ctx.waitUntil(task); else await task;
    }
    return plusResponse;
  }

  const learningResponse = await handleRssReaderLearning(
    request,
    env,
    url,
    (articleId) => authorizeReaderArticle(request, env, ctx, articleId),
  );
  if (learningResponse) return learningResponse;

  const audioResponse = await handleRssReaderAudio(request, env, url, {
    authorize: (articleId) => authorizeReaderArticle(request, env, ctx, articleId),
    cleanView: (articleId, view) => cleanReaderArticleView(request, env, ctx, articleId, view),
  });
  if (audioResponse) return audioResponse;

  const stateId = stateArticleId(request, url);
  const stateClone = stateId ? request.clone() : null;
  const baseResponse = await handleRssReader(request, env, url);
  if (!baseResponse) return null;

  if (stateId && baseResponse.ok && stateClone) {
    const body = await stateClone.json().catch(() => null);
    const tasks = [recordReaderStateLearning(env, stateId, body).catch((error) => {
      console.warn("rss reader learning state failed", stateId, String(error?.message || error));
    })];
    if (shouldPreserveImages(body)) {
      tasks.push(preserveArticleImages(env, stateId).catch((error) => {
        console.warn("rss image preserve failed", stateId, String(error?.message || error));
      }));
    }
    const task = Promise.all(tasks);
    if (ctx?.waitUntil) ctx.waitUntil(task); else await task;
  }
  return baseResponse;
}

async function routeRssPage(request, env, url) {
  if (request.method === "GET" && url.pathname === "/rss/library") {
    return handleRssReaderPlus(request, env, url);
  }
  if (request.method === "GET" && url.pathname.startsWith("/rss/media/")) {
    return serveCachedReaderImage(request, env, url);
  }
  return null;
}

function isDeliveryPath(pathname) {
  return pathname === "/delivery-links" ||
    pathname === "/delivery-permalinks" ||
    pathname === "/delivery-permalinks/revoke" ||
    pathname.startsWith("/delivery/") ||
    pathname.startsWith("/delivery-permanent/");
}

async function routeDelivery(request, env, url) {
  if (!isDeliveryPath(url.pathname)) return null;
  const { handleDelivery } = await import("./src/delivery.js");
  return handleDelivery(request, env, url);
}

async function loadFallbackApp() {
  const module = await import("./rss-article-fast-entry.js");
  return module.default;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const deliveryResponse = await routeDelivery(request, env, url);
    if (deliveryResponse) return deliveryResponse;
    const pageResponse = await routeRssPage(request, env, url);
    if (pageResponse) return pageResponse;
    const response = await routeRead(request, env, url, ctx);
    if (response) return response;
    const extendedResponse = await routeReaderExtended(request, env, url, ctx);
    if (extendedResponse) return extendedResponse;
    const app = await loadFallbackApp();
    return app.fetch(request, env, ctx);
  },
  async scheduled(controller, env, ctx) {
    const app = await loadFallbackApp();
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
