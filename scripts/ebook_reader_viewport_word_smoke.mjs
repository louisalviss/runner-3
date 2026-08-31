import { chromium } from 'playwright';

const CORE_URL = process.env.RUNNER3_CORE_URL || 'https://runner3-core.ducduy2411.workers.dev';
const BOOK_KEY = process.env.EBOOK_BROWSER_SMOKE_BOOK_KEY || 'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub';
const TEST_ID = 'seek-smoke-v16';
const STEP_MS = 50;
const readerUrl = `${CORE_URL}/artifact-library/read?key=${encodeURIComponent(BOOK_KEY)}`;

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

function audioRangeResponse(req, body) {
  const total = body.length;
  const range = String(req.headers()['range'] || '');
  const baseHeaders = { 'content-type': 'audio/wav', 'accept-ranges': 'bytes', 'cache-control': 'no-store' };
  if (!range) return { status: 200, headers: { ...baseHeaders, 'content-length': String(total) }, body };
  const match = /^bytes=(\d*)-(\d*)$/i.exec(range.trim());
  if (!match) return { status: 416, headers: { ...baseHeaders, 'content-range': `bytes */${total}` }, body: Buffer.alloc(0) };
  let start = match[1] ? Number(match[1]) : NaN;
  let end = match[2] ? Number(match[2]) : NaN;
  if (!Number.isFinite(start) && Number.isFinite(end)) {
    const suffix = Math.max(0, Math.min(total, end));
    start = total - suffix;
    end = total - 1;
  } else {
    if (!Number.isFinite(start)) start = 0;
    if (!Number.isFinite(end)) end = total - 1;
  }
  start = Math.max(0, Math.min(total - 1, start));
  end = Math.max(start, Math.min(total - 1, end));
  const chunk = body.subarray(start, end + 1);
  return {
    status: 206,
    headers: {
      ...baseHeaders,
      'content-range': `bytes ${start}-${end}/${total}`,
      'content-length': String(chunk.length),
    },
    body: chunk,
  };
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const errors = [];
page.on('pageerror', e => errors.push(String(e?.stack || e)));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

let words = [];
let wav = makeSilentWav(60);
let syntheticReady = false;
let postCount = 0;
let mediaGetCount = 0;
let mediaRangeCount = 0;
const mediaUrl = `${CORE_URL}/artifact-library/api/audio/${TEST_ID}/media`;
const timingUrl = `${CORE_URL}/artifact-library/api/audio/${TEST_ID}/timing`;
const state = () => ({ ok: true, id: TEST_ID, status: 'ready', mediaUrl, timingUrl, durationSeconds: Math.max(0, (wav.length - 44) / 8000), error: null });

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
  if (u.href === mediaUrl) {
    mediaGetCount++;
    if (req.headers()['range']) mediaRangeCount++;
    return route.fulfill(audioRangeResponse(req, wav));
  }
  return route.continue();
});

async function boot() {
  await page.waitForSelector('#r3AudioMain', { timeout: 30000 });
  await page.waitForSelector('#viewer iframe', { timeout: 30000 });
  await page.waitForFunction(() => Boolean(window.r3ReaderBridge), null, { timeout: 30000 });
}

async function snapshot() {
  return page.evaluate(() => {
    const frames = [...document.querySelectorAll('#viewer iframe')];
    let best = null;
    for (const frame of frames) {
      try {
        const doc = frame.contentDocument;
        const len = String(doc?.body?.innerText || '').trim().length;
        if (!best || len > best.len) best = { frame, doc, len };
      } catch {}
    }
    if (!best?.doc?.body || best.len < 80) return { textLength: best?.len || 0, visibleTokenOrdinal: -1, allTokens: [] };
    const doc = best.doc;
    let blocks = [...doc.querySelectorAll('p,li,h1,h2,h3,h4,h5,h6,blockquote')].filter(el => String(el.innerText || el.textContent || '').trim());
    blocks = blocks.filter(el => String(el.tagName || '').toUpperCase() !== 'BLOCKQUOTE' || !el.querySelector('p,li,h1,h2,h3,h4,h5,h6'));
    if (!blocks.length) blocks = [...doc.body.children].filter(el => String(el.innerText || el.textContent || '').trim());
    if (!blocks.length) blocks = [doc.body];
    const viewer = document.getElementById('viewer');
    const frameRect = best.frame.getBoundingClientRect();
    const viewerRect = viewer?.getBoundingClientRect() || { left: 0, top: 0, right: innerWidth, bottom: innerHeight };
    const re = /[\p{L}\p{M}\p{N}]+/gu;
    const allTokens = [];
    let visibleTokenOrdinal = -1;
    let visibleToken = null;
    let visibleBlockIndex = -1;
    for (let bi = 0; bi < blocks.length; bi++) {
      const walker = doc.createTreeWalker(blocks[bi], NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        const raw = String(node.nodeValue || '');
        re.lastIndex = 0;
        let m;
        while ((m = re.exec(raw))) {
          const token = String(m[0]).normalize('NFKC').toLocaleLowerCase('vi-VN');
          const ordinal = allTokens.length;
          allTokens.push(token);
          if (visibleTokenOrdinal < 0) {
            const range = doc.createRange();
            range.setStart(node, m.index); range.setEnd(node, m.index + m[0].length);
            const visible = [...range.getClientRects()].some(r => {
              const left = frameRect.left + r.left, right = frameRect.left + r.right;
              const top = frameRect.top + r.top, bottom = frameRect.top + r.bottom;
              return right > viewerRect.left + 2 && left < viewerRect.right - 2 && bottom > viewerRect.top + 2 && top < viewerRect.bottom - 2;
            });
            if (visible) { visibleTokenOrdinal = ordinal; visibleToken = token; visibleBlockIndex = bi; }
          }
        }
      }
    }
    return {
      textLength: best.len,
      allTokens: allTokens.slice(0, 12000),
      visibleTokenOrdinal,
      visibleToken,
      visibleBlockIndex,
      frameLeft: Math.round(frameRect.left),
      frameWidth: Math.round(frameRect.width),
      viewerLeft: Math.round(viewerRect.left),
      viewerWidth: Math.round(viewerRect.right - viewerRect.left),
      href: window.r3ReaderBridge?.current?.()?.start?.href || null,
      cfi: window.r3ReaderBridge?.current?.()?.start?.cfi || null,
    };
  });
}

try {
  const nav = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await boot();
  const runtime = nav?.headers()?.['x-r3-reader-runtime'] || '';
  if (!runtime.includes('v16')) throw new Error(`live Reader is not v16: ${runtime || 'missing header'}`);
  await page.waitForFunction(() => window.__r3AudioViewportWordV15 === true && window.__r3AudioOuterGeometryV16 === true, null, { timeout: 10000 });

  let candidate = null;
  for (let n = 0; n < 180; n++) {
    const s = await snapshot();
    if (n < 8 || n % 25 === 0) console.log(JSON.stringify({ phase: 'scan', n, href: s.href, cfi: s.cfi, visibleTokenOrdinal: s.visibleTokenOrdinal, visibleToken: s.visibleToken, frameLeft: s.frameLeft, frameWidth: s.frameWidth, viewerLeft: s.viewerLeft, viewerWidth: s.viewerWidth, tokenCount: s.allTokens.length }));
    if (s.allTokens.length > 120 && s.visibleTokenOrdinal >= 30) { candidate = s; break; }
    await page.evaluate(async () => { if (window.r3ReaderBridge?.next) await window.r3ReaderBridge.next(); });
    await page.waitForTimeout(160);
  }
  if (!candidate) throw new Error('no later viewport word found after pagination');

  words = candidate.allTokens.map((text, index) => ({ text, startMs: index * STEP_MS, durationMs: 35 }));
  const duration = Math.max(60, words.length * STEP_MS / 1000 + 10);
  wav = makeSilentWav(duration);
  syntheticReady = true;
  const expectedStart = candidate.visibleTokenOrdinal * STEP_MS / 1000;
  console.log(JSON.stringify({ phase: 'viewport-anchor', runtime, href: candidate.href, cfi: candidate.cfi, visibleTokenOrdinal: candidate.visibleTokenOrdinal, visibleToken: candidate.visibleToken, visibleBlockIndex: candidate.visibleBlockIndex, tokenCount: words.length, expectedStart }));

  await page.locator('#r3AudioMain').click();
  await page.waitForFunction(id => String(document.getElementById('r3AudioElement')?.currentSrc || '').includes(id), TEST_ID, { timeout: 20000 });
  await page.waitForTimeout(900);
  const started = await page.evaluate((bookKey) => {
    const a = document.getElementById('r3AudioElement');
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem('r3-reader-audio-state-v11:' + bookKey) || 'null'); } catch {}
    const f = document.querySelector('#viewer iframe');
    let active = null;
    try { active = f?.contentDocument?.querySelector('[data-r3-audio-reading-v11="1"]')?.textContent?.trim()?.slice(0, 180) || null; } catch {}
    return { time: Number(a?.currentTime || 0), paused: Boolean(a?.paused), saved, active, cfi: window.r3ReaderBridge?.current?.()?.start?.cfi || null, seekable: a?.seekable?.length ? Number(a.seekable.end(a.seekable.length - 1)) : 0 };
  }, BOOK_KEY);
  console.log(JSON.stringify({ phase: 'started', postCount, mediaGetCount, mediaRangeCount, expectedStart, ...started }));
  if (postCount !== 1) throw new Error(`expected one audio POST, got ${postCount}`);
  if (mediaRangeCount < 1) throw new Error(`browser did not issue an audio Range request: mediaGets=${mediaGetCount}`);
  if (expectedStart < 1 || started.time < expectedStart - 1 || started.time > expectedStart + 3) throw new Error(`viewport start mismatch expected=${expectedStart} actual=${started.time}`);
  if (!started.active) throw new Error('bold active paragraph missing after viewport-word start');
  if (started.saved?.id !== TEST_ID) throw new Error(`saved media id mismatch: ${JSON.stringify(started.saved)}`);

  const beforeFollowCfi = started.cfi;
  const followIndex = Math.min(words.length - 2, candidate.visibleTokenOrdinal + 120);
  const followTime = followIndex * STEP_MS / 1000;
  await page.evaluate(t => {
    const a = document.getElementById('r3AudioElement');
    a.currentTime = t;
    a.dispatchEvent(new Event('seeked'));
    a.dispatchEvent(new Event('timeupdate'));
  }, followTime);
  await page.waitForTimeout(1200);
  const afterFollow = await snapshot();
  console.log(JSON.stringify({ phase: 'word-follow', beforeFollowCfi, followIndex, followTime, afterCfi: afterFollow.cfi, visibleTokenOrdinal: afterFollow.visibleTokenOrdinal, visibleToken: afterFollow.visibleToken }));
  if (!afterFollow.cfi) throw new Error('CFI missing after word follow');
  if (followIndex > candidate.visibleTokenOrdinal + 20 && afterFollow.cfi === beforeFollowCfi) throw new Error('CFI did not advance after seeking audio to a later word');
  if (afterFollow.visibleTokenOrdinal < Math.max(0, followIndex - 30)) throw new Error(`Reader did not follow audio word closely enough: target=${followIndex} visible=${afterFollow.visibleTokenOrdinal}`);

  await page.evaluate(() => { const a = document.getElementById('r3AudioElement'); a.pause(); a.dispatchEvent(new Event('timeupdate')); });
  await page.waitForTimeout(1000);
  const savedTime = await page.evaluate((bookKey) => {
    try { return Number(JSON.parse(localStorage.getItem('r3-reader-audio-state-v11:' + bookKey) || 'null')?.time || 0); } catch { return 0; }
  }, BOOK_KEY);
  if (savedTime < followTime - 0.8) throw new Error(`audio timestamp not persisted: follow=${followTime} saved=${savedTime}`);

  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  await boot();
  await page.waitForFunction(({ id, t }) => {
    const a = document.getElementById('r3AudioElement');
    return String(a?.currentSrc || a?.getAttribute('src') || '').includes(id) && Number(a?.currentTime || 0) >= t - 1;
  }, { id: TEST_ID, t: savedTime }, { timeout: 30000 });
  const restored = await page.evaluate(() => { const a = document.getElementById('r3AudioElement'); return { time: Number(a?.currentTime || 0), src: String(a?.currentSrc || a?.getAttribute('src') || ''), cfi: window.r3ReaderBridge?.current?.()?.start?.cfi || null }; });
  console.log(JSON.stringify({ phase: 'restored', postCount, savedTime, ...restored }));
  if (postCount !== 1) throw new Error(`refresh unexpectedly POSTed audio again: ${postCount}`);

  await page.locator('#r3AudioMain').click();
  await page.waitForTimeout(700);
  const resumed = await page.evaluate(() => { const a = document.getElementById('r3AudioElement'); return { time: Number(a?.currentTime || 0), paused: Boolean(a?.paused), src: String(a?.currentSrc || a?.getAttribute('src') || '') }; });
  console.log(JSON.stringify({ phase: 'resumed', postCount, ...resumed }));
  if (postCount !== 1) throw new Error(`resume created duplicate audio POST: ${postCount}`);
  if (resumed.time < savedTime - 1) throw new Error(`resume restarted: saved=${savedTime} resumed=${resumed.time}`);
  if (!resumed.src.includes(TEST_ID)) throw new Error('resume did not reuse same audio media');
  if (errors.length) throw new Error('browser runtime errors: ' + errors.join(' | ').slice(0, 1500));

  console.log(JSON.stringify({ phase: 'viewport-word-proof', ok: true, runtime, exactVisibleWordStart: true, expectedStart, actualStart: started.time, exactWordPageFollow: true, refreshResume: true, duplicatePostAfterRefresh: false, postCount, mediaGetCount, mediaRangeCount }));
} finally {
  await browser.close();
}
