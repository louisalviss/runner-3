import { handleAudioMedia } from "./src/audio-media.js";
import { handleEbookReaderAudio } from "./src/ebook-reader-audio.js";

let readerAppPromise = null;
let learningModulePromise = null;

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

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const audioResponse = await handleAudioMedia(request, env, url);
    if (audioResponse) return audioResponse;
    const ebookAudioResponse = await handleEbookReaderAudio(request, env);
    if (ebookAudioResponse) return ebookAudioResponse;
    const app = await loadReaderApp();
    return app.fetch(request, env, ctx);
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