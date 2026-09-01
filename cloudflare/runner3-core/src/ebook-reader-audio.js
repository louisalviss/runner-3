const ITEM_PREFIX = "audio-library/items/";
const QUEUE_PREFIX = "audio-library/ebook-reader-queue/";
const MEDIA_PREFIX = "audio-library/media/";
const VOICE = "vi-VN-NamMinhNeural";
const VOICE_RATE = "+3%";
const AUDIO_VERSION = "ebook-reader-audio-v1";
const MAX_SCRIPT_CHARS = 180000;
const MAX_AUDIO_BYTES = 80 * 1024 * 1024;
const MEDIA_TICKET_VERSION = "ebook-audio-media-v1";
const MEDIA_TICKET_TTL_SECONDS = 4 * 60 * 60;
const PROCESSING_LEASE_MS = 10 * 60 * 1000;
const CLAIM_SCAN_LIMIT = 8;

function json(value, status = 200) {
  return Response.json(value, {
    status,
    headers: {
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
      "referrer-policy": "no-referrer",
      "x-robots-tag": "noindex, nofollow, noarchive, nosnippet, noimageindex",
    },
  });
}

function parsePublicRoute(url) {
  if (url.pathname === "/artifact-library/audio") return { kind: "status" };
  if (url.pathname === "/artifact-library/audio/media") return { kind: "media" };
  if (url.pathname === "/artifact-library/audio/timing") return { kind: "timing" };
  return null;
}

function parseInternalRoute(url) {
  const base = "/api/internal/ebook-reader-audio/";
  if (!url.pathname.startsWith(base)) return null;
  const kind = url.pathname.slice(base.length);
  return ["job", "media", "timing", "complete", "fail"].includes(kind) ? kind : null;
}

async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(String(value || ""));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function hmacHex(secret, value) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", encoder.encode(String(secret || "")), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(String(value || "")));
  return [...new Uint8Array(signature)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

function safeEqual(a, b) {
  const left = String(a || "");
  const right = String(b || "");
  if (!left || left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i++) diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  return diff === 0;
}

function internalAuthorized(request, env) {
  const expected = String(env.RUNNER3_CORE_TOKEN || "");
  const header = String(request.headers.get("authorization") || "");
  return Boolean(expected) && header.startsWith("Bearer ") && safeEqual(header.slice(7), expected);
}

function normalizeBookKey(value) {
  const key = String(value || "").trim();
  if (!key || key.length > 1200 || key.includes("\0")) return "";
  return key;
}

function validFinalEpubKey(key) {
  const value = String(key || "").toLowerCase();
  return value.startsWith("core/ebook/") && value.includes("/final/") && value.endsWith(".epub");
}

function normalizeSpeechText(value) {
  return String(value || "")
    .normalize("NFC")
    .replace(/\r/g, "")
    .replace(/\u00a0/g, " ")
    .replace(/[\u200b-\u200d\u2060\ufeff]/g, "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .split(/\n\s*\n+/)
    .map((part) => String(part || "").replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .map((part) => /[.!?…:;”’')\]}]$/.test(part) ? part : `${part}.`)
    .join("\n\n")
    .trim();
}

async function audioId(bookKey, textSha256) {
  const digest = await sha256Hex(`${AUDIO_VERSION}\u0000${bookKey}\u0000${textSha256}\u0000${VOICE}\u0000${VOICE_RATE}`);
  return `ebook-${digest.slice(0, 32)}`;
}

function idValid(id) { return /^ebook-[a-f0-9]{32}$/.test(String(id || "")); }
function itemKey(id) { return `${ITEM_PREFIX}${id}.json`; }
function queueKey(id) { return `${QUEUE_PREFIX}${id}.json`; }
function mediaPrefix(id) { return `${MEDIA_PREFIX}${id}/`; }

function processingLeaseFresh(item, nowMs = Date.now()) {
  const leaseAt = Date.parse(String(item?.processingAt || item?.updatedAt || ""));
  return Number.isFinite(leaseAt) && nowMs - leaseAt < PROCESSING_LEASE_MS;
}

async function getJson(bucket, key) {
  const object = await bucket.get(key);
  if (!object) return null;
  try { return JSON.parse(await object.text()); } catch { return null; }
}

async function putJson(bucket, key, value, scope = "ebook-reader-audio") {
  await bucket.put(key, JSON.stringify(value), {
    httpMetadata: { contentType: "application/json; charset=utf-8" },
    customMetadata: { scope },
  });
}

function ticketPayload(bookKey, id, expiresAt) {
  return `${MEDIA_TICKET_VERSION}\u0000${bookKey}\u0000${id}\u0000${expiresAt}`;
}

async function issueMediaTicket(env, bookKey, id) {
  const secret = String(env.RUNNER3_CORE_TOKEN || "");
  if (!secret) return null;
  const expiresAt = Math.floor(Date.now() / 1000) + MEDIA_TICKET_TTL_SECONDS;
  const signature = await hmacHex(secret, ticketPayload(bookKey, id, expiresAt));
  return `${expiresAt}.${signature}`;
}

async function verifyMediaTicket(env, ticket, bookKey, id) {
  const secret = String(env.RUNNER3_CORE_TOKEN || "");
  const value = String(ticket || "");
  if (!secret || !value) return false;
  const dot = value.indexOf(".");
  if (dot <= 0) return false;
  const expiresAt = Number(value.slice(0, dot));
  const signature = value.slice(dot + 1);
  const now = Math.floor(Date.now() / 1000);
  if (!Number.isInteger(expiresAt) || expiresAt < now || expiresAt > now + MEDIA_TICKET_TTL_SECONDS + 60) return false;
  return safeEqual(signature, await hmacHex(secret, ticketPayload(bookKey, id, expiresAt)));
}

function publicState(item) {
  if (!item) return { ok: true, status: "missing", audioVersion: AUDIO_VERSION, voice: VOICE, voiceRate: VOICE_RATE, durationSeconds: null, timingAvailable: false, error: null };
  return {
    ok: true,
    id: item.id,
    status: String(item.status || "missing"),
    bookKey: item.bookKey,
    chapterTitle: item.chapterTitle || null,
    audioVersion: item.audioVersion || AUDIO_VERSION,
    voice: item.voice || VOICE,
    voiceRate: item.voiceRate || VOICE_RATE,
    durationSeconds: Number.isFinite(Number(item.durationSeconds)) ? Number(item.durationSeconds) : null,
    timingAvailable: Boolean(item.timingUrl),
    updatedAt: item.updatedAt || null,
    error: item.status === "error" ? String(item.error || "Không thể tạo audio").slice(0, 180) : null,
  };
}

async function publicStateWithMedia(env, item) {
  const state = publicState(item);
  if (item?.status !== "ready") return state;
  const ticket = await issueMediaTicket(env, item.bookKey, item.id);
  if (!ticket) return state;
  const q = `id=${encodeURIComponent(item.id)}&bookKey=${encodeURIComponent(item.bookKey)}&ticket=${encodeURIComponent(ticket)}`;
  state.mediaUrl = `/artifact-library/audio/media?${q}`;
  state.timingUrl = `/artifact-library/audio/timing?${q}`;
  state.mediaTicketTtlSeconds = MEDIA_TICKET_TTL_SECONDS;
  return state;
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
  if (!Number.isInteger(start) || !Number.isInteger(requestedEnd) || start < 0 || start >= size || requestedEnd < start) return { invalid: true };
  const end = Math.min(size - 1, requestedEnd);
  return { start, end, length: end - start + 1 };
}

async function serveMedia(request, env, prefix) {
  const mediaKey = `${prefix}episode.mp3`;
  const head = await env.AUDIO_MEDIA.head(mediaKey);
  if (!head) return json({ ok: false, error: "AUDIO_FILE_MISSING" }, 404);
  const size = Number(head.size || 0);
  const headers = new Headers({ "content-type": "audio/mpeg", "cache-control": "private, no-store", "accept-ranges": "bytes", "x-content-type-options": "nosniff", "content-disposition": "inline" });
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

async function readExisting(env, id, bookKey) {
  if (!idValid(id) || !bookKey) return null;
  const item = await getJson(env.AUDIO_MEDIA, itemKey(id));
  if (!item || item.kind !== "ebook-reader" || item.bookKey !== bookKey) return null;
  return item;
}

async function nextInternalJob(env) {
  const listing = await env.AUDIO_MEDIA.list({ prefix: QUEUE_PREFIX, limit: CLAIM_SCAN_LIMIT });
  const objects = [...(listing.objects || [])].sort((a, b) => String(a.uploaded || "").localeCompare(String(b.uploaded || "")));
  for (const object of objects) {
    const queue = await getJson(env.AUDIO_MEDIA, object.key);
    if (!queue || queue.kind !== "ebook-reader" || !idValid(queue.id)) {
      await env.AUDIO_MEDIA.delete(object.key);
      continue;
    }
    const item = await getJson(env.AUDIO_MEDIA, queue.itemKey || itemKey(queue.id));
    if (!item || item.kind !== "ebook-reader" || item.status === "ready" || item.status === "error") {
      await env.AUDIO_MEDIA.delete(object.key);
      continue;
    }
    if (item.status === "processing" && processingLeaseFresh(item)) {
      // Claimed jobs must not remain in the pending queue. Clean legacy entries
      // incrementally so one poll never burns through the whole R2 listing.
      await env.AUDIO_MEDIA.delete(object.key);
      continue;
    }
    const scriptObject = await env.AUDIO_MEDIA.get(queue.scriptKey || `${mediaPrefix(queue.id)}script.txt`);
    if (!scriptObject) {
      item.status = "error";
      item.error = "Audio script missing";
      item.updatedAt = new Date().toISOString();
      await putJson(env.AUDIO_MEDIA, itemKey(queue.id), item);
      await env.AUDIO_MEDIA.delete(object.key);
      continue;
    }
    const script = await scriptObject.text();
    const now = new Date().toISOString();
    item.status = "processing";
    item.error = null;
    item.processingAt = now;
    item.updatedAt = now;
    await putJson(env.AUDIO_MEDIA, itemKey(queue.id), item);
    await env.AUDIO_MEDIA.delete(object.key);
    return { ...queue, script };
  }
  return null;
}

async function handleInternal(request, env, url, kind) {
  if (!internalAuthorized(request, env)) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  if (!env.AUDIO_MEDIA) return json({ ok: false, error: "AUDIO_MEDIA_NOT_BOUND" }, 503);

  if (kind === "job") {
    if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
    const job = await nextInternalJob(env);
    return json({ ok: true, job });
  }

  const id = String(url.searchParams.get("id") || "");
  if ((kind === "media" || kind === "timing") && !idValid(id)) return json({ ok: false, error: "INVALID_AUDIO_ID" }, 400);

  if (kind === "media") {
    if (request.method !== "PUT") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
    const declared = Number(request.headers.get("content-length") || 0);
    if (declared > MAX_AUDIO_BYTES) return json({ ok: false, error: "AUDIO_TOO_LARGE" }, 413);
    const item = await getJson(env.AUDIO_MEDIA, itemKey(id));
    if (!item || item.kind !== "ebook-reader") return json({ ok: false, error: "AUDIO_ITEM_NOT_FOUND" }, 404);
    const body = await request.arrayBuffer();
    if (!body.byteLength || body.byteLength > MAX_AUDIO_BYTES) return json({ ok: false, error: "INVALID_AUDIO_BODY" }, 413);
    await env.AUDIO_MEDIA.put(`${mediaPrefix(id)}episode.mp3`, body, { httpMetadata: { contentType: "audio/mpeg" }, customMetadata: { scope: "ebook-reader-audio", voice: VOICE, version: AUDIO_VERSION } });
    return json({ ok: true, id, bytes: body.byteLength });
  }

  if (kind === "timing") {
    if (request.method !== "PUT") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
    const item = await getJson(env.AUDIO_MEDIA, itemKey(id));
    if (!item || item.kind !== "ebook-reader") return json({ ok: false, error: "AUDIO_ITEM_NOT_FOUND" }, 404);
    const timing = await request.json().catch(() => null);
    if (!timing || timing.id !== id || !Array.isArray(timing.words)) return json({ ok: false, error: "INVALID_TIMING" }, 400);
    await putJson(env.AUDIO_MEDIA, `${mediaPrefix(id)}timing.json`, timing, "ebook-reader-audio-timing");
    return json({ ok: true, id, words: timing.words.length });
  }

  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  const body = await request.json().catch(() => ({}));
  const bodyId = String(body?.id || "");
  if (!idValid(bodyId)) return json({ ok: false, error: "INVALID_AUDIO_ID" }, 400);
  const item = await getJson(env.AUDIO_MEDIA, itemKey(bodyId));
  if (!item || item.kind !== "ebook-reader") return json({ ok: false, error: "AUDIO_ITEM_NOT_FOUND" }, 404);

  if (kind === "fail") {
    item.status = "error";
    item.error = String(body?.error || "TTS render failed").slice(0, 800);
    item.updatedAt = new Date().toISOString();
    item.failedAt = body?.failedAt || item.updatedAt;
    await putJson(env.AUDIO_MEDIA, itemKey(bodyId), item);
    await env.AUDIO_MEDIA.delete(queueKey(bodyId));
    return json({ ok: true, id: bodyId, status: "error" });
  }

  const audioHead = await env.AUDIO_MEDIA.head(`${mediaPrefix(bodyId)}episode.mp3`);
  const timingHead = await env.AUDIO_MEDIA.head(`${mediaPrefix(bodyId)}timing.json`);
  if (!audioHead || !timingHead) return json({ ok: false, error: "AUDIO_OUTPUT_INCOMPLETE" }, 409);
  const now = new Date().toISOString();
  item.status = "ready";
  item.durationSeconds = Number.isFinite(Number(body?.durationSeconds)) ? Number(body.durationSeconds) : null;
  item.progressSeconds = 0;
  item.audioUrl = `${mediaPrefix(bodyId)}episode.mp3`;
  item.transcriptUrl = `${mediaPrefix(bodyId)}script.txt`;
  item.timingUrl = `${mediaPrefix(bodyId)}timing.json`;
  item.voice = VOICE;
  item.voiceRate = VOICE_RATE;
  item.speed = Number.isFinite(Number(body?.speed)) ? Number(body.speed) : 1.03;
  item.wordCount = Number.isFinite(Number(body?.wordCount)) ? Number(body.wordCount) : null;
  item.error = null;
  item.completedAt = body?.completedAt || now;
  item.updatedAt = now;
  await putJson(env.AUDIO_MEDIA, itemKey(bodyId), item);
  await env.AUDIO_MEDIA.delete(queueKey(bodyId));
  return json({ ok: true, id: bodyId, status: "ready", durationSeconds: item.durationSeconds });
}

export async function handleEbookReaderAudio(request, env) {
  const url = new URL(request.url);
  const internalKind = parseInternalRoute(url);
  if (internalKind) return handleInternal(request, env, url, internalKind);

  const route = parsePublicRoute(url);
  if (!route) return null;
  if (!env.AUDIO_MEDIA) return json({ ok: false, error: "AUDIO_MEDIA_NOT_BOUND" }, 503);

  if (route.kind === "status" && request.method === "POST") {
    const body = await request.json().catch(() => ({}));
    const bookKey = normalizeBookKey(body?.bookKey);
    if (!bookKey) return json({ ok: false, error: "BOOK_KEY_REQUIRED" }, 400);
    if (!validFinalEpubKey(bookKey)) return json({ ok: false, error: "FINAL_EPUB_ONLY" }, 403);
    const script = normalizeSpeechText(body?.text);
    if (script.length < 80) return json({ ok: false, error: "EBOOK_AUDIO_TEXT_TOO_SHORT" }, 422);
    if (script.length > MAX_SCRIPT_CHARS) return json({ ok: false, error: "EBOOK_AUDIO_TEXT_TOO_LONG" }, 413);

    const textSha256 = await sha256Hex(script);
    const id = await audioId(bookKey, textSha256);
    const key = itemKey(id);
    const prefix = mediaPrefix(id);
    const existing = await getJson(env.AUDIO_MEDIA, key);
    const now = new Date().toISOString();
    if (existing && existing.kind === "ebook-reader" && existing.bookKey === bookKey && existing.textSha256 === textSha256) {
      if (existing.status === "ready" || existing.status === "pending" || (existing.status === "processing" && processingLeaseFresh(existing))) {
        return json(await publicStateWithMedia(env, existing));
      }
      if (existing.status === "processing") {
        // A crashed consumer no longer leaves a permanent processing tombstone.
        // Recreate the pending queue only after the processing lease expires.
        await env.AUDIO_MEDIA.put(`${prefix}script.txt`, script, { httpMetadata: { contentType: "text/plain; charset=utf-8" }, customMetadata: { scope: "ebook-reader-audio", voice: VOICE, version: AUDIO_VERSION } });
        existing.status = "pending";
        existing.error = null;
        existing.processingAt = null;
        existing.updatedAt = now;
        const recoveryQueue = { id, kind: "ebook-reader", bookKey, itemKey: key, scriptKey: `${prefix}script.txt`, mediaPrefix: prefix, audioVersion: AUDIO_VERSION, voice: VOICE, voiceRate: VOICE_RATE, textSha256, createdAt: now };
        await putJson(env.AUDIO_MEDIA, key, existing);
        await putJson(env.AUDIO_MEDIA, queueKey(id), recoveryQueue);
        return json(publicState(existing), 202);
      }
    }

    await env.AUDIO_MEDIA.put(`${prefix}script.txt`, script, { httpMetadata: { contentType: "text/plain; charset=utf-8" }, customMetadata: { scope: "ebook-reader-audio", voice: VOICE, version: AUDIO_VERSION } });
    const item = {
      id, kind: "ebook-reader", bookKey,
      chapterTitle: String(body?.chapterTitle || "").trim().slice(0, 240) || null,
      chapterHref: String(body?.chapterHref || "").trim().slice(0, 600) || null,
      title: String(body?.bookTitle || "Ebook").trim().slice(0, 240) || "Ebook",
      sourceLabel: "Ebook Library", status: "pending", createdAt: existing?.createdAt || now, updatedAt: now,
      expiresAt: null, pinned: true, durationSeconds: null, progressSeconds: 0, audioUrl: null, transcriptUrl: null, timingUrl: null,
      mediaPrefix: prefix, audioVersion: AUDIO_VERSION, voice: VOICE, voiceRate: VOICE_RATE, textSha256, error: null,
    };
    const queue = { id, kind: "ebook-reader", bookKey, itemKey: key, scriptKey: `${prefix}script.txt`, mediaPrefix: prefix, audioVersion: AUDIO_VERSION, voice: VOICE, voiceRate: VOICE_RATE, textSha256, createdAt: now };
    await putJson(env.AUDIO_MEDIA, key, item);
    await putJson(env.AUDIO_MEDIA, queueKey(id), queue);
    return json(publicState(item), 202);
  }

  const bookKey = normalizeBookKey(url.searchParams.get("bookKey"));
  const id = String(url.searchParams.get("id") || "");
  if (!bookKey || !idValid(id)) return json({ ok: false, error: "AUDIO_ID_AND_BOOK_KEY_REQUIRED" }, 400);
  const existing = await readExisting(env, id, bookKey);
  if (!existing) return json({ ok: false, error: "AUDIO_ITEM_NOT_FOUND" }, 404);

  if (route.kind === "status") {
    if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
    return json(await publicStateWithMedia(env, existing));
  }
  if (request.method !== "GET" && !(route.kind === "media" && request.method === "HEAD")) return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!await verifyMediaTicket(env, url.searchParams.get("ticket"), bookKey, id)) return json({ ok: false, error: "AUDIO_TICKET_INVALID" }, 401);
  if (existing.status !== "ready") return json({ ok: false, error: "AUDIO_NOT_READY" }, 409);
  if (route.kind === "media") return serveMedia(request, env, mediaPrefix(id));
  const timing = await getJson(env.AUDIO_MEDIA, `${mediaPrefix(id)}timing.json`);
  return timing ? json(timing) : json({ ok: false, error: "AUDIO_TIMING_MISSING" }, 404);
}

export default {
  async fetch(request, env, ctx, fallbackApp) {
    const handled = await handleEbookReaderAudio(request, env);
    if (handled) return handled;
    if (fallbackApp?.fetch) return fallbackApp.fetch(request, env, ctx);
    return json({ ok: false, error: "NOT_FOUND" }, 404);
  },
};
