import app from './index.js';
import { extractArticleImages } from './image-extract.js';

const IMAGE_TIMEOUT_MS = 6000;
const UA = 'Mozilla/5.0 (compatible; runner-3-rss-fastlane/1.0; +https://github.com/louisalviss/runner-3)';

function json(value, status = 400) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'access-control-allow-origin': '*',
    },
  });
}

async function enrichImages(payload) {
  const fetched = Array.isArray(payload?.fetched) ? payload.fetched : [];
  if (!fetched.length) return payload;
  await Promise.all(fetched.map(async (item) => {
    const target = String(item?.resolvedUrl || item?.canonicalUrl || '').trim();
    if (!/^https?:\/\//i.test(target)) return;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort('timeout'), IMAGE_TIMEOUT_MS);
    try {
      const response = await fetch(target, {
        redirect: 'follow',
        signal: controller.signal,
        headers: { 'user-agent': UA, accept: 'text/html,application/xhtml+xml,*/*;q=0.8', dnt: '1' },
      });
      if (response.status !== 200) return;
      const raw = await response.text();
      item.images = extractArticleImages(raw, response.url || target);
    } catch {
      item.images = [];
    } finally {
      clearTimeout(timer);
    }
  }));
  return payload;
}

export default {
  async fetch(request, env, ctx) {
    const incoming = new URL(request.url);

    if (request.method === 'GET' && incoming.pathname === '/health') {
      return json({ ok: true, service: 'runner3-rss-fastlane', entrypoint: 'index-get.js', r2Bound: Boolean(env.RSS_ARTIFACTS) }, 200);
    }

    if (request.method === 'GET' && incoming.pathname === '/v1/rss/artifact') {
      const key = String(incoming.searchParams.get('key') || '').trim();
      if (!key.startsWith('rss-analysis/')) return json({ ok: false, error: 'invalid artifact key' });
      const object = await env.RSS_ARTIFACTS.get(key);
      if (!object) return json({ ok: false, error: 'artifact not found' }, 404);
      return new Response(await object.text(), {
        headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', 'access-control-allow-origin': '*' },
      });
    }

    if (request.method === 'GET' && incoming.pathname === '/v1/rss/fetch') {
      const sourceKey = String(incoming.searchParams.get('sourceKey') || '').trim().toLowerCase();
      const canonicalUrl = String(incoming.searchParams.get('url') || '').trim();
      const title = String(incoming.searchParams.get('title') || canonicalUrl).trim();
      const displayIndexRaw = incoming.searchParams.get('displayIndex');
      const displayIndex = displayIndexRaw && /^\d+$/.test(displayIndexRaw) ? Number(displayIndexRaw) : null;
      if (!sourceKey || !canonicalUrl) return json({ ok: false, error: 'sourceKey and url are required' });

      const internalUrl = new URL(request.url);
      internalUrl.pathname = '/v1/rss/selected-analysis';
      internalUrl.search = '';
      const response = await app.fetch(new Request(internalUrl.toString(), {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'user-agent': 'runner3-chatgpt-fastlane/1.0' },
        body: JSON.stringify({ requestId: `direct-${sourceKey}-${Date.now()}`, items: [{ displayIndex, sourceKey, sourceName: sourceKey, canonicalUrl, title, itemType: 'article' }] }),
      }), env, ctx);

      const payload = await response.json().catch(() => null);
      if (!payload) return response;
      if (response.ok) await enrichImages(payload);
      return json(payload, response.status);
    }

    return app.fetch(request, env, ctx);
  },
};
