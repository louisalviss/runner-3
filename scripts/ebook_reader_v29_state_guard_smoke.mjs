import { chromium } from 'playwright';

const CORE_URL = process.env.RUNNER3_CORE_URL || 'https://runner3-core.ducduy2411.workers.dev';
const BOOK_KEY = process.env.EBOOK_BROWSER_SMOKE_BOOK_KEY || 'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub';
const TEST_ID = 'state-guard-v29';
const readerUrl = `${CORE_URL}/artifact-library/read?key=${encodeURIComponent(BOOK_KEY)}`;

function makeSilentWav(seconds = 90) {
  const sampleRate = 8000;
  const samples = Math.max(sampleRate, Math.ceil(seconds * sampleRate));
  const out = Buffer.alloc(44 + samples, 128);
  out.write('RIFF', 0, 'ascii'); out.writeUInt32LE(36 + samples, 4); out.write('WAVE', 8, 'ascii');
  out.write('fmt ', 12, 'ascii'); out.writeUInt32LE(16, 16); out.writeUInt16LE(1, 20); out.writeUInt16LE(1, 22);
  out.writeUInt32LE(sampleRate, 24); out.writeUInt32LE(sampleRate, 28); out.writeUInt16LE(1, 32); out.writeUInt16LE(8, 34);
  out.write('data', 36, 'ascii'); out.writeUInt32LE(samples, 40);
  return out;
}

function audioRangeResponse(req, body) {
  const total = body.length;
  const range = String(req.headers()['range'] || '');
  const baseHeaders = { 'content-type': 'audio/wav', 'accept-ranges': 'bytes', 'cache-control': 'no-store' };
  if (!range) return { status: 200, headers: { ...baseHeaders, 'content-length': String(total) }, body };
  const match = /^bytes=(\d*)-(\d*)$/i.exec(range.trim());
  if (!match) return { status: 416, headers: { ...baseHeaders, 'content-range': `bytes */${total}` }, body: Buffer.alloc(0) };
  let start = match[1] ? Number(match[1]) : 0;
  let end = match[2] ? Number(match[2]) : total - 1;
  start = Math.max(0, Math.min(total - 1, start));
  end = Math.max(start, Math.min(total - 1, end));
  const chunk = body.subarray(start, end + 1);
  return { status: 206, headers: { ...baseHeaders, 'content-range': `bytes ${start}-${end}/${total}`, 'content-length': String(chunk.length) }, body: chunk };
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const errors = [];
page.on('pageerror', e => errors.push(String(e?.stack || e)));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

let syntheticReady = false;
let words = [];
const wav = makeSilentWav();
let postCount = 0;
const mediaUrl = `${CORE_URL}/artifact-library/api/audio/${TEST_ID}/media`;
const timingUrl = `${CORE_URL}/artifact-library/api/audio/${TEST_ID}/timing`;
const state = () => ({ ok: true, id: TEST_ID, status: 'ready', mediaUrl, timingUrl, durationSeconds: 90, error: null });

await page.route('**/*', async route => {
  if (!syntheticReady) return route.continue();
  const req = route.request();
  let u;
  try { u = new URL(req.url()); } catch { return route.continue(); }
  if (u.origin === new URL(CORE_URL).origin && u.pathname === '/artifact-library/audio') {
    if (req.method() === 'POST') { postCount++; return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(state()) }); }
    if (req.method() === 'GET' && u.searchParams.get('id') === TEST_ID) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(state()) });
  }
  if (u.href === timingUrl) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ words }) });
  if (u.href === mediaUrl) return route.fulfill(audioRangeResponse(req, wav));
  return route.continue();
});

async function boot() {
  await page.waitForSelector('#r3AudioMain', { timeout: 30000 });
  await page.waitForSelector('#viewer iframe', { timeout: 30000 });
  await page.waitForFunction(() => Boolean(window.r3ReaderBridge), null, { timeout: 30000 });
}

async function snapshot() {
  return page.evaluate(() => {
    const cfi = window.r3ReaderBridge?.current?.()?.start?.cfi || null;
    const href = window.r3ReaderBridge?.current?.()?.start?.href || null;
    const frames = [...document.querySelectorAll('#viewer iframe')];
    let best = null;
    for (const frame of frames) {
      try {
        const doc = frame.contentDocument;
        const text = String(doc?.body?.innerText || '').trim();
        if (!best || text.length > best.text.length) best = { text, doc };
      } catch {}
    }
    const text = best?.text || '';
    const tokens = (() => { try { return text.match(/[\p{L}\p{M}\p{N}]+/gu) || []; } catch { return text.split(/\s+/).filter(Boolean); } })();
    return { cfi, href, textLength: text.length, tokenCount: tokens.length, tokens: tokens.slice(0, 5000) };
  });
}

try {
  const nav = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await boot();
  const runtime = nav?.headers()?.['x-r3-reader-runtime'] || '';
  if (!runtime.includes('v29')) throw new Error(`live Reader is not v29: ${runtime || 'missing header'}`);
  await page.waitForFunction(() => window.__r3AudioMediaStateGuardV29 === true, null, { timeout: 10000 });

  let candidate = null;
  let previous = null;
  for (let n = 0; n < 80; n++) {
    const s = await snapshot();
    if (s.tokenCount > 120 && previous?.textLength < 80) { candidate = s; break; }
    previous = s;
    await page.evaluate(async () => { if (window.r3ReaderBridge?.next) await window.r3ReaderBridge.next(); });
    await page.waitForTimeout(180);
  }
  if (!candidate) throw new Error('could not find readable page immediately after sparse page');

  words = candidate.tokens.map((text, index) => ({ text, startMs: index * 70, durationMs: 45 }));
  syntheticReady = true;
  await page.locator('#r3AudioMain').click();
  await page.waitForFunction(id => String(document.getElementById('r3AudioElement')?.currentSrc || '').includes(id), TEST_ID, { timeout: 20000 });
  await page.waitForTimeout(500);
  await page.evaluate(() => document.getElementById('r3AudioElement')?.pause());
  if (postCount !== 1) throw new Error(`expected one initial POST, got ${postCount}`);

  await page.evaluate(async () => { if (window.r3ReaderBridge?.prev) await window.r3ReaderBridge.prev(); });
  await page.waitForTimeout(260);
  const sparse = await snapshot();
  if (sparse.textLength >= 80) throw new Error(`expected sparse page, got textLength=${sparse.textLength}`);

  await page.locator('#r3AudioMain').click();
  await page.waitForTimeout(500);
  const proof = await page.evaluate(() => {
    const a = document.getElementById('r3AudioElement');
    const status = document.getElementById('r3AudioStatus')?.textContent || '';
    return { paused: Boolean(a?.paused), ended: Boolean(a?.ended), src: String(a?.currentSrc || a?.getAttribute('src') || ''), status };
  });
  console.log(JSON.stringify({ phase: 'v29-state-guard-proof', postCount, sparseTextLength: sparse.textLength, ...proof }));
  if (postCount !== 1) throw new Error(`sparse-page click created duplicate POST: ${postCount}`);
  if (!proof.src.includes(TEST_ID)) throw new Error('existing media was lost on sparse page');
  if (/Chưa lấy được nội dung chương/i.test(proof.status)) throw new Error(`stale no-content status survived with valid media: ${proof.status}`);
  if (proof.paused && !proof.ended) throw new Error('valid paused media did not resume on sparse page');
  if (errors.length) throw new Error('browser runtime errors: ' + errors.join(' | ').slice(0, 1200));

  console.log(JSON.stringify({ phase: 'v29-state-guard', ok: true, postCount, status: proof.status }));
} finally {
  await browser.close();
}
