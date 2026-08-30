import { chromium } from 'playwright';

const CORE_URL = process.env.RUNNER3_CORE_URL || 'https://runner3-core.ducduy2411.workers.dev';
const BOOK_KEY = process.env.EBOOK_BROWSER_SMOKE_BOOK_KEY || 'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub';
const AUDIO_ID = process.env.EBOOK_BROWSER_SMOKE_AUDIO_ID || 'ebook-5c3258ea79a8ffb76bff5fd299ac4619';
const readerUrl = `${CORE_URL}/artifact-library/read?key=${encodeURIComponent(BOOK_KEY)}`;

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const consoleErrors = [];
page.on('pageerror', err => consoleErrors.push(String(err?.stack || err)));
page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });

try {
  await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('#r3AudioMain', { timeout: 30000 });
  await page.waitForSelector('#viewer iframe', { timeout: 30000 });
  await page.waitForFunction(() => {
    const f = document.querySelector('#viewer iframe');
    try { return Boolean(f?.contentDocument?.body?.innerText?.trim()?.length > 80); } catch { return false; }
  }, null, { timeout: 30000 });

  const boot = await page.evaluate(() => ({
    audio: Boolean(document.getElementById('r3AudioElement')),
    main: Boolean(document.getElementById('r3AudioMain')),
    bridge: Boolean(window.r3ReaderBridge),
    v8Script: Boolean(document.querySelector('script[data-r3-audio-follow-v8="1"]')),
    runtimeDataset: document.documentElement.dataset.r3AudioFollowRuntime || null,
  }));

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

  const proof = { readerUrl, boot, feature, consoleErrors: consoleErrors.slice(0, 20) };
  console.log(JSON.stringify(proof));

  if (!boot.audio || !boot.main || !boot.v8Script) throw new Error('audio/v8 DOM boot missing');
  if (!boot.bridge) throw new Error('reader bridge missing at runtime');
  if (!feature.frameStyle || !feature.highlighted) throw new Error('active paragraph highlight missing at runtime');
  if (feature.savedAudioId !== AUDIO_ID || !(feature.savedAudioTime > 0)) throw new Error('audio resume state not persisted at runtime');
  if (consoleErrors.length) throw new Error('browser runtime errors: ' + consoleErrors.join(' | ').slice(0, 1200));
} finally {
  await browser.close();
}
