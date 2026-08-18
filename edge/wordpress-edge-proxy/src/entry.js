import { WorkerEntrypoint } from 'cloudflare:workers';
import worker, { isPublicHtmlCacheCandidate } from './index.js';
import { StaticResponsiveImageRewriter, StaticImagePreloadRewriter } from './responsive-images.js';

const R2_ORIGIN = 'https://pub-f6e5190178814cd5be8f1eb531f1a164.r2.dev';
const R2_HOST = 'pub-f6e5190178814cd5be8f1eb531f1a164.r2.dev';
const PURGE_PATH = '/__runner3/cache/purge';
const HTML_CACHE_TAG = 'runner3-html';

class HeadResourceHints {
  element(element) {
    element.prepend(
      `<link rel="dns-prefetch" href="//${R2_HOST}"><link rel="preconnect" href="${R2_ORIGIN}" crossorigin>`,
      { html: true },
    );
  }
}

function safeEqual(a, b) {
  const left = String(a || '');
  const right = String(b || '');
  if (!left || left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i += 1) diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  return diff === 0;
}

function bearerToken(request) {
  const value = request.headers.get('Authorization') || '';
  const match = value.match(/^Bearer\s+(.+)$/i);
  return match ? match[1].trim() : '';
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Edge-Proxy': 'cloudflare-worker',
    },
  });
}

async function decorateFrontend(request, response) {
  const contentType = response.headers.get('Content-Type') || '';
  if (!/text\/html/i.test(contentType)) return response;

  const headers = new Headers(response.headers);
  headers.delete('Content-Length');
  headers.set('X-Robots-Tag', 'noindex, nofollow, noarchive, nosnippet');
  headers.append('Link', `<${R2_ORIGIN}>; rel=preconnect; crossorigin`);

  let htmlResponse = new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });

  if (request.method.toUpperCase() !== 'HEAD') {
    htmlResponse = new HTMLRewriter()
      .on('head', new HeadResourceHints())
      .on('img[src]', new StaticResponsiveImageRewriter())
      .on('link[rel="preload"][as="image"]', new StaticImagePreloadRewriter())
      .transform(htmlResponse);
  }
  return htmlResponse;
}

function cacheableHtmlResponse(response) {
  const contentType = response.headers.get('Content-Type') || '';
  if (!/text\/html/i.test(contentType)) return false;
  if (response.status < 200 || response.status >= 400) return false;
  if ((response.headers.get('X-Edge-Mode') || '') === 'snapshot-fallback') return false;
  if (response.headers.has('Set-Cookie')) return false;
  return true;
}

async function publicHtmlResponse(request, env, ctx) {
  let response = await worker.fetch(request, env, ctx);
  response = await decorateFrontend(request, response);
  const headers = new Headers(response.headers);
  headers.delete('Content-Length');

  if (!cacheableHtmlResponse(response)) {
    headers.set('Cache-Control', 'no-store');
    headers.delete('Cloudflare-CDN-Cache-Control');
    headers.delete('Cache-Tag');
    headers.set('X-Edge-Cache-Policy', 'bypass');
  } else {
    // Browser keeps a short copy; Workers Caching keeps the reusable HTML at edge.
    headers.set('Cache-Control', 'public, max-age=60, stale-while-revalidate=30, stale-if-error=600');
    headers.set('Cloudflare-CDN-Cache-Control', 'public, max-age=86400, stale-while-revalidate=3600, stale-if-error=604800');
    headers.set('Cache-Tag', HTML_CACHE_TAG);
    headers.set('X-Edge-Cache-Policy', 'workers-caching');
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export class PublicHtml extends WorkerEntrypoint {
  async fetch(request) {
    return publicHtmlResponse(request, this.env, this.ctx);
  }

  async purgeHtml() {
    const result = await this.ctx.cache.purge({ tags: [HTML_CACHE_TAG] });
    return { ok: true, result };
  }
}

function normalizedPrewarmPaths(value) {
  const raw = Array.isArray(value) ? value : [];
  const paths = ['/'];
  for (const item of raw.slice(0, 12)) {
    if (typeof item !== 'string') continue;
    try {
      const parsed = new URL(item, 'https://runner3.invalid');
      const path = `${parsed.pathname}${parsed.search}`;
      if (!path.startsWith('/wp-admin') && path !== PURGE_PATH && !paths.includes(path)) paths.push(path);
    } catch (_) {
      // Ignore malformed prewarm paths. Purge correctness does not depend on warming.
    }
  }
  return paths.slice(0, 8);
}

async function handlePurge(request, env, ctx) {
  if (request.method.toUpperCase() !== 'POST') return jsonResponse({ ok: false, error: 'method_not_allowed' }, 405);
  const expected = String(env.RUNNER3_CACHE_PURGE_SECRET || '');
  if (!expected) return jsonResponse({ ok: false, error: 'purge_secret_unconfigured' }, 503);
  if (!safeEqual(bearerToken(request), expected)) return jsonResponse({ ok: false, error: 'unauthorized' }, 401);

  let body = {};
  try {
    body = await request.json();
  } catch (_) {
    body = {};
  }

  const purge = await ctx.exports.PublicHtml.purgeHtml();
  const incoming = new URL(request.url);
  const paths = normalizedPrewarmPaths(body.urls);
  const warmed = [];
  for (const path of paths) {
    try {
      const url = new URL(path, incoming.origin);
      const warm = await ctx.exports.PublicHtml.fetch(new Request(url, { method: 'GET' }));
      warmed.push({ path: url.pathname, status: warm.status });
    } catch (_) {
      warmed.push({ path, status: 0 });
    }
  }

  return jsonResponse({
    ok: true,
    purged: Boolean(purge && purge.ok),
    tag: HTML_CACHE_TAG,
    reason: typeof body.reason === 'string' ? body.reason.slice(0, 120) : 'wordpress-change',
    warmed,
  });
}

export default {
  async fetch(request, env, ctx) {
    const incoming = new URL(request.url);
    if (incoming.pathname === PURGE_PATH) return handlePurge(request, env, ctx);

    if (isPublicHtmlCacheCandidate(request)) {
      return ctx.exports.PublicHtml.fetch(request);
    }

    const response = await worker.fetch(request, env, ctx);
    return decorateFrontend(request, response);
  },
};
