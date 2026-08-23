function safeFilename(key) {
  const raw = key.split('/').pop() || 'download';
  return raw.replace(/[\r\n"\\]/g, '_');
}

export default {
  async fetch(request, env) {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response('Method Not Allowed', { status: 405, headers: { Allow: 'GET, HEAD' } });
    }

    const url = new URL(request.url);
    let key;
    try {
      key = decodeURIComponent(url.pathname.replace(/^\/+/, ''));
    } catch {
      return new Response('Bad Request', { status: 400 });
    }

    if (!key || key.includes('..')) {
      return new Response('Not Found', { status: 404 });
    }

    const object = request.method === 'HEAD'
      ? await env.BUCKET.head(key)
      : await env.BUCKET.get(key);

    if (!object) {
      return new Response('Not Found', { status: 404 });
    }

    const headers = new Headers();
    if (object.writeHttpMetadata) object.writeHttpMetadata(headers);

    const filename = safeFilename(key);
    headers.set('Content-Disposition', `attachment; filename="${filename}"; filename*=UTF-8''${encodeURIComponent(filename)}`);
    headers.set('Content-Length', String(object.size));
    headers.set('ETag', object.httpEtag || object.etag);
    headers.set('Cache-Control', 'public, max-age=300');
    headers.set('X-Content-Type-Options', 'nosniff');

    if (!headers.get('Content-Type')) {
      headers.set('Content-Type', 'application/octet-stream');
    }

    if (request.method === 'HEAD') {
      return new Response(null, { status: 200, headers });
    }

    return new Response(object.body, { status: 200, headers });
  },
};
