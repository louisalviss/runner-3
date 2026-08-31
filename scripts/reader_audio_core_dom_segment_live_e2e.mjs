import fs from 'node:fs';
import { chromium } from 'playwright';

const CORE_URL = process.env.RUNNER3_CORE_URL || 'https://runner3-core.ducduy2411.workers.dev';
const BOOK_KEY = process.env.EBOOK_BROWSER_SMOKE_BOOK_KEY || 'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub';
const BUNDLE_PATH = process.argv[2] || '/tmp/reader-audio-core-e2e.js';
const readerUrl = `${CORE_URL}/artifact-library/read?key=${encodeURIComponent(BOOK_KEY)}`;
const bundle = fs.readFileSync(BUNDLE_PATH, 'utf8');

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

try {
  const response = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const runtime = response?.headers()?.['x-r3-reader-runtime'] || '';
  await page.waitForSelector('#viewer iframe', { timeout: 30000 });
  await page.waitForFunction(() => Boolean(window.r3ReaderBridge?.cfiFromNode && window.r3ReaderBridge?.next && window.r3ReaderBridge?.prev), null, { timeout: 30000 });
  await page.waitForFunction(() => window.__r3AudioHighSpeedFollowV31 === true, null, { timeout: 10000 });
  if (runtime && runtime !== 'v31-high-speed-serialized-follow') throw new Error(`LIVE_RUNTIME_NOT_V31:${runtime}`);

  await page.addScriptTag({ content: bundle });
  const result = await page.evaluate(async () => {
    const { DomSegmentBuilder, PositionMapper, ReaderFollower, tokenizeReaderText } = window.R3AudioCoreE2E || {};
    if (!DomSegmentBuilder || !PositionMapper || !ReaderFollower || !tokenizeReaderText) throw new Error('DOM_SEGMENT_EXPORTS_MISSING');

    const frames = [...document.querySelectorAll('#viewer iframe')];
    let payload = null;
    for (const frame of frames) {
      try {
        const doc = frame.contentDocument;
        const text = String(doc?.body?.innerText || '').trim();
        if (text.length < 100) continue;
        if (!payload || text.length > payload.text.length) payload = { frame, doc, text };
      } catch {}
    }
    if (!payload) throw new Error('NO_READER_FRAME_PAYLOAD');

    let blocks = [...payload.doc.querySelectorAll('p,li,h1,h2,h3,h4,h5,h6,blockquote')]
      .filter((el) => String(el.innerText || el.textContent || '').trim());
    blocks = blocks.filter((el) => String(el.tagName || '').toUpperCase() !== 'BLOCKQUOTE' || !el.querySelector('p,li,h1,h2,h3,h4,h5,h6'));
    if (!blocks.length) blocks = [...payload.doc.body.children].filter((el) => String(el.innerText || el.textContent || '').trim());
    if (blocks.length < 8) throw new Error(`TOO_FEW_READER_BLOCKS:${blocks.length}`);

    const timingWords = [];
    let cursorMs = 0;
    for (const block of blocks) {
      for (const token of tokenizeReaderText(block.innerText || block.textContent || '')) {
        timingWords.push({ text: token, startMs: cursorMs, durationMs: 35 });
        cursorMs += 50;
      }
    }
    if (timingWords.length < 120) throw new Error(`TOO_FEW_TIMING_WORDS:${timingWords.length}`);

    const builder = new DomSegmentBuilder({ lookahead: 18, minCoverage: 0.95 });
    const build = () => builder.build({ timingWords, blocks, cfiFromNode: (node) => window.r3ReaderBridge.cfiFromNode(node) });
    const first = build();
    const second = build();
    if (first.segments.length < 8) throw new Error(`TOO_FEW_SEGMENTS:${first.segments.length}`);
    if (first.coverage < 0.95) throw new Error(`LOW_ALIGNMENT_COVERAGE:${first.coverage}`);
    const signature = (x) => x.segments.map((s) => `${s.start.toFixed(3)}|${s.cfi}|${s.token}`).join('\n');
    if (signature(first) !== signature(second)) throw new Error('NON_DETERMINISTIC_DOM_SEGMENTS');

    const visible = (node) => {
      try {
        const doc = node.ownerDocument;
        const win = doc.defaultView;
        const width = win?.innerWidth || doc.documentElement.clientWidth || 1;
        const height = win?.innerHeight || doc.documentElement.clientHeight || 1;
        return [...node.getClientRects()].some((rect) => rect.right > 2 && rect.left < width - 2 && rect.bottom > 2 && rect.top < height - 2);
      } catch { return false; }
    };
    const mappedRows = first.rows.filter((row) => row.cfi && first.nodeByCfi.has(row.cfi));
    const rowIndex = new Map(mappedRows.map((row, i) => [row.cfi, i]));
    const currentVisibleIndex = () => {
      for (let i = 0; i < mappedRows.length; i++) if (visible(mappedRows[i].node)) return i;
      return 0;
    };
    let targetRow = mappedRows.find((row, i) => i > currentVisibleIndex() + 4 && !visible(row.node));
    if (!targetRow) targetRow = mappedRows.at(-1);
    if (!targetRow?.cfi) throw new Error('NO_OFFSCREEN_MAPPED_TARGET');

    let concurrent = 0;
    let maxConcurrent = 0;
    let displayCalls = 0;
    const displayCfi = async (cfi, options = {}) => {
      if (options?.animate !== false) throw new Error('AUTO_FOLLOW_ANIMATION_ENABLED');
      const node = first.nodeByCfi.get(cfi);
      if (!node) throw new Error(`TARGET_NODE_MISSING:${cfi}`);
      displayCalls++;
      concurrent++;
      maxConcurrent = Math.max(maxConcurrent, concurrent);
      try {
        for (let attempt = 0; attempt < 60; attempt++) {
          if (visible(node)) return true;
          const targetIndex = rowIndex.get(cfi) ?? 0;
          const hereIndex = currentVisibleIndex();
          if (targetIndex >= hereIndex) await window.r3ReaderBridge.next();
          else await window.r3ReaderBridge.prev();
          await new Promise((resolve) => setTimeout(resolve, 90));
        }
        throw new Error(`TARGET_NOT_VISIBLE_AFTER_NAV:${cfi}`);
      } finally {
        concurrent--;
      }
    };

    let activeNode = null;
    const follower = new ReaderFollower({
      displayCfi,
      isVisible: async (target) => visible(first.nodeByCfi.get(target.cfi)),
      clearHighlight: () => {
        if (activeNode) activeNode.removeAttribute('data-r3-audio-core-dom-e2e');
        activeNode = null;
      },
      highlight: (target) => {
        activeNode = first.nodeByCfi.get(target.cfi) || null;
        if (activeNode) activeNode.setAttribute('data-r3-audio-core-dom-e2e', '1');
      },
    });
    const mapper = new PositionMapper(first.segments);
    const targetSegment = first.segments.find((segment) => segment.cfi === targetRow.cfi);
    if (!targetSegment) throw new Error('TARGET_SEGMENT_MISSING');
    const mapped = mapper.at(targetSegment.start + 0.001);
    if (!mapped || mapped.cfi !== targetRow.cfi) throw new Error(`MAPPER_TARGET_MISMATCH:${mapped?.cfi || ''}`);
    await follower.follow(mapped, { force: true });
    await new Promise((resolve) => setTimeout(resolve, 120));

    return {
      coverage: first.coverage,
      segmentCount: first.segments.length,
      timingWordCount: timingWords.length,
      deterministic: signature(first) === signature(second),
      mappedCfi: mapped.cfi,
      targetVisible: visible(targetRow.node),
      highlighted: targetRow.node.getAttribute('data-r3-audio-core-dom-e2e') === '1',
      displayCalls,
      maxConcurrent,
      animateFalse: true,
    };
  });

  if (!result.deterministic || result.coverage < 0.95) throw new Error(`DOM_SEGMENT_BUILD_BAD:${JSON.stringify(result)}`);
  if (!result.targetVisible || !result.highlighted) throw new Error(`DOM_SEGMENT_FOLLOW_BAD:${JSON.stringify(result)}`);
  if (result.maxConcurrent !== 1) throw new Error(`DOM_SEGMENT_FOLLOW_OVERLAP:${JSON.stringify(result)}`);
  console.log(JSON.stringify({ phase: 'reader-audio-core-dom-segment-live-e2e', ok: true, runtime: runtime || 'v31-high-speed-serialized-follow', ...result, productionMutation: false }));
  console.log('READER_AUDIO_CORE_DOM_SEGMENT_LIVE_E2E=PASS');
} finally {
  await browser.close();
}
