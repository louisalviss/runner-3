import app from "./artifact-library-reader-v9-runtime-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const READER_CSP = "default-src 'self'; style-src 'self' 'unsafe-inline' blob:; script-src 'self' 'unsafe-inline'; connect-src 'self' https:; img-src 'self' data: blob:; font-src 'self' data: blob:; media-src 'self' data: blob:; frame-src 'self' blob:; child-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'";
const OLD_HIGHLIGHT = '[data-r3-audio-reading="1"]{font-weight:800!important}';
const NEW_HIGHLIGHT = '[data-r3-audio-reading="1"],[data-r3-audio-reading="1"] *{font-weight:800!important}';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html")) return response;

    const original = await response.text();
    const updated = original.includes(OLD_HIGHLIGHT) ? original.replace(OLD_HIGHLIGHT, NEW_HIGHLIGHT) : original;
    const headers = new Headers(response.headers);
    headers.delete("Content-Length");
    headers.set("Content-Security-Policy", READER_CSP);
    headers.set("X-Robots-Tag", ROBOTS);
    headers.set("X-R3-Reader-Runtime", "v10-epub-blob-style-visible-highlight");
    return new Response(updated, { status: response.status, headers });
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
