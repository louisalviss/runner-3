// Cloudflare Pages advanced-mode gateway.
// Existing public traffic is delegated unchanged to wordpress-edge-proxy.
// Only /dl/* is isolated for direct R2 downloads.

const DOWNLOAD_ORIGIN = 'https://pub-7c042a29063743a5ad1e9d919b268036.r2.dev';

function safeFilename(pathname) {
  let name = pathname.split('/').filter(Boolean).pop() || 'download';
  try { name = decodeURIComponent(name); } catch {}
  return name.replace(/[\r\n"\\]/g, '_');
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/__runner3/pages-gateway/health') {
      return Response.json(
        {
          ok: true,
          gateway: 'runner3wp-pages-gateway',
          downstream: 'wordpress-edge-proxy',
          directDownloadPrefix: '/dl/',
        },
        {
          headers: {
            'Cache-Control': 'no-store',
            'X-Robots-Tag': 'noindex, nofollow, noarchive, nosnippet',
          },
        },
      );
    }

    if (url.pathname.startsWith('/dl/')) {
      if (request.method !== 'GET' && request.method !== 'HEAD') {
        return new Response('Method Not Allowed', {
          status: 405,
          headers: { Allow: 'GET, HEAD' },
        });
      }

      const objectPath = url.pathname.slice('/dl'.length);
      if (!objectPath || objectPath === '/' || objectPath.includes('..')) {
        return new Response('Not Found', { status: 404 });
      }

      const upstream = await fetch(DOWNLOAD_ORIGIN + objectPath, {
        method: request.method,
        headers: { 'Accept-Encoding': 'identity' },
      });

      if (!upstream.ok) {
        return new Response(upstream.status === 404 ? 'Not Found' : 'Upstream Error', {
          status: upstream.status,
          headers: {
            'Cache-Control': 'no-store',
            'X-Robots-Tag': 'noindex, nofollow, noarchive, nosnippet',
          },
        });
      }

      const headers = new Headers(upstream.headers);
      const filename = safeFilename(objectPath);
      headers.set(
        'Content-Disposition',
        `attachment; filename="${filename}"; filename*=UTF-8''${encodeURIComponent(filename)}`,
      );
      headers.set('X-Content-Type-Options', 'nosniff');
      headers.set('X-Robots-Tag', 'noindex, nofollow, noarchive, nosnippet');
      headers.set('Cache-Control', 'public, max-age=300');

      return new Response(request.method === 'HEAD' ? null : upstream.body, {
        status: 200,
        headers,
      });
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

    // Critical invariant: every pre-existing non-download request is forwarded unchanged.
    return env.EDGE.fetch(request);
  },
};
