import fs from 'node:fs';
import { execFileSync } from 'node:child_process';

const config = process.env.CF_WORKER_CONFIG || 'edge/wordpress-edge-proxy/wrangler.jsonc';
const workerUrl = process.env.CF_EDGE_URL || 'https://wordpress-edge-proxy.ducduy2411.workers.dev';
const outFile = process.env.CF_EDGE_OUT || '/tmp/cloudflare-wordpress-edge.json';
const snapshotOut = process.env.CF_SNAPSHOT_OUT || '/tmp/runner3-edge-snapshot.json';
const purgeSecret = String(process.env.RUNNER3_PURGE_SECRET || '');
const rotatePurgeSecret = process.env.CF_ROTATE_PURGE_SECRET === '1';
const wrangler = 'wrangler@4.124.0';

if (!process.env.CLOUDFLARE_API_TOKEN) throw new Error('CLOUDFLARE_API_TOKEN missing');
if (rotatePurgeSecret && (!purgeSecret || purgeSecret.length < 32)) throw new Error('RUNNER3_PURGE_SECRET missing or too short');

function run(args, input = null) {
  execFileSync('npx', ['--yes', wrangler, ...args], {
    cwd: process.cwd(),
    env: process.env,
    stdio: input === null ? 'inherit' : ['pipe', 'inherit', 'inherit'],
    ...(input === null ? {} : { input }),
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
  execFileSync('node', ['scripts/build-wordpress-edge-snapshot.mjs'], {
    cwd: process.cwd(), env: process.env, stdio: 'inherit',
  });
  const snapshot = JSON.parse(fs.readFileSync(snapshotOut, 'utf8'));
  if (snapshot.status !== 'ready' || !(snapshot.pages > 0) || !snapshot.paths?.includes('/')) {
    throw new Error(`fresh snapshot unavailable: ${JSON.stringify(snapshot).slice(0, 1200)}`);
  }

  run(['deploy', '--config', config]);
  if (rotatePurgeSecret) {
    run(['secret', 'put', 'RUNNER3_CACHE_PURGE_SECRET', '--config', config], `${purgeSecret}\n`);
  }
  await new Promise((resolve) => setTimeout(resolve, 2500));

  const homeRuns = [];
  for (let i = 0; i < 4; i += 1) {
    homeRuns.push(await request('/'));
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  const first = homeRuns[0];
  const second = homeRuns.at(-1);
  const admin = await request('/wp-admin/');
  const authBypass = await request('/', { headers: { cookie: 'wordpress_logged_in_probe=1' } });
  const unsignedPurge = await request('/__runner3/cache/purge', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ reason: 'unsigned-probe', urls: ['/'] }),
  });

  const publicReady = homeRuns.every((r) => r.status === 200);
  const policyReady = homeRuns.every((r) => ['snapshot-direct', 'workers-caching'].includes(r.headers['x-edge-cache-policy']));
  const snapshotRuns = homeRuns.filter((r) => r.headers['x-edge-mode'] === 'snapshot' && String(r.headers['x-edge-snapshot'] || '').toUpperCase() === 'HIT');
  const snapshotReady = snapshotRuns.length >= 3;
  const snapshotTimes = snapshotRuns.map((r) => r.ms).sort((a, b) => a - b);
  const medianSnapshotMs = snapshotTimes.length ? snapshotTimes[Math.floor(snapshotTimes.length / 2)] : null;
  const coldFast = snapshotReady && Number.isFinite(medianSnapshotMs) && medianSnapshotMs < 300;
  const cacheHit = homeRuns.some((r) => String(r.headers['cf-cache-status'] || '').toUpperCase() === 'HIT' || r.headers.age);
  const signedPurgeRequired = unsignedPurge.status === 401;
  const loginSafe = admin.status === 307 && /runner3-factory-smoke-2\.wasmer\.app/i.test(admin.headers.location || '');
  const cookieSafe = authBypass.headers['x-edge-mode'] === 'bypass' && /private|no-store/i.test(authBypass.headers['cache-control'] || '');
  const responsiveReady = /responsive-v2\/offset-demo-01-w(?:360|480|640)\.webp/i.test(second.text) && /srcset=/i.test(second.text);
  const noindexReady = /noindex/i.test(second.headers['x-robots-tag'] || '');

  const completed = publicReady && policyReady && snapshotReady && coldFast && signedPurgeRequired && loginSafe && cookieSafe && responsiveReady && noindexReady;
  const result = {
    status: completed ? 'completed' : 'failed',
    edgeUrl: workerUrl,
    architecture: 'snapshot-direct',
    purgeEndpoint: `${workerUrl}/__runner3/cache/purge`,
    auth: rotatePurgeSecret ? 'HMAC-SHA256-rotated' : 'HMAC-SHA256-preserved',
    checkedAt: new Date().toISOString(),
    snapshot,
    probe: {
      publicReady,
      policyReady,
      snapshotReady,
      coldFast,
      medianSnapshotMs,
      cacheHit,
      signedPurgeRequired,
      loginSafe,
      cookieSafe,
      responsiveReady,
      noindexReady,
      unsignedPurgeHttp: unsignedPurge.status,
      homeRuns: homeRuns.map((r) => ({
        http: r.status,
        ms: r.ms,
        cfCacheStatus: r.headers['cf-cache-status'] || null,
        age: r.headers.age || null,
        edgeMode: r.headers['x-edge-mode'] || null,
        edgeSnapshot: r.headers['x-edge-snapshot'] || null,
        edgePolicy: r.headers['x-edge-cache-policy'] || null,
        snapshotBuiltAt: r.headers['x-edge-snapshot-built-at'] || null,
      })),
      first: {
        http: first.status,
        ms: first.ms,
        cfCacheStatus: first.headers['cf-cache-status'] || null,
        age: first.headers.age || null,
        edgeMode: first.headers['x-edge-mode'] || null,
        edgeSnapshot: first.headers['x-edge-snapshot'] || null,
        edgePolicy: first.headers['x-edge-cache-policy'] || null,
      },
      second: {
        http: second.status,
        ms: second.ms,
        cfCacheStatus: second.headers['cf-cache-status'] || null,
        age: second.headers.age || null,
        edgeMode: second.headers['x-edge-mode'] || null,
        edgeSnapshot: second.headers['x-edge-snapshot'] || null,
        edgePolicy: second.headers['x-edge-cache-policy'] || null,
      },
      authBypass: {
        http: authBypass.status,
        edgeMode: authBypass.headers['x-edge-mode'] || null,
        cacheControl: authBypass.headers['cache-control'] || null,
      },
    },
  };
  write(result);
  console.log(JSON.stringify(result, null, 2));
  if (result.status !== 'completed') process.exitCode = 9;
} catch (error) {
  const result = {
    status: 'failed',
    edgeUrl: workerUrl,
    architecture: 'snapshot-direct',
    detail: String(error?.message || error),
    checkedAt: new Date().toISOString(),
  };
  write(result);
  console.error(JSON.stringify(result, null, 2));
  process.exitCode = 10;
}
