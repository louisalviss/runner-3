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

  window.__r3V33LiveBootAudit = audit;
});

try {
  const response = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  if (!response || response.status() !== 200) throw new Error(`READER_HTTP_${response?.status?.() || 0}`);

  const headers = response.headers();
  const runtime = headers['x-r3-reader-runtime'] || '';
  const proof = headers['x-r3-reader-patch-proof'] || '';
  if (runtime !== 'v33-audio-core-owner') throw new Error(`LIVE_RUNTIME_WRONG:${runtime}`);
  if (proof !== 'v31+v33:core-single-owner+legacy-suppressed') throw new Error(`LIVE_PROOF_WRONG:${proof}`);

  await page.waitForSelector('#r3AudioMain', { state: 'attached', timeout: 30000 });
  await page.waitForSelector('#r3AudioElement', { state: 'attached', timeout: 30000 });
  await page.waitForSelector('#viewer iframe', { state: 'attached', timeout: 30000 });
  await page.waitForFunction(() => Boolean(
    window.__r3AudioCoreProductionV33
    && window.__r3AudioLegacyV6Suppressed
    && window.__r3AudioLegacyV8Suppressed
    && window.__r3AudioLegacyV11Suppressed
    && window.__r3AudioLegacyV29Suppressed
    && window.__r3AudioLegacyV31ClockSuppressed
    && window.__r3AudioCoreV33Debug?.owner === 'reader-audio-core-v33'
    && window.r3ReaderBridge?.current
  ), null, { timeout: 30000 });
  await page.waitForTimeout(500);

  const result = await page.evaluate(() => ({
    ownerMarker: Boolean(document.querySelector('script[data-r3-audio-core-owner-v33="1"]')),
    runtimeMarker: Boolean(document.querySelector('script[data-r3-audio-core-runtime-v33="1"]')),
    flags: {
      v6: Boolean(window.__r3AudioLegacyV6Suppressed),
      v8: Boolean(window.__r3AudioLegacyV8Suppressed),
      v11: Boolean(window.__r3AudioLegacyV11Suppressed),
      v29: Boolean(window.__r3AudioLegacyV29Suppressed),
      v31: Boolean(window.__r3AudioLegacyV31ClockSuppressed),
      v31ClockStarted: Boolean(window.__r3AudioLegacyV31ClockStarted),
    },
    debugOwner: String(window.__r3AudioCoreV33Debug?.owner || ''),
    bootError: String(window.__r3AudioCoreV33BootError || ''),
    audit: window.__r3V33LiveBootAudit,
    current: window.r3ReaderBridge?.current?.() || null,
  }));

  const listeners = result.audit?.listeners || {};
  const exactOne = [
    'r3AudioMain:click',
    'r3AudioBack:click',
    'r3AudioForward:click',
    'r3AudioSpeed:click',
    'r3AudioExpand:click',
    'r3AudioSeek:input',
    'r3AudioSeek:change',
    'r3AudioElement:timeupdate',
    'r3AudioElement:play',
    'r3AudioElement:pause',
    'r3AudioElement:ended',
  ];

  if (!result.ownerMarker || !result.runtimeMarker) throw new Error('V33_DOM_MARKERS_MISSING');
  if (!result.flags.v6 || !result.flags.v8 || !result.flags.v11 || !result.flags.v29 || !result.flags.v31) throw new Error('LEGACY_SUPPRESSION_INCOMPLETE');
  if (result.flags.v31ClockStarted) throw new Error('LEGACY_V31_CLOCK_STARTED');
  if (result.debugOwner !== 'reader-audio-core-v33') throw new Error(`OWNER_WRONG:${result.debugOwner}`);
  if (result.bootError) throw new Error(`V33_BOOT_ERROR:${result.bootError}`);
  for (const key of exactOne) {
    if (Number(listeners[key] || 0) !== 1) throw new Error(`LISTENER_OWNER_WRONG:${key}:${listeners[key] || 0}`);
  }
  if (Number(result.audit?.interval75 || 0) > 1) throw new Error(`CLOCK_75_DUPLICATE:${result.audit.interval75}`);
  if (audioPostCount !== 0) throw new Error(`PRODUCTION_MUTATION_AUDIO_POST:${audioPostCount}`);

  console.log(JSON.stringify({
    ok: true,
    runtime,
    proof,
    singleListenerOwner: true,
    legacySuppressed: true,
    interval75AtMostOne: true,
    productionMutation: false,
    audioPostCount,
    currentHref: String(result.current?.start?.href || ''),
    pageErrors: pageErrors.slice(0, 5),
  }));
  console.log('READER_AUDIO_CORE_V33_LIVE_BOOT_E2E=PASS');
} finally {
  await browser.close();
}
