import app from "./artifact-library-reader-v36-home-screen-safe-area-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const TRANSLUCENT = '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">';
const OPAQUE = '<meta name="apple-mobile-web-app-status-bar-style" content="black">';
const RESET = `<style data-r3-ios-statusbar-viewport-v37="1">#viewer{top:0!important}</style>`;

function patchIosStatusbarViewport(html) {
  let out = String(html || "");
  if (out.includes('data-r3-ios-statusbar-viewport-v37="1"')) return out;
  if (!out.includes(TRANSLUCENT)) throw new Error("READER_V37_TRANSLUCENT_META_MISSING");
  if (!out.includes('data-r3-home-screen-safe-area-v36="1"')) throw new Error("READER_V37_V36_MISSING");
  out = out.replace(TRANSLUCENT, OPAQUE);
  if (!out.includes('</head>')) throw new Error("READER_V37_HEAD_MARKER_MISSING");
  return out.replace('</head>', RESET + '</head>');
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html") || response.status !== 200) return response;
    try {
      const updated = patchIosStatusbarViewport(await response.text());
      const headers = new Headers(response.headers);
      headers.delete("Content-Length");
      headers.set("X-Robots-Tag", ROBOTS);
      headers.set("X-R3-Reader-IOS-Statusbar-Viewport", "v37");
      return new Response(updated, { status: response.status, headers });
    } catch (error) {
      return new Response("Reader iOS status-bar viewport patch failed", {
        status: 503,
        headers: {
          "Content-Type": "text/plain; charset=utf-8",
          "Cache-Control": "no-store",
          "X-R3-Reader-IOS-Statusbar-Viewport": "v37-patch-failed",
          "X-R3-Reader-Patch-Error": String(error?.message || error).slice(0, 220),
        },
      });
    }
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
