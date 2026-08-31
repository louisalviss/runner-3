import fs from 'node:fs';
import { chromium } from 'playwright';

const CORE_URL = process.env.RUNNER3_CORE_URL || 'https://runner3-core.ducduy2411.workers.dev';
const BOOK_KEY = process.env.EBOOK_BROWSER_SMOKE_BOOK_KEY || 'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub';
const BUNDLE_PATH = process.argv[2] || '/tmp/reader-audio-core-e2e.js';
const readerUrl = `${CORE_URL}/artifact-library/read?key=${encodeURIComponent(BOOK_KEY)}`;
const E2E_STATE_KEY = 'r3-reader-audio-core-e2e-v1';
const bundle = fs.readFileSync(BUNDLE_PATH, 'utf8');

function makeSilentWav(seconds = 20) {
  const sampleRate = 8000;
  const samples = Math.max(sampleRate, Math.ceil(seconds * sampleRate));
  const out = Buffer.alloc(44 + samples, 128);
  out.write('RIFF', 0, 'ascii'); out.writeUInt32LE(36 + samples, 4); out.write('WAVE', 8, 'ascii');
  out.write('fmt ', 12, 'ascii'); out.writeUInt32LE(16, 16); out.writeUInt16LE(1, 20); out.writeUInt16LE(1, 22);
  out.writeUInt32LE(sampleRate, 24); out.writeUInt32LE(sampleRate, 28); out.writeUInt16LE(1, 32); out.writeUInt16LE(8, 34);
  out.write('data', 36, 'ascii'); out.writeUInt32LE(samples, 40);
  return out;
}

function rangeReply(request, body) {
  const total = body.length;
  const raw = String(request.headers()['range'] || '');
  const headers = { 'content-type': 'audio/wav', 'accept-ranges': 'bytes', 'cache-control': 'no-store' };
  if (!raw) return { status: 200, headers: { ...headers, 'content-length': String(total) }, body };
  const match = /^bytes=(\d*)-(\d*)$/i.exec(raw.trim());
  if (!match) return { status: 416, headers: { ...headers, 'content-range': `bytes */${total}` }, body: Buffer.alloc(0) };
  let start = match[1] ? Number(match[1]) : 0;
  let end = match[2] ? Number(match[2]) : total - 1;
  if (!Number.isFinite(start)) start = 0;
  if (!Number.isFinite(end)) end = total - 1;
  start = Math.max(0, Math.min(total - 1, start));
  end = Math.max(start, Math.min(total - 1, end));
  const chunk = body.subarray(start, end + 1);
  return { status: 206, headers: { ...headers, 'content-range': `bytes ${start}-${end}/${total}`, 'content-length': String(chunk.length) }, body: chunk };
}

const wav = makeSilentWav(30);
const browser = await chromium.launch({ headless: true, args: ['--autoplay-policy=no-user-gesture-required'] });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error?.stack || error)));
page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });

await page.route('https://e2e.invalid/**', async (route) => {
  const reply = rangeReply(route.request(), wav);
  await route.fulfill(reply);
});

async function bootAndAssertV31() {
  const response = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const runtime = response?.headers()?.['x-r3-reader-runtime'] || '';
  if (runtime !== 'v31-high-speed-serialized-follow') throw new Error(`LIVE_BASELINE_NOT_V31:${runtime || 'missing'}`);
  await page.waitForSelector('#viewer iframe', { timeout: 30000 });
  await page.waitForFunction(() => Boolean(window.r3ReaderBridge?.current && window.r3ReaderBridge?.next && window.r3ReaderBridge?.prev), null, { timeout: 30000 });
  return runtime;
}

async function currentCfi() {
  return page.evaluate(() => String(window.r3ReaderBridge?.current?.()?.start?.cfi || ''));
}

async function collectPageCfis(count = 3) {
  const cfis = [];
  for (let i = 0; i < count; i++) {
    const cfi = await currentCfi();
    if (!cfi) throw new Error(`MISSING_CFI_AT_PAGE_${i}`);
    if (!cfis.includes(cfi)) cfis.push(cfi);
    if (cfis.length >= count) break;
    await page.evaluate(async () => window.r3ReaderBridge.next());
    await page.waitForTimeout(220);
  }
  if (cfis.length < count) throw new Error(`NEED_${count}_DISTINCT_CFIS_GOT_${cfis.length}`);
  for (let i = cfis.length - 1; i > 0; i--) {
    await page.evaluate(async () => window.r3ReaderBridge.prev());
    await page.waitForTimeout(220);
  }
  const back = await currentCfi();
  if (back !== cfis[0]) throw new Error(`FAILED_TO_RETURN_TO_FIRST_CFI:${back}`);
  return cfis;
}

async function injectAdapter({ cfis, clearState = false } = {}) {
  await page.addScriptTag({ content: bundle });
  await page.evaluate(({ cfis, stateKey, clearState }) => {
    if (!window.R3AudioCoreE2E?.ReaderAudioAdapter) throw new Error('ADAPTER_BUNDLE_EXPORT_MISSING');
    if (clearState) localStorage.removeItem(stateKey);
    document.getElementById('r3AudioCoreE2E')?.remove();
    const audio = document.createElement('audio');
    audio.id = 'r3AudioCoreE2E';
    audio.muted = true;
    audio.preload = 'auto';
    audio.style.display = 'none';
    document.body.appendChild(audio);

    const targetOrder = [...cfis];
    const metrics = window.__r3CoreE2EMetrics = { displayCalls: 0, currentConcurrent: 0, maxConcurrent: 0, animateValues: [], highlights: [], targets: [] };
    const readCfi = () => String(window.r3ReaderBridge?.current?.()?.start?.cfi || '');
    const displayCfi = async (targetCfi, options = {}) => {
      metrics.displayCalls++;
      metrics.currentConcurrent++;
      metrics.maxConcurrent = Math.max(metrics.maxConcurrent, metrics.currentConcurrent);
      metrics.animateValues.push(options?.animate);
      try {
        for (let step = 0; step < 12; step++) {
          const here = readCfi();
          if (here === targetCfi) return true;
          const currentIndex = targetOrder.indexOf(here);
          const targetIndex = targetOrder.indexOf(targetCfi);
          if (targetIndex < 0) throw new Error('UNKNOWN_TARGET_CFI');
          if (currentIndex < 0 || currentIndex < targetIndex) await window.r3ReaderBridge.next();
          else await window.r3ReaderBridge.prev();
          await new Promise((resolve) => setTimeout(resolve, 80));
        }
        throw new Error(`DISPLAY_CFI_DID_NOT_LAND:${targetCfi}`);
      } finally {
        metrics.currentConcurrent--;
      }
    };
    const isVisible = async (target) => readCfi() === target.cfi;
    const segments1 = [
      { start: 0, end: 2.99, cfi: cfis[0], token: 'P0' },
      { start: 3, end: 5.99, cfi: cfis[1], token: 'P1' },
    ];
    const segments2 = [
      { start: 0, end: 5.99, cfi: cfis[2], token: 'P2' },
    ];
    const adapter = new window.R3AudioCoreE2E.ReaderAudioAdapter({
      audio,
      loadState: () => {
        try { return JSON.parse(localStorage.getItem(stateKey) || 'null') || {}; } catch { return {}; }
      },
      saveState: (state) => localStorage.setItem(stateKey, JSON.stringify(state)),
      displayCfi,
      isVisible,
      highlight: (target) => metrics.highlights.push(target.cfi),
      clearHighlight: () => {},
      resolveNextReadable: async (chapter) => chapter === 'one'
        ? { chapter: 'two', mediaId: 'media-two', src: 'https://e2e.invalid/two.wav', segments: segments2, time: 0, cfi: cfis[2] }
        : null,
      prepareNext: async (next) => ({ ...next, prepared: true }),
      activateChapter: async (next) => next,
      continuous: true,
      onTarget: (target) => metrics.targets.push(target.cfi),
    });
    window.__r3CoreE2E = { adapter, audio, segments1, segments2, stateKey };
  }, { cfis, stateKey: E2E_STATE_KEY, clearState });
}

try {
  const runtime = await bootAndAssertV31();
  const bridgeShape = await page.evaluate(() => ({ keys: Object.keys(window.r3ReaderBridge || {}).sort(), current: typeof window.r3ReaderBridge?.current, next: typeof window.r3ReaderBridge?.next, prev: typeof window.r3ReaderBridge?.prev, contents: typeof window.r3ReaderBridge?.contents }));
  console.log(JSON.stringify({ phase: 'live-baseline', runtime, bridgeShape }));

  const cfis = await collectPageCfis(3);
  console.log(JSON.stringify({ phase: 'real-cfis', count: cfis.length, cfis }));
  await injectAdapter({ cfis, clearState: true });

  const mounted = await page.evaluate(async ({ bookKey, cfi }) => {
    const { adapter, segments1 } = window.__r3CoreE2E;
    return adapter.mount({ bookKey, chapter: 'one', mediaId: 'media-one', src: 'https://e2e.invalid/one.wav', segments: segments1, time: 0, cfi, playbackRate: 1, playingIntent: false, autoplay: false });
  }, { bookKey: BOOK_KEY, cfi: cfis[0] });
  if (mounted.chapter !== 'one' || mounted.cfi !== cfis[0]) throw new Error(`MOUNT_STATE_BAD:${JSON.stringify(mounted)}`);

  const ownership = await page.evaluate(async () => {
    const { adapter, audio } = window.__r3CoreE2E;
    await adapter.play();
    const firstTimer = adapter.controller.timer;
    const sameTimer = adapter.controller.startClock() === firstTimer;
    adapter.setRate(2);
    await new Promise((resolve) => setTimeout(resolve, 320));
    return { sameTimer, timer: Boolean(adapter.controller.timer), rate: audio.playbackRate, time: audio.currentTime, paused: audio.paused };
  });
  if (!ownership.sameTimer || !ownership.timer) throw new Error(`DUPLICATE_OR_MISSING_CLOCK:${JSON.stringify(ownership)}`);
  if (ownership.rate < 1.9 || ownership.paused) throw new Error(`PLAY_RATE_OWNERSHIP_BAD:${JSON.stringify(ownership)}`);

  await page.evaluate(async () => window.__r3CoreE2E.adapter.seek(3.4));
  await page.waitForTimeout(180);
  if (await currentCfi() !== cfis[1]) throw new Error('SEEK_DID_NOT_FOLLOW_TO_SECOND_REAL_CFI');

  await page.evaluate(async ({ cfi1, cfi2 }) => {
    const { adapter } = window.__r3CoreE2E;
    const auto = adapter.follower.follow({ cfi: cfi1 }, { force: true });
    await new Promise((resolve) => setTimeout(resolve, 5));
    const manual = adapter.navigate(cfi2);
    await Promise.all([auto, manual]);
  }, { cfi1: cfis[1], cfi2: cfis[2] });
  await page.waitForTimeout(160);
  const race = await page.evaluate(() => ({ cfi: String(window.r3ReaderBridge.current()?.start?.cfi || ''), state: window.__r3CoreE2E.adapter.snapshot(), metrics: window.__r3CoreE2EMetrics }));
  if (race.metrics.maxConcurrent !== 1) throw new Error(`FOLLOW_OVERLAP:${JSON.stringify(race.metrics)}`);
  if (race.cfi !== cfis[2] || race.state.cfi !== cfis[2]) throw new Error(`LATEST_TARGET_DID_NOT_WIN:${JSON.stringify(race)}`);
  if (race.metrics.animateValues.some((value) => value !== false)) throw new Error(`AUTO_FOLLOW_ANIMATION_NOT_DISABLED:${JSON.stringify(race.metrics.animateValues)}`);

  await page.evaluate(async ({ cfi }) => {
    const { adapter } = window.__r3CoreE2E;
    await adapter.navigate(cfi, { time: 1 });
    await adapter.prefetchNext();
    adapter.controller.state.chapter = 'one';
    adapter.controller.state.mediaId = 'media-one';
    adapter.audio.dispatchEvent(new Event('ended'));
  }, { cfi: cfis[0] });
  await page.waitForFunction(({ cfi }) => window.__r3CoreE2E?.adapter?.snapshot?.().chapter === 'two' && String(window.r3ReaderBridge?.current?.()?.start?.cfi || '') === cfi, { cfi: cfis[2] }, { timeout: 8000 });
  const advanced = await page.evaluate(() => ({ state: window.__r3CoreE2E.adapter.snapshot(), src: window.__r3CoreE2E.audio.src, paused: window.__r3CoreE2E.audio.paused }));
  if (advanced.state.mediaId !== 'media-two' || !advanced.src.includes('/two.wav') || advanced.paused) throw new Error(`QUEUE_ADVANCE_BAD:${JSON.stringify(advanced)}`);

  await page.evaluate(() => {
    const { adapter } = window.__r3CoreE2E;
    adapter.setRate(1.5);
    adapter.seek(1.25);
    adapter.pause();
    adapter.persist();
  });
  const savedBeforeReload = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || 'null'), E2E_STATE_KEY);
  if (!savedBeforeReload || savedBeforeReload.chapter !== 'two' || savedBeforeReload.time < 1.2) throw new Error(`RESUME_STATE_NOT_SAVED:${JSON.stringify(savedBeforeReload)}`);

  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForFunction(() => Boolean(window.r3ReaderBridge?.current && window.r3ReaderBridge?.next && window.r3ReaderBridge?.prev), null, { timeout: 30000 });
  await injectAdapter({ cfis, clearState: false });
  const restored = await page.evaluate(async () => {
    const { adapter, segments2 } = window.__r3CoreE2E;
    return adapter.mount({ segments: segments2, src: 'https://e2e.invalid/two.wav', autoplay: false });
  });
  await page.waitForTimeout(220);
  if (restored.chapter !== 'two' || restored.mediaId !== 'media-two' || restored.time < 1.2 || restored.playbackRate < 1.4) throw new Error(`RESTORE_BAD:${JSON.stringify(restored)}`);
  if (await currentCfi() !== cfis[2]) throw new Error('RESTORE_DID_NOT_FOLLOW_SAVED_REAL_CFI');

  const stress = await page.evaluate(async ({ cfis }) => {
    const { adapter } = window.__r3CoreE2E;
    const jobs = [];
    for (let i = 0; i < 12; i++) jobs.push(adapter.navigate(cfis[i % cfis.length]));
    jobs.push(adapter.navigate(cfis[2]));
    await Promise.all(jobs);
    return { state: adapter.snapshot(), metrics: window.__r3CoreE2EMetrics };
  }, { cfis });
  if (stress.metrics.maxConcurrent !== 1 || stress.state.cfi !== cfis[2]) throw new Error(`STRESS_RACE_FAILED:${JSON.stringify(stress)}`);

  const finalResponse = await context.request.get(readerUrl, { timeout: 60000 });
  const finalRuntime = finalResponse.headers()['x-r3-reader-runtime'] || '';
  if (finalRuntime !== 'v31-high-speed-serialized-follow') throw new Error(`LIVE_BASELINE_CHANGED:${finalRuntime || 'missing'}`);

  const fatalErrors = errors.filter((text) => !/favicon|ResizeObserver/i.test(text));
  if (fatalErrors.length) throw new Error(`BROWSER_ERRORS:${fatalErrors.slice(0, 5).join(' | ')}`);
  console.log(JSON.stringify({ phase: 'reader-audio-core-live-injection-e2e', ok: true, runtimeStart: runtime, runtimeEnd: finalRuntime, realCfis: cfis.length, ownership, maxNavigationConcurrent: stress.metrics.maxConcurrent, restored: { chapter: restored.chapter, mediaId: restored.mediaId, time: restored.time, playbackRate: restored.playbackRate }, productionMutated: false }));
  console.log('READER_AUDIO_CORE_LIVE_INJECTION_E2E=PASS');
} finally {
  await browser.close();
}
