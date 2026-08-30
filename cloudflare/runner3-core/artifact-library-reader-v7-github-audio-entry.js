import app from "./artifact-library-reader-v6-entry.js";

const DISPATCH_EVENT = "ebook_reader_audio";
const DISPATCH_URL = "https://api.github.com/repos/louisalviss/runner-3/dispatches";
const AUDIO_POST_PATH = "/artifact-library/audio";
const LEGACY_QUEUE_PREFIX = "audio-library/rss-reader-queue/";
const EBOOK_QUEUE_PREFIX = "audio-library/ebook-reader-queue/";
const ID_RE = /^ebook-[a-f0-9]{32}$/;

async function migrateQueue(env, id) {
  if (!env.AUDIO_MEDIA || !ID_RE.test(id)) return false;
  const nextKey = `${EBOOK_QUEUE_PREFIX}${id}.json`;
  if (await env.AUDIO_MEDIA.head(nextKey)) return true;

  const legacyKey = `${LEGACY_QUEUE_PREFIX}${id}.json`;
  const legacy = await env.AUDIO_MEDIA.get(legacyKey);
  if (!legacy) return false;
  const queue = await legacy.text();
  await env.AUDIO_MEDIA.put(nextKey, queue, {
    httpMetadata: { contentType: "application/json; charset=utf-8" },
    customMetadata: { scope: "ebook-reader-audio" },
  });
  await env.AUDIO_MEDIA.delete(legacyKey);
  return true;
}

async function dispatchAudioJob(env, id) {
  const token = String(env.EBOOK_AUDIO_GITHUB_TOKEN || "").trim();
  if (!token) {
    console.warn("EBOOK_AUDIO_GITHUB_TOKEN missing; scheduled GitHub queue sweep will recover the job");
    return { ok: false, skipped: "missing-token" };
  }

  const response = await fetch(DISPATCH_URL, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json; charset=utf-8",
      "User-Agent": "runner3-core-ebook-reader-audio",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({
      event_type: DISPATCH_EVENT,
      client_payload: {
        schema_version: 1,
        job_id: id,
      },
    }),
  });

  if (!response.ok) {
    const detail = (await response.text()).slice(0, 300);
    throw new Error(`GitHub repository_dispatch failed HTTP ${response.status}: ${detail}`);
  }
  return { ok: true };
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const isAudioPost = request.method === "POST" && url.pathname === AUDIO_POST_PATH;
    const response = await app.fetch(request, env, ctx);
    if (!isAudioPost || !response.ok) return response;

    let state;
    try {
      state = await response.clone().json();
    } catch {
      return response;
    }
    const id = String(state?.id || "");
    if (state?.status !== "pending" || !ID_RE.test(id)) return response;

    const wake = (async () => {
      const migrated = await migrateQueue(env, id);
      if (!migrated) throw new Error(`Ebook audio queue object missing for ${id}`);
      await dispatchAudioJob(env, id);
    })().catch((error) => {
      console.error("Ebook Reader GitHub dispatch warning", error?.message || String(error));
    });

    if (ctx?.waitUntil) ctx.waitUntil(wake);
    else await wake;
    return response;
  },

  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
