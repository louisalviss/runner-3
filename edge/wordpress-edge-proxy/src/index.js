const DEFAULT_ORIGIN = 'https://runner3-factory-smoke-2.wasmer.app';

const STATIC_ASSET_RE = /\.(?:css|js|mjs|png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|otf|eot|mp4|webm|pdf)(?:$|\?)/i;
const DYNAMIC_PREFIXES = ['/wp-json/', '/xmlrpc.php', '/feed/', '/comments/feed/'];

function hasDynamicQuery(url) {
  return ['preview', 'preview_id', 'rest_route', 's'].some((key) => url.searchParams.has(key));
}

function isDynamicPath(pathname) {
  if (pathname === '/wp-login.php' || pathname.startsWith('/wp-admin/')) return true;
  return DYNAMIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isStaticAsset(url) {
  return STATIC_ASSET_RE.test(url.pathname) || url.pathname.startsWith('/wp-content/') || url.pathname.startsWith('/wp-includes/');
}

function rewriteInternal(value, origin, publicOrigin) {
  if (!value) return value;
  const originHost = origin.host.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return value
    .split(origin.origin).join(publicOrigin)
    .replace(new RegExp(`//${originHost}`, 'g'), `//${new URL(publicOrigin).host}`);
}

class AttributeRewriter {
  constructor(attribute, origin, publicOrigin) {
    this.attribute = attribute;
    this.origin = origin;
    this.publicOrigin = publicOrigin;
  }
  element(element) {
    const current = element.getAttribute(this.attribute);
    if (!current) return;
    const next = rewriteInternal(current, this.origin, this.publicOrigin);
    if (next !== current) element.setAttribute(this.attribute, next);
  }
}

function rewriteLocation(headers, origin, publicOrigin) {
  const location = headers.get('Location');
  if (!location) return;
  headers.set('Location', rewriteInternal(location, origin, publicOrigin));
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    const origin = new URL(env.ORIGIN || DEFAULT_ORIGIN);
    const target = new URL(incoming.pathname + incoming.search, origin);
    const method = request.method.toUpperCase();

    // Keep robots crawlable so crawlers can observe the X-Robots-Tag noindex
    // directive applied by the entry wrapper on public HTML.
    if (incoming.pathname === '/robots.txt' && ['GET', 'HEAD'].includes(method)) {
      const body = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /wp-admin/',
        'Disallow: /wp-login.php',
        'Disallow: /wp-json/',
        '',
      ].join('\n');
      return new Response(method === 'HEAD' ? null : body, {
        status: 200,
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'public, max-age=300, s-maxage=3600',
          'X-Edge-Proxy': 'cloudflare-worker',
          'X-Edge-Mode': 'robots',
        },
      });
    }

    // Keep WordPress authentication/admin control on the native origin.
    if (incoming.pathname === '/wp-login.php' || incoming.pathname.startsWith('/wp-admin/')) {
      return Response.redirect(target.toString(), 307);
    }

    const cookiePresent = request.headers.has('Cookie');
    const bypass = !['GET', 'HEAD'].includes(method) || cookiePresent || isDynamicPath(incoming.pathname) || hasDynamicQuery(incoming);
    const staticAsset = isStaticAsset(incoming);
    const ttl = staticAsset ? 86400 : 300;

    const headers = new Headers(request.headers);
    headers.delete('Host');
    headers.set('X-Forwarded-Host', incoming.host);
    headers.set('X-Forwarded-Proto', 'https');

    const upstreamRequest = new Request(target.toString(), {
      method,
      headers,
      redirect: 'manual',
    });

    const upstream = bypass
      ? await fetch(upstreamRequest, { cache: 'no-store' })
      : await fetch(upstreamRequest, {
          cf: {
            cacheEverything: true,
            cacheTtl: ttl,
            cacheTtlByStatus: {
              '200-299': ttl,
              '301-302': 300,
              '404': 5,
              '500-599': 0,
            },
          },
        });

    const outHeaders = new Headers(upstream.headers);
    rewriteLocation(outHeaders, origin, incoming.origin);
    outHeaders.set('X-Edge-Proxy', 'cloudflare-worker');
    outHeaders.set('X-Edge-Mode', bypass ? 'bypass' : (staticAsset ? 'static-cache' : 'html-cache'));
    outHeaders.set('X-Upstream-CF-Cache-Status', upstream.headers.get('CF-Cache-Status') || 'NONE');
    const stamp = upstream.headers.get('X-Edge-Origin-Stamp');
    if (stamp) outHeaders.set('X-Upstream-Origin-Stamp', stamp);

    if (!bypass) {
      outHeaders.set(
        'Cache-Control',
        staticAsset
          ? 'public, max-age=3600, s-maxage=86400, stale-while-revalidate=300'
          : 'public, max-age=60, s-maxage=300, stale-while-revalidate=60, stale-if-error=600',
      );
    }

    let response = new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: outHeaders,
    });

    const contentType = outHeaders.get('Content-Type') || '';
    if (method !== 'HEAD' && /text\/html/i.test(contentType)) {
      const publicOrigin = incoming.origin;
      const selectors = [
        ['a[href]', 'href'],
        ['link[href]', 'href'],
        ['script[src]', 'src'],
        ['img[src]', 'src'],
        ['img[srcset]', 'srcset'],
        ['source[src]', 'src'],
        ['source[srcset]', 'srcset'],
        ['form[action]', 'action'],
        ['meta[content]', 'content'],
      ];
      let rewriter = new HTMLRewriter();
      for (const [selector, attribute] of selectors) {
        rewriter = rewriter.on(selector, new AttributeRewriter(attribute, origin, publicOrigin));
      }
      response = rewriter.transform(response);
    }

    return response;
  },
};
