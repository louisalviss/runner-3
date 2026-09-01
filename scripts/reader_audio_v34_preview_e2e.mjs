import { chromium } from 'playwright';

const base = process.env.PREVIEW_URL;
const bookKey = process.env.EBOOK_BROWSER_SMOKE_BOOK_KEY || 'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub';
if (!base) throw new Error('PREVIEW_URL_REQUIRED');

const readerUrl = `${base}/artifact-library/read?key=${encodeURIComponent(bookKey)}`;
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 390, height: 760 } });
const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', (error) => pageErrors.push(String(error?.message || error)));

try {
  const response = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  if (!response || response.status() !== 200) throw new Error(`READER_HTTP_${response?.status()}`);
  const headers = await response.allHeaders();
  if (headers['x-r3-reader-runtime'] !== 'v34-continuous-range-sync') throw new Error(`RUNTIME_${headers['x-r3-reader-runtime'] || 'missing'}`);
  if (headers['x-r3-reader-patch-proof'] !== 'v33+v34:ahead-prefetch+range-follow+manual-sync') throw new Error('PROOF_MISMATCH');

  await page.waitForFunction(() => Boolean(window.__r3AudioContinuityV34 && window.r3ReaderBridge?.current?.()?.start), null, { timeout: 20000 });
  await page.waitForFunction(() => {
    const frames = [...document.querySelectorAll('#viewer iframe')];
    return frames.some((frame) => {
      try { return String(frame.contentDocument?.body?.innerText || '').trim().length >= 80; } catch { return false; }
    });
  }, null, { timeout: 20000 });

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
    const beforeCfi = window.r3ReaderBridge.current()?.start?.cfi || '';
    const beforeFollow = window.__r3AudioContinuityV34.exactFollowCalls;
    const targetIndex = Math.max(0, timing.length - 12);
    await window.__r3AudioContinuityV34.syncTestWord(targetIndex, true);
    await new Promise((resolve) => setTimeout(resolve, 180));
    const afterCfi = window.r3ReaderBridge.current()?.start?.cfi || '';
    const doc = frame?.contentDocument;
    let highlightText = '';
    try {
      const highlight = doc?.defaultView?.CSS?.highlights?.get('r3-audio-reading-v34');
      highlightText = highlight ? [...highlight].map((range) => range.toString()).join(' ') : '';
    } catch {}
    const legacyCount = doc?.querySelectorAll?.('[data-r3-audio-reading-v11]')?.length || 0;
    return { mapped, timingCount: timing.length, beforeCfi, afterCfi, followDelta: window.__r3AudioContinuityV34.exactFollowCalls - beforeFollow, highlightText, legacyCount };
  });
  if (synthetic.mapped < 20) throw new Error(`MAPPING_TOO_LOW_${synthetic.mapped}`);
  if (synthetic.followDelta < 1) throw new Error('EXACT_RANGE_FOLLOW_NOT_CALLED');
  if (synthetic.highlightText.length > 120) throw new Error(`HIGHLIGHT_TOO_LONG_${synthetic.highlightText.length}`);
  if (synthetic.legacyCount !== 0) throw new Error(`LEGACY_BLOCK_HIGHLIGHT_${synthetic.legacyCount}`);

  const result = {
    ok: true,
    runtime: headers['x-r3-reader-runtime'],
    peekNonMutating: true,
    nextTextLength: peek.payload.textLength,
    rangeMappedWords: synthetic.mapped,
    exactRangeFollow: synthetic.followDelta >= 1,
    shortHighlightChars: synthetic.highlightText.length,
    legacyBlockHighlightCount: synthetic.legacyCount,
    pageErrors,
  };
  if (pageErrors.length) throw new Error(`PAGE_ERRORS:${pageErrors.join(' | ')}`);
  console.log(JSON.stringify(result));
  console.log('READER_AUDIO_V34_PREVIEW_E2E=PASS');
} finally {
  await context.close();
  await browser.close();
}
