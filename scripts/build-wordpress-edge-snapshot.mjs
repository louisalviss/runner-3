import fs from 'node:fs';

const origin = new URL(process.env.CF_SNAPSHOT_ORIGIN || 'https://runner3-factory-smoke-2.wasmer.app');
const modulePath = process.env.CF_SNAPSHOT_MODULE || 'edge/wordpress-edge-proxy/src/snapshot.generated.js';
const outPath = process.env.CF_SNAPSHOT_OUT || '/tmp/runner3-edge-snapshot.json';
const maxPages = Math.max(1, Number(process.env.CF_SNAPSHOT_MAX_PAGES || 40));
const maxBytes = Math.max(250000, Number(process.env.CF_SNAPSHOT_MAX_BYTES || 2500000));
const fcpV2 = process.env.RUNNER3_FCP_V2 === '1';

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

function optimizeFcpHtml(html) {
  if (!fcpV2) return { html, deferredStyleCount: 0, deferredStyleBytes: 0, criticalCopyBytes: 0, headSavedBytes: 0 };

  const headMatch = html.match(/<head\b[^>]*>([\s\S]*?)<\/head>/i);
  if (!headMatch) return { html, deferredStyleCount: 0, deferredStyleBytes: 0, criticalCopyBytes: 0, headSavedBytes: 0 };

  const headHtml = headMatch[1];
  const deferred = [];
  let criticalOriginal = null;
  const strippedHead = headHtml.replace(/<style\b[^>]*>[\s\S]*?<\/style>\s*/gi, (tag) => {
    const id = (tag.match(/\bid=(["'])([^"']+)\1/i) || [])[2] || '';
    deferred.push({ id, tag });
    if (id.toLowerCase() === 'runner3-critical-css') criticalOriginal = tag;
    return '';
  });

  if (!criticalOriginal || deferred.length < 2) {
    return { html, deferredStyleCount: 0, deferredStyleBytes: 0, criticalCopyBytes: 0, headSavedBytes: 0 };
  }

  const criticalMatch = criticalOriginal.match(/<style\b[^>]*>([\s\S]*?)<\/style>/i);
  const criticalCss = criticalMatch?.[1] || '';
  const rootStart = criticalCss.indexOf(':root {');
  const editionStart = criticalCss.indexOf('.edition-hero {', rootStart);
  const signalStart = criticalCss.indexOf('/* OFFSET / SIGNAL — front-page art direction */', rootStart);
  if (rootStart < 0 || editionStart <= rootStart || signalStart <= editionStart) {
    return { html, deferredStyleCount: 0, deferredStyleBytes: 0, criticalCopyBytes: 0, headSavedBytes: 0 };
  }
  const baseCritical = criticalCss.slice(rootStart, editionStart).trim();
  const signalCritical = criticalCss.slice(signalStart).trim();
  const criticalSubset = `${baseCritical}\n\n${signalCritical}`;
  const criticalCopy = `<style id="runner3-v2-critical-css" data-runner3-v2-critical="r1">\n${criticalSubset}\n</style>`;
  const optimizedHead = `${strippedHead}${criticalCopy}\n`;
  const headStart = headMatch.index + headMatch[0].indexOf(headMatch[1]);
  const headEnd = headStart + headMatch[1].length;
  const withCritical = `${html.slice(0, headStart)}${optimizedHead}${html.slice(headEnd)}`;

  const deferredCss = `\n<!-- runner3-v2-original-css-order -->\n${deferred.map(({ tag }) => tag.trim()).join('\n')}\n`;
  const bodyClose = withCritical.lastIndexOf('</body>');
  const optimized = bodyClose >= 0
    ? `${withCritical.slice(0, bodyClose)}${deferredCss}${withCritical.slice(bodyClose)}`
    : `${withCritical}${deferredCss}`;

  const deferredStyleBytes = deferred.reduce((sum, { tag }) => sum + Buffer.byteLength(tag), 0);
  const criticalCopyBytes = Buffer.byteLength(criticalCopy);
  return {
    html: optimized,
    deferredStyleCount: deferred.length,
    deferredStyleBytes,
    criticalCopyBytes,
    headSavedBytes: Math.max(0, Buffer.byteLength(headHtml) - Buffer.byteLength(optimizedHead)),
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
let deferredStyleCount = 0;
let deferredStyleBytes = 0;
let criticalCopyBytes = 0;
let headSavedBytes = 0;
let homepageFcp = null;

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

    const sourceHtml = await response.text();
    const fcp = optimizeFcpHtml(sourceHtml);
    const html = fcp.html;
    deferredStyleCount += fcp.deferredStyleCount;
    deferredStyleBytes += fcp.deferredStyleBytes;
    criticalCopyBytes += fcp.criticalCopyBytes;
    headSavedBytes += fcp.headSavedBytes;
    if (normalizePath(requestedUrl.pathname) === '/') {
      homepageFcp = {
        enabled: fcpV2,
        deferredStyleCount: fcp.deferredStyleCount,
        deferredStyleBytes: fcp.deferredStyleBytes,
        criticalCopyBytes: fcp.criticalCopyBytes,
        headSavedBytes: fcp.headSavedBytes,
        beforeBytes: Buffer.byteLength(sourceHtml),
        afterBytes: Buffer.byteLength(html),
      };
    }

    const bytes = Buffer.byteLength(html);
    if (bytes < 256) {
      errors.push({ path: requestedPath, status: response.status, detail: `html_too_small=${bytes}` });
      continue;
    }
    if (totalBytes + bytes > maxBytes && Object.keys(snapshots).length > 0) break;

    const finalUrl = new URL(response.url || requestedUrl);
    const requestedKey = normalizePath(requestedUrl.pathname);
    const finalKey = normalizePath(finalUrl.pathname);
    if (!(requestedKey in snapshots)) {
      snapshots[requestedKey] = html;
      totalBytes += bytes;
    }
    if (finalKey !== requestedKey && !(finalKey in snapshots)) snapshots[finalKey] = html;

    for (const path of internalPaths(sourceHtml, finalUrl)) {
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
  errors: errors.slice(0, 20),
  modulePath,
  fcpV2: {
    enabled: fcpV2,
    deferredStyleCount,
    deferredStyleBytes,
    criticalCopyBytes,
    headSavedBytes,
    homepage: homepageFcp,
  },
};
fs.writeFileSync(outPath, `${JSON.stringify(result, null, 2)}\n`);
console.log(JSON.stringify(result, null, 2));
