import app from "./artifact-library-reader-v35-continuity-single-owner-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const TRANSLUCENT = '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">';
const OPAQUE = '<meta name="apple-mobile-web-app-status-bar-style" content="black">';
const CAPABLE = '<meta name="apple-mobile-web-app-capable" content="yes">';
const MOBILE_CAPABLE = '<meta name="mobile-web-app-capable" content="yes">';
const STARTUP_MARKER = '<meta name="r3-ios-home-screen-startup-policy" content="opaque-v39">';

const READER_MARKER = `<style data-r3-home-screen-safe-area-v36="1" data-r3-ios-statusbar-viewport-v39="1">
/* v39: the Home Screen startup document owns the non-overlay viewport policy.
   The Reader must not add a second top inset. */
#viewer { top: 0 !important; }
</style>
<script data-r3-home-screen-safe-area-runtime-v36="1" data-r3-ios-startup-viewport-runtime-v39="1">
(()=>{
  if(window.__r3HomeScreenSafeAreaV36)return;
  const standalone=Boolean((window.matchMedia&&window.matchMedia('(display-mode: standalone)').matches)||navigator.standalone===true);
  window.__r3HomeScreenSafeAreaV36={version:'v39-startup-opaque',standalone,statusbar:'black',viewerTop:'0',forcedInset:false};
})();
</script>`;

function ensureHeadMeta(html, meta) {
  const out = String(html || "");
  if (out.includes(meta)) return out;
  if (!out.includes('</head>')) throw new Error("READER_V39_HEAD_MARKER_MISSING");
  return out.replace('</head>', meta + '\n</head>');
}

function patchLibraryStartup(html) {
  let out = String(html || "");
  if (!out.includes('<meta name="viewport"') || !out.includes('viewport-fit=cover')) {
    throw new Error("READER_V39_LIBRARY_VIEWPORT_FIT_COVER_MISSING");
  }
  out = ensureHeadMeta(out, CAPABLE);
  out = ensureHeadMeta(out, MOBILE_CAPABLE);
  if (out.includes(TRANSLUCENT)) out = out.replace(TRANSLUCENT, OPAQUE);
  else if (!out.includes(OPAQUE)) out = ensureHeadMeta(out, OPAQUE);
  out = ensureHeadMeta(out, STARTUP_MARKER);
  return out;
}

function patchReader(html) {
  let out = String(html || "");
  if (out.includes('data-r3-home-screen-safe-area-v36="1"')) return out;
  if (!out.includes('<meta name="viewport"') || !out.includes('viewport-fit=cover')) {
    throw new Error("READER_V39_READER_VIEWPORT_FIT_COVER_MISSING");
  }
  if (!out.includes('id="viewer"')) throw new Error("READER_V39_VIEWER_MISSING");
  if (out.includes(TRANSLUCENT)) out = out.replace(TRANSLUCENT, OPAQUE);
  else if (!out.includes(OPAQUE)) out = ensureHeadMeta(out, OPAQUE);
  out = ensureHeadMeta(out, CAPABLE);
  out = ensureHeadMeta(out, MOBILE_CAPABLE);
  out = ensureHeadMeta(out, STARTUP_MARKER);
  return out.replace('</head>', READER_MARKER + '</head>');
}

function patchedHtmlResponse(response, updated, extraHeaders = {}) {
  const headers = new Headers(response.headers);
  headers.delete("Content-Length");
  headers.set("X-Robots-Tag", ROBOTS);
  for (const [key, value] of Object.entries(extraHeaders)) headers.set(key, value);
  return new Response(updated, { status: response.status, headers });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html") || response.status !== 200) return response;

    try {
      if (url.pathname === "/artifact-library") {
        return patchedHtmlResponse(response, patchLibraryStartup(await response.text()), {
          "X-R3-Reader-IOS-Startup-Viewport": "opaque-v39",
        });
      }
      if (url.pathname === "/artifact-library/read") {
        return patchedHtmlResponse(response, patchReader(await response.text()), {
          "X-R3-Reader-Home-Screen-Safe-Area": "v36",
          "X-R3-Reader-IOS-Statusbar-Viewport": "opaque-v39",
          "X-R3-Reader-IOS-Forced-Inset": "disabled-v39",
          "X-R3-Reader-IOS-Startup-Viewport": "opaque-v39",
        });
      }
      return response;
    } catch (error) {
      return new Response("Reader Home Screen viewport patch failed", {
        status: 503,
        headers: {
          "Content-Type": "text/plain; charset=utf-8",
          "Cache-Control": "no-store",
          "X-R3-Reader-Home-Screen-Safe-Area": "v36-patch-failed",
          "X-R3-Reader-Patch-Error": String(error?.message || error).slice(0, 220),
        },
      });
    }
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
