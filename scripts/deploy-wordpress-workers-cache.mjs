import fs from 'fs';
import { execFileSync } from 'child_process';

const config = process.env.CF_WORKER_CONFIG || 'edge/wordpress-edge-proxy/wrangler.jsonc';
const workerUrl = process.env.CF_EDGE_URL || 'https://wordpress-edge-proxy.ducduy2411.workers.dev';
const outFile = process.env.CF_EDGE_OUT || '/tmp/cloudflare-wordpress-edge.json';
const wrangler = 'wrangler@4.124.0';

if (!process.env.CLOUDFLARE_API_TOKEN) throw new Error('CLOUDFLARE_API_TOKEN missing');

function run(args) {
  execFileSync('npx', ['--yes', wrangler, ...args], {
    cwd: process.cwd(),
    env: process.env,
    stdio: 'inherit',
  });
}

function write(data) {
  fs.writeFileSync(outFile, `${JSON.stringify(data, null, 2)}\n`);
}

async function request(path, init = {}) {
  const started = performance.now();
  const response = await fetch(new URL(path, workerUrl), { redirect: 'manual', ...init });
  const text = init.method === 'HEAD' ? '' : await response.text();
  return {
    status: response.status,
    ms: Math.round((performance.now() - started) * 10) / 10,
    text,
    headers: Object.fromEntries([...response.headers.entries()].map(([k, v]) => [k.toLowerCase(), v])),
  };
}

try {
  run(['deploy', '--config', config]);
  const first = await request('/');
  await new Promise((resolve) => setTimeout(resolve, 600));
  const second = await request('/');
  const admin = await request('/wp-admin/');
  const authBypass = await request('/', { headers: { cookie: 'wordpress_logged_in_probe=1' } });
  const unsignedPurge = await request('/__runner3/cache/purge', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ reason: 'unsigned-probe', urls: ['/'] }),
  });

  const firstCache = String(first.headers['cf-cache-status'] || '').toUpperCase();
  const secondCache = String(second.headers['cf-cache-status'] || '').toUpperCase();
  const publicReady = first.status === 200 && second.status === 200;
  const policyReady = first.headers['x-edge-cache-policy'] === 'workers-caching' && second.headers['x-edge-cache-policy'] === 'workers-caching';
  const cacheHit = firstCache === 'HIT' || secondCache === 'HIT' || Boolean(first.headers.age || second.headers.age);
  const signedPurgeRequired = unsignedPurge.status === 401;
  const loginSafe = admin.status === 307 && /runner3-factory-smoke-2\.wasmer\.app/i.test(admin.headers.location || '');
  const cookieSafe = authBypass.headers['x-edge-mode'] === 'bypass' && /private|no-store/i.test(authBypass.headers['cache-control'] || '');
  const responsiveReady = /responsive-v2\/offset-demo-01-w(?:360|480|640)\.webp/i.test(first.text) && /srcset=/i.test(first.text);
  const noindexReady = /noindex/i.test(first.headers['x-robots-tag'] || '');

  const result = {
    status: publicReady && policyReady && cacheHit && signedPurgeRequired && loginSafe && cookieSafe && responsiveReady && noindexReady ? 'completed' : 'failed',
    edgeUrl: workerUrl,
    architecture: 'workers-caching-live-origin',
    purgeEndpoint: `${workerUrl}/__runner3/cache/purge`,
    checkedAt: new Date().toISOString(),
    probe: {
      publicReady,
      policyReady,
      cacheHit,
      signedPurgeRequired,
      loginSafe,
      cookieSafe,
      responsiveReady,
      noindexReady,
      unsignedPurgeHttp: unsignedPurge.status,
      first: { http: first.status, ms: first.ms, cfCacheStatus: firstCache || null, age: first.headers.age || null, edgeMode: first.headers['x-edge-mode'] || null },
      second: { http: second.status, ms: second.ms, cfCacheStatus: secondCache || null, age: second.headers.age || null, edgeMode: second.headers['x-edge-mode'] || null },
      authBypass: { http: authBypass.status, edgeMode: authBypass.headers['x-edge-mode'] || null, cacheControl: authBypass.headers['cache-control'] || null },
    },
  };
  write(result);
  console.log(JSON.stringify(result, null, 2));
  if (result.status !== 'completed') process.exitCode = 9;
} catch (error) {
  const result = { status: 'failed', edgeUrl: workerUrl, detail: String(error?.message || error), checkedAt: new Date().toISOString() };
  write(result);
  console.error(JSON.stringify(result, null, 2));
  process.exitCode = 10;
}
