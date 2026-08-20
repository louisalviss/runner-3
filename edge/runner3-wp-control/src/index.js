const EVENT_KEY = 'sites/runner3-factory-smoke-2/automation/pending.json';
const MAX_BODY = 32768;
const MAX_URLS = 40;
const MAX_REASONS = 16;
const MAX_MEDIA = 16;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'x-runner3-control': 'events-v1',
    },
  });
}

function safeString(value, max = 160) {
  return typeof value === 'string' ? value.trim().slice(0, max) : '';
}

function uniq(values, limit) {
  return [...new Set(values.filter(Boolean))].slice(0, limit);
}

function normalizePath(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const u = new URL(value, 'https://runner3.invalid');
    const path = `${u.pathname}${u.search}`;
    if (!path.startsWith('/') || path.startsWith('/wp-admin') || path.startsWith('/wp-login.php')) return null;
    return path.slice(0, 600);
  } catch { return null; }
}

function normalizeMedia(value) {
  return (Array.isArray(value) ? value : []).slice(0, MAX_MEDIA).map((row) => {
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

function base64Bytes(value) {
  const binary = atob(String(value || ''));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function verify(request, env, rawBody) {
  const tsText = request.headers.get('x-runner3-timestamp') || '';
  const sigText = request.headers.get('x-runner3-signature') || '';
  const secret = String(env.RUNNER3_AUTOMATION_SECRET || '');
  const ts = Number(tsText);
  if (!secret) return { ok: false, error: 'auth_unconfigured' };
  if (!Number.isInteger(ts) || Math.abs(Math.floor(Date.now() / 1000) - ts) > 300) return { ok: false, error: 'timestamp_invalid' };
  if (!sigText || rawBody.length > MAX_BODY) return { ok: false, error: 'signature_missing' };
  try {
    const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']);
    const ok = await crypto.subtle.verify('HMAC', key, base64Bytes(sigText), new TextEncoder().encode(`${tsText}\n${rawBody}`));
    return ok ? { ok: true } : { ok: false, error: 'signature_invalid' };
  } catch { return { ok: false, error: 'signature_invalid' }; }
}

async function readPending(bucket) {
  const object = await bucket.get(EVENT_KEY);
  if (!object) return null;
  try { return JSON.parse(await object.text()); } catch { return null; }
}

async function writePending(bucket, pending) {
  await bucket.put(EVENT_KEY, `${JSON.stringify(pending)}\n`, {
    httpMetadata: { contentType: 'application/json; charset=utf-8', cacheControl: 'no-store' },
  });
}

async function events(request, env) {
  if (request.method !== 'POST') return json({ ok: false, error: 'method_not_allowed' }, 405);
  if (!env.AUTOMATION_BUCKET) return json({ ok: false, error: 'bucket_unavailable' }, 503);
  const raw = await request.text();
  const auth = await verify(request, env, raw);
  if (!auth.ok) return json({ ok: false, error: auth.error }, 401);
  let body;
  try { body = raw ? JSON.parse(raw) : {}; } catch { return json({ ok: false, error: 'invalid_json' }, 400); }
  const op = safeString(body.op, 20).toLowerCase();
  if (op === 'peek') return json({ ok: true, pending: await readPending(env.AUTOMATION_BUCKET) });
  if (op === 'ack') {
    const revision = safeString(body.revision, 100);
    if (!revision) return json({ ok: false, error: 'revision_required' }, 400);
    const pending = await readPending(env.AUTOMATION_BUCKET);
    if (!pending) return json({ ok: true, acknowledged: false, reason: 'empty' });
    if (pending.revision !== revision) return json({ ok: true, acknowledged: false, reason: 'revision_changed', currentRevision: pending.revision }, 409);
    await env.AUTOMATION_BUCKET.delete(EVENT_KEY);
    return json({ ok: true, acknowledged: true, revision });
  }
  if (op !== 'enqueue') return json({ ok: false, error: 'unsupported_operation' }, 400);
  const previous = await readPending(env.AUTOMATION_BUCKET);
  const now = new Date().toISOString();
  const revision = `${Date.now().toString(36)}-${crypto.randomUUID().slice(0, 12)}`;
  const pending = {
    version: 1,
    revision,
    firstSeenAt: previous?.firstSeenAt || now,
    lastSeenAt: now,
    global: Boolean(previous?.global || body.global),
    reasons: uniq([...(previous?.reasons || []), safeString(body.reason, 120), ...((Array.isArray(body.reasons) ? body.reasons : []).map(x => safeString(x, 120)))], MAX_REASONS),
    urls: uniq([...(previous?.urls || []), ...((Array.isArray(body.urls) ? body.urls : []).map(normalizePath))], MAX_URLS),
    media: [...(previous?.media || []), ...normalizeMedia(body.media)].slice(-MAX_MEDIA),
    source: safeString(body.source, 80) || previous?.source || 'wordpress',
  };
  if (!pending.urls.length) pending.urls = ['/'];
  await writePending(env.AUTOMATION_BUCKET, pending);
  return json({ ok: true, queued: true, revision, pending: { ...pending, media: pending.media.length } });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/health') return json({ ok: true, service: 'runner3-wp-control', version: 1 });
    if (url.pathname === '/v1/events') return events(request, env);
    return json({ ok: false, error: 'not_found' }, 404);
  },
};
