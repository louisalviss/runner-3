import app from './index.js';

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

export default {
  async fetch(request, env, ctx) {
    const incoming = new URL(request.url);

    if (request.method === 'GET' && incoming.pathname === '/v1/rss/fetch') {
      const sourceKey = String(incoming.searchParams.get('sourceKey') || '').trim().toLowerCase();
      const canonicalUrl = String(incoming.searchParams.get('url') || '').trim();
      const title = String(incoming.searchParams.get('title') || canonicalUrl).trim();
      const displayIndexRaw = incoming.searchParams.get('displayIndex');
      const displayIndex = displayIndexRaw && /^\d+$/.test(displayIndexRaw) ? Number(displayIndexRaw) : null;

      if (!sourceKey || !canonicalUrl) {
        return json({ ok: false, error: 'sourceKey and url are required' });
      }
      if (canonicalUrl.length > 4096 || title.length > 1000) {
        return json({ ok: false, error: 'query parameter too long' }, 413);
      }

      const requestId = `direct-${sourceKey}-${Date.now()}`;
      const body = {
        requestId,
        items: [{
          displayIndex,
          sourceKey,
          sourceName: sourceKey,
          canonicalUrl,
          title,
          itemType: 'article',
        }],
      };

      const internalUrl = new URL(request.url);
      internalUrl.pathname = '/v1/rss/selected-analysis';
      internalUrl.search = '';
      const internalRequest = new Request(internalUrl.toString(), {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'user-agent': 'runner3-chatgpt-fastlane/1.0',
        },
        body: JSON.stringify(body),
      });
      return app.fetch(internalRequest, env, ctx);
    }

    return app.fetch(request, env, ctx);
  },
};
