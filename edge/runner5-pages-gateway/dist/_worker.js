// Runner5 public Pages gateway.
// Purpose: provide a Pages hostname for clients that cannot reliably reach workers.dev.
// The optimized WordPress response is produced by the runner5-restore-proxy service;
// this gateway deliberately avoids a second HTML/CSS transform layer.

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/__runner5/pages-gateway/health') {
      return Response.json(
        {
          ok: true,
          gateway: 'runner5-restore-gateway',
          downstream: 'runner5-restore-proxy',
          mode: 'service-binding-passthrough',
          version: 8
        },
        {
          headers: {
            'Cache-Control': 'no-store',
            'X-Robots-Tag': 'noindex,nofollow'
          }
        }
      );
    }

    if (!env.EDGE || typeof env.EDGE.fetch !== 'function') {
      return new Response('Runner5 Pages gateway downstream unavailable', {
        status: 503,
        headers: { 'Cache-Control': 'no-store' }
      });
    }

    const upstream = await env.EDGE.fetch(request);
    const headers = new Headers(upstream.headers);
    headers.set('X-Runner5-Gateway', 'pages-v8');

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers
    });
  }
};
