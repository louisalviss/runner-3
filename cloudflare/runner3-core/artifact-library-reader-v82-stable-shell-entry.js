import app from "./artifact-library-reader-v36-home-screen-safe-area-entry.js";
import { patchReaderV82 } from "./artifact-library-reader-v82-patch.js";
export { r3StableEarlyV82, r3StableRuntimeV82, patchReaderV82 } from "./artifact-library-reader-v82-patch.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (request.method !== 'GET' || url.pathname !== '/artifact-library/read') return response;
    const type = response.headers.get('Content-Type') || '';
    if (response.status !== 200 || !type.toLowerCase().includes('text/html')) return response;
    try {
      const updated = patchReaderV82(await response.text());
      const headers = new Headers(response.headers);
      headers.delete('Content-Length');
      headers.set('X-Robots-Tag', ROBOTS);
      headers.set('X-R3-Reader-Stable-Shell', 'v82');
      headers.set('X-R3-Reader-Pagination-Owner', 'v82');
      headers.set('X-R3-Reader-Restore-Guard', 'nonblocking-v89');
      headers.set('X-R3-Reader-Layout-Owner', 'converged-v90');
      headers.set('X-R3-Reader-Interaction-Owner', 'single-v92');
      headers.set('X-R3-Reader-WebKit-Runtime', 'compat-v93');
      headers.set('X-R3-Reader-Frame-Bind', 'relocated-v94');
      headers.set('X-R3-Reader-Touch-Owner', 'hybrid-v96');
      return new Response(updated, { status: 200, headers });
    } catch (error) {
      return new Response('Reader stable shell v82 patch failed', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store', 'X-R3-Reader-Stable-Shell': 'v82-patch-failed', 'X-R3-Reader-Patch-Error': String(error && error.message || error).slice(0, 200) } });
    }
  },
  async scheduled(controller, env, ctx) { if (typeof app.scheduled === 'function') return app.scheduled(controller, env, ctx); },
};
