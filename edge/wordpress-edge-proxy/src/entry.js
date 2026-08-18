import { WorkerEntrypoint } from 'cloudflare:workers';
import worker, { isPublicHtmlCacheCandidate } from './index.js';
import { StaticResponsiveImageRewriter, StaticImagePreloadRewriter } from './responsive-images.js';

const R2_ORIGIN = 'https://pub-f6e5190178814cd5be8f1eb531f1a164.r2.dev';
const R2_HOST = 'pub-f6e5190178814cd5be8f1eb531f1a164.r2.dev';
const PURGE_PATH = '/__runner3/cache/purge';
const HTML_CACHE_TAG = 'runner3-html';
const KEY_PATH = '/wp-json/runner3/v1/edge-key';

class HeadResourceHints {
  element(element) {
    element.prepend(
      `<link rel="dns-prefetch" href="//${R2_HOST}"><link rel="preconnect" href="${R2_ORIGIN}" crossorigin>`,
      { html: true },
    );
  }
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

function pemToDer(pem) {
  const base64 = String(pem || '')
    .replace(/-----BEGIN PUBLIC KEY-----/g, '')
    .replace(/-----END PUBLIC KEY-----/g, '')
    .replace(/\s+/g, '');
  if (!base64) throw new Error('public_key_empty');
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function base64Bytes(value) {
  const binary = atob(String(value || ''));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function fetchSigningKey(env) {
  const origin = new URL(env.ORIGIN || 'https://runner3-factory-smoke-2.wasmer.app');
  const keyUrl = new URL(KEY_PATH, origin);
  const response = await fetch(keyUrl, {
    headers: { Accept: 'application/json' },
    cf: { cacheEverything: true, cacheTtl: 86400 },
  });
  if (!response.ok) throw new Error(`signing_key_http_${response.status}`);
  const data = await response.json();
  if (!data || !data.public_key || !data.key_id) throw new Error('signing_key_invalid');
  return data;
}

async function verifyPurgeSignature(request, env, rawBody) {
  const timestampText = request.headers.get('X-Runner3-Timestamp') || '';
  const signatureText = request.headers.get('X-Runner3-Signature') || '';
  const keyId = request.headers.get('X-Runner3-Key-Id') || '';
  const timestamp = Number(timestampText);
  if (!Number.isInteger(timestamp) || Math.abs(Math.floor(Date.now() / 1000) - timestamp) > 300) {
    return { ok: false, error: 'timestamp_invalid' };
  }
  if (!signatureText || !keyId || rawBody.length > 32768) return { ok: false, error: 'signature_missing' };

  try {
    const keyData = await fetchSigningKey(env);
    if (String(keyData.key_id) !== keyId) return { ok: false, error: 'key_id_mismatch' };
    const key = await crypto.subtle.importKey(
      'spki',
      pemToDer(keyData.public_key),
      { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
      false,
      ['verify'],
    );
    const message = new TextEncoder().encode(`${timestampText}\n${rawBody}`);
    const valid = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, base64Bytes(signatureText), message);
    return valid ? { ok: true } : { ok: false, error: 'signature_invalid' };
  } catch (error) {
    return { ok: false, error: String(error?.message || 'signature_verify_failed').slice(0, 120) };
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
