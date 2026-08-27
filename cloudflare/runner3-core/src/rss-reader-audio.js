const ITEM_PREFIX = "audio-library/items/";
const QUEUE_PREFIX = "audio-library/rss-reader-queue/";
const MEDIA_PREFIX = "audio-library/media/";
const VOICE = "vi-VN-NamMinhNeural";
const VOICE_RATE = "+3%";
const MAX_SCRIPT_CHARS = 180000;

function json(value, status = 200) {
  return Response.json(value, {
    status,
    headers: {
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
      "referrer-policy": "no-referrer",
    },
  });
}

function parseRoute(url) {
  const media = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/audio\/media$/);
  const status = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/audio$/);
  const match = media || status;
  if (!match) return null;
  let articleId;
  try { articleId = decodeURIComponent(match[1]); } catch { return null; }
  return { articleId, media: Boolean(media) };
}

function normalizeView(value) {
  return value === "original" ? "original" : "vi";
}

async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(String(value || ""));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function audioId(articleId, view) {
  const hash = await sha256Hex(`${articleId}\u0000${view}\u0000${VOICE}\u0000${VOICE_RATE}`);
  return `rss-${hash.slice(0, 32)}`;
}

function itemKey(id) { return `${ITEM_PREFIX}${id}.json`; }
function queueKey(id) { return `${QUEUE_PREFIX}${id}.json`; }
function mediaPrefix(id) { return `${MEDIA_PREFIX}${id}/`; }

async function getJson(bucket, key) {
  const object = await bucket.get(key);
  if (!object) return null;
  try { return JSON.parse(await object.text()); } catch { return null; }
}

async function putJson(bucket, key, value) {
  await bucket.put(key, JSON.stringify(value), {
    httpMetadata: { contentType: "application/json; charset=utf-8" },
    customMetadata: { scope: "rss-reader-audio" },
  });
}

function publicState(item, view) {
  if (!item) {
    return {
      ok: true,
      status: "missing",
      view,
      voice: VOICE,
      voiceRate: VOICE_RATE,
      durationSeconds: null,
      error: null,
    };
  }
  return {
    ok: true,
    status: String(item.status || "missing"),
    view,
    voice: VOICE,
    voiceRate: VOICE_RATE,
    durationSeconds: Number.isFinite(Number(item.durationSeconds)) ? Number(item.durationSeconds) : null,
    updatedAt: item.updatedAt || null,
    error: item.status === "error" ? String(item.error || "Không thể tạo audio").slice(0, 180) : null,
  };
}

async function readPostView(request, fallback) {
  if (request.method !== "POST") return fallback;
  const body = await request.clone().json().catch(() => ({}));
  return normalizeView(body?.view || fallback);
}

function safeText(value) {
  return String(value || "")
    .replace(/\r/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export async function handleRssReaderAudio(request, env, url, helpers) {
  const route = parseRoute(url);
  if (!route) return null;
  if (!env.AUDIO_MEDIA) return json({ ok: false, error: "AUDIO_MEDIA_NOT_BOUND" }, 503);
  if (!helpers || typeof helpers.authorize !== "function" || typeof helpers.cleanView !== "function") {
    return json({ ok: false, error: "RSS_AUDIO_HELPERS_MISSING" }, 500);
  }

  const fallbackView = normalizeView(url.searchParams.get("view") || "vi");
  const view = await readPostView(request, fallbackView);
  const auth = await helpers.authorize(route.articleId);
  if (!auth?.ok) return auth?.response || json({ ok: false, error: "UNAUTHORIZED" }, 401);

  const id = await audioId(route.articleId, view);
  const key = itemKey(id);
  const prefix = mediaPrefix(id);
  const existing = await getJson(env.AUDIO_MEDIA, key);

  if (route.media) {
    if (request.method !== "GET" && request.method !== "HEAD") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
    if (!existing || existing.status !== "ready") return json({ ok: false, error: "AUDIO_NOT_READY" }, 409);
    const object = request.method === "HEAD"
      ? await env.AUDIO_MEDIA.head(`${prefix}episode.mp3`)
      : await env.AUDIO_MEDIA.get(`${prefix}episode.mp3`);
    if (!object) return json({ ok: false, error: "AUDIO_FILE_MISSING" }, 404);
    const headers = new Headers();
    headers.set("content-type", "audio/mpeg");
    headers.set("cache-control", "private, no-store");
    headers.set("accept-ranges", "none");
    headers.set("x-content-type-options", "nosniff");
    if (object.size) headers.set("content-length", String(object.size));
    if (request.method === "HEAD") return new Response(null, { status: 200, headers });
    return new Response(object.body, { status: 200, headers });
  }

  if (request.method === "GET") return json(publicState(existing, view));
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);

  const clean = await helpers.cleanView(route.articleId, view);
  if (!clean?.ok) return clean?.response || json({ ok: false, error: "ARTICLE_AUDIO_SOURCE_FAILED" }, 502);

  const payload = clean.payload || {};
  const article = payload.article || auth.payload?.article || {};
  const script = safeText(payload.artifact?.body || "");
  if (script.length < 80) return json({ ok: false, error: "ARTICLE_AUDIO_TEXT_TOO_SHORT" }, 422);
  if (script.length > MAX_SCRIPT_CHARS) return json({ ok: false, error: "ARTICLE_AUDIO_TEXT_TOO_LONG" }, 413);

  const textSha256 = await sha256Hex(script);
  if (existing && existing.textSha256 === textSha256 && existing.voice === VOICE && existing.voiceRate === VOICE_RATE) {
    if (["pending", "processing", "ready"].includes(existing.status)) return json(publicState(existing, view));
  }

  const now = new Date().toISOString();
  if (existing?.status === "ready") await env.AUDIO_MEDIA.delete(`${prefix}episode.mp3`);
  await env.AUDIO_MEDIA.put(`${prefix}script.txt`, script, {
    httpMetadata: { contentType: "text/plain; charset=utf-8" },
    customMetadata: { scope: "rss-reader-audio", voice: VOICE },
  });

  const item = {
    id,
    kind: "rss-reader",
    articleId: route.articleId,
    view,
    sourceUrl: String(article.canonical_url || ""),
    sourceLabel: String(article.source_name || article.source_key || "RSS").slice(0, 120),
    title: String(article.title || "RSS article").slice(0, 240),
    status: "pending",
    createdAt: existing?.createdAt || now,
    updatedAt: now,
    expiresAt: null,
    pinned: true,
    durationSeconds: null,
    progressSeconds: 0,
    audioUrl: null,
    transcriptUrl: null,
    mediaPrefix: prefix,
    voice: VOICE,
    voiceRate: VOICE_RATE,
    textSha256,
    error: null,
  };
  const queue = {
    id,
    kind: "rss-reader",
    articleId: route.articleId,
    view,
    itemKey: key,
    scriptKey: `${prefix}script.txt`,
    mediaPrefix: prefix,
    voice: VOICE,
    voiceRate: VOICE_RATE,
    textSha256,
    createdAt: now,
  };
  await putJson(env.AUDIO_MEDIA, key, item);
  await putJson(env.AUDIO_MEDIA, queueKey(id), queue);
  return json(publicState(item, view), 202);
}
