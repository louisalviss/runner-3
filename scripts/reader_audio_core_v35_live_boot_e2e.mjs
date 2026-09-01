import { chromium } from 'playwright';

const CORE_URL = process.env.RUNNER3_CORE_URL || 'https://runner3-core.ducduy2411.workers.dev';
const BOOK_KEY = process.env.EBOOK_BROWSER_SMOKE_BOOK_KEY || 'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub';
const readerUrl = `${CORE_URL}/artifact-library/read?key=${encodeURIComponent(BOOK_KEY)}`;

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();
const pageErrors = [];
let audioPostCount = 0;

page.on('pageerror', (error) => pageErrors.push(String(error?.message || error).slice(0, 300)));
page.on('request', (request) => {
  try {
    const url = new URL(request.url());
    if (request.method() === 'POST' && url.pathname === '/artifact-library/audio') audioPostCount++;
  } catch {}
});

await page.addInitScript(() => {
  const audit = { listeners: {}, interval75: 0 };
  const ids = new Set([
    'r3AudioMain',
    'r3AudioBack',
    'r3AudioForward',
    'r3AudioSpeed',
    'r3AudioExpand',
    'r3AudioSeek',
    'r3AudioElement',
  ]);

  const originalAdd = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function(type, listener, options) {
    try {
      const id = String(this?.id || '');
      if (ids.has(id)) {
        const key = `${id}:${String(type)}`;
        audit.listeners[key] = (audit.listeners[key] || 0) + 1;
      }
    } catch {}
    return originalAdd.call(this, type, listener, options);
  };

  const originalInterval = window.setInterval;
  window.setInterval = function(handler, timeout, ...args) {
    if (Number(timeout) === 75) audit.interval75++;
    return originalInterval.call(this, handler, timeout, ...args);
  };

  window.__r3V35LiveBootAudit = audit;
});

try {
  let response = null;
  for (let attempt = 1; attempt <= 4; attempt++) {
    response = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    if (response && response.status() === 200) break;
    if (!response || response.status() < 500 || attempt === 4) break;
    await page.waitForTimeout(500 * attempt);
  }
  if (!response || response.status() !== 200) throw new Error(`READER_HTTP_${response?.status?.() || 0}`);

  const headers = response.headers();
  const runtime = headers['x-r3-reader-runtime'] || '';
  const proof = headers['x-r3-reader-patch-proof'] || '';
  if (runtime !== 'v35-continuity-single-owner') throw new Error(`LIVE_RUNTIME_WRONG:${runtime}`);
  if (proof !== 'v34+v35:ahead-prefetch+range-follow+single-audio-owner') throw new Error(`LIVE_PROOF_WRONG:${proof}`);

  await page.waitForSelector('#r3AudioMain', { state: 'attached', timeout: 30000 });
  await page.waitForSelector('#r3AudioElement', { state: 'attached', timeout: 30000 });
  await page.waitForSelector('#viewer iframe', { state: 'attached', timeout: 30000 });
  await page.waitForFunction(() => Boolean(
    window.__r3AudioCoreProductionV33
    && window.__r3AudioContinuityV34?.owner === 'reader-audio-continuity-v34'
    && window.__r3AudioContinuityV35?.singleAudioListenerOwner === true
    && window.__r3AudioLegacyV6Suppressed
    && window.__r3AudioLegacyV8Suppressed
    && window.__r3AudioLegacyV11Suppressed
    && window.__r3AudioLegacyV29Suppressed
    && window.__r3AudioLegacyV31ClockSuppressed
    && window.__r3AudioCoreV33Debug?.owner === 'reader-audio-core-v33'
    && window.r3ReaderBridge?.current
  ), null, { timeout: 30000 });
  await page.waitForTimeout(500);

  const result = await page.evaluate(async () => {
    const before = window.r3ReaderBridge?.current?.() || null;
    let peek = null;
    if (window.__r3AudioContinuityV34?.peek) {
      try { peek = await window.__r3AudioContinuityV34.peek(1); } catch {}
    }
    const after = window.r3ReaderBridge?.current?.() || null;
    return {
      ownerMarker: Boolean(document.querySelector('script[data-r3-audio-core-owner-v33="1"]')),
      coreRuntimeMarker: Boolean(document.querySelector('script[data-r3-audio-core-runtime-v33="1"]')),
      continuityV34Marker: Boolean(document.querySelector('script[data-r3-audio-continuity-v34="1"]')),
      continuityV35Marker: Boolean(document.querySelector('script[data-r3-audio-continuity-v35="1"]')),
      flags: {
        v6: Boolean(window.__r3AudioLegacyV6Suppressed),
        v8: Boolean(window.__r3AudioLegacyV8Suppressed),
        v11: Boolean(window.__r3AudioLegacyV11Suppressed),
        v29: Boolean(window.__r3AudioLegacyV29Suppressed),
        v31: Boolean(window.__r3AudioLegacyV31ClockSuppressed),
        v31ClockStarted: Boolean(window.__r3AudioLegacyV31ClockStarted),
      },
      coreOwner: String(window.__r3AudioCoreV33Debug?.owner || ''),
      continuityV34Owner: String(window.__r3AudioContinuityV34?.owner || ''),
      continuityV35Owner: String(window.__r3AudioContinuityV35?.owner || ''),
      singleAudioListenerOwner: Boolean(window.__r3AudioContinuityV35?.singleAudioListenerOwner),
      bootError: String(window.__r3AudioCoreV33BootError || ''),
      continuityError: String(window.__r3AudioContinuityV34?.lastError || ''),
      audit: window.__r3V35LiveBootAudit,
      before,
      after,
      peek: peek ? { chapterHref: String(peek.chapterHref || ''), textLength: String(peek.text || '').length } : null,
    };
  });

  const listeners = result.audit?.listeners || {};
  const exactOne = [
    'r3AudioMain:click',
    'r3AudioBack:click',
    'r3AudioForward:click',
    'r3AudioSpeed:click',
    'r3AudioExpand:click',
    'r3AudioSeek:input',
    'r3AudioSeek:change',
    'r3AudioElement:loadedmetadata',
    'r3AudioElement:durationchange',
    'r3AudioElement:timeupdate',
    'r3AudioElement:play',
    'r3AudioElement:pause',
    'r3AudioElement:ended',
  ];

  if (!result.ownerMarker || !result.coreRuntimeMarker || !result.continuityV34Marker || !result.continuityV35Marker) throw new Error('V35_DOM_MARKERS_MISSING');
  if (!result.flags.v6 || !result.flags.v8 || !result.flags.v11 || !result.flags.v29 || !result.flags.v31) throw new Error('LEGACY_SUPPRESSION_INCOMPLETE');
  if (result.flags.v31ClockStarted) throw new Error('LEGACY_V31_CLOCK_STARTED');
  if (result.coreOwner !== 'reader-audio-core-v33') throw new Error(`CORE_OWNER_WRONG:${result.coreOwner}`);
  if (result.continuityV34Owner !== 'reader-audio-continuity-v34') throw new Error(`CONTINUITY_V34_OWNER_WRONG:${result.continuityV34Owner}`);
  if (result.continuityV35Owner !== 'reader-audio-continuity-v35' || !result.singleAudioListenerOwner) throw new Error(`CONTINUITY_V35_OWNER_WRONG:${result.continuityV35Owner}`);
  if (result.bootError) throw new Error(`V33_CORE_BOOT_ERROR:${result.bootError}`);
  for (const key of exactOne) {
    if (Number(listeners[key] || 0) !== 1) throw new Error(`LISTENER_OWNER_WRONG:${key}:${listeners[key] || 0}`);
  }
  if (Number(result.audit?.interval75 || 0) > 1) throw new Error(`CLOCK_75_DUPLICATE:${result.audit.interval75}`);
  if (audioPostCount !== 0) throw new Error(`PRODUCTION_MUTATION_AUDIO_POST:${audioPostCount}`);
  const beforeHref = String(result.before?.start?.href || '');
  const beforeCfi = String(result.before?.start?.cfi || '');
  const afterHref = String(result.after?.start?.href || '');
  const afterCfi = String(result.after?.start?.cfi || '');
  if (beforeHref !== afterHref || beforeCfi !== afterCfi) throw new Error('V35_PEEK_MUTATED_READER');
  if (pageErrors.length) throw new Error(`PAGE_ERRORS:${pageErrors.join(' | ')}`);

  console.log(JSON.stringify({
    ok: true,
    runtime,
    proof,
    singleAudioListenerOwner: true,
    listenerAudit: listeners,
    legacySuppressed: true,
    interval75AtMostOne: true,
    peekNonMutating: true,
    peekTextLength: Number(result.peek?.textLength || 0),
    productionMutation: false,
    audioPostCount,
    currentHref: beforeHref,
    pageErrors: pageErrors.slice(0, 5),
  }));
  console.log('READER_AUDIO_CORE_V35_LIVE_BOOT_E2E=PASS');
} finally {
  await browser.close();
}
