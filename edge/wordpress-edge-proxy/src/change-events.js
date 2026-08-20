const EVENT_API_PREFIX = '/__runner3/events/';
const ALLOWED_EVENTS = new Set([
  'post_published',
  'post_updated',
  'post_deleted',
  'terms_changed',
  'full_refresh',
]);
const MAX_BODY_BYTES = 16 * 1024;
const MAX_PULL = 20;
const MAX_ACK = 50;
const SIGNATURE_TTL_SECONDS = 300;

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

function base64Bytes(value) {
  const binary = atob(String(value || ''));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

async function verifySignature(request, env, rawBody) {
  const timestampText = request.headers.get('X-Runner3-Timestamp') || '';
  const signatureText = request.headers.get('X-Runner3-Signature') || '';
  const secret = String(env.RUNNER3_CACHE_PURGE_SECRET || '');
  const timestamp = Number(timestampText);

  if (!secret) return { ok: false, error: 'auth_unconfigured' };
  if (!Number.isInteger(timestamp) || Math.abs(Math.floor(Date.now() / 1000) - timestamp) > SIGNATURE_TTL_SECONDS) {
    return { ok: false, error: 'timestamp_invalid' };
  }
  if (!signatureText) return { ok: false, error: 'signature_missing' };
  if (new TextEncoder().encode(rawBody).byteLength > MAX_BODY_BYTES) return { ok: false, error: 'body_too_large' };

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
    return valid ? { ok: true, algorithm: 'HMAC-SHA256' } : { ok: false, error: 'signature_invalid' };
  } catch (_) {
    return { ok: false, error: 'signature_invalid' };
  }
}

function safeSite(value, defaultSite) {
  const site = typeof value === 'string' && value ? value : defaultSite;
  return site === defaultSite ? site : null;
}

function safePostType(value) {
  if (value == null || value === '') return null;
  const postType = String(value);
  return /^[a-z0-9_-]{1,64}$/i.test(postType) ? postType : null;
}

function safeUrl(value) {
  if (value == null || value === '') return null;
  try {
    const parsed = new URL(String(value));
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.toString() : null;
  } catch (_) {
    return null;
  }
}

function pendingPrefix(site) {
  return `sites/${site}/events/pending/`;
}

function pendingKey(site, receivedAt, id) {
  const stamp = receivedAt.replace(/[-:.TZ]/g, '').slice(0, 17);
  return `${pendingPrefix(site)}${stamp}-${id}.json`;
}

function validPendingKey(site, key) {
  if (typeof key !== 'string' || !key.startsWith(pendingPrefix(site))) return false;
  const name = key.slice(pendingPrefix(site).length);
  return /^\d{14,17}-[0-9a-f-]{36}\.json$/i.test(name);
}

async function parseAuthenticatedJson(request, env) {
  if (request.method.toUpperCase() !== 'POST') {
    return { response: jsonResponse({ ok: false, error: 'method_not_allowed' }, 405) };
  }
  const rawBody = await request.text();
  const auth = await verifySignature(request, env, rawBody);
  if (!auth.ok) return { response: jsonResponse({ ok: false, error: auth.error || 'unauthorized' }, 401) };
  try {
    return { body: rawBody ? JSON.parse(rawBody) : {}, auth };
  } catch (_) {
    return { response: jsonResponse({ ok: false, error: 'invalid_json' }, 400) };
  }
}

async function enqueue(request, env, options) {
  const parsed = await parseAuthenticatedJson(request, env);
  if (parsed.response) return parsed.response;
  if (!env.MEDIA_BUCKET) return jsonResponse({ ok: false, error: 'queue_unconfigured' }, 503);

  const body = parsed.body || {};
  const event = String(body.event || '');
  const site = safeSite(body.site, options.defaultSite);
  if (!ALLOWED_EVENTS.has(event)) return jsonResponse({ ok: false, error: 'event_invalid' }, 400);
  if (!site) return jsonResponse({ ok: false, error: 'site_invalid' }, 400);

  const postId = body.postId == null ? null : Number(body.postId);
  if (postId !== null && (!Number.isSafeInteger(postId) || postId <= 0)) {
    return jsonResponse({ ok: false, error: 'post_id_invalid' }, 400);
  }
  const postType = safePostType(body.postType);
  if (body.postType != null && body.postType !== '' && !postType) return jsonResponse({ ok: false, error: 'post_type_invalid' }, 400);
  const url = safeUrl(body.url);
  if (body.url != null && body.url !== '' && !url) return jsonResponse({ ok: false, error: 'url_invalid' }, 400);

  const receivedAt = new Date().toISOString();
  const eventId = crypto.randomUUID();
  const record = {
    version: 1,
    eventId,
    event,
    site,
    postId,
    postType,
    url,
    receivedAt,
  };
  const key = pendingKey(site, receivedAt, eventId);
  await env.MEDIA_BUCKET.put(key, JSON.stringify(record), {
    httpMetadata: { contentType: 'application/json' },
    customMetadata: { event, site },
  });

  if (typeof options.purgeLocalCache === 'function') options.purgeLocalCache(site);
  return jsonResponse({ ok: true, queued: true, eventId, receivedAt, signing_algorithm: parsed.auth.algorithm }, 202);
}

async function pull(request, env, options) {
  const parsed = await parseAuthenticatedJson(request, env);
  if (parsed.response) return parsed.response;
  if (!env.MEDIA_BUCKET) return jsonResponse({ ok: false, error: 'queue_unconfigured' }, 503);

  const body = parsed.body || {};
  const site = safeSite(body.site, options.defaultSite);
  if (!site) return jsonResponse({ ok: false, error: 'site_invalid' }, 400);
  const requestedLimit = Number(body.limit ?? 10);
  const limit = Number.isInteger(requestedLimit) ? Math.min(Math.max(requestedLimit, 1), MAX_PULL) : 10;
  const listed = await env.MEDIA_BUCKET.list({ prefix: pendingPrefix(site), limit });
  const items = [];

  for (const object of listed.objects || []) {
    if (!validPendingKey(site, object.key)) continue;
    const stored = await env.MEDIA_BUCKET.get(object.key);
    if (!stored) continue;
    try {
      const event = JSON.parse(await stored.text());
      items.push({ key: object.key, event });
    } catch (_) {
      items.push({ key: object.key, event: null, malformed: true });
    }
  }

  return jsonResponse({ ok: true, site, count: items.length, truncated: Boolean(listed.truncated), items });
}

async function ack(request, env, options) {
  const parsed = await parseAuthenticatedJson(request, env);
  if (parsed.response) return parsed.response;
  if (!env.MEDIA_BUCKET) return jsonResponse({ ok: false, error: 'queue_unconfigured' }, 503);

  const body = parsed.body || {};
  const site = safeSite(body.site, options.defaultSite);
  if (!site) return jsonResponse({ ok: false, error: 'site_invalid' }, 400);
  if (!Array.isArray(body.keys) || body.keys.length < 1 || body.keys.length > MAX_ACK) {
    return jsonResponse({ ok: false, error: 'keys_invalid' }, 400);
  }
  const keys = [...new Set(body.keys)];
  if (keys.some((key) => !validPendingKey(site, key))) return jsonResponse({ ok: false, error: 'key_invalid' }, 400);

  await env.MEDIA_BUCKET.delete(keys);
  return jsonResponse({ ok: true, site, acknowledged: keys.length });
}

export async function maybeServeChangeEventApi(request, env, pathname, options = {}) {
  if (!pathname.startsWith(EVENT_API_PREFIX)) return null;
  const defaultSite = String(options.defaultSite || 'runner3-factory-smoke-2');
  const normalizedOptions = { ...options, defaultSite };

  if (pathname === `${EVENT_API_PREFIX}enqueue`) return enqueue(request, env, normalizedOptions);
  if (pathname === `${EVENT_API_PREFIX}pull`) return pull(request, env, normalizedOptions);
  if (pathname === `${EVENT_API_PREFIX}ack`) return ack(request, env, normalizedOptions);
  return jsonResponse({ ok: false, error: 'not_found' }, 404);
}

export const changeEventInternals = {
  ALLOWED_EVENTS,
  EVENT_API_PREFIX,
  pendingPrefix,
  validPendingKey,
};
