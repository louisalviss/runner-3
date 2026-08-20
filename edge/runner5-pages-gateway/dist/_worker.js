// Cloudflare Pages advanced-mode gateway for Runner5 Restore Lab.
// Delegates all public traffic to the tested runner5-restore-proxy Worker via Service Binding.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/__runner5/pages-gateway/health') {
      return Response.json({ ok: true, gateway: 'runner5-restore-gateway', downstream: 'runner5-restore-proxy' }, {
        headers: { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow, noarchive, nosnippet' },
      });
    }
    if (!env.EDGE || typeof env.EDGE.fetch !== 'function') {
      return new Response('Runner5 Pages gateway service binding unavailable', {
        status: 503,
        headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow, noarchive, nosnippet' },
      });
    }
    return env.EDGE.fetch(request);
  },
};
