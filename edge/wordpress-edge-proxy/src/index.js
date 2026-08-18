const DEFAULT_ORIGIN = 'https://runner3-factory-smoke-2.wasmer.app';

const STATIC_ASSET_RE = /\.(?:css|js|mjs|png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|otf|eot|mp4|webm|pdf)(?:$|\?)/i;
const DYNAMIC_PREFIXES = ['/wp-json/', '/xmlrpc.php', '/feed/', '/comments/feed/'];
const IMAGE_WIDTHS = [360, 480, 640, 960, 1200];
const IMAGE_SOURCE_HOSTS = new Set([
  'pub-f6e5190178814cd5be8f1eb531f1a164.r2.dev',
  'images.unsplash.com',
]);

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

function parseAllowedImageSource(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || !IMAGE_SOURCE_HOSTS.has(url.hostname)) return null;
    if (!/\.(?:jpe?g|png|gif|webp|avif)(?:$|\?)/i.test(`${url.pathname}${url.search}`)) return null;
    return url;
  } catch {
    return null;
  }
}

function edgeImageUrl(publicOrigin, source, width) {
  const url = new URL(`/_img/${width}`, publicOrigin);
  url.searchParams.set('url', source);
  return url.toString();
}

function responsiveSrcset(publicOrigin, source) {
  return IMAGE_WIDTHS.map((width) => `${edgeImageUrl(publicOrigin, source, width)} ${width}w`).join(', ');
}

function negotiatedImageFormat(accept) {
  if (/image\/avif/i.test(accept || '')) return 'avif';
  if (/image\/webp/i.test(accept || '')) return 'webp';
  return 'webp';
}

async function serveTransformedImage(request, incoming) {
  const method = request.method.toUpperCase();
  if (!['GET', 'HEAD'].includes(method)) return new Response('Method not allowed', { status: 405 });

  const match = incoming.pathname.match(/^\/_img\/(\d+)$/);
  const width = Number(match?.[1] || 0);
  if (!IMAGE_WIDTHS.includes(width)) return new Response('Unsupported image width', { status: 400 });

  const source = parseAllowedImageSource(incoming.searchParams.get('url'));
  if (!source) return new Response('Invalid image source', { status: 400 });

  const format = negotiatedImageFormat(request.headers.get('Accept'));
  const imageRequest = new Request(source.toString(), {
    method: 'GET',
    headers: {
      Accept: request.headers.get('Accept') || 'image/avif,image/webp,image/*,*/*;q=0.8',
    },
  });

  let transformed;
  try {
    transformed = await fetch(imageRequest, {
      cf: {
        image: {
          fit: 'scale-down',
          width,
          quality: 78,
          format,
        },
        cacheEverything: true,
        cacheTtl: 86400,
      },
    });
  } catch {
    transformed = null;
  }

  if (!transformed?.ok) {
    const fallback = await fetch(imageRequest, { cf: { cacheEverything: true, cacheTtl: 86400 } });
    const fallbackHeaders = new Headers(fallback.headers);
    fallbackHeaders.set('Cache-Control', 'public, max-age=31536000, immutable');
    fallbackHeaders.set('X-Edge-Proxy', 'cloudflare-worker');
    fallbackHeaders.set('X-Edge-Mode', 'image-fallback');
    return new Response(method === 'HEAD' ? null : fallback.body, {
      status: fallback.status,
      statusText: fallback.statusText,
      headers: fallbackHeaders,
    });
  }

  const headers = new Headers(transformed.headers);
  headers.set('Cache-Control', 'public, max-age=31536000, immutable');
  headers.set('Vary', 'Accept');
  headers.set('X-Edge-Proxy', 'cloudflare-worker');
  headers.set('X-Edge-Mode', 'image-transform');
  headers.set('X-Edge-Image-Width', String(width));
  headers.set('X-Edge-Image-Format', format);
  return new Response(method === 'HEAD' ? null : transformed.body, {
    status: transformed.status,
    statusText: transformed.statusText,
    headers,
  });
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

class ResponsiveImageRewriter {
  constructor(publicOrigin) {
    this.publicOrigin = publicOrigin;
  }
  element(element) {
    const source = parseAllowedImageSource(element.getAttribute('src'));
    if (!source) return;
    const sourceUrl = source.toString();
    element.setAttribute('src', edgeImageUrl(this.publicOrigin, sourceUrl, 640));
    element.setAttribute('srcset', responsiveSrcset(this.publicOrigin, sourceUrl));
    if (!element.getAttribute('sizes')) element.setAttribute('sizes', '(max-width: 767px) 92vw, 1100px');
  }
}

class ResponsiveSourceRewriter {
  constructor(publicOrigin) {
    this.publicOrigin = publicOrigin;
  }
  element(element) {
    const raw = element.getAttribute('src') || element.getAttribute('srcset');
    if (!raw) return;
    const first = raw.split(',')[0].trim().split(/\s+/)[0];
    const source = parseAllowedImageSource(first);
    if (!source) return;
    const sourceUrl = source.toString();
    if (element.getAttribute('src')) element.setAttribute('src', edgeImageUrl(this.publicOrigin, sourceUrl, 640));
    element.setAttribute('srcset', responsiveSrcset(this.publicOrigin, sourceUrl));
  }
}

class ImagePreloadRewriter {
  constructor(publicOrigin) {
    this.publicOrigin = publicOrigin;
  }
  element(element) {
    const source = parseAllowedImageSource(element.getAttribute('href'));
    if (!source) return;
    const sourceUrl = source.toString();
    element.setAttribute('href', edgeImageUrl(this.publicOrigin, sourceUrl, 640));
    element.setAttribute('imagesrcset', responsiveSrcset(this.publicOrigin, sourceUrl));
    if (!element.getAttribute('imagesizes')) element.setAttribute('imagesizes', '(max-width: 767px) 80vw, 580px');
    element.setAttribute('fetchpriority', 'high');
  }
}

class PublicRobotsRewriter {
  element(element) {
    element.setAttribute('content', 'index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1');
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

    // Dedicated, allowlisted image transformation path. Keeping it separate from
    // source R2 URLs prevents resize loops and avoids turning the Worker into an SSRF proxy.
    if (incoming.pathname.startsWith('/_img/')) {
      return serveTransformedImage(request, incoming);
    }

    // Keep public crawl policy explicit at the edge. The Wasmer origin remains a
    // staging/control origin and may intentionally advertise noindex.
    if (incoming.pathname === '/robots.txt' && ['GET', 'HEAD'].includes(method)) {
      const body = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /wp-admin/',
        'Disallow: /wp-login.php',
        'Disallow: /wp-json/',
        `Sitemap: ${incoming.origin}/wp-sitemap.xml`,
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

    // Keep WordPress authentication/admin control on the native origin. This avoids
    // caching or proxy-cookie ambiguity on sensitive control paths.
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

    // `cache: no-store` is the hard bypass path for authenticated/dynamic traffic.
    // Do not merely set cacheTtl=0: an existing cached object may still be reused.
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
      // Public edge pages are the canonical browsable surface. Do not inherit the
      // staging origin's noindex header.
      if (!staticAsset) outHeaders.delete('X-Robots-Tag');
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
        ['form[action]', 'action'],
        ['meta[content]', 'content'],
      ];
      let rewriter = new HTMLRewriter();
      for (const [selector, attribute] of selectors) {
        rewriter = rewriter.on(selector, new AttributeRewriter(attribute, origin, publicOrigin));
      }
      rewriter = rewriter
        .on('img[src]', new ResponsiveImageRewriter(publicOrigin))
        .on('source[src], source[srcset]', new ResponsiveSourceRewriter(publicOrigin))
        .on('link[rel="preload"][as="image"]', new ImagePreloadRewriter(publicOrigin));
      if (!bypass) {
        rewriter = rewriter.on('meta[name="robots" i]', new PublicRobotsRewriter());
      }
      response = rewriter.transform(response);
    }

    return response;
  },
};
