import { SNAPSHOTS, SNAPSHOT_BUILT_AT } from './snapshot.generated.js';

const DEFAULT_ORIGIN = 'https://runner3-factory-smoke-2.wasmer.app';

const STATIC_ASSET_RE = /\.(?:css|js|mjs|png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|otf|eot|mp4|webm|pdf)(?:$|\?)/i;
const DYNAMIC_PREFIXES = ['/wp-json/', '/xmlrpc.php', '/feed/', '/comments/feed/'];
const PRIVATE_COOKIE_RE = /(?:^|;\s*)(?:wordpress_logged_in_|wordpress_sec_|wp-postpass_|comment_author_)/i;

function hasDynamicQuery(url) {
  return [
    'preview',
    'preview_id',
    'preview_nonce',
    'rest_route',
    's',
    'customize_changeset_uuid',
    'customize_theme',
    'post_type',
    'paged',
    'author',
  ].some((key) => url.searchParams.has(key));
}

function isDynamicPath(pathname) {
  if (pathname === '/wp-login.php' || pathname.startsWith('/wp-admin/')) return true;
  if (pathname === '/wp-cron.php' || pathname === '/wp-comments-post.php') return true;
  return DYNAMIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

function isStaticAsset(url) {
  return STATIC_ASSET_RE.test(url.pathname) || url.pathname.startsWith('/wp-content/') || url.pathname.startsWith('/wp-includes/');
}

function hasPrivateCookie(request) {
  const cookie = request.headers.get('Cookie') || '';
  return PRIVATE_COOKIE_RE.test(cookie);
}

export function isPublicHtmlCacheCandidate(request) {
  const incoming = new URL(request.url);
  const method = request.method.toUpperCase();
  if (!['GET', 'HEAD'].includes(method)) return false;
  if (incoming.pathname === '/robots.txt' || isStaticAsset(incoming)) return false;
  if (isDynamicPath(incoming.pathname) || hasDynamicQuery(incoming)) return false;
  if (hasPrivateCookie(request)) return false;
  return true;
}

function normalizeSnapshotPath(pathname) {
  const path = pathname || '/';
  if (path === '/' || path.endsWith('/') || /\.[^/]+$/.test(path)) return path;
  return `${path}/`;
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

function snapshotResponse(method, pathname, fallback = false) {
  const key = normalizeSnapshotPath(pathname);
  const body = SNAPSHOTS[key] ?? SNAPSHOTS[pathname];
  if (typeof body !== 'string') return null;
  return new Response(method === 'HEAD' ? null : body, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=UTF-8',
      'Cache-Control': fallback
        ? 'no-store'
        : 'public, max-age=60, stale-while-revalidate=30, stale-if-error=600',
      'X-Edge-Proxy': 'cloudflare-worker',
      'X-Edge-Mode': fallback ? 'snapshot-fallback' : 'snapshot',
      'X-Edge-Snapshot': fallback ? 'FALLBACK' : 'HIT',
      'X-Upstream-CF-Cache-Status': 'SNAPSHOT',
      ...(SNAPSHOT_BUILT_AT ? { 'X-Edge-Snapshot-Built-At': SNAPSHOT_BUILT_AT } : {}),
    },
  });
}

async function fetchOrigin(request, target, incoming, method, bypass, staticAsset) {
  const headers = new Headers(request.headers);
  headers.delete('Host');
  headers.set('X-Forwarded-Host', incoming.host);
  headers.set('X-Forwarded-Proto', 'https');

  const upstreamRequest = new Request(target.toString(), {
    method,
    headers,
    redirect: 'manual',
  });

  if (bypass) return fetch(upstreamRequest, { cache: 'no-store' });
  if (!staticAsset) return fetch(upstreamRequest, { cache: 'no-store' });

  return fetch(upstreamRequest, {
    cf: {
      cacheEverything: true,
      cacheTtl: 86400,
      cacheTtlByStatus: {
        '200-299': 86400,
        '301-302': 300,
        '404': 5,
        '500-599': 0,
      },
    },
  });
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    const origin = new URL(env.ORIGIN || DEFAULT_ORIGIN);
    const target = new URL(incoming.pathname + incoming.search, origin);
    const method = request.method.toUpperCase();

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

    if (incoming.pathname === '/wp-login.php' || incoming.pathname.startsWith('/wp-admin/')) {
      return Response.redirect(target.toString(), 307);
    }

    const bypass = !['GET', 'HEAD'].includes(method) || hasPrivateCookie(request) || isDynamicPath(incoming.pathname) || hasDynamicQuery(incoming);
    const staticAsset = isStaticAsset(incoming);

    let upstream = null;
    let snapshotHit = false;
    let snapshotFallback = false;

    // Anonymous public HTML is served directly from the snapshot bundled into the
    // Worker. This removes the WordPress/Wasmer round-trip even on a cold edge PoP.
    if (!bypass && !staticAsset) {
      const snapshot = snapshotResponse(method, incoming.pathname);
      if (snapshot) {
        upstream = snapshot;
        snapshotHit = true;
      }
    }

    if (!upstream) {
      try {
        upstream = await fetchOrigin(request, target, incoming, method, bypass, staticAsset);
        if (!bypass && !staticAsset && upstream.status >= 500) {
          const fallback = snapshotResponse(method, incoming.pathname, true);
          if (fallback) {
            upstream = fallback;
            snapshotFallback = true;
          }
        }
      } catch (error) {
        const fallback = !bypass && !staticAsset ? snapshotResponse(method, incoming.pathname, true) : null;
        if (!fallback) throw error;
        upstream = fallback;
        snapshotFallback = true;
      }
    }

    const outHeaders = new Headers(upstream.headers);
    rewriteLocation(outHeaders, origin, incoming.origin);
    outHeaders.set('X-Edge-Proxy', 'cloudflare-worker');
    outHeaders.set(
      'X-Edge-Mode',
      snapshotHit ? 'snapshot' : (snapshotFallback ? 'snapshot-fallback' : (bypass ? 'bypass' : (staticAsset ? 'static-cache' : 'html-origin'))),
    );
    outHeaders.set('X-Upstream-CF-Cache-Status', snapshotHit || snapshotFallback ? 'SNAPSHOT' : (upstream.headers.get('CF-Cache-Status') || 'NONE'));

    if (snapshotHit) {
      outHeaders.set('Cache-Control', 'public, max-age=60, stale-while-revalidate=30, stale-if-error=600');
      outHeaders.set('X-Edge-Snapshot', 'HIT');
      if (SNAPSHOT_BUILT_AT) outHeaders.set('X-Edge-Snapshot-Built-At', SNAPSHOT_BUILT_AT);
    } else if (snapshotFallback) {
      outHeaders.set('Cache-Control', 'no-store');
      outHeaders.set('X-Edge-Snapshot', 'FALLBACK');
      if (SNAPSHOT_BUILT_AT) outHeaders.set('X-Edge-Snapshot-Built-At', SNAPSHOT_BUILT_AT);
    } else if (!bypass) {
      outHeaders.set(
        'Cache-Control',
        staticAsset
          ? 'public, max-age=3600, s-maxage=86400, stale-while-revalidate=300'
          : 'public, max-age=60, stale-while-revalidate=30, stale-if-error=600',
      );
    } else {
      outHeaders.set('Cache-Control', 'private, no-store');
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
