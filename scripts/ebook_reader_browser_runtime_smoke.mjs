import { chromium } from 'playwright';

const CORE_URL = process.env.RUNNER3_CORE_URL || 'https://runner3-core.ducduy2411.workers.dev';
const BOOK_KEY = process.env.EBOOK_BROWSER_SMOKE_BOOK_KEY || 'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub';
const AUDIO_ID = process.env.EBOOK_BROWSER_SMOKE_AUDIO_ID || 'ebook-5c3258ea79a8ffb76bff5fd299ac4619';
const readerUrl = `${CORE_URL}/artifact-library/read?key=${encodeURIComponent(BOOK_KEY)}`;

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const consoleErrors = [];
const failedRequests = [];
const badResponses = [];
page.on('pageerror', err => consoleErrors.push(String(err?.stack || err)));
page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
page.on('requestfailed', req => failedRequests.push({ url: req.url(), error: req.failure()?.errorText || 'failed' }));
page.on('response', res => { if (res.status() >= 400) badResponses.push({ status: res.status(), url: res.url() }); });

function print(label, value) {
  console.log(JSON.stringify({ phase: label, ...value }));
}

async function frameInfo() {
  return page.evaluate(() => {
    const f = document.querySelector('#viewer iframe');
    try {
      return {
        src: f?.getAttribute('src') || null,
        contentDocument: Boolean(f?.contentDocument),
        readyState: f?.contentDocument?.readyState || null,
        body: Boolean(f?.contentDocument?.body),
        textLength: String(f?.contentDocument?.body?.innerText || '').trim().length,
        textSample: String(f?.contentDocument?.body?.innerText || '').trim().slice(0, 160),
        bodyHtmlLength: String(f?.contentDocument?.body?.innerHTML || '').length,
      };
    } catch (error) {
      return { src: f?.getAttribute('src') || null, accessError: String(error), textLength: 0 };
    }
  });
}

try {
  const navResponse = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('#r3AudioMain', { timeout: 30000 });
  await page.waitForSelector('#viewer iframe', { timeout: 30000 });
  await page.waitForFunction(() => Boolean(window.r3ReaderBridge), null, { timeout: 30000 });

  let frame = await frameInfo();
  for (let n = 0; n < 24 && Number(frame.textLength || 0) <= 80; n++) {
    await page.evaluate(async () => {
      const bridge = window.r3ReaderBridge;
      if (bridge?.next) await bridge.next();
      else document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    });
    await page.waitForTimeout(220);
    frame = await frameInfo();
  }

  const diagnostics = await page.evaluate(() => ({
    loadingText: document.getElementById('loading')?.textContent || null,
    loadingClass: document.getElementById('loading')?.className || null,
    audio: Boolean(document.getElementById('r3AudioElement')),
    main: Boolean(document.getElementById('r3AudioMain')),
    bridge: Boolean(window.r3ReaderBridge),
    v8Script: Boolean(document.querySelector('script[data-r3-audio-follow-v8="1"]')),
    runtimeDataset: document.documentElement.dataset.r3AudioFollowRuntime || null,
    baseURI: document.baseURI,
  }));
  diagnostics.frameReady = Number(frame.textLength || 0) > 80;
  diagnostics.frame = frame;
  diagnostics.readerRuntimeHeader = navResponse?.headers()?.['x-r3-reader-runtime'] || null;
  diagnostics.csp = navResponse?.headers()?.['content-security-policy'] || null;

  print('reader-diagnostics', {
    diagnostics,
    consoleErrors: consoleErrors.slice(0, 20),
    failedRequests: failedRequests.slice(0, 20),
    badResponses: badResponses.slice(0, 20),
  });

  if (!diagnostics.frameReady) throw new Error('EPUB real chapter content never became readable in live Chromium');
  if (!String(diagnostics.csp || '').includes("base-uri 'self'")) throw new Error('live Reader CSP base-uri self fix missing');

  const boot = diagnostics;
  const state = await page.evaluate(async ({ id, bookKey }) => {
    const response = await fetch(`/artifact-library/audio?id=${encodeURIComponent(id)}&bookKey=${encodeURIComponent(bookKey)}`, { cache: 'no-store' });
    return { status: response.status, data: await response.json() };
  }, { id: AUDIO_ID, bookKey: BOOK_KEY });
  if (state.status !== 200 || state.data?.status !== 'ready' || !state.data?.mediaUrl || !state.data?.timingUrl) {
    throw new Error(`known audio state unavailable: ${JSON.stringify(state).slice(0, 800)}`);
  }

  await page.evaluate((mediaUrl) => {
    const audio = document.getElementById('r3AudioElement');
    audio.src = mediaUrl;
    audio.load();
  }, state.data.mediaUrl);
  await page.waitForFunction(() => {
    const a = document.getElementById('r3AudioElement');
    return Boolean(a && Number.isFinite(a.duration) && a.duration > 1);
  }, null, { timeout: 30000 });

  await page.evaluate(() => {
    const a = document.getElementById('r3AudioElement');
    a.currentTime = Math.min(8, Math.max(1, a.duration * 0.2));
    a.dispatchEvent(new Event('timeupdate'));
  });
  await page.waitForTimeout(1500);

  const feature = await page.evaluate(() => {
    const frame = document.querySelector('#viewer iframe');
    let highlighted = null;
    let frameStyle = false;
    try {
      highlighted = frame?.contentDocument?.querySelector('[data-r3-audio-reading="1"]')?.textContent?.trim()?.slice(0, 160) || null;
      frameStyle = Boolean(frame?.contentDocument?.getElementById('r3AudioReadingStyle'));
    } catch {}
    const key = new URLSearchParams(location.search).get('key') || '';
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem('r3-reader-audio-state:' + key) || 'null'); } catch {}
    return {
      highlighted,
      frameStyle,
      savedAudioTime: Number(saved?.time),
      savedAudioId: saved?.id || null,
      readerPosition: localStorage.getItem('r3-reader-position:' + key) || null,
      bridge: Boolean(window.r3ReaderBridge),
    };
  });

  const proof = { readerUrl, boot, feature, consoleErrors: consoleErrors.slice(0, 20), failedRequests: failedRequests.slice(0, 20), badResponses: badResponses.slice(0, 20) };
  print('runtime-proof', proof);

  if (!boot.audio || !boot.main || !boot.v8Script) throw new Error('audio/v8 DOM boot missing');
  if (!boot.bridge) throw new Error('reader bridge missing at runtime');
  if (!feature.frameStyle || !feature.highlighted) throw new Error('active paragraph highlight missing at runtime');
  if (feature.savedAudioId !== AUDIO_ID || !(feature.savedAudioTime > 0)) throw new Error('audio resume state not persisted at runtime');
  if (consoleErrors.length) throw new Error('browser runtime errors: ' + consoleErrors.join(' | ').slice(0, 1200));
} finally {
  await browser.close();
}
