import { handleAudioMedia } from "./src/audio-media.js";

let readerAppPromise = null;
let learningModulePromise = null;

const IOS_CAPABLE = '<meta name="apple-mobile-web-app-capable" content="yes">';
const MOBILE_CAPABLE = '<meta name="mobile-web-app-capable" content="yes">';
const IOS_STATUS_BLACK = '<meta name="apple-mobile-web-app-status-bar-style" content="black">';
const IOS_STATUS_TRANSLUCENT = '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">';
const IOS_STARTUP_MARKER = '<meta name="r3-ios-home-screen-startup-policy" content="opaque-v39">';

function loadReaderApp() {
  if (!readerAppPromise) {
    readerAppPromise = import("./artifact-library-reader-v7-github-audio-entry.js").then((module) => module.default);
  }
  return readerAppPromise;
}

function loadLearningModule() {
  if (!learningModulePromise) learningModulePromise = import("./src/rss-reader-learning.js");
  return learningModulePromise;
}

function ensureHeadMeta(html, meta) {
  const out = String(html || "");
  if (out.includes(meta)) return out;
  if (!out.includes("</head>")) return out;
  return out.replace("</head>", `${meta}\n</head>`);
}

function patchLibraryHomeScreenStartup(html) {
  let out = String(html || "");
  if (!out.includes('<meta name="viewport"') || !out.includes("viewport-fit=cover")) return out;
  out = ensureHeadMeta(out, IOS_CAPABLE);
  out = ensureHeadMeta(out, MOBILE_CAPABLE);
  if (out.includes(IOS_STATUS_TRANSLUCENT)) out = out.replace(IOS_STATUS_TRANSLUCENT, IOS_STATUS_BLACK);
  else out = ensureHeadMeta(out, IOS_STATUS_BLACK);
  out = ensureHeadMeta(out, IOS_STARTUP_MARKER);
  return out;
}

async function maybePatchLibraryStartup(request, url, response) {
  if (request.method !== "GET" || url.pathname !== "/artifact-library" || response.status !== 200) return response;
  const type = String(response.headers.get("Content-Type") || "").toLowerCase();
  if (!type.includes("text/html")) return response;
  const updated = patchLibraryHomeScreenStartup(await response.text());
  const headers = new Headers(response.headers);
  headers.delete("Content-Length");
  headers.set("X-R3-Reader-IOS-Startup-Viewport", "opaque-v39");
  return new Response(updated, { status: response.status, headers });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const audioResponse = await handleAudioMedia(request, env, url);
    if (audioResponse) return audioResponse;
    const app = await loadReaderApp();
    const response = await app.fetch(request, env, ctx);
    return maybePatchLibraryStartup(request, url, response);
  },

  async scheduled(controller, env, ctx) {
    const [{ maybeRecomputePersonal }, app] = await Promise.all([
      loadLearningModule(),
      loadReaderApp(),
    ]);
    const flush = maybeRecomputePersonal(env, { force: true }).catch((error) => {
      console.warn("content intelligence scheduled recompute failed", String(error?.message || error));
    });
    if (ctx?.waitUntil) ctx.waitUntil(flush);
    else await flush;
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
