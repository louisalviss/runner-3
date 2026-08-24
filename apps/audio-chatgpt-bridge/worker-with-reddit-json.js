import baseWorker from './worker.js';

const encoder = new TextEncoder();
const REDDIT_UA = 'runner3-reddit-deep-sweep/1.0 (+public read-only research)';
const ALLOWED_QUERY_KEYS = new Set(['limit', 'raw_json', 't', 'after', 'depth', 'sort']);

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
  const token = url.searchParams.get('token') || request.headers.get('x-runner-token') || '';
  if (!token || !env.CHATGPT_QUEUE_SHA256) return false;
  return (await sha256Hex(token)) === env.CHATGPT_QUEUE_SHA256;
}

function parseAllowedRedditJsonUrl(value) {
  let url;
  try { url = new URL(String(value || '')); } catch { return null; }
  if (url.protocol !== 'https:' || url.username || url.password || url.hash) return null;
  const host = url.hostname.toLowerCase();
  if (!['www.reddit.com', 'old.reddit.com'].includes(host)) return null;

  const listing = /^\/r\/[A-Za-z0-9_]+\/(?:top|new|hot)\.json$/i.test(url.pathname);
  const thread = /^\/comments\/[A-Za-z0-9]+\.json$/i.test(url.pathname);
  if (!listing && !thread) return null;

  for (const key of url.searchParams.keys()) {
    if (!ALLOWED_QUERY_KEYS.has(key)) return null;
  }
  if (url.searchParams.get('limit') && !/^\d{1,3}$/.test(url.searchParams.get('limit'))) return null;
  if (url.searchParams.get('depth') && !/^\d{1,2}$/.test(url.searchParams.get('depth'))) return null;
  if (url.searchParams.get('raw_json') && url.searchParams.get('raw_json') !== '1') return null;
  if (url.searchParams.get('t') && !['hour', 'day', 'week', 'month', 'year', 'all'].includes(url.searchParams.get('t'))) return null;
  if (url.searchParams.get('sort') && !['top', 'new', 'hot', 'best', 'confidence'].includes(url.searchParams.get('sort'))) return null;
  if ((url.searchParams.get('after') || '').length > 128) return null;
  return url;
}

function redditHeaders() {
  return {
    'user-agent': REDDIT_UA,
    'accept': 'application/json,text/plain;q=0.9,*/*;q=0.1',
    'accept-language': 'en-US,en;q=0.9',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
  };
}

async function fetchRedditJson(rawUrl) {
  const input = parseAllowedRedditJsonUrl(rawUrl);
  if (!input) throw new Error('reddit_json_url_not_allowed');

  const candidates = [input];
  const alternate = new URL(input.toString());
  alternate.hostname = input.hostname === 'www.reddit.com' ? 'old.reddit.com' : 'www.reddit.com';
  candidates.push(alternate);

  const diagnostics = [];
  for (const target of candidates) {
    try {
      const response = await fetch(target.toString(), { headers: redditHeaders(), redirect: 'follow' });
      const text = await response.text();
      diagnostics.push(`${target.hostname}:${response.status}:${text.length}`);
      if (!response.ok || text.length < 2) continue;
      let data;
      try { data = JSON.parse(text); } catch { continue; }
      return { data, via: target.hostname, bytes: text.length, diagnostics };
    } catch (error) {
      diagnostics.push(`${target.hostname}:error:${String(error).slice(0, 120)}`);
    }
  }
  throw new Error(`reddit_json_fetch_failed:${diagnostics.join('|')}`);
}

async function sourceRedditJson(request, env) {
  if (!(await authorized(request, env))) return json({ ok: false, error: 'Unauthorized' }, 401);
  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: 'Invalid JSON body' }, 400); }
  if (String(body?.url || '').length > 1800) return json({ ok: false, error: 'URL too long' }, 400);
  try {
    const result = await fetchRedditJson(body?.url);
    return json({ ok: true, ...result, fetched_at: new Date().toISOString() });
  } catch (error) {
    return json({ ok: false, error: String(error?.message || error) }, 502);
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/source/reddit-json' && request.method === 'POST') {
      return sourceRedditJson(request, env);
    }
    return baseWorker.fetch(request, env, ctx);
  },
};
