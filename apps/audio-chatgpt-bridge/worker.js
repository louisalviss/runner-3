const ITEM_PREFIX = 'audio-library/items/';
const MAX_ITEMS = 50;
const encoder = new TextEncoder();
const REDDIT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36';

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

function parseAllowedRedditUrl(value) {
  let u;
  try { u = new URL(String(value || '')); } catch { return null; }
  const host = u.hostname.toLowerCase();
  if (u.protocol !== 'https:' || !(host === 'reddit.com' || host.endsWith('.reddit.com'))) return null;
  if (u.username || u.password) return null;
  u.hash = '';
  return u;
}

function htmlDecode(value) {
  return String(value || '')
    .replaceAll('&amp;', '&')
    .replaceAll('&#x2F;', '/')
    .replaceAll('&#47;', '/')
    .replaceAll('&quot;', '"')
    .replaceAll('\\u002F', '/')
    .replaceAll('\\/', '/');
}

function canonicalCandidate(value) {
  const decoded = htmlDecode(value);
  const match = decoded.match(/https?:\/\/(?:www\.)?reddit\.com(\/r\/[^\s"'<>]+\/comments\/[a-z0-9]+(?:\/[^\s"'<>?]*)?)/i)
    || decoded.match(/(\/r\/[^\s"'<>]+\/comments\/[a-z0-9]+(?:\/[^\s"'<>?]*)?)/i)
    || decoded.match(/https?:\/\/(?:www\.)?reddit\.com(\/comments\/[a-z0-9]+(?:\/[^\s"'<>?]*)?)/i);
  if (!match) return null;
  const path = match[1] || match[0];
  const url = path.startsWith('http') ? path : `https://www.reddit.com${path}`;
  const parsed = parseAllowedRedditUrl(url);
  return parsed ? parsed.toString().split('?')[0] : null;
}

function extractCanonicalFromHtml(body) {
  const text = htmlDecode(body || '');
  const patterns = [
    /<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["']/i,
    /<link[^>]+href=["']([^"']+)["'][^>]+rel=["']canonical["']/i,
    /<meta[^>]+property=["']og:url["'][^>]+content=["']([^"']+)["']/i,
    /<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:url["']/i,
  ];
  for (const pattern of patterns) {
    const m = text.match(pattern);
    const candidate = m && canonicalCandidate(m[1]);
    if (candidate) return candidate;
  }
  return canonicalCandidate(text);
}

function redditHeaders(accept = 'text/html,application/xhtml+xml,*/*') {
  return {
    'user-agent': REDDIT_UA,
    'accept': accept,
    'accept-language': 'en-US,en;q=0.9',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
  };
}

async function resolveReddit(rawUrl) {
  const input = parseAllowedRedditUrl(rawUrl);
  if (!input) return { canonicalUrl: null, diagnostics: ['invalid-reddit-url'] };
  if (/\/comments\/[a-z0-9]+/i.test(input.pathname)) {
    return { canonicalUrl: input.toString().split('?')[0], diagnostics: ['already-canonical'] };
  }

  const candidates = [input.toString()];
  if (input.hostname !== 'www.reddit.com') {
    const www = new URL(input.toString());
    www.hostname = 'www.reddit.com';
    candidates.push(www.toString());
  }
  const diagnostics = [];

  for (const target of candidates) {
    try {
      const response = await fetch(target, { headers: redditHeaders(), redirect: 'manual' });
      const location = response.headers.get('location');
      diagnostics.push(`manual:${response.status}:${location ? 'location' : 'no-location'}`);
      if (location) {
        const absolute = new URL(location, target).toString();
        const found = canonicalCandidate(absolute);
        if (found) return { canonicalUrl: found, diagnostics };
      }
      const body = await response.text();
      const found = extractCanonicalFromHtml(body);
      if (found) return { canonicalUrl: found, diagnostics };
    } catch (error) {
      diagnostics.push(`manual-error:${String(error).slice(0, 80)}`);
    }

    try {
      const response = await fetch(target, { headers: redditHeaders(), redirect: 'follow' });
      diagnostics.push(`follow:${response.status}:${response.url || 'no-url'}`);
      const byUrl = canonicalCandidate(response.url || '');
      if (byUrl) return { canonicalUrl: byUrl, diagnostics };
      const body = await response.text();
      const found = extractCanonicalFromHtml(body);
      if (found) return { canonicalUrl: found, diagnostics };
    } catch (error) {
      diagnostics.push(`follow-error:${String(error).slice(0, 80)}`);
    }
  }
  return { canonicalUrl: null, diagnostics };
}

function cleanRaw(value) {
  return String(value || '')
    .replace(/\r/g, '')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function redditJsonToRaw(data) {
  if (!Array.isArray(data) || data.length < 2) throw new Error('reddit-json-shape');
  const post = data?.[0]?.data?.children?.[0]?.data || {};
  const title = cleanRaw(post.title || 'Reddit');
  const selftext = cleanRaw(post.selftext || '');
  const comments = [];

  function walk(children, depth = 0) {
    if (!Array.isArray(children) || depth > 3 || comments.length >= 150) return;
    for (const child of children) {
      if (comments.length >= 150) break;
      if (child?.kind !== 't1') continue;
      const row = child?.data || {};
      const body = cleanRaw(row.body || '');
      if (body.length >= 40) {
        const score = Number.isFinite(row.score) ? ` score ${row.score}` : '';
        comments.push(`[Comment${score}] ${body}`);
      }
      const replies = row.replies;
      if (replies && typeof replies === 'object') walk(replies?.data?.children || [], depth + 1);
    }
  }
  walk(data?.[1]?.data?.children || []);
  const parts = [];
  if (selftext) parts.push(`[Post]\n${selftext}`);
  parts.push(...comments);
  const rawText = cleanRaw(parts.join('\n\n'));
  return { title, rawText };
}

async function fetchRedditJson(canonicalUrl) {
  const parsed = parseAllowedRedditUrl(canonicalUrl);
  if (!parsed) return { ok: false, diagnostics: ['canonical-invalid'] };
  const path = parsed.pathname.replace(/\/$/, '');
  const idMatch = path.match(/\/comments\/([a-z0-9]+)/i);
  const endpoints = [
    `https://www.reddit.com${path}.json?raw_json=1&limit=100&sort=top`,
    `https://old.reddit.com${path}.json?raw_json=1&limit=100&sort=top`,
  ];
  if (idMatch) endpoints.push(`https://www.reddit.com/comments/${idMatch[1]}.json?raw_json=1&limit=100&sort=top`);
  const diagnostics = [];
  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint, { headers: redditHeaders('application/json,text/plain,*/*'), redirect: 'follow' });
      const text = await response.text();
      diagnostics.push(`json:${new URL(endpoint).hostname}:${response.status}:${text.length}`);
      if (response.status !== 200 || text.length < 200) continue;
      let data;
      try { data = JSON.parse(text); } catch { continue; }
      const parsedRaw = redditJsonToRaw(data);
      if (parsedRaw.rawText.length >= 400) return { ok: true, ...parsedRaw, diagnostics };
    } catch (error) {
      diagnostics.push(`json-error:${String(error).slice(0, 80)}`);
    }
  }
  return { ok: false, diagnostics };
}

async function redditSource(rawUrl) {
  const resolved = await resolveReddit(rawUrl);
  if (!resolved.canonicalUrl) {
    return { ok: false, canonicalUrl: null, diagnostics: resolved.diagnostics };
  }
  const fetched = await fetchRedditJson(resolved.canonicalUrl);
  return {
    ok: Boolean(fetched.ok),
    canonicalUrl: resolved.canonicalUrl,
    sourceLabel: 'Reddit',
    title: fetched.title || 'Reddit',
    rawText: fetched.rawText || '',
    diagnostics: [...resolved.diagnostics, ...(fetched.diagnostics || [])],
  };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/health') return json({ ok: true, service: 'runner3-audio-chatgpt-bridge' });
    if (url.pathname === '/pending' && request.method === 'GET') {
      if (!(await authorized(request, env))) return json({ error: 'Unauthorized' }, 401);
      return json({ items: await pendingItems(env) });
    }
    if (url.pathname === '/source/reddit' && request.method === 'POST') {
      if (!(await authorized(request, env))) return json({ error: 'Unauthorized' }, 401);
      let body;
      try { body = await request.json(); } catch { return json({ error: 'Invalid JSON body' }, 400); }
      const source = parseAllowedRedditUrl(body?.url);
      if (!source) return json({ error: 'Only https reddit.com URLs are allowed' }, 400);
      const result = await redditSource(source.toString());
      return json(result, result.ok ? 200 : 502);
    }
    return json({ error: 'Not found' }, 404);
  },
};
