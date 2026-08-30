const ITEM_PREFIX = "audio-library/items/";
const QUEUE_PREFIX = "audio-library/rss-reader-queue/";
const MEDIA_PREFIX = "audio-library/media/";
const VOICE = "vi-VN-NamMinhNeural";
const VOICE_RATE = "+3%";
const AUDIO_VERSION = "ebook-reader-audio-v1";
const MAX_SCRIPT_CHARS = 180000;
const MEDIA_TICKET_VERSION = "ebook-audio-media-v1";
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
  if (url.pathname === "/artifact-library/audio") return { kind: "status" };
  if (url.pathname === "/artifact-library/audio/media") return { kind: "media" };
  if (url.pathname === "/artifact-library/audio/timing") return { kind: "timing" };
  return null;
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
  if (!left.length || left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i++) diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  return diff === 0;
}

function normalizeBookKey(value) {
  const key = String(value || "").trim();
  if (!key || key.length > 1200 || key.includes("\0")) return "";
  return key;
}

function normalizeSpeechText(value) {
  return String(value || "")
    .normalize("NFC")
    .replace(/\r/g, "")
    .replace(/\u00a0/g, " ")
    .replace(/[\u200b-\u200d\u2060\ufeff]/g, "")
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

function itemKey(id) { return `${ITEM_PREFIX}${id}.json`; }
function queueKey(id) { return `${QUEUE_PREFIX}${id}.json`; }
function mediaPrefix(id) { return `${MEDIA_PREFIX}${id}/`; }

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
  const expected = await hmacHex(secret, ticketPayload(bookKey, id, expiresAt));
  return safeEqualHex(signature, expected);
}

function publicState(item) {
  if (!item) {
    return {
      ok: true,
      status: "missing",
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
  const headers = new Headers({
    "content-type": "audio/mpeg",
    "cache-control": "private, no-store",
    "accept-ranges": "bytes",
    "x-content-type-options": "nosniff",
    "content-disposition": "inline",
  });
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

function idValid(id) {
  return /^ebook-[a-f0-9]{32}$/.test(String(id || ""));
}

async function readExisting(env, id, bookKey) {
  if (!idValid(id) || !bookKey) return null;
  const item = await getJson(env.AUDIO_MEDIA, itemKey(id));
  if (!item || item.kind !== "ebook-reader" || item.bookKey !== bookKey) return null;
  return item;
}

export async function handleEbookReaderAudio(request, env) {
  const url = new URL(request.url);
  const route = parseRoute(url);
  if (!route) return null;
  if (!env.AUDIO_MEDIA) return json({ ok: false, error: "AUDIO_MEDIA_NOT_BOUND" }, 503);

  if (route.kind === "status" && request.method === "POST") {
    const body = await request.json().catch(() => ({}));
    const bookKey = normalizeBookKey(body?.bookKey);
    if (!bookKey) return json({ ok: false, error: "BOOK_KEY_REQUIRED" }, 400);
    const script = normalizeSpeechText(body?.text);
    if (script.length < 80) return json({ ok: false, error: "EBOOK_AUDIO_TEXT_TOO_SHORT" }, 422);
    if (script.length > MAX_SCRIPT_CHARS) return json({ ok: false, error: "EBOOK_AUDIO_TEXT_TOO_LONG" }, 413);

    const textSha256 = await sha256Hex(script);
    const id = await audioId(bookKey, textSha256);
    const key = itemKey(id);
    const prefix = mediaPrefix(id);
    const existing = await getJson(env.AUDIO_MEDIA, key);
    if (existing && existing.kind === "ebook-reader" && existing.bookKey === bookKey && existing.textSha256 === textSha256 && ["pending", "processing", "ready"].includes(existing.status)) {
      return json(await publicStateWithMedia(env, existing));
    }

    const now = new Date().toISOString();
    await env.AUDIO_MEDIA.put(`${prefix}script.txt`, script, {
      httpMetadata: { contentType: "text/plain; charset=utf-8" },
      customMetadata: { scope: "ebook-reader-audio", voice: VOICE, version: AUDIO_VERSION },
    });

    const item = {
      id,
      kind: "ebook-reader",
      bookKey,
      chapterTitle: String(body?.chapterTitle || "").trim().slice(0, 240) || null,
      chapterHref: String(body?.chapterHref || "").trim().slice(0, 600) || null,
      title: String(body?.bookTitle || "Ebook").trim().slice(0, 240) || "Ebook",
      sourceLabel: "Ebook Library",
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
      kind: "ebook-reader",
      bookKey,
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

  if (request.method !== "GET" && !(route.kind === "media" && request.method === "HEAD")) {
    return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  }
  const ticketOk = await verifyMediaTicket(env, url.searchParams.get("ticket"), bookKey, id);
  if (!ticketOk) return json({ ok: false, error: "AUDIO_TICKET_INVALID" }, 401);
  if (existing.status !== "ready") return json({ ok: false, error: "AUDIO_NOT_READY" }, 409);

  if (route.kind === "media") return serveMedia(request, env, mediaPrefix(id));
  const timing = await getJson(env.AUDIO_MEDIA, `${mediaPrefix(id)}timing.json`);
  if (!timing) return json({ ok: false, error: "AUDIO_TIMING_MISSING" }, 404);
  return json(timing);
}
