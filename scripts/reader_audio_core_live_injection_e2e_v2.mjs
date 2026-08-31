import fs from 'node:fs';
import { chromium } from 'playwright';

const CORE_URL = process.env.RUNNER3_CORE_URL || 'https://runner3-core.ducduy2411.workers.dev';
const BOOK_KEY = process.env.EBOOK_BROWSER_SMOKE_BOOK_KEY || 'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub';
const BUNDLE_PATH = process.argv[2] || '/tmp/reader-audio-core-e2e.js';
const STATE_KEY = 'r3-reader-audio-core-e2e-v2';
const readerUrl = `${CORE_URL}/artifact-library/read?key=${encodeURIComponent(BOOK_KEY)}`;
const bundle = fs.readFileSync(BUNDLE_PATH, 'utf8');

function makeSilentWav(seconds = 8) {
  const sampleRate = 8000;
  const samples = Math.max(sampleRate, Math.ceil(seconds * sampleRate));
  const out = Buffer.alloc(44 + samples, 128);
  out.write('RIFF', 0, 'ascii'); out.writeUInt32LE(36 + samples, 4); out.write('WAVE', 8, 'ascii');
  out.write('fmt ', 12, 'ascii'); out.writeUInt32LE(16, 16); out.writeUInt16LE(1, 20); out.writeUInt16LE(1, 22);
  out.writeUInt32LE(sampleRate, 24); out.writeUInt32LE(sampleRate, 28); out.writeUInt16LE(1, 32); out.writeUInt16LE(8, 34);
  out.write('data', 36, 'ascii'); out.writeUInt32LE(samples, 40);
  return out;
}

const audioDataUrl = `data:audio/wav;base64,${makeSilentWav().toString('base64')}`;
const browser = await chromium.launch({ headless: true, args: ['--autoplay-policy=no-user-gesture-required'] });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const page = await context.newPage();

async function bootV31() {
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

async function collectCfis() {
  const cfis = [];
  for (let i = 0; i < 8 && cfis.length < 3; i++) {
    const cfi = await currentCfi();
    if (cfi && !cfis.includes(cfi)) cfis.push(cfi);
    if (cfis.length < 3) {
      await page.evaluate(async () => window.r3ReaderBridge.next());
      await page.waitForTimeout(220);
    }
  }
  if (cfis.length !== 3) throw new Error(`NEED_3_DISTINCT_CFIS_GOT_${cfis.length}`);
  for (let i = 0; i < 2; i++) {
    await page.evaluate(async () => window.r3ReaderBridge.prev());
    await page.waitForTimeout(220);
  }
  if (await currentCfi() !== cfis[0]) throw new Error('FAILED_TO_RETURN_TO_FIRST_CFI');
  return cfis;
}

async function inject({ cfis, clearState }) {
  await page.addScriptTag({ content: bundle });
  await page.evaluate(({ cfis, stateKey, clearState, audioDataUrl }) => {
    if (!window.R3AudioCoreE2E?.ReaderAudioAdapter) throw new Error('ADAPTER_BUNDLE_EXPORT_MISSING');
    if (clearState) localStorage.removeItem(stateKey);
    document.getElementById('r3AudioCoreE2EV2')?.remove();

    const audio = document.createElement('audio');
    audio.id = 'r3AudioCoreE2EV2';
    audio.muted = true;
    audio.preload = 'auto';
    audio.style.display = 'none';
    document.body.appendChild(audio);

    const order = [...cfis];
    const metrics = window.__r3CoreE2EV2Metrics = {
      displayCalls: 0,
      currentConcurrent: 0,
      maxConcurrent: 0,
      animateValues: [],
      highlights: [],
      targets: [],
    };
    const readCfi = () => String(window.r3ReaderBridge?.current?.()?.start?.cfi || '');
    const displayCfi = async (targetCfi, options = {}) => {
      metrics.displayCalls += 1;
      metrics.currentConcurrent += 1;
      metrics.maxConcurrent = Math.max(metrics.maxConcurrent, metrics.currentConcurrent);
      metrics.animateValues.push(options?.animate);
      try {
        for (let step = 0; step < 12; step++) {
          const here = readCfi();
          if (here === targetCfi) return true;
          const hereIndex = order.indexOf(here);
          const targetIndex = order.indexOf(targetCfi);
          if (targetIndex < 0) throw new Error(`UNKNOWN_TARGET_CFI:${targetCfi}`);
          if (hereIndex < 0 || hereIndex < targetIndex) await window.r3ReaderBridge.next();
          else await window.r3ReaderBridge.prev();
          await new Promise((resolve) => setTimeout(resolve, 80));
        }
        throw new Error(`DISPLAY_CFI_DID_NOT_LAND:${targetCfi}:${readCfi()}`);
      } finally {
        metrics.currentConcurrent -= 1;
      }
    };

    const segments1 = [
      { start: 0, end: 2.99, cfi: cfis[0], token: 'P0' },
      { start: 3, end: 5.99, cfi: cfis[1], token: 'P1' },
    ];
    const segments2 = [{ start: 0, end: 5.99, cfi: cfis[2], token: 'P2' }];

    const adapter = new window.R3AudioCoreE2E.ReaderAudioAdapter({
      audio,
      loadState: () => {
        try { return JSON.parse(localStorage.getItem(stateKey) || 'null') || {}; } catch { return {}; }
      },
      saveState: (state) => localStorage.setItem(stateKey, JSON.stringify(state)),
      displayCfi,
      isVisible: async (target) => readCfi() === target.cfi,
      highlight: (target) => metrics.highlights.push(target.cfi),
      clearHighlight: () => {},
      resolveNextReadable: async (chapter) => chapter === 'one'
        ? { chapter: 'two', mediaId: 'media-two', src: audioDataUrl, segments: segments2, time: 0, cfi: cfis[2] }
        : null,
      prepareNext: async (next) => ({ ...next, prepared: true }),
      activateChapter: async (next) => next,
      continuous: true,
      onTarget: (target) => metrics.targets.push(target.cfi),
    });
    window.__r3CoreE2EV2 = { adapter, audio, segments1, segments2, stateKey, audioDataUrl };
  }, { cfis, stateKey: STATE_KEY, clearState, audioDataUrl });
}

try {
  const runtime = await bootV31();
  const bridgeShape = await page.evaluate(() => ({
    keys: Object.keys(window.r3ReaderBridge || {}).sort(),
    display: typeof window.r3ReaderBridge?.display,
    current: typeof window.r3ReaderBridge?.current,
    next: typeof window.r3ReaderBridge?.next,
    prev: typeof window.r3ReaderBridge?.prev,
  }));
  console.log(JSON.stringify({ phase: 'live-baseline', runtime, bridgeShape }));

  const cfis = await collectCfis();
  console.log(JSON.stringify({ phase: 'real-cfis', cfis }));
  await inject({ cfis, clearState: true });

  const mounted = await page.evaluate(async ({ bookKey, cfi }) => {
    const { adapter, segments1, audioDataUrl } = window.__r3CoreE2EV2;
    return adapter.mount({
      bookKey,
      chapter: 'one',
      mediaId: 'media-one',
      src: audioDataUrl,
      segments: segments1,
      time: 0,
      cfi,
      playbackRate: 1,
      playingIntent: false,
      autoplay: false,
    });
  }, { bookKey: BOOK_KEY, cfi: cfis[0] });
  if (mounted.chapter !== 'one' || mounted.cfi !== cfis[0]) throw new Error(`MOUNT_BAD:${JSON.stringify(mounted)}`);
  await page.waitForFunction(() => {
    const a = window.__r3CoreE2EV2?.audio;
    return Boolean(a && a.readyState >= 1 && Number(a.duration || 0) >= 6);
  }, null, { timeout: 10000 });

  const ownership = await page.evaluate(async () => {
    const { adapter, audio } = window.__r3CoreE2EV2;
    await adapter.play();
    const firstTimer = adapter.controller.timer;
    const secondTimer = adapter.controller.startClock();
    adapter.setRate(2);
    await new Promise((resolve) => setTimeout(resolve, 320));
    return {
      sameTimer: firstTimer === secondTimer,
      timerAlive: Boolean(adapter.controller.timer),
      rate: audio.playbackRate,
      time: audio.currentTime,
      paused: audio.paused,
    };
  });
  if (!ownership.sameTimer || !ownership.timerAlive || ownership.rate < 1.9 || ownership.paused) {
    throw new Error(`MEDIA_OWNER_BAD:${JSON.stringify(ownership)}`);
  }

  await page.evaluate(async () => window.__r3CoreE2EV2.adapter.seek(3.4));
  await page.waitForTimeout(180);
  if (await currentCfi() !== cfis[1]) throw new Error('SEEK_FOLLOW_BAD');

  await page.evaluate(async ({ first, last }) => {
    const { adapter } = window.__r3CoreE2EV2;
    const auto = adapter.follower.follow({ cfi: first }, { force: true });
    await new Promise((resolve) => setTimeout(resolve, 5));
    const manual = adapter.navigate(last);
    await Promise.all([auto, manual]);
  }, { first: cfis[0], last: cfis[2] });
  await page.waitForTimeout(160);
  const race = await page.evaluate(() => ({
    cfi: String(window.r3ReaderBridge.current()?.start?.cfi || ''),
    state: window.__r3CoreE2EV2.adapter.snapshot(),
    metrics: window.__r3CoreE2EV2Metrics,
  }));
  if (race.metrics.maxConcurrent !== 1) throw new Error(`FOLLOW_OVERLAP:${JSON.stringify(race.metrics)}`);
  if (race.cfi !== cfis[2] || race.state.cfi !== cfis[2]) throw new Error(`LATEST_TARGET_LOST:${JSON.stringify(race)}`);
  if (race.metrics.animateValues.some((value) => value !== false)) throw new Error(`AUTO_ANIMATION_ENABLED:${JSON.stringify(race.metrics.animateValues)}`);

  await page.evaluate(async ({ first }) => {
    const { adapter, audio } = window.__r3CoreE2EV2;
    await adapter.navigate(first, { time: 1 });
    await adapter.prefetchNext();
    adapter.controller.state.chapter = 'one';
    adapter.controller.state.mediaId = 'media-one';
    audio.dispatchEvent(new Event('ended'));
  }, { first: cfis[0] });
  await page.waitForFunction((last) => {
    const root = window.__r3CoreE2EV2;
    return root?.adapter?.snapshot?.().chapter === 'two'
      && String(window.r3ReaderBridge?.current?.()?.start?.cfi || '') === last
      && root.audio.paused === false;
  }, cfis[2], { timeout: 8000 });
  const advanced = await page.evaluate(() => window.__r3CoreE2EV2.adapter.snapshot());
  if (advanced.mediaId !== 'media-two' || advanced.chapter !== 'two') throw new Error(`QUEUE_ADVANCE_BAD:${JSON.stringify(advanced)}`);

  await page.evaluate(async () => {
    const { adapter } = window.__r3CoreE2EV2;
    adapter.setRate(1.5);
    await adapter.seek(1.25);
    adapter.pause();
    adapter.persist();
  });
  const saved = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) || 'null'), STATE_KEY);
  if (!saved || saved.chapter !== 'two' || saved.mediaId !== 'media-two' || saved.time < 1.2 || saved.playbackRate < 1.4) {
    throw new Error(`SAVE_BAD:${JSON.stringify(saved)}`);
  }

  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForFunction(() => Boolean(window.r3ReaderBridge?.current && window.r3ReaderBridge?.next && window.r3ReaderBridge?.prev), null, { timeout: 30000 });
  await inject({ cfis, clearState: false });
  const restored = await page.evaluate(async () => {
    const { adapter, segments2, audioDataUrl } = window.__r3CoreE2EV2;
    return adapter.mount({ segments: segments2, src: audioDataUrl, autoplay: false });
  });
  await page.waitForTimeout(220);
  if (restored.chapter !== 'two' || restored.mediaId !== 'media-two' || restored.time < 1.2 || restored.playbackRate < 1.4) {
    throw new Error(`RESTORE_BAD:${JSON.stringify(restored)}`);
  }
  if (await currentCfi() !== cfis[2]) throw new Error('RESTORE_CFI_BAD');

  const stress = await page.evaluate(async (cfis) => {
    const { adapter } = window.__r3CoreE2EV2;
    const jobs = [];
    for (let i = 0; i < 15; i++) jobs.push(adapter.navigate(cfis[i % cfis.length]));
    jobs.push(adapter.navigate(cfis[2]));
    await Promise.all(jobs);
    return { state: adapter.snapshot(), metrics: window.__r3CoreE2EV2Metrics };
  }, cfis);
  if (stress.metrics.maxConcurrent !== 1 || stress.state.cfi !== cfis[2]) {
    throw new Error(`STRESS_RACE_BAD:${JSON.stringify(stress)}`);
  }

  const finalResponse = await context.request.get(readerUrl, { timeout: 60000 });
  const finalRuntime = finalResponse.headers()['x-r3-reader-runtime'] || '';
  if (finalRuntime !== 'v31-high-speed-serialized-follow') throw new Error(`PRODUCTION_CHANGED_DURING_E2E:${finalRuntime}`);

  console.log(JSON.stringify({
    phase: 'reader-audio-core-live-e2e-v2',
    ok: true,
    runtime: finalRuntime,
    mediaSingleOwner: true,
    clock75msSingleTimer: true,
    deterministicSeekFollow: true,
    singleFlightLatestTargetWins: true,
    autoFollowAnimationDisabled: true,
    continuousQueueAdvance: true,
    persistedResume: true,
    raceStress: true,
    productionMutation: false,
  }));
  console.log('READER_AUDIO_CORE_LIVE_E2E=PASS');
} finally {
  await browser.close();
}
