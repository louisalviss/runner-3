const UPSTREAM = 'https://runner5-restore-lab-1.wasmer.app';
const UPSTREAM_HTTP = 'http://runner5-restore-lab-1.wasmer.app';

export default {
  async fetch(request) {
    const incoming = new URL(request.url);
    const target = new URL(incoming.pathname + incoming.search, UPSTREAM);

    const headers = new Headers(request.headers);
    headers.delete('host');
    headers.set('x-forwarded-host', incoming.host);
    headers.set('x-forwarded-proto', 'https');

    const init = {
      method: request.method,
      headers,
      redirect: 'manual',
    };
    if (!['GET', 'HEAD'].includes(request.method)) init.body = request.body;

    const upstreamResponse = await fetch(target.toString(), init);
    const outHeaders = new Headers(upstreamResponse.headers);

    const location = outHeaders.get('location');
    if (location) {
      outHeaders.set(
        'location',
        location
          .replaceAll(UPSTREAM, incoming.origin)
          .replaceAll(UPSTREAM_HTTP, incoming.origin)
      );
    }

    const contentType = (outHeaders.get('content-type') || '').toLowerCase();
    const rewriteable =
      contentType.includes('text/html') ||
      contentType.includes('text/css') ||
      contentType.includes('javascript') ||
      contentType.includes('application/json') ||
      contentType.includes('application/xml') ||
      contentType.includes('text/xml');

    if (rewriteable && request.method !== 'HEAD') {
      let body = await upstreamResponse.text();
      body = body
        .replaceAll(UPSTREAM, incoming.origin)
        .replaceAll(UPSTREAM_HTTP, incoming.origin);
      outHeaders.delete('content-length');
      outHeaders.delete('content-encoding');
      return new Response(body, {
        status: upstreamResponse.status,
        statusText: upstreamResponse.statusText,
        headers: outHeaders,
      });
    }

    return new Response(upstreamResponse.body, {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
      headers: outHeaders,
    });
  },
};
