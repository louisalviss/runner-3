import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import { performance } from 'node:perf_hooks';

const token = process.env.CLOUDFLARE_API_TOKEN;
const workerName = process.env.CF_WORKER_NAME || 'wordpress-edge-proxy';
const configPath = process.env.CF_WORKER_CONFIG || 'edge/wordpress-edge-proxy/wrangler.jsonc';
const outPath = process.env.CF_EDGE_OUT || '/tmp/cloudflare-wordpress-edge.json';
const snapshotModulePath = process.env.CF_SNAPSHOT_MODULE || 'edge/wordpress-edge-proxy/src/snapshot.generated.js';
const wasmerOrigin = 'https://runner3-factory-smoke-2.wasmer.app';
const maxSnapshotPages = Math.max(1, Number(process.env.CF_SNAPSHOT_MAX_PAGES || 40));
const maxSnapshotBytes = Math.max(250000, Number(process.env.CF_SNAPSHOT_MAX_BYTES || 2500000));

const result = {
  status: 'starting',
  workerName,
  edgeUrl: null,
  deployed: false,
  workersDevEnabled: false,
  snapshot: null,
  probe: null,
  detail: null,
  checkedAt: new Date().toISOString(),
};

function save() {
  result.checkedAt = new Date().toISOString();
  fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
}

function safeText(value) {
  return String(value ?? '')
    .replace(/[A-Za-z0-9_-]{32,}/g, '[redacted]')
    .slice(0, 4000);
}

async function cf(path, init = {}) {
  const response = await fetch(`https://api.cloudflare.com/client/v4${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || !data?.success) {
    throw new Error(`Cloudflare API ${path} failed ${response.status}: ${safeText(JSON.stringify(data?.errors || data))}`);
  }
  return data.result;
}

function median(values) {
  const a = values.filter(Number.isFinite).sort((x, y) => x - y);
  return a.length ? a[Math.floor(a.length / 2)] : null;
}

function normalizeSnapshotPath(pathname) {
  const path = pathname || '/';
  if (path === '/' || path.endsWith('/') || /\.[^/]+$/.test(path)) return path;
  return `${path}/`;
}

function isPublicSnapshotPath(pathname) {
  if (!pathname || pathname === '/') return true;
  if (pathname === '/wp-login.php' || pathname.startsWith('/wp-admin/') || pathname.startsWith('/wp-json/')) return false;
  if (pathname === '/xmlrpc.php' || pathname === '/wp-cron.php') return false;
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

function extractInternalPaths(html, baseUrl, origin) {
  const paths = [];
  const seen = new Set();
  for (const match of html.matchAll(/href\s*=\s*["']([^"']+)["']/gi)) {
    const raw = decodeHref(match[1]).trim();
    if (!raw || raw.startsWith('#') || /^(?:mailto:|tel:|javascript:|data:)/i.test(raw)) continue;
    try {
      const url = new URL(raw, baseUrl);
      if (url.origin !== origin.origin || url.search) continue;
      const path = normalizeSnapshotPath(url.pathname);
      if (!isPublicSnapshotPath(path) || seen.has(path)) continue;
      seen.add(path);
      paths.push(path);
    } catch {
      // Ignore malformed author-supplied links.
    }
  }
  return paths;
}

async function discoverSitemapPaths(origin) {
  const pages = new Set();
  const sitemapQueue = [new URL('/wp-sitemap.xml', origin).toString()];
  const seenSitemaps = new Set();

  while (sitemapQueue.length && seenSitemaps.size < 12 && pages.size < maxSnapshotPages) {
    const sitemapUrl = sitemapQueue.shift();
    if (seenSitemaps.has(sitemapUrl)) continue;
    seenSitemaps.add(sitemapUrl);
    try {
      const response = await fetch(sitemapUrl, {
        redirect: 'follow',
        headers: { 'User-Agent': 'CloudflareEdgeSnapshotBuilder/1.0', Accept: 'application/xml,text/xml,*/*' },
      });
      if (!response.ok) continue;
      const xml = await response.text();
      for (const match of xml.matchAll(/<loc>\s*([^<]+?)\s*<\/loc>/gi)) {
        const loc = decodeHref(match[1]);
        let url;
        try { url = new URL(loc, sitemapUrl); } catch { continue; }
        if (url.origin !== origin.origin) continue;
        if (/\.xml$/i.test(url.pathname)) {
          if (!seenSitemaps.has(url.toString())) sitemapQueue.push(url.toString());
          continue;
        }
        const path = normalizeSnapshotPath(url.pathname);
        if (isPublicSnapshotPath(path)) pages.add(path);
        if (pages.size >= maxSnapshotPages) break;
      }
    } catch {
      // Sitemap is discovery-only; homepage crawling still provides a fallback.
    }
  }
  return [...pages];
}

async function buildSnapshotModule() {
  const origin = new URL(wasmerOrigin);
  const builtAt = new Date().toISOString();
  const queue = ['/'];
  const queued = new Set(queue);
  const sitemapPaths = await discoverSitemapPaths(origin);
  for (const path of sitemapPaths) {
    if (!queued.has(path) && queue.length < maxSnapshotPages) {
      queue.push(path);
      queued.add(path);
    }
  }

  const snapshots = {};
  const errors = [];
  let totalBytes = 0;

  while (queue.length && Object.keys(snapshots).length < maxSnapshotPages && totalBytes < maxSnapshotBytes) {
    const requestedPath = queue.shift();
    const requestedUrl = new URL(requestedPath, origin);
    try {
      const response = await fetch(requestedUrl, {
        redirect: 'follow',
        headers: {
          'User-Agent': 'CloudflareEdgeSnapshotBuilder/1.0',
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
      if (totalBytes + bytes > maxSnapshotBytes && Object.keys(snapshots).length > 0) break;

      const finalUrl = new URL(response.url || requestedUrl);
      const requestedKey = normalizeSnapshotPath(requestedUrl.pathname);
      const finalKey = normalizeSnapshotPath(finalUrl.pathname);
      if (!(requestedKey in snapshots)) {
        snapshots[requestedKey] = html;
        totalBytes += bytes;
      }
      if (finalKey !== requestedKey && !(finalKey in snapshots)) snapshots[finalKey] = html;

      for (const path of extractInternalPaths(html, finalUrl, origin)) {
        if (queued.has(path) || Object.keys(snapshots).length + queue.length >= maxSnapshotPages) continue;
        queued.add(path);
        queue.push(path);
      }
    } catch (error) {
      errors.push({ path: requestedPath, status: null, detail: safeText(error?.message || error) });
    }
  }

  if (typeof snapshots['/'] !== 'string') throw new Error(`Snapshot builder failed to capture homepage: ${safeText(JSON.stringify(errors))}`);

  const json = JSON.stringify(snapshots).replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
  const source = [
    '// Generated locally immediately before Cloudflare deployment. Do not hand-edit.',
    `export const SNAPSHOT_BUILT_AT = ${JSON.stringify(builtAt)};`,
    `export const SNAPSHOTS = Object.freeze(${json});`,
    '',
  ].join('\n');
  fs.writeFileSync(snapshotModulePath, source);

  return {
    builtAt,
    pages: Object.keys(snapshots).length,
    bytes: totalBytes,
    paths: Object.keys(snapshots).sort(),
    errors: errors.slice(0, 20),
    modulePath: snapshotModulePath,
  };
}

async function request(url, init = {}) {
  const started = performance.now();
  const response = await fetch(url, { redirect: 'manual', ...init });
  const ttfbMs = performance.now() - started;
  const body = init.method === 'HEAD' ? '' : await response.text();
  return {
    status: response.status,
    ttfbMs: Math.round(ttfbMs * 1000) / 1000,
    totalMs: Math.round((performance.now() - started) * 1000) / 1000,
    bytes: Buffer.byteLength(body),
    edgeProxy: response.headers.get('x-edge-proxy'),
    edgeMode: response.headers.get('x-edge-mode'),
    snapshot: response.headers.get('x-edge-snapshot'),
    snapshotBuiltAt: response.headers.get('x-edge-snapshot-built-at'),
    upstreamCache: response.headers.get('x-upstream-cf-cache-status'),
    upstreamStamp: response.headers.get('x-upstream-origin-stamp'),
    location: response.headers.get('location'),
    cacheControl: response.headers.get('cache-control'),
    body,
  };
}

function summarize(r) {
  const { body, ...safe } = r;
  return safe;
}

async function runProbe(edgeUrl) {
  const homepageRuns = [];
  for (let i = 0; i < 8; i++) homepageRuns.push(await request(`${edgeUrl}/`));

  const stamps = homepageRuns.map((x) => x.upstreamStamp).filter(Boolean);
  const stampCounts = new Map();
  for (const stamp of stamps) stampCounts.set(stamp, (stampCounts.get(stamp) || 0) + 1);
  const repeatedOriginStamp = [...stampCounts.values()].some((count) => count >= 2);
  const explicitHit = homepageRuns.slice(1).some((x) => String(x.upstreamCache || '').toUpperCase() === 'HIT');
  const snapshotVerified = homepageRuns.every((x) => String(x.snapshot || '').toUpperCase() === 'HIT' && x.edgeMode === 'snapshot');
  const warmMedianTtfbMs = median(homepageRuns.slice(1).map((x) => x.ttfbMs));
  const firstTtfbMs = homepageRuns[0]?.ttfbMs ?? null;
  const coldFast = Number.isFinite(firstTtfbMs) && firstTtfbMs < 300;

  const homeBody = homepageRuns.at(-1)?.body || '';
  const escapedEdge = edgeUrl.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const hrefs = [...homeBody.matchAll(/href=["']([^"']+)["']/gi)].map((m) => m[1]);
  const articleHref = hrefs.find((href) => new RegExp(`^${escapedEdge}/2026/`, 'i').test(href)) || null;
  const internalLinkRewritten = Boolean(articleHref) && !/href=["']https:\/\/runner3-factory-smoke-2\.wasmer\.app\//i.test(homeBody);

  const articleRuns = [];
  if (articleHref) {
    articleRuns.push(await request(articleHref));
    articleRuns.push(await request(articleHref));
  }
  const articleSnapshot = articleRuns.length === 2 && articleRuns.every((x) => String(x.snapshot || '').toUpperCase() === 'HIT');
  const articleHit = articleRuns.length === 2 && (
    articleSnapshot ||
    String(articleRuns[1].upstreamCache || '').toUpperCase() === 'HIT' ||
    (articleRuns[0].upstreamStamp && articleRuns[0].upstreamStamp === articleRuns[1].upstreamStamp)
  );

  const login = await request(`${edgeUrl}/wp-login.php`);
  const rest = await request(`${edgeUrl}/wp-json/`);
  const cookieBypass = await request(`${edgeUrl}/`, { headers: { Cookie: 'edge_probe=1' } });

  const loginSafe = login.status === 307 && String(login.location || '').startsWith(`${wasmerOrigin}/wp-login.php`);
  const restSafe = rest.status === 200 && rest.edgeMode === 'bypass' && String(rest.upstreamCache || '').toUpperCase() !== 'HIT' && String(rest.snapshot || '').toUpperCase() !== 'HIT';
  const cookieSafe = cookieBypass.status === 200 && cookieBypass.edgeMode === 'bypass' && String(cookieBypass.upstreamCache || '').toUpperCase() !== 'HIT' && String(cookieBypass.snapshot || '').toUpperCase() !== 'HIT';
  const homeHealthy = homepageRuns.every((x) => x.status === 200 && x.edgeProxy === 'cloudflare-worker');
  const cacheVerified = snapshotVerified || explicitHit || repeatedOriginStamp;

  return {
    pass: homeHealthy && snapshotVerified && coldFast && internalLinkRewritten && loginSafe && restSafe && cookieSafe && (!articleHref || articleSnapshot),
    cacheVerified,
    snapshotVerified,
    coldFast,
    proof: { snapshotVerified, explicitHit, repeatedOriginStamp, articleHit, articleSnapshot },
    firstTtfbMs,
    warmMedianTtfbMs,
    homepageRuns: homepageRuns.map(summarize),
    internalLinkRewritten,
    articleHref,
    articleRuns: articleRuns.map(summarize),
    loginSafe,
    restSafe,
    cookieSafe,
    login: summarize(login),
    rest: summarize(rest),
    cookieBypass: summarize(cookieBypass),
  };
}

try {
  if (!token) throw new Error('CLOUDFLARE_API_TOKEN missing');
  save();

  result.snapshot = await buildSnapshotModule();
  save();

  const accounts = await cf('/accounts?per_page=50');
  if (!Array.isArray(accounts) || !accounts.length) throw new Error('No Cloudflare account available to token');
  const account = [...accounts].sort((a, b) => String(a.id).localeCompare(String(b.id)))[0];
  const accountId = account.id;

  const deploy = spawnSync('npx', ['--yes', 'wrangler@4.102.0', 'deploy', '--config', configPath], {
    encoding: 'utf8',
    env: { ...process.env, CLOUDFLARE_ACCOUNT_ID: accountId },
    timeout: 180000,
  });
  if (deploy.status !== 0) {
    throw new Error(`wrangler deploy failed: ${safeText((deploy.stderr || '') + '\n' + (deploy.stdout || ''))}`);
  }
  result.deployed = true;
  save();

  let subdomainState = await cf(`/accounts/${accountId}/workers/scripts/${encodeURIComponent(workerName)}/subdomain`);
  if (!subdomainState.enabled) {
    subdomainState = await cf(`/accounts/${accountId}/workers/scripts/${encodeURIComponent(workerName)}/subdomain`, {
      method: 'POST',
      body: JSON.stringify({ enabled: true, previews_enabled: false }),
    });
  }
  result.workersDevEnabled = Boolean(subdomainState.enabled);

  const accountSubdomain = await cf(`/accounts/${accountId}/workers/subdomain`);
  if (!accountSubdomain?.subdomain) throw new Error('Cloudflare workers.dev account subdomain missing');
  result.edgeUrl = `https://${workerName}.${accountSubdomain.subdomain}.workers.dev`;
  save();

  await new Promise((resolve) => setTimeout(resolve, 2500));
  result.probe = await runProbe(result.edgeUrl);
  result.status = result.probe.pass ? 'completed' : 'probe_failed';
  save();
} catch (error) {
  result.status = 'failed';
  result.detail = safeText(error?.message || error);
  save();
}

console.log(JSON.stringify({
  status: result.status,
  workerName: result.workerName,
  edgeUrl: result.edgeUrl,
  deployed: result.deployed,
  workersDevEnabled: result.workersDevEnabled,
  snapshot: result.snapshot && {
    builtAt: result.snapshot.builtAt,
    pages: result.snapshot.pages,
    bytes: result.snapshot.bytes,
    paths: result.snapshot.paths,
    errors: result.snapshot.errors,
  },
  probe: result.probe && {
    pass: result.probe.pass,
    cacheVerified: result.probe.cacheVerified,
    snapshotVerified: result.probe.snapshotVerified,
    coldFast: result.probe.coldFast,
    proof: result.probe.proof,
    firstTtfbMs: result.probe.firstTtfbMs,
    warmMedianTtfbMs: result.probe.warmMedianTtfbMs,
    internalLinkRewritten: result.probe.internalLinkRewritten,
    loginSafe: result.probe.loginSafe,
    restSafe: result.probe.restSafe,
    cookieSafe: result.probe.cookieSafe,
  },
  detail: result.detail,
}, null, 2));

if (result.status !== 'completed') process.exitCode = 1;
