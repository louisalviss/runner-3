import app from "./artifact-library-reader-v36-home-screen-safe-area-entry.js";
import core from "./src/index.js";
import readerMedia from "./reader-media-entry.js";
import legacyAudio from "./artifact-library-reader-v6-audio-entry.js";
import ebookAudio from "./src/ebook-reader-audio.js";
import { handleRssLibrary } from "./src/rss-library.js";
import { handleRssLibrarySave } from "./src/rss-library-save.js";
import { handleRssReader } from "./src/rss-reader.js";
import { handleRssReaderPlus } from "./src/rss-reader-plus.js";
import { handleRssReaderAudio } from "./src/rss-reader-audio.js";
import { handleRssReaderLearning, recordReaderStateLearning } from "./src/rss-reader-learning.js";
import { handleContentIntelligence } from "./src/content-intelligence.js";
import { preserveArticleImages } from "./src/rss-image-enrich.js";

const ROBOTS = "noindex, nofollow,noarchive,nosnippet,noimageindex";
const ALLOWED_EVENT = "ebook_reader_audio";
const GITHUB_API = "https://api.github.com";
const GITHUB_REPO = "louisalviss/runner-3";
const GITHUB_WORKFLOW = "ebook-reader-audio.yml";
const ID_RE = /^ebook-[a-f0-9]{32}$/;
const EBOOK_AUDIO_INTERNAL_PREFIX = "/api/internal/ebook-reader-audio/";

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

function bearerToken(request) {
  const header = String(request.headers.get("authorization") || "");
  return header.startsWith("Bearer ") ? header.slice(7) : "";
}

function internalAuthorized(request, env) {
  const bearer = bearerToken(request);
  if (!bearer) return false;
  const coreToken = String(env.RUNNER3_CORE_TOKEN || "");
  const dedicated = String(env.EBOOK_AUDIO_VPS_TOKEN || "");
  return (Boolean(coreToken) && safeEqual(bearer, coreToken)) || (Boolean(dedicated) && safeEqual(bearer, dedicated));
}

function canonicalizeEbookAudioInternalRequest(request, env, url) {
  if (!url.pathname.startsWith(EBOOK_AUDIO_INTERNAL_PREFIX)) return request;
  const dedicated = String(env.EBOOK_AUDIO_VPS_TOKEN || "");
  const coreToken = String(env.RUNNER3_CORE_TOKEN || "");
  const bearer = bearerToken(request);
  if (!dedicated || !coreToken || !safeEqual(bearer, dedicated)) return request;
  const headers = new Headers(request.headers);
  headers.set("authorization", `Bearer ${coreToken}`);
  return new Request(request, { headers });
}

function triggerRoute(pathname) {
  return pathname === "/api/internal/ebook-reader-audio/dispatch" || pathname === "/artifact-library/api/audio/internal/dispatch";
}

function isCoreControlPlaneRoute(pathname) {
  return pathname === "/health" ||
    pathname === "/status" ||
    pathname === "/events" ||
    pathname === "/events/latest" ||
    pathname === "/radar/latest" ||
    pathname.startsWith("/state/") ||
    pathname.startsWith("/checkpoints/") ||
    pathname.startsWith("/artifacts/");
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

async function directReaderPayload(request, env, articleId, suffix = "") {
  const internal = internalReaderRequest(request, articleId, suffix);
  const response = await handleRssReader(internal.request, env, internal.target);
  if (!response?.ok) return { ok: false, response };
  const payload = await response.json().catch(() => null);
  if (!payload?.article) return { ok: false, response: json({ ok: false, error: "ARTICLE_NOT_FOUND" }, 404) };
  return { ok: true, payload };
}

function stateArticleId(request, url) {
  if (request.method !== "POST") return null;
  const match = url.pathname.match(/^\/reader\/rss\/articles\/([^/]+)\/state$/);
  if (!match) return null;
  try { return decodeURIComponent(match[1]); } catch { return null; }
}

function shouldPreserveImages(body) {
  return Boolean(body && (body.featured === true || body.preference === "like" || body.lifecycle === "archived"));
}

async function dispatchRssReader(request, env, ctx, url) {
  const plusResponse = await handleRssReaderPlus(request, env, url);
  if (plusResponse) return plusResponse;

  const learningResponse = await handleRssReaderLearning(request, env, url, (articleId) => directReaderPayload(request, env, articleId));
  if (learningResponse) return learningResponse;

  const audioResponse = await handleRssReaderAudio(request, env, url, {
    authorize: (articleId) => directReaderPayload(request, env, articleId),
    cleanView: (articleId, view) => directReaderPayload(request, env, articleId, `/${view === "original" ? "original" : "vi"}`),
  });
  if (audioResponse) return audioResponse;

  const articleId = stateArticleId(request, url);
  const stateClone = articleId ? request.clone() : null;
  const baseResponse = await handleRssReader(request, env, url);
  if (baseResponse) {
    if (articleId && stateClone && baseResponse.ok) {
      const body = await stateClone.json().catch(() => null);
      const tasks = [recordReaderStateLearning(env, articleId, body).catch(() => null)];
      if (shouldPreserveImages(body)) tasks.push(preserveArticleImages(env, articleId).catch(() => null));
      const task = Promise.all(tasks);
      if (ctx?.waitUntil) ctx.waitUntil(task); else await task;
    }
    return baseResponse;
  }
  return json({ ok: false, error: "NOT_FOUND" }, 404);
}

async function dispatchWorkflow(env, jobId = "") {
  const secret = String(env.RUNNER3_GITHUB_PAT || env.EBOOK_AUDIO_GITHUB_TOKEN || "").trim();
  if (!secret) throw new Error("GITHUB_PAT_NOT_CONFIGURED");
  const repoApi = String(env.RUNNER3_GITHUB_REPO_API || `${GITHUB_API}/repos/${GITHUB_REPO}`).replace(/\/+$/, "");
  const workflow = String(env.RUNNER3_EBOOK_AUDIO_WORKFLOW || GITHUB_WORKFLOW);
  const payload = { schema_version: 1, source: "ebook-reader", at: new Date().toISOString(), workflow };
  if (ID_RE.test(String(jobId || ""))) payload.job_id = String(jobId);
  const response = await fetch(`${repoApi}/dispatches`, {
    method: "POST",
    headers: { Accept: "application/vnd.github+json", Authorization: `Bearer ${secret}`, "Content-Type": "application/json", "User-Agent": "runner3-core/ebook-audio", "X-GitHub-Api-Version": "2022-11-28" },
    body: JSON.stringify({ event_type: ALLOWED_EVENT, client_payload: payload }),
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 500);
    throw new Error(`GITHUB_DISPATCH_FAILED:${response.status}:${detail}`);
  }
  return { ok: true, dispatched: true, eventType: ALLOWED_EVENT, workflow, jobId: payload.job_id || null };
}

async function manualDispatch(request, env) {
  if (request.method !== "POST") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  if (!internalAuthorized(request, env)) return json({ ok: false, error: "UNAUTHORIZED" }, 401);
  const body = await request.json().catch(() => ({}));
  const jobId = ID_RE.test(String(body?.job_id || "")) ? String(body.job_id) : "";
  try { return json(await dispatchWorkflow(env, jobId), 202); }
  catch (error) {
    const message = String(error?.message || error || "dispatch failed");
    return json({ ok: false, error: message.slice(0, 600) }, message === "GITHUB_PAT_NOT_CONFIGURED" ? 503 : 502);
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/healthz") {
      return json({ ok: true, service: "runner3-core" });
    }
    if (request.method === "GET" && url.pathname === "/") {
      return Response.redirect(new URL("/artifact-library", url).toString(), 302);
    }
    if (isCoreControlPlaneRoute(url.pathname)) {
      return core.fetch(request, env, ctx);
    }

    const rssSaveResponse = await handleRssLibrarySave(request, env, url);
    if (rssSaveResponse) return rssSaveResponse;
    if (request.method === "GET" && url.pathname === "/ui/rss") {
      return Response.redirect(new URL("/rss/library", url).toString(), 302);
    }
    if (url.pathname === "/rss/library" || url.pathname.startsWith("/rss/media/") || /^\/rss\/article\/[^/]+$/.test(url.pathname)) {
      return readerMedia.fetch(request, env, ctx);
    }
    if (url.pathname.startsWith("/api/rss/")) {
      const rssResponse = await handleRssLibrary(request, env, url);
      return rssResponse || json({ ok: false, error: "NOT_FOUND" }, 404);
    }
    if (url.pathname.startsWith("/reader/rss/")) {
      return dispatchRssReader(request, env, ctx, url);
    }
    if (url.pathname.startsWith("/content-intelligence/")) {
      const ciResponse = await handleContentIntelligence(request, env, url);
      return ciResponse || json({ ok: false, error: "NOT_FOUND" }, 404);
    }

    if (triggerRoute(url.pathname)) return manualDispatch(request, env);
    if (url.pathname.startsWith("/artifact-library/api/audio/")) {
      return legacyAudio.fetch(request, env, ctx);
    }
    if (url.pathname.startsWith("/api/ebook-reader-audio/")) {
      return json({ ok: false, error: "NOT_FOUND" }, 404);
    }
    const routedRequest = canonicalizeEbookAudioInternalRequest(request, env, url);
    return ebookAudio.fetch(routedRequest, env, ctx, app);
  },
};
