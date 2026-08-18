// Cloudflare Pages advanced-mode gateway.
// Public traffic is delegated to the already-tested wordpress-edge-proxy Worker
// through a zero-hop Service Binding. No DNS/custom-domain changes are made here.

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/__runner3/pages-gateway/health') {
      return Response.json(
        {
          ok: true,
          gateway: 'runner3wp-pages-gateway',
          downstream: 'wordpress-edge-proxy',
        },
        {
          headers: {
            'Cache-Control': 'no-store',
            'X-Robots-Tag': 'noindex, nofollow, noarchive, nosnippet',
          },
        },
      );
    }

    if (!env.EDGE || typeof env.EDGE.fetch !== 'function') {
      return new Response('Pages gateway service binding unavailable', {
        status: 503,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store',
          'X-Robots-Tag': 'noindex, nofollow, noarchive, nosnippet',
        },
      });
    }

    return env.EDGE.fetch(request);
  },
};
