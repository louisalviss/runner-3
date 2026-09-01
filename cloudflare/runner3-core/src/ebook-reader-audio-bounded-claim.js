import ebookAudio from "./ebook-reader-audio.js";

const ITEM_PREFIX = "audio-library/items/";
const QUEUE_PREFIX = "audio-library/ebook-reader-queue/";
const MEDIA_PREFIX = "audio-library/media/";
const SCAN_LIMIT = 10;
const PROCESSING_LEASE_SECONDS = 15 * 60;
const ID_RE = /^ebook-[a-f0-9]{32}$/;

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

function itemKey(id) {
  return `${ITEM_PREFIX}${id}.json`;
}

function mediaPrefix(id) {
  return `${MEDIA_PREFIX}${id}/`;
}

async function getJson(bucket, key) {
  const object = await bucket.get(key);
  if (!object) return null;
  try {
    return JSON.parse(await object.text());
  } catch {
    return null;
  }
}

async function putJson(bucket, key, value) {
  await bucket.put(key, JSON.stringify(value), {
    httpMetadata: { contentType: "application/json; charset=utf-8" },
    customMetadata: { scope: "ebook-reader-audio" },
  });
}

function freshProcessingLease(item, nowMs) {
  if (String(item?.status || "") !== "processing") return false;
  const processingAtMs = Date.parse(String(item?.processingAt || ""));
  if (!Number.isFinite(processingAtMs)) return false;
  return nowMs - processingAtMs >= 0 && nowMs - processingAtMs < PROCESSING_LEASE_SECONDS * 1000;
}

async function boundedNextJob(request, env) {
  const nowMs = Date.now();
  const worker = String(request.headers.get("x-ebook-audio-worker") || request.headers.get("x-runner3-source") || "internal-consumer")
    .trim()
    .slice(0, 120) || "internal-consumer";
  const listing = await env.AUDIO_MEDIA.list({ prefix: QUEUE_PREFIX, limit: SCAN_LIMIT });
  const objects = [...(listing.objects || [])].sort((a, b) => String(a.uploaded || "").localeCompare(String(b.uploaded || "")));

  let scanned = 0;
  let cleaned = 0;
  let leased = 0;
  for (const object of objects) {
    scanned += 1;
    const queue = await getJson(env.AUDIO_MEDIA, object.key);
    if (!queue || queue.kind !== "ebook-reader" || !ID_RE.test(String(queue.id || ""))) {
      await env.AUDIO_MEDIA.delete(object.key);
      cleaned += 1;
      continue;
    }

    const key = queue.itemKey || itemKey(queue.id);
    const item = await getJson(env.AUDIO_MEDIA, key);
    if (!item || item.kind !== "ebook-reader" || ["ready", "error"].includes(String(item.status || ""))) {
      await env.AUDIO_MEDIA.delete(object.key);
      cleaned += 1;
      continue;
    }

    if (freshProcessingLease(item, nowMs)) {
      leased += 1;
      continue;
    }

    const scriptKey = queue.scriptKey || `${mediaPrefix(queue.id)}script.txt`;
    const scriptObject = await env.AUDIO_MEDIA.get(scriptKey);
    if (!scriptObject) {
      const now = new Date(nowMs).toISOString();
      item.status = "error";
      item.error = "Audio script missing";
      item.updatedAt = now;
      item.failedAt = now;
      await putJson(env.AUDIO_MEDIA, key, item);
      await env.AUDIO_MEDIA.delete(object.key);
      cleaned += 1;
      continue;
    }

    const script = await scriptObject.text();
    const now = new Date().toISOString();
    item.status = "processing";
    item.error = null;
    item.processingAt = now;
    item.processingWorker = worker;
    item.processingLeaseSeconds = PROCESSING_LEASE_SECONDS;
    item.claimAttempt = Math.max(0, Number(item.claimAttempt) || 0) + 1;
    item.updatedAt = now;
    await putJson(env.AUDIO_MEDIA, key, item);
    return {
      job: {
        ...queue,
        script,
        processingWorker: worker,
        processingAt: now,
        processingLeaseSeconds: PROCESSING_LEASE_SECONDS,
      },
      meta: { scanned, cleaned, leased, scanLimit: SCAN_LIMIT },
    };
  }

  return { job: null, meta: { scanned, cleaned, leased, scanLimit: SCAN_LIMIT } };
}

export async function handleBoundedEbookAudioInternal(request, env) {
  const url = new URL(request.url);
  const isJob = url.pathname === "/api/internal/ebook-reader-audio/job";
  const isHealth = url.pathname === "/api/internal/ebook-reader-audio/health";
  if (!isJob && !isHealth) return null;
  if (!internalAuthorized(request, env)) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  if (!env.AUDIO_MEDIA) return json({ ok: false, error: "AUDIO_MEDIA_NOT_BOUND" }, 503);
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);

  if (isHealth) {
    return json({
      ok: true,
      mode: "vps-bounded-lease-v1",
      scanLimit: SCAN_LIMIT,
      processingLeaseSeconds: PROCESSING_LEASE_SECONDS,
      mutatesQueue: false,
    });
  }

  const result = await boundedNextJob(request, env);
  return json({ ok: true, job: result.job, claim: result.meta });
}

export default {
  async fetch(request, env, ctx, fallbackApp) {
    const handled = await handleBoundedEbookAudioInternal(request, env);
    if (handled) return handled;
    return ebookAudio.fetch(request, env, ctx, fallbackApp);
  },
};
