function safeFilename(pathname) {
  const raw = pathname.split('/').pop() || 'download';
  try {
    return decodeURIComponent(raw).replace(/[\r\n"\\]/g, '_');
  } catch {
    return raw.replace(/[\r\n"\\]/g, '_');
  }
}

export default {
  async fetch(request, env) {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response('Method Not Allowed', { status: 405, headers: { Allow: 'GET, HEAD' } });
    }

    const url = new URL(request.url);
    if (!url.pathname || url.pathname === '/' || url.pathname.includes('..')) {
      return new Response('Not Found', { status: 404 });
    }

    const origin = new URL(url.pathname, env.R2_ORIGIN);
    const upstream = await fetch(origin, {
      method: request.method,
      headers: request.headers.get('Range') ? { Range: request.headers.get('Range') } : undefined,
      redirect: 'follow',
    });

    if (!upstream.ok && upstream.status !== 206) {
      return new Response(upstream.body, { status: upstream.status, headers: upstream.headers });
    }

    const headers = new Headers(upstream.headers);
    const filename = safeFilename(url.pathname);
    headers.set('Content-Disposition', `attachment; filename="${filename}"; filename*=UTF-8''${encodeURIComponent(filename)}`);
    headers.set('X-Content-Type-Options', 'nosniff');
    headers.set('Cache-Control', 'public, max-age=300');

    if (!headers.get('Content-Type')) {
      headers.set('Content-Type', 'application/octet-stream');
    }

    return new Response(request.method === 'HEAD' ? null : upstream.body, {
      status: upstream.status,
      headers,
    });
  },
};
