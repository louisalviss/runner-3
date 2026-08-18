import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import { performance } from 'node:perf_hooks';

const token = process.env.CLOUDFLARE_API_TOKEN;
const workerName = process.env.CF_WORKER_NAME || 'wordpress-edge-proxy';
const configPath = process.env.CF_WORKER_CONFIG || 'edge/wordpress-edge-proxy/wrangler.jsonc';
const outPath = process.env.CF_EDGE_OUT || '/tmp/cloudflare-wordpress-edge.json';
const wasmerOrigin = 'https://runner3-factory-smoke-2.wasmer.app';

const result = {
  status: 'starting',
  workerName,
  edgeUrl: null,
  deployed: false,
  workersDevEnabled: false,
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
  const warmMedianTtfbMs = median(homepageRuns.slice(1).map((x) => x.ttfbMs));

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
  const articleHit = articleRuns.length === 2 && (
    String(articleRuns[1].upstreamCache || '').toUpperCase() === 'HIT' ||
    (articleRuns[0].upstreamStamp && articleRuns[0].upstreamStamp === articleRuns[1].upstreamStamp)
  );

  const login = await request(`${edgeUrl}/wp-login.php`);
  const rest = await request(`${edgeUrl}/wp-json/`);
  const cookieBypass = await request(`${edgeUrl}/`, { headers: { Cookie: 'edge_probe=1' } });

  const loginSafe = login.status === 307 && String(login.location || '').startsWith(`${wasmerOrigin}/wp-login.php`);
  const restSafe = rest.status === 200 && rest.edgeMode === 'bypass' && String(rest.upstreamCache || '').toUpperCase() !== 'HIT';
  const cookieSafe = cookieBypass.status === 200 && cookieBypass.edgeMode === 'bypass' && String(cookieBypass.upstreamCache || '').toUpperCase() !== 'HIT';
  const homeHealthy = homepageRuns.every((x) => x.status === 200 && x.edgeProxy === 'cloudflare-worker');
  const cacheVerified = explicitHit || repeatedOriginStamp;

  return {
    pass: homeHealthy && cacheVerified && internalLinkRewritten && loginSafe && restSafe && cookieSafe && (!articleHref || articleHit),
    cacheVerified,
    proof: { explicitHit, repeatedOriginStamp, articleHit },
    firstTtfbMs: homepageRuns[0]?.ttfbMs ?? null,
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
  probe: result.probe && {
    pass: result.probe.pass,
    cacheVerified: result.probe.cacheVerified,
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
