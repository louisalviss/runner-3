import fs from 'node:fs';

const origin = new URL(process.env.CF_SNAPSHOT_ORIGIN || 'https://runner3-factory-smoke-2.wasmer.app');
const modulePath = process.env.CF_SNAPSHOT_MODULE || 'edge/wordpress-edge-proxy/src/snapshot.generated.js';
const inlineCssModulePath = process.env.CF_INLINE_CSS_MODULE || 'edge/wordpress-edge-proxy/src/inline-css.generated.js';
const outPath = process.env.CF_SNAPSHOT_OUT || '/tmp/runner3-edge-snapshot.json';
const maxPages = Math.max(1, Number(process.env.CF_SNAPSHOT_MAX_PAGES || 40));
const maxBytes = Math.max(250000, Number(process.env.CF_SNAPSHOT_MAX_BYTES || 2500000));
const maxInlineCssBytes = Math.max(32768, Number(process.env.CF_INLINE_CSS_MAX_BYTES || 262144));

function normalizePath(pathname) {
  const path = pathname || '/';
  if (path === '/' || path.endsWith('/') || /\.[^/]+$/.test(path)) return path;
  return `${path}/`;
}

function publicHtmlPath(pathname) {
  if (!pathname || pathname === '/') return true;
  if (pathname === '/wp-login.php' || pathname.startsWith('/wp-admin/') || pathname.startsWith('/wp-json/')) return false;
  if (pathname === '/xmlrpc.php' || pathname === '/wp-cron.php' || pathname === '/wp-comments-post.php') return false;
  if (pathname.startsWith('/feed/') || pathname.startsWith('/comments/feed/')) return false;
  if (/\.(?:xml|json|txt|css|js|mjs|png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|otf|eot|mp4|webm|pdf)$/i.test(pathname)) return false;
  return true;
}

function decodeHref(value) {
  return String(value || '')
    .replace(/&amp;/gi, '&')
    .replace(/&#038;/gi, '&')
    .replace(/&#x26;/gi, '&');
}

function internalPaths(html, baseUrl) {
  const paths = [];
  const seen = new Set();
  for (const match of html.matchAll(/href\s*=\s*["']([^"']+)["']/gi)) {
    const raw = decodeHref(match[1]).trim();
    if (!raw || raw.startsWith('#') || /^(?:mailto:|tel:|javascript:|data:)/i.test(raw)) continue;
    try {
      const url = new URL(raw, baseUrl);
      if (url.origin !== origin.origin || url.search) continue;
      const path = normalizePath(url.pathname);
      if (!publicHtmlPath(path) || seen.has(path)) continue;
      seen.add(path);
      paths.push(path);
    } catch {
      // Ignore malformed author-supplied links.
    }
  }
  return paths;
}

function attr(tag, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const quoted = tag.match(new RegExp(`\\b${escaped}\\s*=\\s*(["'])(.*?)\\1`, 'i'));
  if (quoted) return quoted[2];
  const bare = tag.match(new RegExp(`\\b${escaped}\\s*=\\s*([^\\s>]+)`, 'i'));
  return bare ? bare[1] : null;
}

function stylesheetRefs(html, baseUrl) {
  const refs = [];
  const seen = new Set();
  for (const match of html.matchAll(/<link\b[^>]*>/gi)) {
    const tag = match[0];
    const rel = String(attr(tag, 'rel') || '').toLowerCase().split(/\s+/);
    if (!rel.includes('stylesheet')) continue;
    if (/\bdisabled(?:\s|=|>)/i.test(tag)) continue;
    const media = String(attr(tag, 'media') || '').trim().toLowerCase();
    if (media === 'print') continue;
    const href = decodeHref(attr(tag, 'href') || '').trim();
    if (!href) continue;
    try {
      const url = new URL(href, baseUrl);
      if (!/^https?:$/.test(url.protocol)) continue;
      const key = url.origin === origin.origin ? `${url.pathname}${url.search}` : url.toString();
      if (seen.has(key)) continue;
      seen.add(key);
      refs.push({ key, url: url.toString(), media: media || 'all' });
    } catch {
      // Ignore malformed stylesheet URLs.
    }
  }
  return refs;
}

function rewriteCssUrls(css, cssUrl) {
  return css.replace(/url\(\s*(["']?)([^"')]+)\1\s*\)/gi, (full, quote, rawValue) => {
    const raw = String(rawValue || '').trim();
    if (!raw || raw.startsWith('#') || /^(?:data:|blob:|var\()/i.test(raw)) return full;
    try {
      const resolved = new URL(raw, cssUrl);
      const value = resolved.origin === origin.origin
        ? `${resolved.pathname}${resolved.search}${resolved.hash}`
        : resolved.toString();
      const q = quote || '"';
      return `url(${q}${value}${q})`;
    } catch {
      return full;
    }
  });
}

async function buildInlineCss(html, baseUrl, builtAt) {
  const styles = {};
  const errors = [];
  let bytes = 0;
  const refs = stylesheetRefs(html, baseUrl).slice(0, 16);

  for (const ref of refs) {
    try {
      const response = await fetch(ref.url, {
        redirect: 'follow',
        signal: AbortSignal.timeout(15000),
        headers: {
          'User-Agent': 'Runner3EdgeCssBundler/1.0',
          Accept: 'text/css,*/*;q=0.1',
          'Cache-Control': 'no-cache',
        },
      });
      const type = response.headers.get('content-type') || '';
      if (!response.ok || (!/text\/css/i.test(type) && !/\.css(?:\?|$)/i.test(ref.url))) {
        errors.push({ url: ref.url, status: response.status, detail: `content-type=${type}` });
        continue;
      }
      let css = await response.text();
      css = rewriteCssUrls(css, response.url || ref.url);
      const cssBytes = Buffer.byteLength(css);
      if (cssBytes < 1) continue;
      if (bytes + cssBytes > maxInlineCssBytes) {
        errors.push({ url: ref.url, status: response.status, detail: `inline_css_budget_exceeded=${bytes + cssBytes}` });
        continue;
      }
      styles[ref.key] = { css, media: ref.media, source: ref.url };
      bytes += cssBytes;
    } catch (error) {
      errors.push({ url: ref.url, status: null, detail: String(error?.message || error).slice(0, 240) });
    }
  }

  const serialized = JSON.stringify(styles).replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
  const source = [
    '// Generated immediately before the V2 Cloudflare deployment. Do not hand-edit.',
    `export const INLINE_CSS_BUILT_AT = ${JSON.stringify(builtAt)};`,
    `export const INLINE_STYLES = Object.freeze(${serialized});`,
    '',
  ].join('\n');
  fs.writeFileSync(inlineCssModulePath, source);

  return {
    status: Object.keys(styles).length ? 'ready' : 'empty',
    builtAt,
    stylesheets: Object.keys(styles).length,
    bytes,
    keys: Object.keys(styles),
    errors: errors.slice(0, 20),
    modulePath: inlineCssModulePath,
  };
}

async function sitemapPaths() {
  const pages = new Set();
  const queue = [new URL('/wp-sitemap.xml', origin).toString()];
  const seen = new Set();
  while (queue.length && seen.size < 12 && pages.size < maxPages) {
    const sitemapUrl = queue.shift();
    if (seen.has(sitemapUrl)) continue;
    seen.add(sitemapUrl);
    try {
      const response = await fetch(sitemapUrl, {
        redirect: 'follow',
        headers: { 'User-Agent': 'Runner3EdgeSnapshotBuilder/2.0', Accept: 'application/xml,text/xml,*/*' },
      });
      if (!response.ok) continue;
      const xml = await response.text();
      for (const match of xml.matchAll(/<loc>\s*([^<]+?)\s*<\/loc>/gi)) {
        let url;
        try { url = new URL(decodeHref(match[1]), sitemapUrl); } catch { continue; }
        if (url.origin !== origin.origin) continue;
        if (/\.xml$/i.test(url.pathname)) {
          if (!seen.has(url.toString())) queue.push(url.toString());
          continue;
        }
        const path = normalizePath(url.pathname);
        if (publicHtmlPath(path)) pages.add(path);
        if (pages.size >= maxPages) break;
      }
    } catch {
      // Homepage crawling below remains the fallback discovery path.
    }
  }
  return [...pages];
}

const builtAt = new Date().toISOString();
const queue = ['/'];
const queued = new Set(queue);
for (const path of await sitemapPaths()) {
  if (!queued.has(path) && queue.length < maxPages) {
    queue.push(path);
    queued.add(path);
  }
}

const snapshots = {};
const errors = [];
let totalBytes = 0;
let inlineCss = null;

while (queue.length && Object.keys(snapshots).length < maxPages && totalBytes < maxBytes) {
  const requestedPath = queue.shift();
  const requestedUrl = new URL(requestedPath, origin);
  try {
    const response = await fetch(requestedUrl, {
      redirect: 'follow',
      headers: {
        'User-Agent': 'Runner3EdgeSnapshotBuilder/2.0',
        Accept: 'text/html,application/xhtml+xml',
        'Cache-Control': 'no-cache',
      },
    });
    const contentType = response.headers.get('content-type') || '';
    if (!response.ok || !/text\/html/i.test(contentType)) {
      errors.push({ path: requestedPath, status: response.status, detail: `content-type=${contentType}` });
      continue;
    }

    const html = await response.text();
    const bytes = Buffer.byteLength(html);
    if (bytes < 256) {
      errors.push({ path: requestedPath, status: response.status, detail: `html_too_small=${bytes}` });
      continue;
    }
    if (totalBytes + bytes > maxBytes && Object.keys(snapshots).length > 0) break;

    const finalUrl = new URL(response.url || requestedUrl);
    const requestedKey = normalizePath(requestedUrl.pathname);
    const finalKey = normalizePath(finalUrl.pathname);
    if (requestedKey === '/' && inlineCss === null) inlineCss = await buildInlineCss(html, finalUrl, builtAt);

    if (!(requestedKey in snapshots)) {
      snapshots[requestedKey] = html;
      totalBytes += bytes;
    }
    if (finalKey !== requestedKey && !(finalKey in snapshots)) snapshots[finalKey] = html;

    for (const path of internalPaths(html, finalUrl)) {
      if (queued.has(path) || Object.keys(snapshots).length + queue.length >= maxPages) continue;
      queued.add(path);
      queue.push(path);
    }
  } catch (error) {
    errors.push({ path: requestedPath, status: null, detail: String(error?.message || error).slice(0, 240) });
  }
}

if (typeof snapshots['/'] !== 'string') {
  const failed = { status: 'failed', builtAt, pages: 0, bytes: 0, errors };
  fs.writeFileSync(outPath, `${JSON.stringify(failed, null, 2)}\n`);
  throw new Error(`Snapshot builder failed to capture homepage: ${JSON.stringify(errors).slice(0, 1000)}`);
}

if (inlineCss === null) inlineCss = await buildInlineCss(snapshots['/'], origin, builtAt);

const serialized = JSON.stringify(snapshots).replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
const source = [
  '// Generated immediately before Cloudflare deployment. Do not hand-edit.',
  `export const SNAPSHOT_BUILT_AT = ${JSON.stringify(builtAt)};`,
  `export const SNAPSHOTS = Object.freeze(${serialized});`,
  '',
].join('\n');
fs.writeFileSync(modulePath, source);

const result = {
  status: 'ready',
  origin: origin.origin,
  builtAt,
  pages: Object.keys(snapshots).length,
  bytes: totalBytes,
  paths: Object.keys(snapshots).sort(),
  inlineCss,
  errors: errors.slice(0, 20),
  modulePath,
};
fs.writeFileSync(outPath, `${JSON.stringify(result, null, 2)}\n`);
console.log(JSON.stringify(result, null, 2));
