const ITEM_PREFIX = "audio-library/items/";
const QUEUE_PREFIX = "audio-library/rss-reader-queue/";
const MEDIA_PREFIX = "audio-library/media/";
const VOICE = "vi-VN-NamMinhNeural";
const VOICE_RATE = "+3%";
const AUDIO_VERSION = "rss-reader-audio-v2";
const MAX_SCRIPT_CHARS = 180000;
const MEDIA_TICKET_VERSION = "rss-audio-media-v1";
const MEDIA_TICKET_TTL_SECONDS = 4 * 60 * 60;

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
  const timing = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/audio\/timing$/);
  const media = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/audio\/media$/);
  const status = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/audio$/);
  const match = timing || media || status;
  if (!match) return null;
  let articleId;
  try { articleId = decodeURIComponent(match[1]); } catch { return null; }
  return { articleId, kind: timing ? "timing" : media ? "media" : "status" };
}

function normalizeView(value) {
  return value === "original" ? "original" : "vi";
}

async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(String(value || ""));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function hmacHex(secret, value) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(String(secret || "")),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(String(value || "")));
  return [...new Uint8Array(signature)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

function safeEqualHex(a, b) {
  const left = String(a || "");
  const right = String(b || "");
  if (left.length !== right.length || !left.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i++) diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  return diff === 0;
}

async function audioId(articleId, view) {
  const hash = await sha256Hex(`${AUDIO_VERSION}\u0000${articleId}\u0000${view}\u0000${VOICE}\u0000${VOICE_RATE}`);
  return `rss-${hash.slice(0, 32)}`;
}

function itemKey(id) { return `${ITEM_PREFIX}${id}.json`; }
function queueKey(id) { return `${QUEUE_PREFIX}${id}.json`; }
function mediaPrefix(id) { return `${MEDIA_PREFIX}${id}/`; }

function ticketPayload(articleId, view, id, expiresAt) {
  return `${MEDIA_TICKET_VERSION}\u0000${articleId}\u0000${view}\u0000${id}\u0000${expiresAt}`;
}

async function issueMediaTicket(env, articleId, view, id) {
  const secret = String(env.RUNNER3_CORE_TOKEN || "");
  if (!secret) return null;
  const expiresAt = Math.floor(Date.now() / 1000) + MEDIA_TICKET_TTL_SECONDS;
  const signature = await hmacHex(secret, ticketPayload(articleId, view, id, expiresAt));
  return `${expiresAt}.${signature}`;
}

async function verifyMediaTicket(env, ticket, articleId, view, id) {
  const secret = String(env.RUNNER3_CORE_TOKEN || "");
  const value = String(ticket || "");
  if (!secret || !value) return false;
  const dot = value.indexOf(".");
  if (dot <= 0) return false;
  const expiresAt = Number(value.slice(0, dot));
  const signature = value.slice(dot + 1);
  const now = Math.floor(Date.now() / 1000);
  if (!Number.isInteger(expiresAt) || expiresAt < now || expiresAt > now + MEDIA_TICKET_TTL_SECONDS + 60) return false;
  const expected = await hmacHex(secret, ticketPayload(articleId, view, id, expiresAt));
  return safeEqualHex(signature, expected);
}

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
      audioVersion: AUDIO_VERSION,
      voice: VOICE,
      voiceRate: VOICE_RATE,
      durationSeconds: null,
      timingAvailable: false,
      error: null,
    };
  }
  return {
    ok: true,
    status: String(item.status || "missing"),
    view,
    audioVersion: AUDIO_VERSION,
    voice: VOICE,
    voiceRate: VOICE_RATE,
    durationSeconds: Number.isFinite(Number(item.durationSeconds)) ? Number(item.durationSeconds) : null,
    timingAvailable: Boolean(item.timingUrl),
    updatedAt: item.updatedAt || null,
    error: item.status === "error" ? String(item.error || "Không thể tạo audio").slice(0, 180) : null,
  };
}

async function publicStateWithMedia(env, item, articleId, view, id) {
  const state = publicState(item, view);
  if (item?.status !== "ready") return state;
  const ticket = await issueMediaTicket(env, articleId, view, id);
  if (!ticket) return state;
  state.mediaUrl = `/reader/rss/articles/${encodeURIComponent(articleId)}/audio/media?view=${encodeURIComponent(view)}&ticket=${encodeURIComponent(ticket)}`;
  state.mediaTicketTtlSeconds = MEDIA_TICKET_TTL_SECONDS;
  return state;
}

async function readPostView(request, fallback) {
  if (request.method !== "POST") return fallback;
  const body = await request.clone().json().catch(() => ({}));
  return normalizeView(body?.view || fallback);
}

function normalizeSpeechText(value) {
  let source = String(value || "").normalize("NFC")
    .replace(/\r/g, "")
    .replace(/\u00a0/g, " ")
    .replace(/[\u200b-\u200d\u2060\ufeff]/g, "")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\((?:https?:\/\/|\/)[^)]*\)/g, "$1")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/^\s{0,3}#{1,6}\s+(.+)$/gm, "$1.")
    .replace(/^\s*>\s?/gm, "")
    .replace(/^\s*[-*•]\s+/gm, "• ")
    .replace(/^\s*(\d+)[.)]\s+/gm, "$1. ")
    .replace(/`{1,3}([^`]+)`{1,3}/g, "$1")
    .replace(/[~*_]{1,3}/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  if (!source) return "";
  const paragraphs = source.split(/\n\s*\n+/).map((part) => {
    let text = String(part || "")
      .replace(/\n+/g, " ")
      .replace(/\s*•\s*/g, "; ")
      .replace(/[ \t]{2,}/g, " ")
      .replace(/\s+([,.;:!?…])/g, "$1")
      .replace(/([,.;:!?…])(?=[^\s”’')\]}])/g, "$1 ")
      .trim();
    if (text && !/[.!?…:;”’')\]}]$/.test(text)) text += ".";
    return text;
  }).filter(Boolean);
  return paragraphs.join("\n\n");
}

function parseByteRange(header, size) {
  const value = String(header || "").trim();
  if (!value) return null;
  const match = value.match(/^bytes=(\d*)-(\d*)$/i);
  if (!match || (!match[1] && !match[2])) return { invalid: true };
  if (!match[1]) {
    const suffix = Number(match[2]);
    if (!Number.isInteger(suffix) || suffix <= 0) return { invalid: true };
    const length = Math.min(size, suffix);
    return { start: size - length, end: size - 1, length };
  }
  const start = Number(match[1]);
  const requestedEnd = match[2] ? Number(match[2]) : size - 1;
  if (!Number.isInteger(start) || !Number.isInteger(requestedEnd) || start < 0 || start >= size || requestedEnd < start) {
    return { invalid: true };
  }
  const end = Math.min(size - 1, requestedEnd);
  return { start, end, length: end - start + 1 };
}

async function serveMedia(request, env, prefix) {
  const mediaKey = `${prefix}episode.mp3`;
  const head = await env.AUDIO_MEDIA.head(mediaKey);
  if (!head) return json({ ok: false, error: "AUDIO_FILE_MISSING" }, 404);
  const size = Number(head.size || 0);
  const headers = new Headers();
  headers.set("content-type", "audio/mpeg");
  headers.set("cache-control", "private, no-store");
  headers.set("accept-ranges", "bytes");
  headers.set("x-content-type-options", "nosniff");
  headers.set("content-disposition", "inline");
  if (head.etag) headers.set("etag", head.etag);
  if (request.method === "HEAD") {
    if (size) headers.set("content-length", String(size));
    return new Response(null, { status: 200, headers });
  }

  const range = parseByteRange(request.headers.get("range"), size);
  if (range?.invalid) {
    headers.set("content-range", `bytes */${size}`);
    return new Response(null, { status: 416, headers });
  }
  if (range) {
    const object = await env.AUDIO_MEDIA.get(mediaKey, { range: { offset: range.start, length: range.length } });
    if (!object) return json({ ok: false, error: "AUDIO_FILE_MISSING" }, 404);
    headers.set("content-range", `bytes ${range.start}-${range.end}/${size}`);
    headers.set("content-length", String(range.length));
    return new Response(object.body, { status: 206, headers });
  }

  const object = await env.AUDIO_MEDIA.get(mediaKey);
  if (!object) return json({ ok: false, error: "AUDIO_FILE_MISSING" }, 404);
  if (size) headers.set("content-length", String(size));
  return new Response(object.body, { status: 200, headers });
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
  const id = await audioId(route.articleId, view);
  const key = itemKey(id);
  const prefix = mediaPrefix(id);
  const existing = await getJson(env.AUDIO_MEDIA, key);

  let auth = null;
  const ticketAuthorized = route.kind === "media"
    ? await verifyMediaTicket(env, url.searchParams.get("ticket"), route.articleId, view, id)
    : false;
  if (!ticketAuthorized) {
    auth = await helpers.authorize(route.articleId);
    if (!auth?.ok) return auth?.response || json({ ok: false, error: "UNAUTHORIZED" }, 401);
  }

  if (route.kind === "media") {
    if (request.method !== "GET" && request.method !== "HEAD") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
    if (!existing || existing.status !== "ready") return json({ ok: false, error: "AUDIO_NOT_READY" }, 409);
    return serveMedia(request, env, prefix);
  }

  if (route.kind === "timing") {
    if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
    if (!existing || existing.status !== "ready") return json({ ok: false, error: "AUDIO_NOT_READY" }, 409);
    const timing = await getJson(env.AUDIO_MEDIA, `${prefix}timing.json`);
    if (!timing) return json({ ok: false, error: "AUDIO_TIMING_MISSING" }, 404);
    return json(timing);
  }

  if (request.method === "GET") return json(await publicStateWithMedia(env, existing, route.articleId, view, id));
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);

  const clean = await helpers.cleanView(route.articleId, view);
  if (!clean?.ok) return clean?.response || json({ ok: false, error: "ARTICLE_AUDIO_SOURCE_FAILED" }, 502);

  const payload = clean.payload || {};
  const article = payload.article || auth?.payload?.article || {};
  const script = normalizeSpeechText(payload.artifact?.body || "");
  if (script.length < 80) return json({ ok: false, error: "ARTICLE_AUDIO_TEXT_TOO_SHORT" }, 422);
  if (script.length > MAX_SCRIPT_CHARS) return json({ ok: false, error: "ARTICLE_AUDIO_TEXT_TOO_LONG" }, 413);

  const textSha256 = await sha256Hex(script);
  if (existing && existing.textSha256 === textSha256 && existing.voice === VOICE && existing.voiceRate === VOICE_RATE && existing.audioVersion === AUDIO_VERSION) {
    if (["pending", "processing", "ready"].includes(existing.status)) {
      return json(await publicStateWithMedia(env, existing, route.articleId, view, id));
    }
  }

  const now = new Date().toISOString();
  if (existing?.status === "ready") {
    await Promise.all([
      env.AUDIO_MEDIA.delete(`${prefix}episode.mp3`),
      env.AUDIO_MEDIA.delete(`${prefix}timing.json`),
    ]);
  }
  await env.AUDIO_MEDIA.put(`${prefix}script.txt`, script, {
    httpMetadata: { contentType: "text/plain; charset=utf-8" },
    customMetadata: { scope: "rss-reader-audio", voice: VOICE, version: AUDIO_VERSION },
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
    timingUrl: null,
    mediaPrefix: prefix,
    audioVersion: AUDIO_VERSION,
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
    audioVersion: AUDIO_VERSION,
    voice: VOICE,
    voiceRate: VOICE_RATE,
    textSha256,
    createdAt: now,
  };
  await putJson(env.AUDIO_MEDIA, key, item);
  await putJson(env.AUDIO_MEDIA, queueKey(id), queue);
  return json(publicState(item, view), 202);
}
