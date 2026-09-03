import app from "./artifact-library-reader-v35-continuity-single-owner-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

const HOME_SCREEN_SAFE_AREA_V36 = `<style data-r3-home-screen-safe-area-v36="1">
@media (display-mode: standalone) {
  #viewer { top: env(safe-area-inset-top, 0px) !important; }
}
html.r3-home-screen-v36 #viewer { top: env(safe-area-inset-top, 0px) !important; }
</style>
<script data-r3-home-screen-safe-area-runtime-v36="1">
(()=>{
  if(window.__r3HomeScreenSafeAreaV36)return;
  const standalone=Boolean((window.matchMedia&&window.matchMedia('(display-mode: standalone)').matches)||navigator.standalone===true);
  window.__r3HomeScreenSafeAreaV36={version:'v36',standalone};
  if(standalone)document.documentElement.classList.add('r3-home-screen-v36');
})();
</script>`;

function patchHomeScreenSafeArea(html) {
  let out = String(html || "");
  if (out.includes('data-r3-home-screen-safe-area-v36="1"')) return out;
  if (!out.includes('<meta name="viewport"') || !out.includes('viewport-fit=cover')) {
    throw new Error("READER_V36_VIEWPORT_FIT_COVER_MISSING");
  }
  if (!out.includes('id="viewer"')) throw new Error("READER_V36_VIEWER_MISSING");
  if (!out.includes('</head>')) throw new Error("READER_V36_HEAD_MARKER_MISSING");
  return out.replace('</head>', HOME_SCREEN_SAFE_AREA_V36 + '</head>');
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html") || response.status !== 200) return response;
    try {
      const updated = patchHomeScreenSafeArea(await response.text());
      const headers = new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag", ROBOTS);
      headers.set("X-R3-Reader-Home-Screen-Safe-Area", "v36");
      return new Response(updated, { status: response.status, headers });
    } catch (error) {
      return new Response("Reader Home Screen safe-area patch failed", {
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
