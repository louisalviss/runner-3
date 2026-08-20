const EVENT_KEY = 'sites/runner3-factory-smoke-2/automation/pending.json';
const MAX_URLS = 40;
const MAX_REASONS = 16;
const MAX_MEDIA = 16;

function safeString(value, max = 160) {
  return typeof value === 'string' ? value.trim().slice(0, max) : '';
}

function normalizePath(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const url = new URL(value, 'https://runner3.invalid');
    const path = `${url.pathname}${url.search}`;
    if (!path.startsWith('/') || path.startsWith('/wp-admin') || path.startsWith('/wp-login.php')) return null;
    return path.slice(0, 600);
  } catch {
    return null;
  }
}

function uniq(values, limit) {
  return [...new Set(values.filter(Boolean))].slice(0, limit);
}

function normalizeMedia(value) {
  const rows = Array.isArray(value) ? value : [];
  return rows.slice(0, MAX_MEDIA).map((row) => {
    if (!row || typeof row !== 'object') return null;
    const url = safeString(row.url, 800);
    if (!url) return null;
    return {
      url,
      attachmentId: Number.isInteger(Number(row.attachmentId)) ? Number(row.attachmentId) : null,
      postId: Number.isInteger(Number(row.postId)) ? Number(row.postId) : null,
      role: safeString(row.role, 40) || null,
      width: Number.isFinite(Number(row.width)) ? Number(row.width) : null,
      height: Number.isFinite(Number(row.height)) ? Number(row.height) : null,
      mime: safeString(row.mime, 80) || null,
    };
  }).filter(Boolean);
}

async function readPending(bucket) {
  const object = await bucket.get(EVENT_KEY);
  if (!object) return null;
  try {
    const parsed = JSON.parse(await object.text());
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

async function writePending(bucket, pending) {
  await bucket.put(EVENT_KEY, `${JSON.stringify(pending)}\n`, {
    httpMetadata: { contentType: 'application/json; charset=utf-8', cacheControl: 'no-store' },
  });
}

function response(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Runner3-Automation': 'events-v1',
    },
  });
}

export const AUTOMATION_EVENTS_PATH = '/__runner3/automation/events';

export async function handleAutomationEvents(request, env, verifySignature) {
  if (request.method.toUpperCase() !== 'POST') {
    return response({ ok: false, error: 'method_not_allowed' }, 405);
  }
  if (!env.MEDIA_BUCKET) return response({ ok: false, error: 'media_bucket_unavailable' }, 503);

  const rawBody = await request.text();
  const auth = await verifySignature(request, env, rawBody);
  if (!auth.ok) return response({ ok: false, error: auth.error || 'unauthorized' }, 401);

  let body;
  try {
    body = rawBody ? JSON.parse(rawBody) : {};
  } catch {
    return response({ ok: false, error: 'invalid_json' }, 400);
  }

  const op = safeString(body.op, 20).toLowerCase();
  if (op === 'peek') {
    const pending = await readPending(env.MEDIA_BUCKET);
    return response({ ok: true, pending, signing_algorithm: auth.algorithm });
  }

  if (op === 'ack') {
    const revision = safeString(body.revision, 100);
    if (!revision) return response({ ok: false, error: 'revision_required' }, 400);
    const pending = await readPending(env.MEDIA_BUCKET);
    if (!pending) return response({ ok: true, acknowledged: false, reason: 'empty' });
    if (pending.revision !== revision) {
      return response({ ok: true, acknowledged: false, reason: 'revision_changed', currentRevision: pending.revision }, 409);
    }
    await env.MEDIA_BUCKET.delete(EVENT_KEY);
    return response({ ok: true, acknowledged: true, revision });
  }

  if (op !== 'enqueue') return response({ ok: false, error: 'unsupported_operation' }, 400);

  const now = new Date().toISOString();
  const previous = await readPending(env.MEDIA_BUCKET);
  const reasons = uniq([
    ...(Array.isArray(previous?.reasons) ? previous.reasons : []),
    safeString(body.reason, 120),
    ...(Array.isArray(body.reasons) ? body.reasons.map((x) => safeString(x, 120)) : []),
  ], MAX_REASONS);
  const urls = uniq([
    ...(Array.isArray(previous?.urls) ? previous.urls : []),
    ...(Array.isArray(body.urls) ? body.urls.map(normalizePath) : []),
  ], MAX_URLS);
  const media = [...(Array.isArray(previous?.media) ? previous.media : []), ...normalizeMedia(body.media)].slice(-MAX_MEDIA);
  const revision = `${Date.now().toString(36)}-${crypto.randomUUID().slice(0, 12)}`;
  const pending = {
    version: 1,
    revision,
    firstSeenAt: previous?.firstSeenAt || now,
    lastSeenAt: now,
    global: Boolean(previous?.global || body.global),
    reasons,
    urls: urls.length ? urls : ['/'],
    media,
    source: safeString(body.source, 80) || previous?.source || 'wordpress',
  };
  await writePending(env.MEDIA_BUCKET, pending);
  return response({ ok: true, queued: true, revision, pending: { ...pending, media: pending.media.length } });
}
