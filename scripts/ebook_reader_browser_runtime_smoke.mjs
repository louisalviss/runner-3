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
        contentDocument: Boolean(f?.contentDocument),
        readyState: f?.contentDocument?.readyState || null,
        body: Boolean(f?.contentDocument?.body),
        textLength: String(f?.contentDocument?.body?.innerText || '').trim().length,
        textSample: String(f?.contentDocument?.body?.innerText || '').trim().slice(0, 160),
        bodyHtmlLength: String(f?.contentDocument?.body?.innerHTML || '').length,
      };
    } catch (error) {
      return { accessError: String(error), textLength: 0 };
    }
  });
}

async function waitReader() {
  await page.waitForSelector('#r3AudioMain', { timeout: 30000 });
  await page.waitForSelector('#viewer iframe', { timeout: 30000 });
  await page.waitForFunction(() => Boolean(window.r3ReaderBridge), null, { timeout: 30000 });
  await page.waitForFunction(() => {
    const f = document.querySelector('#viewer iframe');
    try { return String(f?.contentDocument?.body?.innerText || '').trim().length > 80; } catch { return false; }
  }, null, { timeout: 30000 });
}

try {
  const navResponse = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('#r3AudioMain', { timeout: 30000 });
  await page.waitForSelector('#viewer iframe', { timeout: 30000 });
  await page.waitForFunction(() => Boolean(window.r3ReaderBridge), null, { timeout: 30000 });

  let frame = await frameInfo();
  let firstReadable = null;
  for (let n = 0; n < 60 && Number(frame.textLength || 0) < 2500; n++) {
    if (!firstReadable && Number(frame.textLength || 0) > 80) firstReadable = frame;
    await page.evaluate(async () => {
      const bridge = window.r3ReaderBridge;
      if (bridge?.next) await bridge.next();
      else document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    });
    await page.waitForTimeout(180);
    frame = await frameInfo();
  }
  if (Number(frame.textLength || 0) <= 80 && firstReadable) frame = firstReadable;

  const diagnostics = await page.evaluate(() => ({
    loadingText: document.getElementById('loading')?.textContent || null,
    loadingClass: document.getElementById('loading')?.className || null,
    audio: Boolean(document.getElementById('r3AudioElement')),
    main: Boolean(document.getElementById('r3AudioMain')),
    bridge: Boolean(window.r3ReaderBridge),
    v8Script: Boolean(document.querySelector('script[data-r3-audio-follow-v8="1"]')),
    baseURI: document.baseURI,
  }));
  diagnostics.frameReady = Number(frame.textLength || 0) > 80;
  diagnostics.frame = frame;
  diagnostics.readerRuntimeHeader = navResponse?.headers()?.['x-r3-reader-runtime'] || null;
  diagnostics.csp = navResponse?.headers()?.['content-security-policy'] || null;

  print('reader-diagnostics', { diagnostics, consoleErrors: consoleErrors.slice(0, 20), badResponses: badResponses.slice(0, 20) });

  if (!diagnostics.frameReady) throw new Error('EPUB real chapter content never became readable in live Chromium');
  if (!String(diagnostics.csp || '').includes("base-uri 'self'")) throw new Error('live Reader CSP base-uri self fix missing');
  if (!String(diagnostics.csp || '').includes("style-src 'self' 'unsafe-inline' blob:")) throw new Error('live Reader CSP blob stylesheet fix missing');

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

  const beforeFollow = await page.evaluate(() => window.r3ReaderBridge?.current?.()?.start?.cfi || null);
  const playStarted = await page.evaluate(async () => {
    const a = document.getElementById('r3AudioElement');
    try { await a.play(); return !a.paused; } catch { return false; }
  });
  await page.evaluate(() => {
    const a = document.getElementById('r3AudioElement');
    a.currentTime = Math.max(1, a.duration * 0.92);
    a.dispatchEvent(new Event('timeupdate'));
  });
  await page.waitForTimeout(1800);

  const follow = await page.evaluate(() => {
    const f = document.querySelector('#viewer iframe');
    let highlighted = null;
    let visible = false;
    try {
      const el = f?.contentDocument?.querySelector('[data-r3-audio-reading="1"]');
      highlighted = el?.textContent?.trim()?.slice(0, 160) || null;
      if (el) {
        const r = el.getBoundingClientRect();
        const doc = el.ownerDocument;
        const win = doc.defaultView;
        const w = win?.innerWidth || doc.documentElement.clientWidth || 1;
        const h = win?.innerHeight || doc.documentElement.clientHeight || 1;
        visible = r.right > 4 && r.left < w - 4 && r.bottom > 4 && r.top < h - 4;
      }
    } catch {}
    return {
      highlighted,
      visible,
      currentCfi: window.r3ReaderBridge?.current?.()?.start?.cfi || null,
    };
  });
  print('page-follow', { playStarted, beforeFollow, ...follow });
  if (!follow.highlighted || !follow.visible) throw new Error('active audio paragraph did not become visible during follow runtime');

  await page.evaluate(() => {
    const a = document.getElementById('r3AudioElement');
    a.pause();
    a.currentTime = Math.min(8, Math.max(1, a.duration * 0.2));
    a.dispatchEvent(new Event('timeupdate'));
  });
  await page.waitForTimeout(1500);

  const feature = await page.evaluate(() => {
    const frame = document.querySelector('#viewer iframe');
    let highlighted = null;
    let frameStyle = false;
    let nestedBoldRule = false;
    try {
      highlighted = frame?.contentDocument?.querySelector('[data-r3-audio-reading="1"]')?.textContent?.trim()?.slice(0, 160) || null;
      const style = frame?.contentDocument?.getElementById('r3AudioReadingStyle');
      frameStyle = Boolean(style);
      nestedBoldRule = String(style?.textContent || '').includes('[data-r3-audio-reading="1"] *');
    } catch {}
    const key = new URLSearchParams(location.search).get('key') || '';
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem('r3-reader-audio-state:' + key) || 'null'); } catch {}
    return {
      highlighted,
      frameStyle,
      nestedBoldRule,
      savedAudioTime: Number(saved?.time),
      savedAudioId: saved?.id || null,
      readerPosition: localStorage.getItem('r3-reader-position:' + key) || null,
      currentCfi: window.r3ReaderBridge?.current?.()?.start?.cfi || null,
      bridge: Boolean(window.r3ReaderBridge),
    };
  });
  print('persistence-before-refresh', feature);

  if (!diagnostics.audio || !diagnostics.main || !diagnostics.v8Script || !diagnostics.bridge) throw new Error('audio/bridge runtime boot missing');
  if (!feature.frameStyle || !feature.nestedBoldRule || !feature.highlighted) throw new Error('visible active paragraph bold runtime missing');
  if (feature.savedAudioId !== AUDIO_ID || !(feature.savedAudioTime > 0)) throw new Error('audio resume state not persisted at runtime');
  if (!feature.readerPosition) throw new Error('Reader CFI not persisted before refresh');

  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitReader();
  await page.waitForFunction(({ id }) => {
    const a = document.getElementById('r3AudioElement');
    const src = String(a?.currentSrc || a?.getAttribute('src') || '');
    return src.includes(id) && Number(a?.currentTime || 0) >= 6.5;
  }, { id: AUDIO_ID }, { timeout: 30000 });
  await page.waitForTimeout(700);

  const restored = await page.evaluate(() => {
    const a = document.getElementById('r3AudioElement');
    const frame = document.querySelector('#viewer iframe');
    let highlighted = null;
    try { highlighted = frame?.contentDocument?.querySelector('[data-r3-audio-reading="1"]')?.textContent?.trim()?.slice(0, 160) || null; } catch {}
    return {
      audioTime: Number(a?.currentTime || 0),
      audioSrc: String(a?.currentSrc || a?.getAttribute('src') || ''),
      currentCfi: window.r3ReaderBridge?.current?.()?.start?.cfi || null,
      highlighted,
    };
  });
  print('refresh-restore', restored);
  if (!restored.audioSrc.includes(AUDIO_ID) || restored.audioTime < 6.5 || restored.audioTime > 10.5) throw new Error('audio timestamp did not restore after refresh');
  if (!restored.currentCfi) throw new Error('Reader location did not restore after refresh');

  let nextAudioPostSeen = false;
  await page.route('**/artifact-library/audio', async route => {
    const request = route.request();
    if (request.method() === 'POST') {
      nextAudioPostSeen = true;
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });

  const beforeHref = await page.evaluate(() => window.r3ReaderBridge?.current?.()?.start?.href || null);
  await page.evaluate(() => document.getElementById('r3AudioElement')?.dispatchEvent(new Event('ended')));
  try {
    await page.waitForFunction(before => {
      const href = window.r3ReaderBridge?.current?.()?.start?.href || '';
      return Boolean(href && before && href !== before);
    }, beforeHref, { timeout: 12000 });
  } catch {}
  await page.waitForTimeout(1200);
  const continuous = await page.evaluate(() => ({
    href: window.r3ReaderBridge?.current?.()?.start?.href || null,
    status: document.getElementById('r3AudioStatus')?.textContent || null,
  }));
  continuous.beforeHref = beforeHref;
  continuous.nextAudioPostSeen = nextAudioPostSeen;
  print('continuous-chapter', continuous);
  if (!beforeHref || !continuous.href || continuous.href === beforeHref) throw new Error('ended audio did not navigate to the next chapter');
  if (!continuous.nextAudioPostSeen) throw new Error('next chapter audio was not automatically requested');

  if (consoleErrors.length) throw new Error('browser runtime errors: ' + consoleErrors.join(' | ').slice(0, 1200));
  print('runtime-proof', {
    ok: true,
    readerRuntime: diagnostics.readerRuntimeHeader,
    highlight: true,
    pageFollow: true,
    readerPersistence: true,
    audioPersistenceAcrossRefresh: true,
    continuousChapterTransition: true,
    nextChapterAudioAutoRequest: true,
  });
} finally {
  await browser.close();
}
