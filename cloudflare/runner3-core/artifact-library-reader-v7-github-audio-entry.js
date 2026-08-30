import app from "./artifact-library-reader-v6-entry.js";
import ebookAudio from "./src/ebook-reader-audio.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const ALLOWED_EVENT = "ebook_reader_audio";
const GITHUB_API = "https://api.github.com";
const GITHUB_REPO = "louisalviss/runner-3";
const GITHUB_WORKFLOW = "audio-library-ebook-tts.yml";

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "X-Robots-Tag": ROBOTS,
      "Cache-Control": "private, no-store, max-age=0",
      Pragma: "no-cache",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
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

function triggerRoute(pathname) {
  return pathname === "/api/internal/ebook-reader-audio/dispatch" || pathname === "/artifact-library/api/audio/internal/dispatch";
}

async function dispatchWorkflow(env) {
  const secret = String(env.RUNNER3_GITHUB_PAT || "");
  if (!secret) throw new Error("GITHUB_PAT_NOT_CONFIGURED");
  const repoApi = String(env.RUNNER3_GITHUB_REPO_API || `${GITHUB_API}/repos/${GITHUB_REPO}`).replace(/\/+$/, "");
  const workflow = String(env.RUNNER3_EBOOK_AUDIO_WORKFLOW || GITHUB_WORKFLOW);
  const response = await fetch(`${repoApi}/dispatches`, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${secret}`,
      "Content-Type": "application/json",
      "User-Agent": "runner3-core/ebook-audio",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({
      event_type: ALLOWED_EVENT,
      client_payload: { source: "ebook-reader", at: new Date().toISOString(), workflow },
    }),
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 500);
    throw new Error(`GITHUB_DISPATCH_FAILED:${response.status}:${detail}`);
  }
  return { ok: true, dispatched: true, eventType: ALLOWED_EVENT, workflow };
}

async function manualDispatch(request, env) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!internalAuthorized(request, env)) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  try {
    return json(await dispatchWorkflow(env), 202);
  } catch (error) {
    const message = String(error?.message || error || "dispatch failed");
    const status = message === "GITHUB_PAT_NOT_CONFIGURED" ? 503 : 502;
    return json({ ok: false, error: message.slice(0, 600) }, status);
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (triggerRoute(url.pathname)) return manualDispatch(request, env);

    const shouldDispatch = url.pathname === "/artifact-library/audio" && request.method === "POST";
    const response = await ebookAudio.fetch(request, env, ctx, app);
    if (shouldDispatch && response?.status === 202) {
      const task = dispatchWorkflow(env).catch((error) => console.error("ebook audio dispatch failed", String(error?.message || error)));
      if (ctx?.waitUntil) ctx.waitUntil(task);
      else await task;
    }
    return response;
  },
};
