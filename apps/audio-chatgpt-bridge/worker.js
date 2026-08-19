const ITEM_PREFIX = 'audio-library/items/';
const MAX_ITEMS = 50;
const encoder = new TextEncoder();

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'x-content-type-options': 'nosniff',
      'referrer-policy': 'no-referrer',
    },
  });
}

async function sha256Hex(value) {
  const digest = await crypto.subtle.digest('SHA-256', encoder.encode(value || ''));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function authorized(request, env) {
  const url = new URL(request.url);
  const token = url.searchParams.get('token') || '';
  if (!token || !env.CHATGPT_QUEUE_SHA256) return false;
  return (await sha256Hex(token)) === env.CHATGPT_QUEUE_SHA256;
}

async function getJsonObject(bucket, key) {
  const object = await bucket.get(key);
  if (!object || !object.body) return null;
  try { return JSON.parse(await object.text()); } catch { return null; }
}

async function listItemKeys(bucket, max = MAX_ITEMS) {
  const keys = [];
  let cursor;
  do {
    const page = await bucket.list({ prefix: ITEM_PREFIX, cursor, limit: Math.min(1000, max - keys.length) });
    for (const object of page.objects) {
      keys.push(object.key);
      if (keys.length >= max) return keys;
    }
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor && keys.length < max);
  return keys;
}

async function pendingItems(env) {
  const keys = await listItemKeys(env.AUDIO_BUCKET, MAX_ITEMS);
  const items = (await Promise.all(keys.map((key) => getJsonObject(env.AUDIO_BUCKET, key)))).filter(Boolean);
  return items
    .filter((item) => ['pending', 'waiting_chatgpt'].includes(item.status) && !item.audioUrl)
    .sort((a, b) => String(a.createdAt).localeCompare(String(b.createdAt)))
    .slice(0, 5)
    .map((item) => ({
      id: item.id,
      sourceUrl: item.sourceUrl,
      sourceLabel: item.sourceLabel || 'Web',
      title: item.title || item.sourceLabel || 'Web',
      createdAt: item.createdAt,
    }));
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/health') return json({ ok: true, service: 'runner3-audio-chatgpt-bridge' });
    if (url.pathname === '/pending' && request.method === 'GET') {
      if (!(await authorized(request, env))) return json({ error: 'Unauthorized' }, 401);
      return json({ items: await pendingItems(env) });
    }
    return json({ error: 'Not found' }, 404);
  },
};
