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
page.on('pageerror', (error) => pageErrors.push(String(error?.message || error)));

await page.route('**/__reader_v34_epub_proxy__', async (route) => {
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
      data.delivery.url = `${base}/__reader_v34_epub_proxy__`;
      body = JSON.stringify(data);
    }
  } catch {}
  await route.fulfill({
    status: upstream.status(),
    headers: { 'content-type': 'application/json', 'cache-control': 'private, no-store' },
    body,
  });
});

async function readerDiag() {
  return page.evaluate(() => ({
    v34: Boolean(window.__r3AudioContinuityV34),
    bridge: Boolean(window.r3ReaderBridge),
    current: window.r3ReaderBridge?.current?.() || null,
    core: Boolean(window.__r3AudioCoreProductionV33),
    coreBootError: window.__r3AudioCoreV33BootError || '',
    loading: { text: document.getElementById('loading')?.textContent || '', hidden: document.getElementById('loading')?.classList.contains('hidden') || false },
    frames: [...document.querySelectorAll('#viewer iframe')].map((frame) => {
      try {
        return { src: frame.getAttribute('src') || '', readyState: frame.contentDocument?.readyState || '', textLength: String(frame.contentDocument?.body?.innerText || '').trim().length, title: frame.contentDocument?.title || '' };
      } catch { return { src: frame.getAttribute('src') || '', inaccessible: true }; }
    }),
    bodyText: String(document.body?.innerText || '').slice(0, 320),
  }));
}

try {
  const response = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  if (!response || response.status() !== 200) throw new Error(`READER_HTTP_${response?.status()}`);
  const headers = await response.allHeaders();
  if (headers['x-r3-reader-runtime'] !== 'v34-continuous-range-sync') throw new Error(`RUNTIME_${headers['x-r3-reader-runtime'] || 'missing'}`);
  if (headers['x-r3-reader-patch-proof'] !== 'v33+v34:ahead-prefetch+range-follow+manual-sync') throw new Error('PROOF_MISMATCH');

  try {
    await page.waitForFunction(() => Boolean(window.__r3AudioContinuityV34 && window.r3ReaderBridge?.current?.()?.start), null, { timeout: 20000 });
  } catch (error) {
    console.log('V34_BOOT_DIAG', JSON.stringify({ diag: await readerDiag(), signedEpubUrl: Boolean(signedEpubUrl), epubProxyStatus, epubProxyBytes, pageErrors }));
    throw error;
  }

  const readable = await page.evaluate(async () => {
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const inspect = () => {
      const frames = [...document.querySelectorAll('#viewer iframe')];
      let best = null;
      for (const frame of frames) {
        try {
          const text = String(frame.contentDocument?.body?.innerText || '').trim();
          if (!best || text.length > best.textLength) best = { textLength: text.length, src: frame.getAttribute('src') || '', title: frame.contentDocument?.title || '' };
        } catch {}
      }
      const loc = window.r3ReaderBridge?.current?.();
      return { best, href: loc?.start?.href || '', cfi: loc?.start?.cfi || '' };
    };
    const visited = [];
    for (let step = 0; step < 36; step++) {
      const state = inspect();
      visited.push({ step, href: state.href, textLength: state.best?.textLength || 0 });
      if ((state.best?.textLength || 0) >= 80) return { ok: true, step, state, visited };
      if (!window.r3ReaderBridge?.next) break;
      const before = `${state.href}|${state.cfi}`;
      try { await Promise.race([Promise.resolve(window.r3ReaderBridge.next()), sleep(1200)]); } catch {}
      for (let n = 0; n < 12; n++) {
        await sleep(100);
        const after = inspect();
        if (`${after.href}|${after.cfi}` !== before || (after.best?.textLength || 0) >= 80) break;
      }
    }
    return { ok: false, state: inspect(), visited };
  });
  if (!readable.ok) {
    console.log('V34_READABLE_DIAG', JSON.stringify({ readable, diag: await readerDiag(), epubProxyStatus, epubProxyBytes, pageErrors }));
    throw new Error('READABLE_SECTION_NOT_FOUND');
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

  const synthetic = await page.evaluate(async () => {
    const frame = [...document.querySelectorAll('#viewer iframe')].find((candidate) => {
      try { return String(candidate.contentDocument?.body?.innerText || '').trim().length >= 80; } catch { return false; }
    });
    const text = String(frame?.contentDocument?.body?.innerText || '');
    const words = text.match(/[\p{L}\p{M}\p{N}]+/gu) || [];
    const timing = words.slice(0, 220).map((word, index) => ({ text: word, startMs: index * 120, durationMs: 100 }));
    const mapped = window.__r3AudioContinuityV34.installTestTiming(timing);
    const beforeFollow = window.__r3AudioContinuityV34.exactFollowCalls;
    const targetIndex = Math.max(0, timing.length - 12);
    await window.__r3AudioContinuityV34.syncTestWord(targetIndex, true);
    await new Promise((resolve) => setTimeout(resolve, 180));
    const doc = frame?.contentDocument;
    let highlightText = '';
    try {
      const highlight = doc?.defaultView?.CSS?.highlights?.get('r3-audio-reading-v34');
      highlightText = highlight ? [...highlight].map((range) => range.toString()).join(' ') : '';
    } catch {}
    const legacyCount = doc?.querySelectorAll?.('[data-r3-audio-reading-v11]')?.length || 0;
    return { mapped, timingCount: timing.length, followDelta: window.__r3AudioContinuityV34.exactFollowCalls - beforeFollow, highlightText, legacyCount };
  });
  if (synthetic.mapped < 20) throw new Error(`MAPPING_TOO_LOW_${synthetic.mapped}`);
  if (synthetic.followDelta < 1) throw new Error('EXACT_RANGE_FOLLOW_NOT_CALLED');
  if (synthetic.highlightText.length > 120) throw new Error(`HIGHLIGHT_TOO_LONG_${synthetic.highlightText.length}`);
  if (synthetic.legacyCount !== 0) throw new Error(`LEGACY_BLOCK_HIGHLIGHT_${synthetic.legacyCount}`);

  const result = {
    ok: true,
    runtime: headers['x-r3-reader-runtime'],
    readableStep: readable.step,
    readableHref: readable.state.href,
    readableTextLength: readable.state.best?.textLength || 0,
    peekNonMutating: true,
    nextTextLength: peek.payload.textLength,
    rangeMappedWords: synthetic.mapped,
    exactRangeFollow: synthetic.followDelta >= 1,
    shortHighlightChars: synthetic.highlightText.length,
    legacyBlockHighlightCount: synthetic.legacyCount,
    epubProxyStatus,
    epubProxyBytes,
    pageErrors,
  };
  if (pageErrors.length) throw new Error(`PAGE_ERRORS:${pageErrors.join(' | ')}`);
  console.log(JSON.stringify(result));
  console.log('READER_AUDIO_V34_PREVIEW_E2E=PASS');
} finally {
  await context.close();
  await browser.close();
}
