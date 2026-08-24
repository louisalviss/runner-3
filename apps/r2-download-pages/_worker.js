const ORIGIN = 'https://pub-7c042a29063743a5ad1e9d919b268036.r2.dev';

function safeName(pathname) {
  let name = pathname.split('/').filter(Boolean).pop() || 'download';
  try { name = decodeURIComponent(name); } catch {}
  return name.replace(/[\r\n"\\]/g, '_');
}

export default {
  async fetch(request) {
    if (!['GET','HEAD'].includes(request.method)) {
      return new Response('Method Not Allowed', {status:405, headers:{Allow:'GET, HEAD'}});
    }
    const url = new URL(request.url);
    if (!url.pathname || url.pathname === '/' || url.pathname.includes('..')) return new Response('Not Found',{status:404});
    const upstreamUrl = ORIGIN + url.pathname;
    const upstream = await fetch(upstreamUrl, {method:request.method, headers:{'Accept-Encoding':'identity'}});
    if (!upstream.ok) return new Response('Not Found',{status:upstream.status===404?404:upstream.status});
    const h = new Headers(upstream.headers);
    const filename = safeName(url.pathname);
    h.set('Content-Disposition', `attachment; filename="${filename}"; filename*=UTF-8''${encodeURIComponent(filename)}`);
    h.set('X-Content-Type-Options','nosniff');
    h.set('X-Robots-Tag','noindex, nofollow, noarchive, nosnippet');
    h.set('Cache-Control','public, max-age=300');
    return new Response(request.method==='HEAD'?null:upstream.body,{status:200,headers:h});
  }
};
