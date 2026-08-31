import { chromium } from 'playwright';

const CORE_URL = process.env.RUNNER3_CORE_URL;
const BOOK_KEY = process.env.EBOOK_BROWSER_SMOKE_BOOK_KEY || 'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub';
if (!CORE_URL) throw new Error('RUNNER3_CORE_URL_REQUIRED');
const readerUrl = `${CORE_URL}/artifact-library/read?key=${encodeURIComponent(BOOK_KEY)}`;
const ID1 = 'ebook-11111111111111111111111111111111';
const ID2 = 'ebook-22222222222222222222222222222222';
const STEP_MS = 50;

function tokensOf(value) {
  const text = String(value || '').normalize('NFKC').toLocaleLowerCase('vi-VN');
  try { return text.match(/[\p{L}\p{M}\p{N}]+/gu) || []; } catch { return text.split(/[^A-Za-z0-9À-ỹ]+/).filter(Boolean); }
}
function wordsFor(text) {
  return tokensOf(text).slice(0, 8000).map((token, index) => ({ text: token, startMs: index * STEP_MS, durationMs: 35 }));
}
function makeSilentWav(seconds) {
  const sampleRate = 8000;
  const samples = Math.max(sampleRate, Math.ceil(seconds * sampleRate));
  const out = Buffer.alloc(44 + samples, 128);
  out.write('RIFF', 0, 'ascii'); out.writeUInt32LE(36 + samples, 4); out.write('WAVE', 8, 'ascii');
  out.write('fmt ', 12, 'ascii'); out.writeUInt32LE(16, 16); out.writeUInt16LE(1, 20); out.writeUInt16LE(1, 22);
  out.writeUInt32LE(sampleRate, 24); out.writeUInt32LE(sampleRate, 28); out.writeUInt16LE(1, 32); out.writeUInt16LE(8, 34);
  out.write('data', 36, 'ascii'); out.writeUInt32LE(samples, 40);
  return out;
}
function rangeResponse(request, body) {
  const total = body.length;
  const range = String(request.headers()['range'] || '');
  const headers = { 'content-type': 'audio/wav', 'accept-ranges': 'bytes', 'cache-control': 'no-store' };
  if (!range) return { status: 200, headers: { ...headers, 'content-length': String(total) }, body };
  const match = /^bytes=(\d*)-(\d*)$/i.exec(range.trim());
  if (!match) return { status: 416, headers: { ...headers, 'content-range': `bytes */${total}` }, body: Buffer.alloc(0) };
  let start = match[1] ? Number(match[1]) : 0;
  let end = match[2] ? Number(match[2]) : total - 1;
  start = Math.max(0, Math.min(total - 1, start));
  end = Math.max(start, Math.min(total - 1, end));
  const chunk = body.subarray(start, end + 1);
  return { status: 206, headers: { ...headers, 'content-range': `bytes ${start}-${end}/${total}`, 'content-length': String(chunk.length) }, body: chunk };
}

const browser = await chromium.launch({ headless: true, args: ['--autoplay-policy=no-user-gesture-required'] });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
await context.addInitScript(() => {
  const audit = window.__r3OwnerAudit = { mainClicks: 0, speedClicks: 0, audioListeners: {}, intervals: [] };
  const originalAdd = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function(type, listener, options) {
    try {
      if (this?.id === 'r3AudioMain' && type === 'click') audit.mainClicks++;
      if (this?.id === 'r3AudioSpeed' && type === 'click') audit.speedClicks++;
      if (this?.id === 'r3AudioElement') audit.audioListeners[type] = (audit.audioListeners[type] || 0) + 1;
    } catch {}
    return originalAdd.call(this, type, listener, options);
  };
  const originalInterval = window.setInterval;
  window.setInterval = function(handler, delay, ...args) {
    audit.intervals.push(Number(delay) || 0);
    return originalInterval.call(this, handler, delay, ...args);
  };
});
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error?.stack || error)));
page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });

let ready = false;
let first = null;
let next = null;
let wav1 = null;
let wav2 = null;
let postCount = 0;
const origin = new URL(CORE_URL).origin;
const stateFor = (which) => {
  const id = which === 2 ? ID2 : ID1;
  return { ok: true, id, status: 'ready', mediaUrl: `${origin}/artifact-library/api/audio/${id}/media`, timingUrl: `${origin}/artifact-library/api/audio/${id}/timing`, durationSeconds: which === 2 ? next.duration : first.duration, error: null };
};

await page.route('**/*', async (route) => {
  if (!ready) return route.continue();
  const req = route.request();
  let url;
  try { url = new URL(req.url()); } catch { return route.continue(); }
  if (url.origin !== origin) return route.continue();
  if (url.pathname === '/artifact-library/audio') {
    if (req.method() === 'POST') {
      postCount++;
      let body = {};
      try { body = JSON.parse(req.postData() || '{}'); } catch {}
      const which = next && String(body.chapterHref || '') === next.href ? 2 : 1;
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(stateFor(which)) });
    }
    if (req.method() === 'GET') {
      const id = url.searchParams.get('id');
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(stateFor(id === ID2 ? 2 : 1)) });
    }
  }
  if (url.pathname === `/artifact-library/api/audio/${ID1}/timing`) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ words: first.words }) });
  if (url.pathname === `/artifact-library/api/audio/${ID2}/timing`) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ words: next.words }) });
  if (url.pathname === `/artifact-library/api/audio/${ID1}/media`) return route.fulfill(rangeResponse(req, wav1));
  if (url.pathname === `/artifact-library/api/audio/${ID2}/media`) return route.fulfill(rangeResponse(req, wav2));
  return route.continue();
});

async function bestFrame() {
  return page.evaluate(() => {
    let best = null;
    for (const frame of document.querySelectorAll('#viewer iframe')) {
      try {
        const text = String(frame.contentDocument?.body?.innerText || '').trim();
        if (text.length >= 80 && (!best || text.length > best.text.length)) best = { text };
      } catch {}
    }
    const loc = window.r3ReaderBridge?.current?.();
    return best ? { text: best.text, href: String(loc?.start?.href || ''), cfi: String(loc?.start?.cfi || '') } : null;
  });
}

try {
  const response = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const runtime = response?.headers()?.['x-r3-reader-runtime'] || '';
  const proof = response?.headers()?.['x-r3-reader-patch-proof'] || '';
  if (runtime !== 'v33-audio-core-owner') throw new Error(`PREVIEW_RUNTIME_BAD:${runtime}`);
  if (!proof.includes('core-single-owner')) throw new Error(`PREVIEW_PROOF_BAD:${proof}`);
  await page.waitForSelector('#r3AudioMain', { timeout: 30000 });
  await page.waitForSelector('#viewer iframe', { timeout: 30000 });
  await page.waitForFunction(() => Boolean(window.r3ReaderBridge?.current && window.__r3AudioCoreProductionV33), null, { timeout: 30000 });
  await page.waitForFunction(() => Boolean(window.__r3AudioLegacyV6Suppressed && window.__r3AudioLegacyV8Suppressed && window.__r3AudioLegacyV11Suppressed && window.__r3AudioLegacyV29Suppressed && window.__r3AudioLegacyV31ClockSuppressed), null, { timeout: 10000 });

  first = await bestFrame();
  if (!first?.href || !first?.cfi) throw new Error('FIRST_FRAME_MISSING');
  const startCfi = first.cfi;
  for (let i = 0; i < 40; i++) {
    await page.evaluate(async () => window.r3ReaderBridge.next());
    await page.waitForTimeout(120);
    const candidate = await bestFrame();
    if (candidate?.href && candidate.href !== first.href && candidate.text.length >= 80) { next = candidate; break; }
  }
  if (!next) throw new Error('NEXT_READABLE_CHAPTER_MISSING');
  await page.evaluate(async (cfi) => window.r3ReaderBridge.display(cfi), startCfi);
  await page.waitForTimeout(250);
  first.words = wordsFor(first.text);
  next.words = wordsFor(next.text);
  first.duration = Math.max(20, first.words.length * STEP_MS / 1000 + 2);
  next.duration = Math.max(20, next.words.length * STEP_MS / 1000 + 2);
  wav1 = makeSilentWav(first.duration);
  wav2 = makeSilentWav(next.duration);
  ready = true;

  await page.locator('#r3AudioMain').click();
  await page.waitForFunction((id) => String(document.getElementById('r3AudioElement')?.currentSrc || '').includes(id), ID1, { timeout: 15000 });
  await page.waitForFunction(() => !document.getElementById('r3AudioElement')?.paused, null, { timeout: 8000 });
  await page.waitForTimeout(400);

  const ownership = await page.evaluate(() => ({
    flags: {
      v6: window.__r3AudioLegacyV6Suppressed,
      v8: window.__r3AudioLegacyV8Suppressed,
      v11: window.__r3AudioLegacyV11Suppressed,
      v29: window.__r3AudioLegacyV29Suppressed,
      v31: window.__r3AudioLegacyV31ClockSuppressed,
      v31ClockStarted: Boolean(window.__r3AudioHighSpeedFollowV31),
    },
    audit: window.__r3OwnerAudit,
    debug: window.__r3AudioCoreV33Debug,
  }));
  if (ownership.audit.mainClicks !== 1) throw new Error(`MAIN_OWNER_COUNT_BAD:${JSON.stringify(ownership.audit)}`);
  if (ownership.audit.speedClicks !== 1) throw new Error(`SPEED_OWNER_COUNT_BAD:${JSON.stringify(ownership.audit)}`);
  if (ownership.flags.v31ClockStarted) throw new Error('LEGACY_V31_CLOCK_STARTED');
  const clocks75 = ownership.audit.intervals.filter((ms) => ms === 75).length;
  if (clocks75 !== 1) throw new Error(`CORE_75MS_CLOCK_COUNT_BAD:${clocks75}`);

  for (let i = 0; i < 4; i++) await page.locator('#r3AudioSpeed').click();
  await page.waitForTimeout(120);
  const speedState = await page.evaluate(() => ({ rate: document.getElementById('r3AudioElement')?.playbackRate, label: document.getElementById('r3AudioSpeed')?.textContent }));
  if (speedState.rate !== 2 || !String(speedState.label).includes('2')) throw new Error(`RATE_UI_BAD:${JSON.stringify(speedState)}`);

  await page.waitForTimeout(1300);
  const persisted = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || 'null'), `r3-reader-audio-core-v1:${BOOK_KEY}`);
  if (!persisted || persisted.time <= 0.5 || persisted.playbackRate !== 2 || persisted.mediaId !== ID1) throw new Error(`PERIODIC_PERSIST_BAD:${JSON.stringify(persisted)}`);

  await page.evaluate(() => document.getElementById('r3AudioElement')?.dispatchEvent(new Event('ended')));
  await page.waitForFunction((id) => String(document.getElementById('r3AudioElement')?.currentSrc || '').includes(id), ID2, { timeout: 15000 });
  await page.waitForFunction(() => !document.getElementById('r3AudioElement')?.paused, null, { timeout: 8000 });
  const advanced = await page.evaluate(() => ({ href: String(window.r3ReaderBridge.current()?.start?.href || ''), debug: window.__r3AudioCoreV33Debug, rate: document.getElementById('r3AudioElement')?.playbackRate }));
  if (advanced.href === first.href || advanced.debug.advances < 1) throw new Error(`AUTO_NEXT_BAD:${JSON.stringify(advanced)}`);
  if (advanced.rate !== 2) throw new Error(`RATE_NOT_PRESERVED_ACROSS_CHAPTER:${JSON.stringify(advanced)}`);

  await page.evaluate(() => document.getElementById('r3AudioElement')?.pause());
  await page.waitForTimeout(200);
  const beforeReload = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || 'null'), `r3-reader-audio-core-v1:${BOOK_KEY}`);
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForFunction(() => Boolean(window.__r3AudioCoreProductionV33), null, { timeout: 30000 });
  await page.waitForFunction((id) => String(document.getElementById('r3AudioElement')?.currentSrc || '').includes(id), ID2, { timeout: 15000 });
  await page.waitForTimeout(300);
  const restored = await page.evaluate((key) => ({ saved: JSON.parse(localStorage.getItem(key) || 'null'), time: Number(document.getElementById('r3AudioElement')?.currentTime || 0), rate: Number(document.getElementById('r3AudioElement')?.playbackRate || 0), paused: document.getElementById('r3AudioElement')?.paused }), `r3-reader-audio-core-v1:${BOOK_KEY}`);
  if (restored.saved?.mediaId !== ID2 || restored.time < Math.max(0, Number(beforeReload.time || 0) - 1) || restored.rate !== 2 || restored.paused !== true) throw new Error(`RESTORE_BAD:${JSON.stringify(restored)}`);

  const finalAudit = await page.evaluate(() => ({ audit: window.__r3OwnerAudit, debug: window.__r3AudioCoreV33Debug }));
  if (finalAudit.debug.maxDisplayConcurrent > 1) throw new Error(`DISPLAY_OVERLAP:${JSON.stringify(finalAudit.debug)}`);
  const fatal = errors.filter((text) => !/favicon|ResizeObserver/i.test(text));
  if (fatal.length) throw new Error(`BROWSER_ERRORS:${fatal.slice(0, 5).join(' | ')}`);

  console.log(JSON.stringify({ phase: 'reader-audio-core-v33-preview', ok: true, runtime, proof, postCount, singleMainOwner: ownership.audit.mainClicks === 1, single75msClock: clocks75 === 1, legacyOwnersSuppressed: ownership.flags, periodicPersist: true, rate2x: true, autoNext: true, resume: true, maxDisplayConcurrent: finalAudit.debug.maxDisplayConcurrent, productionMutation: false }));
  console.log('READER_AUDIO_CORE_V33_PREVIEW_E2E=PASS');
} finally {
  await browser.close();
}
