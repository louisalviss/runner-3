import { chromium } from 'playwright';

const base = process.env.PREVIEW_URL;
const productionBase = process.env.PRODUCTION_URL || 'https://runner3-core.ducduy2411.workers.dev';
const bookKey = process.env.EBOOK_BROWSER_SMOKE_BOOK_KEY || 'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub';
if (!base) throw new Error('PREVIEW_URL_REQUIRED');

const readerUrl = `${base}/artifact-library/read?key=${encodeURIComponent(bookKey)}`;
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 390, height: 760 } });
const page = await context.newPage();
const pageErrors = [];
let signedEpubUrl = '';
let epubProxyStatus = 0;
let epubProxyBytes = 0;
let audioPostCount = 0;
const audioPostChapters = [];
page.on('pageerror', (error) => pageErrors.push(String(error?.message || error)));

await page.addInitScript(() => {
  const audit = { listeners: {} };
  const originalAdd = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function(type, listener, options) {
    try {
      if (String(this?.id || '') === 'r3AudioElement') {
        audit.listeners[type] = (audit.listeners[type] || 0) + 1;
      }
    } catch {}
    return originalAdd.call(this, type, listener, options);
  };
  window.__r3V35ListenerAudit = audit;
});

await page.route('**/artifact-library/audio*', async (route) => {
  const request = route.request();
  const url = new URL(request.url());
  if (url.pathname !== '/artifact-library/audio') return route.continue();
  if (request.method() === 'POST') {
    audioPostCount++;
    let body = {};
    try { body = JSON.parse(request.postData() || '{}'); } catch {}
    audioPostChapters.push(String(body.chapterHref || ''));
    const id = `mock-prefetch-${audioPostCount}`;
    return route.fulfill({
      status: 200,
      headers: { 'content-type': 'application/json', 'cache-control': 'private, no-store' },
      body: JSON.stringify({
        ok: true,
        id,
        status: 'ready',
        bookKey,
        chapterTitle: body.chapterTitle || null,
        mediaUrl: `/__mock_audio__?id=${id}`,
        timingUrl: `/__mock_timing__?id=${id}`,
      }),
    });
  }
  return route.fulfill({
    status: 404,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ ok: false, error: 'MOCK_AUDIO_STATE_NOT_EXPECTED' }),
  });
});

await page.route('**/__reader_v35_epub_proxy__', async (route) => {
  if (!signedEpubUrl) return route.fulfill({ status: 503, body: 'SIGNED_EPUB_URL_MISSING' });
  const upstream = await context.request.fetch(signedEpubUrl, { method: 'GET', failOnStatusCode: false });
  const body = await upstream.body();
  epubProxyStatus = upstream.status();
  epubProxyBytes = body.byteLength;
  await route.fulfill({
    status: upstream.status(),
    headers: {
      'content-type': upstream.headers()['content-type'] || 'application/epub+zip',
      'cache-control': 'private, no-store',
    },
    body,
  });
});

await page.route('**/artifact-library/api/delivery', async (route) => {
  const request = route.request();
  const upstream = await context.request.fetch(`${productionBase}/artifact-library/api/delivery`, {
    method: request.method(),
    headers: { 'content-type': 'application/json', 'x-runner3-library': '1' },
    data: request.postData() || '{}',
    failOnStatusCode: false,
  });
  const raw = await upstream.text();
  let body = raw;
  try {
    const data = JSON.parse(raw);
    if (upstream.ok() && data?.delivery?.url) {
      signedEpubUrl = new URL(data.delivery.url, productionBase).href;
      data.delivery.url = `${base}/__reader_v35_epub_proxy__`;
      body = JSON.stringify(data);
    }
  } catch {}
  await route.fulfill({
    status: upstream.status(),
    headers: { 'content-type': 'application/json', 'cache-control': 'private, no-store' },
    body,
  });
});

async function advanceToReadable() {
  return page.evaluate(async () => {
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const inspect = () => {
      let best = null;
      for (const frame of [...document.querySelectorAll('#viewer iframe')]) {
        try {
          const text = String(frame.contentDocument?.body?.innerText || '').trim();
          if (!best || text.length > best.textLength) best = { textLength: text.length, title: frame.contentDocument?.title || '' };
        } catch {}
      }
      const loc = window.r3ReaderBridge?.current?.();
      return { best, href: loc?.start?.href || '', cfi: loc?.start?.cfi || '' };
    };
    for (let step = 0; step < 36; step++) {
      const state = inspect();
      if ((state.best?.textLength || 0) >= 80) return { ok: true, step, state };
      if (!window.r3ReaderBridge?.next) break;
      const before = `${state.href}|${state.cfi}`;
      try { await Promise.race([Promise.resolve(window.r3ReaderBridge.next()), sleep(1200)]); } catch {}
      for (let n = 0; n < 12; n++) {
        await sleep(100);
        const after = inspect();
        if (`${after.href}|${after.cfi}` !== before || (after.best?.textLength || 0) >= 80) break;
      }
    }
    return { ok: false, state: inspect() };
  });
}

try {
  const response = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  if (!response || response.status() !== 200) throw new Error(`READER_HTTP_${response?.status()}`);
  const headers = await response.allHeaders();
  if (headers['x-r3-reader-runtime'] !== 'v35-continuity-single-owner') throw new Error(`RUNTIME_${headers['x-r3-reader-runtime'] || 'missing'}`);
  if (headers['x-r3-reader-patch-proof'] !== 'v34+v35:ahead-prefetch+range-follow+single-audio-owner') throw new Error('PROOF_MISMATCH');

  await page.waitForFunction(() => Boolean(
    window.__r3AudioContinuityV35?.singleAudioListenerOwner
    && window.__r3AudioContinuityV34?.primePrefetch
    && window.r3ReaderBridge?.current?.()?.start
  ), null, { timeout: 20000 });

  const readable = await advanceToReadable();
  if (!readable.ok) throw new Error(`READABLE_SECTION_NOT_FOUND:${JSON.stringify(readable)}`);

  const listenerAudit = await page.evaluate(() => ({ ...(window.__r3V35ListenerAudit?.listeners || {}) }));
  for (const type of ['timeupdate', 'play', 'pause', 'ended']) {
    if (Number(listenerAudit[type] || 0) !== 1) throw new Error(`AUDIO_LISTENER_OWNER_WRONG:${type}:${listenerAudit[type] || 0}`);
  }

  const peek = await page.evaluate(async () => {
    const before = window.r3ReaderBridge.current();
    const payload = await window.__r3AudioContinuityV34.peek(1);
    const after = window.r3ReaderBridge.current();
    return {
      payload: payload ? { textLength: String(payload.text || '').length, chapterHref: payload.chapterHref || '', chapterTitle: payload.chapterTitle || '' } : null,
      before: { href: before?.start?.href || '', cfi: before?.start?.cfi || '' },
      after: { href: after?.start?.href || '', cfi: after?.start?.cfi || '' },
    };
  });
  if (!peek.payload || peek.payload.textLength < 80 || !peek.payload.chapterHref) throw new Error('PEEK_NEXT_EMPTY');
  if (peek.before.href !== peek.after.href || peek.before.cfi !== peek.after.cfi) throw new Error('PEEK_MUTATED_READER');

  await page.evaluate(() => window.__r3AudioContinuityV34.primePrefetch());
  await page.waitForFunction(() => Number(window.__r3AudioContinuityV34?.prefetchReady || 0) >= 1, null, { timeout: 5000 });
  const postsBeforeHandoff = audioPostCount;

  const handoff = await page.evaluate(async () => {
    const payload = await window.__r3AudioContinuityV34.peek(1);
    const beforeHits = Number(window.__r3AudioContinuityV34.cacheHits || 0);
    const response = await window.fetch('/artifact-library/audio', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        bookKey: new URLSearchParams(location.search).get('key') || '',
        text: payload.text,
        chapterTitle: payload.chapterTitle,
        chapterHref: payload.chapterHref,
        bookTitle: document.title || 'Ebook',
        clientVersion: 'reader-audio-core-v33',
      }),
    });
    const state = await response.json().catch(() => ({}));
    return {
      http: response.status,
      status: state.status || '',
      mediaUrl: state.mediaUrl || '',
      hitDelta: Number(window.__r3AudioContinuityV34.cacheHits || 0) - beforeHits,
    };
  });
  if (audioPostCount !== postsBeforeHandoff) throw new Error(`HANDOFF_NETWORK_POST_${postsBeforeHandoff}_${audioPostCount}`);
  if (handoff.http !== 200 || handoff.status !== 'ready' || !handoff.mediaUrl || handoff.hitDelta !== 1) throw new Error(`HANDOFF_CACHE_MISS:${JSON.stringify(handoff)}`);

  const range = await page.evaluate(async () => {
    const frame = [...document.querySelectorAll('#viewer iframe')].find((candidate) => {
      try { return String(candidate.contentDocument?.body?.innerText || '').trim().length >= 80; } catch { return false; }
    });
    const text = String(frame?.contentDocument?.body?.innerText || '');
    const words = text.match(/[\p{L}\p{M}\p{N}]+/gu) || [];
    const timing = words.slice(0, 220).map((word, index) => ({ text: word, startMs: index * 120, durationMs: 100 }));
    const mapped = window.__r3AudioContinuityV34.installTestTiming(timing);
    const beforeFollow = Number(window.__r3AudioContinuityV34.exactFollowCalls || 0);
    await window.__r3AudioContinuityV34.syncTestWord(Math.max(0, timing.length - 12), true);
    await new Promise((resolve) => setTimeout(resolve, 180));
    const doc = frame?.contentDocument;
    let highlightText = '';
    try {
      const highlight = doc?.defaultView?.CSS?.highlights?.get('r3-audio-reading-v34');
      highlightText = highlight ? [...highlight].map((item) => item.toString()).join(' ') : '';
    } catch {}
    return {
      mapped,
      followDelta: Number(window.__r3AudioContinuityV34.exactFollowCalls || 0) - beforeFollow,
      highlightText,
      legacyCount: doc?.querySelectorAll?.('[data-r3-audio-reading-v11]')?.length || 0,
    };
  });
  if (range.mapped < 20) throw new Error(`MAPPING_TOO_LOW_${range.mapped}`);
  if (range.followDelta < 1) throw new Error('EXACT_RANGE_FOLLOW_NOT_CALLED');
  if (range.highlightText.length > 120) throw new Error(`HIGHLIGHT_TOO_LONG_${range.highlightText.length}`);
  if (range.legacyCount !== 0) throw new Error(`LEGACY_BLOCK_HIGHLIGHT_${range.legacyCount}`);
  if (pageErrors.length) throw new Error(`PAGE_ERRORS:${pageErrors.join(' | ')}`);

  console.log(JSON.stringify({
    ok: true,
    runtime: headers['x-r3-reader-runtime'],
    singleAudioListenerOwner: true,
    listenerAudit,
    readableStep: readable.step,
    readableHref: readable.state.href,
    peekNonMutating: true,
    nextTextLength: peek.payload.textLength,
    prefetchReady: true,
    prefetchNetworkPosts: postsBeforeHandoff,
    handoffCacheHit: true,
    handoffExtraNetworkPosts: audioPostCount - postsBeforeHandoff,
    rangeMappedWords: range.mapped,
    exactRangeFollow: true,
    shortHighlightChars: range.highlightText.length,
    legacyBlockHighlightCount: range.legacyCount,
    epubProxyStatus,
    epubProxyBytes,
    pageErrors,
  }));
  console.log('READER_AUDIO_V35_PREVIEW_E2E=PASS');
} finally {
  await context.close();
  await browser.close();
}
