import { WorkerEntrypoint } from 'cloudflare:workers';
import worker, { isPublicHtmlCacheCandidate } from './index.js';
import { StaticResponsiveImageRewriter, StaticImagePreloadRewriter } from './responsive-images.js';

const PURGE_PATH = '/__runner3/cache/purge';
const HTML_CACHE_TAG = 'runner3-html';
const LCP_R2_PREFIX = '/__runner3/r2-image/';
const LCP_R2_NAME_RE = /^offset-demo-01-w(?:360|480|640)\.webp$/;
const LCP_R2_KEY_PREFIX = 'sites/runner3-factory-smoke-2/responsive-v2/';

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
  // Proven Site1 mobile path uses an inline LCP source and a same-origin desktop
  // image. Drop inherited/explicit Link hints so no r2.dev preconnect competes
  // on the critical path.
  headers.delete('Link');
  headers.set('X-Robots-Tag', 'noindex, nofollow, noarchive, nosnippet');

  let htmlResponse = new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });

  if (request.method.toUpperCase() !== 'HEAD') {
    htmlResponse = new HTMLRewriter()
      .on('img[src]', new StaticResponsiveImageRewriter())
      .on('link[rel="preload"][as="image"]', new StaticImagePreloadRewriter())
      .transform(htmlResponse);
  }
  return htmlResponse;
}

function cacheableHtmlResponse(response) {
  const contentType = response.headers.get('Content-Type') || '';
  return /text\/html/i.test(contentType)
    && response.status >= 200
    && response.status < 400
    && (response.headers.get('X-Edge-Mode') || '') !== 'snapshot-fallback'
    && !response.headers.has('Set-Cookie');
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

// Kept only for the legacy purge endpoint while the site is transitioning away
// from full-page Workers Caching. Public anonymous traffic no longer enters this
// cached service binding, so an old cached html-origin response cannot shadow a
// newly deployed snapshot.
export class PublicHtml extends WorkerEntrypoint {
  async fetch(request) {
    return publicHtmlResponse(request, this.env, this.ctx);
  }

  async purgeHtml() {
    const result = await this.ctx.cache.purge({ tags: [HTML_CACHE_TAG] });
    return { ok: true, result };
  }
}

async function directPublicResponse(request, env, ctx) {
  let response = await worker.fetch(request, env, ctx);
  response = await decorateFrontend(request, response);
  const headers = new Headers(response.headers);
  headers.delete('Content-Length');
  headers.delete('Cache-Tag');
  headers.delete('Cloudflare-CDN-Cache-Control');

  const mode = String(headers.get('X-Edge-Mode') || '');
  if (mode === 'snapshot') {
    headers.set('Cache-Control', 'public, max-age=60, stale-while-revalidate=30, stale-if-error=600');
    headers.set('Cloudflare-CDN-Cache-Control', 'no-store');
    headers.set('X-Edge-Cache-Policy', 'snapshot-direct');
  } else if (mode === 'snapshot-fallback') {
    headers.set('Cache-Control', 'no-store');
    headers.set('Cloudflare-CDN-Cache-Control', 'no-store');
    headers.set('X-Edge-Cache-Policy', 'snapshot-fallback');
  } else {
    headers.set('X-Edge-Cache-Policy', 'origin-direct');
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function sameOriginLcpImage(request, env, incoming) {
  const method = request.method.toUpperCase();
  if (!['GET', 'HEAD'].includes(method)) {
    return new Response('Method Not Allowed', {
      status: 405,
      headers: { Allow: 'GET, HEAD' },
    });
  }

  const name = incoming.pathname.slice(LCP_R2_PREFIX.length);
  if (!LCP_R2_NAME_RE.test(name)) return new Response('Not Found', { status: 404 });

  const key = `${LCP_R2_KEY_PREFIX}${name}`;
  const object = method === 'HEAD'
    ? await env.MEDIA_BUCKET.head(key)
    : await env.MEDIA_BUCKET.get(key);

  if (!object) return new Response('Not Found', { status: 404 });

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('ETag', object.httpEtag);
  headers.set('Content-Type', object.httpMetadata?.contentType || 'image/webp');
  headers.set('Cache-Control', 'public, max-age=31536000, immutable');
  headers.set('X-Runner3-LCP', 'r2-binding-same-origin');
  if (Number.isFinite(object.size)) headers.set('Content-Length', String(object.size));

  return new Response(method === 'HEAD' ? null : object.body, {
    status: 200,
    headers,
  });
}

function base64Bytes(value) {
  const binary = atob(String(value || ''));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function verifyPurgeSignature(request, env, rawBody) {
  const timestampText = request.headers.get('X-Runner3-Timestamp') || '';
  const signatureText = request.headers.get('X-Runner3-Signature') || '';
  const secret = String(env.RUNNER3_CACHE_PURGE_SECRET || '');
  const timestamp = Number(timestampText);

  if (!secret) return { ok: false, error: 'auth_unconfigured' };
  if (!Number.isInteger(timestamp) || Math.abs(Math.floor(Date.now() / 1000) - timestamp) > 300) {
    return { ok: false, error: 'timestamp_invalid' };
  }
  if (!signatureText || rawBody.length > 32768) {
    return { ok: false, error: 'signature_missing' };
  }

  try {
    const key = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(secret),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['verify'],
    );
    const valid = await crypto.subtle.verify(
      'HMAC',
      key,
      base64Bytes(signatureText),
      new TextEncoder().encode(`${timestampText}\n${rawBody}`),
    );
    return valid
      ? { ok: true, algorithm: 'HMAC-SHA256' }
      : { ok: false, error: 'signature_invalid' };
  } catch (error) {
    return {
      ok: false,
      error: String(error?.message || 'signature_verify_failed').slice(0, 120),
    };
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
      if (!path.startsWith('/wp-admin')
        && path !== PURGE_PATH
        && !paths.includes(path)) {
        paths.push(path);
      }
    } catch (_) {}
  }
  return paths.slice(0, 8);
}

async function warmAndVerify(ctx, incoming, path) {
  try {
    const url = new URL(path, incoming.origin);
    const first = await ctx.exports.PublicHtml.fetch(new Request(url, { method: 'GET' }));
    await first.arrayBuffer();
    const second = await ctx.exports.PublicHtml.fetch(new Request(url, { method: 'GET' }));
    await second.arrayBuffer();
    const status = String(second.headers.get('CF-Cache-Status') || '').toUpperCase();
    const age = second.headers.get('Age');
    return {
      path: url.pathname,
      status: second.status,
      cacheStatus: status || null,
      age,
      verified: second.status === 200 && (status === 'HIT' || age !== null),
    };
  } catch (_) {
    return {
      path,
      status: 0,
      cacheStatus: null,
      age: null,
      verified: false,
    };
  }
}

async function handlePurge(request, env, ctx) {
  if (request.method.toUpperCase() !== 'POST') {
    return jsonResponse({ ok: false, error: 'method_not_allowed' }, 405);
  }

  const rawBody = await request.text();
  const auth = await verifyPurgeSignature(request, env, rawBody);
  if (!auth.ok) return jsonResponse({ ok: false, error: auth.error || 'unauthorized' }, 401);

  let body = {};
  try {
    body = rawBody ? JSON.parse(rawBody) : {};
  } catch (_) {
    return jsonResponse({ ok: false, error: 'invalid_json' }, 400);
  }

  const purge = await ctx.exports.PublicHtml.purgeHtml();
  const incoming = new URL(request.url);
  const paths = normalizedPrewarmPaths(body.urls);
  const warmed = [];
  for (const path of paths) warmed.push(await warmAndVerify(ctx, incoming, path));

  const cacheVerified = warmed.length > 0 && warmed.every((row) => row.verified);
  return jsonResponse({
    ok: true,
    purged: Boolean(purge && purge.ok),
    cache_verified: cacheVerified,
    signing_algorithm: auth.algorithm,
    tag: HTML_CACHE_TAG,
    reason: typeof body.reason === 'string'
      ? body.reason.slice(0, 120)
      : 'wordpress-change',
    warmed,
  });
}

export default {
  async fetch(request, env, ctx) {
    const incoming = new URL(request.url);

    if (incoming.pathname === PURGE_PATH) {
      return handlePurge(request, env, ctx);
    }
    if (incoming.pathname.startsWith(LCP_R2_PREFIX)) {
      return sameOriginLcpImage(request, env, incoming);
    }
    if (isPublicHtmlCacheCandidate(request)) {
      return directPublicResponse(request, env, ctx);
    }

    const response = await worker.fetch(request, env, ctx);
    return decorateFrontend(request, response);
  },
};
