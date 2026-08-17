export default {
  async fetch(request, env) {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response('Method Not Allowed', { status: 405, headers: { Allow: 'GET, HEAD' } });
    }

    const url = new URL(request.url);
    const key = decodeURIComponent(url.pathname.replace(/^\/+/, ''));
    if (!key || key.includes('..')) return new Response('Not Found', { status: 404 });

    const object = request.method === 'HEAD' ? await env.MEDIA.head(key) : await env.MEDIA.get(key);
    if (!object) return new Response('Not Found', { status: 404 });

    const headers = new Headers();
    object.writeHttpMetadata?.(headers);
    if (object.httpEtag) headers.set('ETag', object.httpEtag);
    headers.set('Cache-Control', 'public, max-age=31536000, immutable');
    headers.set('X-Content-Type-Options', 'nosniff');
    headers.set('Cross-Origin-Resource-Policy', 'cross-origin');

    if (request.method === 'HEAD') return new Response(null, { status: 200, headers });
    return new Response(object.body, { status: 200, headers });
  }
};
