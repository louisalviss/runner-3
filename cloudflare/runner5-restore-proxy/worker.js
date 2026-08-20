import { HOME_SNAPSHOT, SNAPSHOT_BUILT_AT, STYLE_BUNDLE } from './snapshot.generated.js';

const UPSTREAM = 'https://runner5-restore-lab-1.wasmer.app';
const UPSTREAM_HTTP = 'http://runner5-restore-lab-1.wasmer.app';
const CACHE_VERSION = 'runner5-opt-v7';
const EDGE_CSS_PATH = '/__edge/runner5.css';
const META_DESCRIPTION = 'Runner5 Restore Lab Demo — WordPress restore verification articles and case studies.';
const SYSTEM_FONT_STACK = '-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif';

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
function optimizedCss(incomingOrigin) {
  let css = rewriteOrigin(STYLE_BUNDLE || '', incomingOrigin);
  css = css.replace(/font-display\s*:\s*swap\s*;/gi, 'font-display:optional;');
  css += `\n/* Runner5 Lighthouse stability/accessibility overrides */\n` +
    `body,button,input,select,textarea,h1,h2,h3,h4,h5,h6,p,a,li,span,time{font-family:${SYSTEM_FONT_STACK}!important}` +
    `.site-header{position:fixed!important;top:0!important;width:100%!important;z-index:1000!important}` +
    `body.home.blog:not(.has-header-image):not(.has-header-video) #content{padding-top:105px!important}` +
    `.entry-meta,.entry-meta a,.entry-meta .byline a,.entry-meta .posted-on a{color:#555!important}` +
    `.site-info,.site-info a,.site-info .copyright{color:#d0d0d0!important}` +
    `img,svg,video{height:auto}`;
  return css;
}
function optimizeSnapshotHtml(source, incoming) {
  let html = rewriteOrigin(source || '', incoming.origin);

  html = html.replace(/<link\b[^>]*\brel=["']preload["'][^>]*\bas=["']font["'][^>]*>/gi, '');

  const css = optimizedCss(incoming.origin);
  let inlined = false;
  html = html.replace(/<link\b[^>]*>/gi, (tag) => {
    const isStylesheet = /\brel=["'][^"']*stylesheet[^"']*["']/i.test(tag);
    const isEdgeBundle = /\bhref=["'](?:\/__edge\/runner5\.css|\/__edge-bundle-v2\.css)(?:\?[^"']*)?["']/i.test(tag);
    if (isStylesheet && isEdgeBundle) {
      inlined = true;
      return `<style id="runner5-critical-css">${css}</style>`;
    }
    return tag;
  });
  if (!inlined && css && /<\/head>/i.test(html)) {
    html = html.replace(/<\/head>/i, `<style id="runner5-critical-css">${css}</style></head>`);
  }

  if (!/<meta\b[^>]*\bname=["']description["']/i.test(html)) {
    html = html.replace(/<\/head>/i, `<meta name="description" content="${META_DESCRIPTION}"></head>`);
  }

  // Inspiro has used both search-icon and sb-search-button-open for its icon-only search control.
  html = html.replace(/<button\b[^>]*>/gi, (tag) => {
    const classMatch = tag.match(/\bclass=["']([^"']*)["']/i);
    const classes = classMatch ? classMatch[1] : '';
    if (!/(?:^|\s)(?:search-icon|sb-search-button-open)(?:\s|$)/i.test(classes)) return tag;
    if (/\baria-label\s*=|\baria-labelledby\s*=|\btitle\s*=/i.test(tag)) return tag;
    return tag.replace(/^<button/i, '<button aria-label="Search" title="Search"');
  });

  html = html.replace(/<h3(\s[^>]*\bclass=["'][^"']*\bentry-title\b[^"']*["'][^>]*)>([\s\S]*?)<\/h3>/gi, '<h2$1>$2</h2>');

  return html;
}
function snapshotResponse(request, incoming) {
  const html = optimizeSnapshotHtml(HOME_SNAPSHOT, incoming);
  const headers = new Headers({
    'content-type': 'text/html; charset=UTF-8',
    'cache-control': 'public, max-age=60, stale-while-revalidate=600',
    'x-edge-mode': 'snapshot', 'x-edge-cache': 'SNAPSHOT',
    'x-edge-snapshot-built-at': SNAPSHOT_BUILT_AT || 'unknown', 'x-content-type-options': 'nosniff',
    'x-runner5-opt': CACHE_VERSION,
  });
  return new Response(request.method === 'HEAD' ? null : html, { status: 200, headers });
}
function cssBundleResponse(request, incoming) {
  const body = optimizedCss(incoming.origin);
  const headers = new Headers({
    'content-type': 'text/css; charset=UTF-8',
    'cache-control': 'public, max-age=86400, stale-while-revalidate=604800',
    'x-edge-mode': 'snapshot-asset', 'x-edge-cache': 'SNAPSHOT',
    'x-edge-snapshot-built-at': SNAPSHOT_BUILT_AT || 'unknown', 'x-content-type-options': 'nosniff',
    'x-runner5-opt': CACHE_VERSION,
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
      headers.set('x-edge-mode', 'bypass'); headers.set('x-edge-cache', 'BYPASS'); headers.set('x-runner5-opt', CACHE_VERSION);
      return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
    }
    if (request.method === 'HEAD') {
      const response = await proxyOrigin(request, incoming); const headers = new Headers(response.headers);
      headers.set('x-edge-mode', 'proxy'); headers.set('x-edge-cache', 'BYPASS'); headers.set('x-runner5-opt', CACHE_VERSION);
      return new Response(null, { status: response.status, statusText: response.statusText, headers });
    }
    const key = cacheKey(incoming); const cache = caches.default; const hit = await cache.match(key);
    if (hit) {
      const headers = new Headers(hit.headers); headers.set('x-edge-mode', 'cache'); headers.set('x-edge-cache', 'HIT'); headers.set('x-runner5-opt', CACHE_VERSION);
      return new Response(hit.body, { status: hit.status, statusText: hit.statusText, headers });
    }
    const response = await proxyOrigin(request, incoming); const headers = new Headers(response.headers);
    headers.set('x-edge-mode', 'cache'); headers.set('x-edge-cache', 'MISS'); headers.set('x-runner5-opt', CACHE_VERSION);
    const staticAsset = isStaticPath(incoming.pathname);
    if (response.status === 200 && !headers.has('set-cookie')) {
      headers.set('cache-control', staticAsset ? 'public, max-age=86400, stale-while-revalidate=604800' : 'public, max-age=60, stale-while-revalidate=600');
      const cacheable = new Response(response.body, { status: response.status, statusText: response.statusText, headers });
      ctx.waitUntil(cache.put(key, cacheable.clone())); return cacheable;
    }
    return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
  },
};
