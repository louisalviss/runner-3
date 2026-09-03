import app from "./mailbox-entry.js";
import coreApp from "./src/index.js";
import { handleOpportunityRegime } from "./src/opportunity-regime.js";
import { guardOpportunityRegimeWrite } from "./src/opportunity-regime-write-guard.js";
import { handlePrivateCoreFastPath } from "./vps-persistence-auth.js";

const READER_VENDOR_CACHE_V67_OUTERMOST = new Set([
  "/artifact-library/vendor/jszip.min.js",
  "/artifact-library/vendor/epub.min.js",
]);

function isPrivateCoreFastPath(pathname) {
  return pathname.startsWith("/artifacts/") || pathname.startsWith("/checkpoints/");
}

function applyReaderVendorCacheV67Outermost(request, url, response) {
  if (request.method !== "GET" || response.status !== 200 || !READER_VENDOR_CACHE_V67_OUTERMOST.has(url.pathname)) return response;
  const headers = new Headers(response.headers);
  headers.set("Cache-Control", "public, max-age=86400, stale-while-revalidate=604800");
  headers.delete("Pragma");
  headers.set("X-R3-Reader-Vendor-Cache", "v67-outermost");
  return new Response(response.body, { status: response.status, headers });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Keep durable artifact/checkpoint traffic out of the heavy Reader chain.
    // src/index.js remains the canonical owner; this wrapper only authenticates
    // the existing VPS mailbox RSA identity for the typed persistence surface.
    if (isPrivateCoreFastPath(url.pathname)) {
      return handlePrivateCoreFastPath(request, env, ctx, coreApp);
    }

    const regimeWriteGuard = await guardOpportunityRegimeWrite(request, url);
    if (regimeWriteGuard) return regimeWriteGuard;

    const regimeResponse = await handleOpportunityRegime(request, env, url);
    if (regimeResponse) return regimeResponse;

    const response = await app.fetch(request, env, ctx);
    return applyReaderVendorCacheV67Outermost(request, url, response);
  },

  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") {
      return app.scheduled(controller, env, ctx);
    }
  },
};
