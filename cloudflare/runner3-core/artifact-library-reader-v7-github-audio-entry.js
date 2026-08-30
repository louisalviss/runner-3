import app from "./artifact-library-reader-v6-audio-entry.js";

const DISPATCH_EVENT = "ebook_reader_audio";
const DISPATCH_URL = "https://api.github.com/repos/louisalviss/runner-3/dispatches";
const AUDIO_POST_RE = /^\/artifact-library\/api\/audio\/([a-f0-9]{32})$/;

async function dispatchAudioJob(env, shortId) {
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
        job_id: `ebook-${shortId}`,
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
    const match = request.method === "POST" ? url.pathname.match(AUDIO_POST_RE) : null;
    const response = await app.fetch(request, env, ctx);

    if (!match || !response.ok) return response;

    try {
      const state = await response.clone().json();
      if (state?.status !== "pending") return response;
    } catch {
      return response;
    }

    const wake = dispatchAudioJob(env, match[1]).catch((error) => {
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
