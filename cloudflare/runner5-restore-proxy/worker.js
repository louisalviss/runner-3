import { HOME_SNAPSHOT, SNAPSHOT_BUILT_AT, STYLE_BUNDLE } from './snapshot.generated.js';

const UPSTREAM = 'https://runner5-restore-lab-1.wasmer.app';
const UPSTREAM_HTTP = 'http://runner5-restore-lab-1.wasmer.app';
const CACHE_VERSION = 'runner5-opt-v4';
const EDGE_CSS_PATH = '/__edge/runner5.css';

function isAdminPath(pathname) {
  return pathname === '/wp-login.php' ||
    pathname.startsWith('/wp-admin/') ||
    pathname.startsWith('/wp-json/') ||
    pathname === '/xmlrpc.php' ||
    pathname === '/wp-cron.php';
}
function isStaticPath(pathname) {
  return /\.(?:css|js|mjs|png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|otf|eot|mp4|webm|pdf)$/i.test(pathname);
}
function canUsePublicEdge(request, url) {
  if (!['GET', 'HEAD'].includes(request.method)) return false;
  if (isAdminPath(url.pathname)) return false;
  if (request.headers.get('cookie')) return false;
  if (!isStaticPath(url.pathname) && url.search) return false;
  return true;
}
function rewriteOrigin(text, incomingOrigin) {
  return String(text).replaceAll(UPSTREAM, incomingOrigin).replaceAll(UPSTREAM_HTTP, incomingOrigin);
}
function cacheKey(url) {
  const key = new URL(url.toString());
  key.searchParams.set('__edge_cache_version', CACHE_VERSION);
  return new Request(key.toString(), { method: 'GET' });
}
async function proxyOrigin(request, incoming) {
  const target = new URL(incoming.pathname + incoming.search, UPSTREAM);
  const headers = new Headers(request.headers);
  headers.delete('host'); headers.set('x-forwarded-host', incoming.host); headers.set('x-forwarded-proto', 'https');
  const init = { method: request.method, headers, redirect: 'manual' };
  if (!['GET', 'HEAD'].includes(request.method)) init.body = request.body;
  const upstreamResponse = await fetch(target.toString(), init);
  const outHeaders = new Headers(upstreamResponse.headers);
  const location = outHeaders.get('location');
  if (location) outHeaders.set('location', rewriteOrigin(location, incoming.origin));
  const contentType = (outHeaders.get('content-type') || '').toLowerCase();
  const rewriteable = contentType.includes('text/html') || contentType.includes('text/css') || contentType.includes('javascript') || contentType.includes('application/json') || contentType.includes('application/xml') || contentType.includes('text/xml');
  if (rewriteable && request.method !== 'HEAD') {
    const body = rewriteOrigin(await upstreamResponse.text(), incoming.origin);
    outHeaders.delete('content-length'); outHeaders.delete('content-encoding');
    return new Response(body, { status: upstreamResponse.status, statusText: upstreamResponse.statusText, headers: outHeaders });
  }
  return new Response(upstreamResponse.body, { status: upstreamResponse.status, statusText: upstreamResponse.statusText, headers: outHeaders });
}
function snapshotResponse(request, incoming) {
  let html = rewriteOrigin(HOME_SNAPSHOT || '', incoming.origin);
  // Font preloads caused a large lab CLS regression on this theme. Let the browser use fallback
  // metrics instead of forcing a late swap during the first render.
  html = html.replace(/<link\b[^>]*\brel=["']preload["'][^>]*\bas=["']font["'][^>]*>/gi, '');
  const headers = new Headers({
    'content-type': 'text/html; charset=UTF-8',
    'cache-control': 'public, max-age=60, stale-while-revalidate=600',
    'x-edge-mode': 'snapshot', 'x-edge-cache': 'SNAPSHOT',
    'x-edge-snapshot-built-at': SNAPSHOT_BUILT_AT || 'unknown', 'x-content-type-options': 'nosniff',
  });
  return new Response(request.method === 'HEAD' ? null : html, { status: 200, headers });
}
function cssBundleResponse(request, incoming) {
  let body = rewriteOrigin(STYLE_BUNDLE || '', incoming.origin);
  body = body.replace(/font-display\s*:\s*swap\s*;/gi, 'font-display:optional;');
  const headers = new Headers({
    'content-type': 'text/css; charset=UTF-8',
    'cache-control': 'public, max-age=86400, stale-while-revalidate=604800',
    'x-edge-mode': 'snapshot-asset', 'x-edge-cache': 'SNAPSHOT',
    'x-edge-snapshot-built-at': SNAPSHOT_BUILT_AT || 'unknown', 'x-content-type-options': 'nosniff',
  });
  return new Response(request.method === 'HEAD' ? null : body, { status: 200, headers });
}
export default {
  async fetch(request, env, ctx) {
    const incoming = new URL(request.url);
    if (canUsePublicEdge(request, incoming) && incoming.pathname === '/' && !incoming.search && HOME_SNAPSHOT) return snapshotResponse(request, incoming);
    if (canUsePublicEdge(request, incoming) && incoming.pathname === EDGE_CSS_PATH && STYLE_BUNDLE) return cssBundleResponse(request, incoming);
    if (!canUsePublicEdge(request, incoming)) {
      const response = await proxyOrigin(request, incoming); const headers = new Headers(response.headers);
      headers.set('x-edge-mode', 'bypass'); headers.set('x-edge-cache', 'BYPASS');
      return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
    }
    if (request.method === 'HEAD') {
      const response = await proxyOrigin(request, incoming); const headers = new Headers(response.headers);
      headers.set('x-edge-mode', 'proxy'); headers.set('x-edge-cache', 'BYPASS');
      return new Response(null, { status: response.status, statusText: response.statusText, headers });
    }
    const key = cacheKey(incoming); const cache = caches.default; const hit = await cache.match(key);
    if (hit) {
      const headers = new Headers(hit.headers); headers.set('x-edge-mode', 'cache'); headers.set('x-edge-cache', 'HIT');
      return new Response(hit.body, { status: hit.status, statusText: hit.statusText, headers });
    }
    const response = await proxyOrigin(request, incoming); const headers = new Headers(response.headers);
    headers.set('x-edge-mode', 'cache'); headers.set('x-edge-cache', 'MISS');
    const staticAsset = isStaticPath(incoming.pathname);
    if (response.status === 200 && !headers.has('set-cookie')) {
      headers.set('cache-control', staticAsset ? 'public, max-age=86400, stale-while-revalidate=604800' : 'public, max-age=60, stale-while-revalidate=600');
      const cacheable = new Response(response.body, { status: response.status, statusText: response.statusText, headers });
      ctx.waitUntil(cache.put(key, cacheable.clone())); return cacheable;
    }
    return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
  },
};
