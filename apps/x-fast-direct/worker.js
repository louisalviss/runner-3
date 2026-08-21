const ALLOWED_HOSTS = new Set(['x.com', 'www.x.com', 'twitter.com', 'www.twitter.com', 'mobile.twitter.com']);
const USER_AGENT = 'runner3-x-fast-direct/2.0 (+https://github.com/louisalviss/runner-3)';
const FX_TIMEOUT_MS = 2200;
const X_HTML_TIMEOUT_MS = 3200;

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'access-control-allow-origin': '*',
    },
  });
}

function parseStatusUrl(raw) {
  let url;
  try {
    url = new URL(raw);
  } catch {
    throw new Error('invalid_url');
  }
  if (url.protocol !== 'https:' || !ALLOWED_HOSTS.has(url.hostname.toLowerCase()) || url.username || url.password) {
    throw new Error('unsupported_url');
  }
  const match = url.pathname.match(/^\/([^/]+)\/status\/(\d+)/i);
  if (!match) throw new Error('status_url_required');
  return { handle: match[1], id: match[2], canonical: `https://x.com/${match[1]}/status/${match[2]}` };
}

function decodeHtml(value = '') {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&#x27;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)));
}

function extractAttr(tag, name) {
  const re = new RegExp(`\\b${name}\\s*=\\s*(["'])(.*?)\\1`, 'i');
  const m = tag.match(re);
  return m ? decodeHtml(m[2]) : '';
}

function extractMeta(html) {
  const meta = {};
  for (const tag of html.match(/<meta\b[^>]*>/gi) || []) {
    const key = (extractAttr(tag, 'property') || extractAttr(tag, 'name')).toLowerCase();
    const value = extractAttr(tag, 'content');
    if (key && value) meta[key] = value;
  }
  return meta;
}

function visibleText(html) {
  return decodeHtml(
    html
      .replace(/<(script|style|noscript|svg|template)\b[^>]*>[\s\S]*?<\/\1>/gi, ' ')
      .replace(/<\/?(?:article|aside|blockquote|br|div|figcaption|figure|footer|h[1-6]|header|li|main|nav|ol|p|section|table|td|th|tr|ul)\b[^>]*>/gi, '\n')
      .replace(/<[^>]+>/g, ' ')
  )
    .split(/\n+/)
    .map((s) => s.replace(/[ \t\r\f\v]+/g, ' ').trim())
    .filter(Boolean)
    .join('\n')
    .slice(0, 30000);
}

async function readLimited(response, maxBytes = 600000) {
  if (!response.body) return '';
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let total = 0;
  let out = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) {
        await reader.cancel('body_limit');
        break;
      }
      out += decoder.decode(value, { stream: true });
    }
    out += decoder.decode();
    return out;
  } finally {
    reader.releaseLock();
  }
}

async function fetchFx(handle, id) {
  const endpoint = `https://api.fxtwitter.com/${encodeURIComponent(handle)}/status/${id}`;
  const response = await fetch(endpoint, {
    headers: { 'user-agent': USER_AGENT, accept: 'application/json' },
    redirect: 'follow',
    signal: AbortSignal.timeout(FX_TIMEOUT_MS),
  });
  const data = await response.json().catch(() => null);
  const tweet = data?.tweet || data?.status || null;
  if (!response.ok || !tweet || !(tweet.text || tweet.raw_text?.text)) {
    throw new Error(`fxtwitter_unusable_${response.status}`);
  }
  return {
    engine: 'fxtwitter',
    ok: true,
    post_id: String(tweet.id || id),
    canonical_url: tweet.url || `https://x.com/${handle}/status/${id}`,
    text: tweet.text || tweet.raw_text?.text || '',
    created_at: tweet.created_at || null,
    author: {
      name: tweet.author?.name || null,
      handle: tweet.author?.screen_name || tweet.author?.username || handle,
      avatar_url: tweet.author?.avatar_url || tweet.author?.avatar || null,
    },
    metrics: {
      views: tweet.views ?? null,
      likes: tweet.likes ?? null,
      retweets: tweet.retweets ?? null,
      replies: tweet.replies ?? null,
      bookmarks: tweet.bookmarks ?? null,
    },
    quote: tweet.quote || null,
    media: tweet.media || null,
  };
}

async function fetchXHtml(canonical, handle, id) {
  const response = await fetch(canonical, {
    headers: {
      'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
      'accept-language': 'en-US,en;q=0.9',
    },
    redirect: 'follow',
    signal: AbortSignal.timeout(X_HTML_TIMEOUT_MS),
  });
  const html = await readLimited(response);
  const meta = extractMeta(html);
  const text = visibleText(html);
  const description = meta['og:description'] || meta['twitter:description'] || meta.description || '';
  if (!response.ok || (!description && text.length < 100)) {
    throw new Error(`x_html_unusable_${response.status}`);
  }
  return {
    engine: 'x-html',
    ok: true,
    post_id: id,
    canonical_url: canonical,
    text: description || text,
    page_text: text,
    author: { name: null, handle, avatar_url: meta['og:image'] || meta['twitter:image'] || null },
    title: meta['og:title'] || meta['twitter:title'] || '',
    login_wall_present: /log in or sign up for x/i.test(text),
  };
}

export default {
  async fetch(request) {
    const started = Date.now();
    const requestUrl = new URL(request.url);
    if (request.method !== 'GET') return json({ ok: false, error: 'GET only' }, 405);
    if (requestUrl.pathname === '/health') {
      return json({ ok: true, service: 'runner3-x-fast-direct', version: 2 });
    }

    const raw = requestUrl.searchParams.get('url');
    if (!raw) return json({ ok: false, error: 'missing url' }, 400);

    let parsed;
    try {
      parsed = parseStatusUrl(raw);
    } catch (error) {
      return json({ ok: false, error: error.message }, 400);
    }

    const candidates = [
      fetchFx(parsed.handle, parsed.id),
      fetchXHtml(parsed.canonical, parsed.handle, parsed.id),
    ];

    try {
      const result = await Promise.any(candidates);
      return json({ ...result, requested_url: raw, elapsed_ms: Date.now() - started });
    } catch (aggregate) {
      const errors = Array.from(aggregate?.errors || []).map((error) => String(error?.message || error));
      return json({
        ok: false,
        requested_url: raw,
        post_id: parsed.id,
        canonical_url: parsed.canonical,
        elapsed_ms: Date.now() - started,
        errors,
        fallback: 'runner-3 GitHub Actions x-fast',
      }, 502);
    }
  },
};
