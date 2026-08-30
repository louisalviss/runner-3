import { chromium } from 'playwright';

const CORE_URL = process.env.RUNNER3_CORE_URL || 'https://runner3-core.ducduy2411.workers.dev';
const BOOK_KEY = process.env.EBOOK_BROWSER_SMOKE_BOOK_KEY || 'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub';
const TEST_ID = 'seek-smoke-v14';
const readerUrl = `${CORE_URL}/artifact-library/read?key=${encodeURIComponent(BOOK_KEY)}`;

function normalize(value) {
  return String(value || '').normalize('NFC').replace(/\r/g, '').replace(/\u00a0/g, ' ').replace(/[\u200b-\u200d\u2060\ufeff]/g, '').replace(/https?:\/\/\S+/g, '').replace(/\s+/g, ' ').trim();
}
function tokensOf(value) {
  const text = normalize(value).normalize('NFKC').toLocaleLowerCase('vi-VN');
  if (!text) return [];
  try { return text.match(/[\p{L}\p{M}\p{N}]+/gu) || []; } catch { return text.split(/[^A-Za-z0-9À-ỹ]+/).filter(Boolean); }
}
function makeSilentWav(seconds) {
  const sampleRate = 8000;
  const samples = Math.max(8000, Math.ceil(seconds * sampleRate));
  const dataSize = samples;
  const out = Buffer.alloc(44 + dataSize, 128);
  out.write('RIFF', 0, 'ascii');
  out.writeUInt32LE(36 + dataSize, 4);
  out.write('WAVE', 8, 'ascii');
  out.write('fmt ', 12, 'ascii');
  out.writeUInt32LE(16, 16);
  out.writeUInt16LE(1, 20);
  out.writeUInt16LE(1, 22);
  out.writeUInt32LE(sampleRate, 24);
  out.writeUInt32LE(sampleRate, 28);
  out.writeUInt16LE(1, 32);
  out.writeUInt16LE(8, 34);
  out.write('data', 36, 'ascii');
  out.writeUInt32LE(dataSize, 40);
  return out;
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const consoleErrors = [];
page.on('pageerror', err => consoleErrors.push(String(err?.stack || err)));
page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });

let timingWords = [];
let wav = makeSilentWav(30);
let postCount = 0;
let syntheticReady = false;
const mediaUrl = `${CORE_URL}/artifact-library/api/audio/${TEST_ID}/media`;
const timingUrl = `${CORE_URL}/artifact-library/api/audio/${TEST_ID}/timing`;
const readyState = () => ({ ok: true, id: TEST_ID, status: 'ready', mediaUrl, timingUrl, durationSeconds: Math.max(1, wav.length / 8000), error: null });

await page.route('**/*', async route => {
  const req = route.request();
  let url;
  try { url = new URL(req.url()); } catch { return route.continue(); }
  if (!syntheticReady) return route.continue();
  if (url.origin === new URL(CORE_URL).origin && url.pathname === '/artifact-library/audio') {
    if (req.method() === 'POST') {
      postCount++;
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(readyState()) });
    }
    if (req.method() === 'GET' && url.searchParams.get('id') === TEST_ID) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(readyState()) });
    }
  }
  if (url.href === mediaUrl) return route.fulfill({ status: 200, contentType: 'audio/wav', body: wav });
  if (url.href === timingUrl) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ words: timingWords }) });
  return route.continue();
});

async function waitBoot() {
  await page.waitForSelector('#r3AudioMain', { timeout: 30000 });
  await page.waitForSelector('#viewer iframe', { timeout: 30000 });
  await page.waitForFunction(() => Boolean(window.r3ReaderBridge), null, { timeout: 30000 });
}

async function readerState() {
  return page.evaluate(() => {
    const frames = [...document.querySelectorAll('#viewer iframe')];
    let best = null;
    for (const frame of frames) {
      try {
        const doc = frame.contentDocument;
        const text = String(doc?.body?.innerText || '').trim();
        if (!best || text.length > best.text.length) best = { frame, doc, text };
      } catch {}
    }
    if (!best?.doc?.body) return { text: '', textLength: 0, visibleIndex: -1, tokensBeforeVisible: 0, href: window.r3ReaderBridge?.current?.()?.start?.href || null };
    const rows = [...best.doc.querySelectorAll('p,li,h1,h2,h3,h4,h5,h6,blockquote')].filter(el => String(el.innerText || el.textContent || '').trim());
    const win = best.doc.defaultView;
    const w = win?.innerWidth || best.doc.documentElement.clientWidth || 1;
    const h = win?.innerHeight || best.doc.documentElement.clientHeight || 1;
    const visible = rows.findIndex(el => [...el.getClientRects()].some(r => r.right > 2 && r.left < w - 2 && r.bottom > 2 && r.top < h - 2));
    const tokenize = value => {
      const text = String(value || '').normalize('NFC').replace(/\r/g, '').replace(/\u00a0/g, ' ').replace(/[\u200b-\u200d\u2060\ufeff]/g, '').replace(/https?:\/\/\S+/g, '').replace(/\s+/g, ' ').trim().normalize('NFKC').toLocaleLowerCase('vi-VN');
      try { return text.match(/[\p{L}\p{M}\p{N}]+/gu) || []; } catch { return text.split(/[^A-Za-z0-9À-ỹ]+/).filter(Boolean); }
    };
    let tokensBeforeVisible = 0;
    if (visible > 0) for (let i = 0; i < visible; i++) tokensBeforeVisible += tokenize(rows[i].innerText || rows[i].textContent).length;
    return {
      text: best.text,
      textLength: best.text.length,
      blockCount: rows.length,
      visibleIndex: visible,
      visibleText: visible >= 0 ? String(rows[visible].innerText || rows[visible].textContent || '').trim().slice(0, 180) : null,
      tokensBeforeVisible,
      href: window.r3ReaderBridge?.current?.()?.start?.href || null,
      cfi: window.r3ReaderBridge?.current?.()?.start?.cfi || null,
    };
  });
}

try {
  const nav = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitBoot();
  const runtime = nav?.headers()?.['x-r3-reader-runtime'] || '';
  if (!runtime.includes('v14')) throw new Error(`live Reader is not v14: ${runtime || 'missing header'}`);

  let candidate = null;
  for (let step = 0; step < 140; step++) {
    const state = await readerState();
    if (state.textLength > 1200 && state.visibleIndex > 0 && state.tokensBeforeVisible >= 30) { candidate = state; break; }
    await page.evaluate(async () => { const b = window.r3ReaderBridge; if (b?.next) await b.next(); });
    await page.waitForTimeout(180);
  }
  if (!candidate) throw new Error('could not reach a later visible page in a long EPUB chapter');

  const tokens = tokensOf(candidate.text).slice(0, 12000);
  if (tokens.length < 100) throw new Error('candidate chapter tokenization too short');
  const STEP_MS = 25;
  timingWords = tokens.map((text, index) => ({ text, startMs: index * STEP_MS, durationMs: 18 }));
  const durationSeconds = Math.max(30, (timingWords.length * STEP_MS) / 1000 + 10);
  wav = makeSilentWav(durationSeconds);
  syntheticReady = true;

  console.log(JSON.stringify({ phase: 'visible-anchor', runtime, href: candidate.href, cfi: candidate.cfi, textLength: candidate.textLength, visibleIndex: candidate.visibleIndex, tokensBeforeVisible: candidate.tokensBeforeVisible, visibleText: candidate.visibleText }));

  await page.locator('#r3AudioMain').click();
  await page.waitForFunction(id => {
    const a = document.getElementById('r3AudioElement');
    return String(a?.currentSrc || a?.getAttribute('src') || '').includes(id) && Number(a?.currentTime || 0) > 0.5;
  }, TEST_ID, { timeout: 30000 });
  await page.waitForTimeout(700);

  const started = await page.evaluate((bookKey) => {
    const a = document.getElementById('r3AudioElement');
    const frame = document.querySelector('#viewer iframe');
    let active = null;
    let visible = false;
    try {
      const el = frame?.contentDocument?.querySelector('[data-r3-audio-reading-v11="1"]');
      active = el?.textContent?.trim()?.slice(0, 180) || null;
      if (el) {
        const r = el.getBoundingClientRect();
        const d = el.ownerDocument, w = d.defaultView?.innerWidth || d.documentElement.clientWidth || 1, h = d.defaultView?.innerHeight || d.documentElement.clientHeight || 1;
        visible = r.right > 2 && r.left < w - 2 && r.bottom > 2 && r.top < h - 2;
      }
    } catch {}
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem('r3-reader-audio-state-v11:' + bookKey) || 'null'); } catch {}
    return { time: Number(a?.currentTime || 0), paused: Boolean(a?.paused), active, activeVisible: visible, saved, cfi: window.r3ReaderBridge?.current?.()?.start?.cfi || null };
  }, BOOK_KEY);
  console.log(JSON.stringify({ phase: 'play-from-visible', postCount, ...started }));
  if (postCount !== 1) throw new Error(`expected one chapter audio request, got ${postCount}`);
  if (!(started.time > 0.5)) throw new Error(`audio restarted near zero: ${started.time}`);
  if (!started.active || !started.activeVisible) throw new Error('active paragraph is not visibly highlighted on the current Reader page');
  if (!started.saved?.id || started.saved.id !== TEST_ID) throw new Error(`v11 state did not persist synthetic audio id: ${JSON.stringify(started.saved)}`);

  await page.evaluate(() => {
    const a = document.getElementById('r3AudioElement');
    a.pause();
    a.currentTime = Math.min((Number(a.currentTime) || 0) + 2.25, Math.max(1, (Number(a.duration) || 5) - 1));
    a.dispatchEvent(new Event('timeupdate'));
  });
  await page.waitForTimeout(1000);
  const savedTime = await page.evaluate((bookKey) => {
    try { return Number(JSON.parse(localStorage.getItem('r3-reader-audio-state-v11:' + bookKey) || 'null')?.time || 0); } catch { return 0; }
  }, BOOK_KEY);
  if (!(savedTime > started.time + 1)) throw new Error(`resume timestamp was not persisted: started=${started.time} saved=${savedTime}`);

  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitBoot();
  await page.waitForFunction(({ id, expected }) => {
    const a = document.getElementById('r3AudioElement');
    return String(a?.currentSrc || a?.getAttribute('src') || '').includes(id) && Number(a?.currentTime || 0) >= expected - 0.8;
  }, { id: TEST_ID, expected: savedTime }, { timeout: 30000 });

  const restoredBeforeClick = await page.evaluate(() => {
    const a = document.getElementById('r3AudioElement');
    return { time: Number(a?.currentTime || 0), paused: Boolean(a?.paused), src: String(a?.currentSrc || a?.getAttribute('src') || ''), cfi: window.r3ReaderBridge?.current?.()?.start?.cfi || null };
  });
  console.log(JSON.stringify({ phase: 'restored-before-click', postCount, savedTime, ...restoredBeforeClick }));

  await page.locator('#r3AudioMain').click();
  await page.waitForTimeout(800);
  const resumed = await page.evaluate(() => {
    const a = document.getElementById('r3AudioElement');
    return { time: Number(a?.currentTime || 0), paused: Boolean(a?.paused), src: String(a?.currentSrc || a?.getAttribute('src') || ''), cfi: window.r3ReaderBridge?.current?.()?.start?.cfi || null };
  });
  console.log(JSON.stringify({ phase: 'resume-click', postCount, ...resumed }));

  if (postCount !== 1) throw new Error(`refresh/resume requested chapter audio again; postCount=${postCount}`);
  if (resumed.time < savedTime - 1) throw new Error(`refresh/resume lost timestamp: saved=${savedTime} resumed=${resumed.time}`);
  if (!resumed.src.includes(TEST_ID)) throw new Error('refresh/resume lost the same audio media id');
  if (!resumed.cfi) throw new Error('Reader CFI missing after refresh/resume');
  if (consoleErrors.length) throw new Error('browser runtime errors: ' + consoleErrors.join(' | ').slice(0, 1500));

  console.log(JSON.stringify({ phase: 'visible-seek-proof', ok: true, runtime, startFromVisible: true, nonZeroStart: started.time, activeParagraphVisible: true, refreshRestoredTime: restoredBeforeClick.time, resumeReusedAudioWithoutPost: true, postCount }));
} finally {
  await browser.close();
}
