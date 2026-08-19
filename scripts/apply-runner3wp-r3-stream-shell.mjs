import fs from 'node:fs';

const file = 'edge/wordpress-edge-proxy/src/entry.js';
const source = fs.readFileSync(file, 'utf8');

if (source.includes("const R3_STREAM_PATH = '/__runner3/r3-stream';")) {
  console.log('R3 streaming shell already applied');
  process.exit(0);
}

const helperMarker = '\nexport default {\n';
if (!source.includes(helperMarker)) throw new Error('entry.js export marker not found');

const helper = String.raw`
const R3_STREAM_PATH = '/__runner3/r3-stream';
const R3_DELAY_MS = 900;
const R3_FIRST_CHUNK = '<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>Runner3 R3 FCP</title><style>html,body{margin:0}body{font:16px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#fff;color:#111}.r3-first{max-width:760px;margin:0 auto;padding:24px 20px}.r3-kicker{margin:0 0 8px;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}.r3-first h1{margin:0;font-size:32px;line-height:1.08;letter-spacing:-.03em}</style></head><body><main class="r3-first" data-runner3-r3="first-paint"><p class="r3-kicker">Runner 3</p><h1>Tín hiệu quan trọng, hiển thị ngay.</h1></main>';

function r3DeferredTail(html) {
  const head = (html.match(/<head\b[^>]*>([\s\S]*?)<\/head>/i) || [])[1] || '';
  const body = (html.match(/<body\b[^>]*>([\s\S]*?)<\/body>/i) || [])[1] || '';
  const styles = (head.match(/<style\b[^>]*>[\s\S]*?<\/style>/gi) || []).join('');
  const stylesheetLinks = (head.match(/<link\b[^>]*>/gi) || []).filter((tag) => /\brel\s*=\s*["'][^"']*stylesheet/i.test(tag)).join('');
  const safeBody = body || '<main><p>Runner3 R3 deferred content unavailable.</p></main>';
  return styles + stylesheetLinks + '<div data-runner3-r3="deferred">' + safeBody + '</div><script>document.querySelector("[data-runner3-r3=first-paint]")?.remove();</script></body></html>';
}

async function r3StreamingShellResponse(request, env, ctx) {
  const method = request.method.toUpperCase();
  if (!['GET', 'HEAD'].includes(method)) return new Response('Method Not Allowed', { status: 405, headers: { Allow: 'GET, HEAD' } });
  const headers = new Headers({
    'Content-Type': 'text/html; charset=UTF-8',
    'Cache-Control': 'no-store',
    'X-Robots-Tag': 'noindex, nofollow, noarchive, nosnippet',
    'X-Edge-Proxy': 'cloudflare-worker',
    'X-Runner3-R3': 'stream-shell',
  });
  if (method === 'HEAD') return new Response(null, { status: 200, headers });

  const encoder = new TextEncoder();
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  const task = (async () => {
    try {
      await writer.write(encoder.encode(R3_FIRST_CHUNK));
      await new Promise((resolve) => setTimeout(resolve, R3_DELAY_MS));
      const rootUrl = new URL('/', request.url);
      const rootRequest = new Request(rootUrl, { method: 'GET', headers: { 'User-Agent': 'Runner3-R3-Deferred/1.0' } });
      let original = await worker.fetch(rootRequest, env, ctx);
      original = await decorateFrontend(rootRequest, original);
      const html = await original.text();
      await writer.write(encoder.encode(r3DeferredTail(html)));
    } catch (_) {
      try { await writer.write(encoder.encode('<p data-runner3-r3="fallback">Deferred content failed.</p></body></html>')); } catch (_) {}
    } finally {
      try { await writer.close(); } catch (_) {}
    }
  })();
  ctx.waitUntil(task);
  return new Response(readable, { status: 200, headers });
}
`;

let next = source.replace(helperMarker, `${helper}\nexport default {\n`);
const fetchMarker = "    const incoming = new URL(request.url); if (incoming.pathname === PURGE_PATH) return handlePurge(request, env, ctx);";
if (!next.includes(fetchMarker)) throw new Error('entry.js fetch marker not found');
next = next.replace(
  fetchMarker,
  "    const incoming = new URL(request.url); if (incoming.pathname === R3_STREAM_PATH) return r3StreamingShellResponse(request, env, ctx); if (incoming.pathname === PURGE_PATH) return handlePurge(request, env, ctx);",
);

fs.writeFileSync(file, next);
console.log(JSON.stringify({
  status: 'patched',
  file,
  route: '/__runner3/r3-stream',
  delayMs: 900,
  firstChunkBytes: Buffer.byteLength('<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>Runner3 R3 FCP</title><style>html,body{margin:0}body{font:16px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#fff;color:#111}.r3-first{max-width:760px;margin:0 auto;padding:24px 20px}.r3-kicker{margin:0 0 8px;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}.r3-first h1{margin:0;font-size:32px;line-height:1.08;letter-spacing:-.03em}</style></head><body><main class="r3-first" data-runner3-r3="first-paint"><p class="r3-kicker">Runner 3</p><h1>Tín hiệu quan trọng, hiển thị ngay.</h1></main>'),
}, null, 2));
