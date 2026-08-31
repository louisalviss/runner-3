import { chromium } from 'playwright';

const CORE_URL = process.env.RUNNER3_CORE_URL || 'https://runner3-core.ducduy2411.workers.dev';
const BOOK_KEY = process.env.EBOOK_BROWSER_SMOKE_BOOK_KEY || 'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub';
const TEST_ID = 'seek-smoke-v32';
const STEP_MS = 50;
const readerUrl = `${CORE_URL}/artifact-library/read?key=${encodeURIComponent(BOOK_KEY)}`;

function tokensOf(value) {
  const text = String(value || '').normalize('NFKC').toLocaleLowerCase('vi-VN');
  try { return text.match(/[\p{L}\p{M}\p{N}]+/gu) || []; }
  catch { return text.split(/[^A-Za-z0-9À-ỹ]+/).filter(Boolean); }
}

function makeSilentWav(seconds) {
  const sampleRate = 8000;
  const samples = Math.max(sampleRate, Math.ceil(seconds * sampleRate));
  const out = Buffer.alloc(44 + samples, 128);
  out.write('RIFF', 0, 'ascii'); out.writeUInt32LE(36 + samples, 4); out.write('WAVE', 8, 'ascii');
  out.write('fmt ', 12, 'ascii'); out.writeUInt32LE(16, 16); out.writeUInt16LE(1, 20); out.writeUInt16LE(1, 22);
  out.writeUInt32LE(sampleRate, 24); out.writeUInt32LE(sampleRate, 28); out.writeUInt16LE(1, 32); out.writeUInt16LE(8, 34);
  out.write('data', 36, 'ascii'); out.writeUInt32LE(samples, 40);
  return out;
}

function audioRangeResponse(req, body) {
  const total = body.length;
  const range = String(req.headers()['range'] || '');
  const baseHeaders = { 'content-type': 'audio/wav', 'accept-ranges': 'bytes', 'cache-control': 'no-store' };
  if (!range) return { status: 200, headers: { ...baseHeaders, 'content-length': String(total) }, body };
  const match = /^bytes=(\d*)-(\d*)$/i.exec(range.trim());
  if (!match) return { status: 416, headers: { ...baseHeaders, 'content-range': `bytes */${total}` }, body: Buffer.alloc(0) };
  let start = match[1] ? Number(match[1]) : NaN;
  let end = match[2] ? Number(match[2]) : NaN;
  if (!Number.isFinite(start) && Number.isFinite(end)) {
    const suffix = Math.max(0, Math.min(total, end));
    start = total - suffix;
    end = total - 1;
  } else {
    if (!Number.isFinite(start)) start = 0;
    if (!Number.isFinite(end)) end = total - 1;
  }
  start = Math.max(0, Math.min(total - 1, start));
  end = Math.max(start, Math.min(total - 1, end));
  const chunk = body.subarray(start, end + 1);
  return {
    status: 206,
    headers: { ...baseHeaders, 'content-range': `bytes ${start}-${end}/${total}`, 'content-length': String(chunk.length) },
    body: chunk,
  };
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const errors = [];
page.on('pageerror', e => errors.push(String(e?.stack || e)));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

let words = [];
let wav = makeSilentWav(60);
let syntheticReady = false;
let postCount = 0;
let mediaGetCount = 0;
let mediaRangeCount = 0;
const posts = [];
const mediaUrl = `${CORE_URL}/artifact-library/api/audio/${TEST_ID}/media`;
const timingUrl = `${CORE_URL}/artifact-library/api/audio/${TEST_ID}/timing`;
const state = () => ({ ok: true, id: TEST_ID, status: 'ready', mediaUrl, timingUrl, durationSeconds: Math.max(0, (wav.length - 44) / 8000), error: null });

await page.route('**/*', async route => {
  if (!syntheticReady) return route.continue();
  const req = route.request();
  let u;
  try { u = new URL(req.url()); } catch { return route.continue(); }
  if (u.origin === new URL(CORE_URL).origin && u.pathname === '/artifact-library/audio') {
    if (req.method() === 'POST') {
      postCount++;
      let payload = {};
      try { payload = JSON.parse(req.postData() || '{}'); } catch {}
      const tokens = tokensOf(payload.text || '');
      words = tokens.map((text, index) => ({ text, startMs: index * STEP_MS, durationMs: 35 }));
      const duration = Math.max(20, words.length * STEP_MS / 1000 + 2);
      wav = makeSilentWav(duration);
      posts.push({ chapterTitle: String(payload.chapterTitle || ''), chapterHref: String(payload.chapterHref || ''), textLength: String(payload.text || '').length, tokenCount: tokens.length });
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(state()) });
    }
    if (req.method() === 'GET' && u.searchParams.get('id') === TEST_ID) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(state()) });
    }
  }
  if (u.href === timingUrl) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ words }) });
  if (u.href === mediaUrl) {
    mediaGetCount++;
    if (req.headers()['range']) mediaRangeCount++;
    return route.fulfill(audioRangeResponse(req, wav));
  }
  return route.continue();
});

async function boot() {
  await page.waitForSelector('#r3AudioMain', { timeout: 30000 });
  await page.waitForSelector('#viewer iframe', { timeout: 30000 });
  await page.waitForFunction(() => Boolean(window.r3ReaderBridge), null, { timeout: 30000 });
}

async function snapshot() {
  return page.evaluate(() => {
    const frames = [...document.querySelectorAll('#viewer iframe')];
    let best = null;
    for (const frame of frames) {
      try {
        const doc = frame.contentDocument;
        const text = String(doc?.body?.innerText || '').trim();
        if (!best || text.length > best.text.length) best = { frame, doc, text };
      } catch {}
    }
    const text = best?.text || '';
    const signature = text ? `${text.length}|${text.slice(0,180)}|${text.slice(-180)}` : '';
    const tokens = (() => {
      try { return text.normalize('NFKC').toLocaleLowerCase('vi-VN').match(/[\p{L}\p{M}\p{N}]+/gu) || []; }
      catch { return []; }
    })();
    let visibleTokenOrdinal = -1;
    if (best?.doc?.body && tokens.length) {
      const doc = best.doc;
      const frameRect = best.frame.getBoundingClientRect();
      const viewerRect = document.getElementById('viewer')?.getBoundingClientRect() || { left:0, top:0, right:innerWidth, bottom:innerHeight };
      const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
      const re = /[\p{L}\p{M}\p{N}]+/gu;
      let node, ordinal = 0, found = false;
      while (!found && (node = walker.nextNode())) {
        const raw = String(node.nodeValue || '');
        re.lastIndex = 0;
        let m;
        while ((m = re.exec(raw))) {
          const range = doc.createRange();
          range.setStart(node, m.index); range.setEnd(node, m.index + m[0].length);
          const visible = [...range.getClientRects()].some(r => {
            const left = frameRect.left + r.left, right = frameRect.left + r.right;
            const top = frameRect.top + r.top, bottom = frameRect.top + r.bottom;
            return right > viewerRect.left + 2 && left < viewerRect.right - 2 && bottom > viewerRect.top + 2 && top < viewerRect.bottom - 2;
          });
          if (visible) { visibleTokenOrdinal = ordinal; found = true; break; }
          ordinal++;
        }
      }
    }
    const loc = window.r3ReaderBridge?.current?.();
    const audio = document.getElementById('r3AudioElement');
    return {
      textLength: text.length,
      signature,
      tokenCount: tokens.length,
      visibleTokenOrdinal,
      href: loc?.start?.href || '',
      cfi: loc?.start?.cfi || '',
      paused: Boolean(audio?.paused),
      ended: Boolean(audio?.ended),
      currentTime: Number(audio?.currentTime || 0),
      duration: Number(audio?.duration || 0),
      status: String(document.getElementById('r3AudioStatus')?.textContent || ''),
      title: String(document.getElementById('r3AudioTitle')?.textContent || ''),
      debug: window.__r3AudioAutoNextV32Debug || null,
    };
  });
}

try {
  const nav = await page.goto(readerUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await boot();
  const runtime = nav?.headers()?.['x-r3-reader-runtime'] || '';
  if (!runtime.includes('v32')) throw new Error(`live Reader is not v32: ${runtime || 'missing header'}`);
  await page.waitForFunction(() => window.__r3AudioAutoNextChapterV32 === true && window.__r3AudioHighSpeedFollowV31 === true, null, { timeout: 10000 });

  let candidate = null;
  for (let n = 0; n < 180; n++) {
    const snap = await snapshot();
    if (n < 10 || n % 25 === 0) console.log(JSON.stringify({ phase:'scan', n, href:snap.href, cfi:snap.cfi, textLength:snap.textLength, tokenCount:snap.tokenCount, visibleTokenOrdinal:snap.visibleTokenOrdinal }));
    if (snap.textLength > 1000 && snap.tokenCount > 300) { candidate = snap; break; }
    await page.evaluate(async () => { if (window.r3ReaderBridge?.next) await window.r3ReaderBridge.next(); });
    await page.waitForTimeout(180);
  }
  if (!candidate) throw new Error('no readable long spine found');

  syntheticReady = true;
  await page.locator('#r3AudioMain').click();
  await page.waitForFunction(() => {
    const a=document.getElementById('r3AudioElement');
    return Boolean(a?.src) && !a.paused && Number.isFinite(a.duration) && a.duration > 1;
  }, null, { timeout: 10000 });
  await page.waitForTimeout(350);
  const started = await snapshot();
  if (postCount !== 1) throw new Error(`initial audio POST count unexpected: ${postCount}`);
  console.log(JSON.stringify({ phase:'started-v32', runtime, postCount, started, firstPost:posts[0] || null }));

  await page.evaluate(() => {
    const a=document.getElementById('r3AudioElement');
    a.pause();
    const target=Math.max(0,(Number(a.duration)||0)-0.08);
    a.currentTime=target;
    a.dispatchEvent(new Event('seeked'));
    a.dispatchEvent(new Event('timeupdate'));
  });

  let endAligned = null;
  for (let n=0;n<30;n++) {
    const snap=await snapshot();
    if (snap.tokenCount > 0 && snap.visibleTokenOrdinal >= Math.max(0, snap.tokenCount - 350)) { endAligned=snap; break; }
    await page.waitForTimeout(180);
  }
  if (!endAligned) throw new Error(`could not align Reader near end of current spine: ${JSON.stringify(await snapshot())}`);
  console.log(JSON.stringify({ phase:'end-aligned-v32', href:endAligned.href, cfi:endAligned.cfi, visibleTokenOrdinal:endAligned.visibleTokenOrdinal, tokenCount:endAligned.tokenCount, currentTime:endAligned.currentTime, duration:endAligned.duration }));

  const before = await snapshot();
  await page.evaluate(() => document.getElementById('r3AudioElement')?.dispatchEvent(new Event('ended')));
  await page.waitForFunction(() => window.__r3AudioAutoNextV32Debug?.runs >= 1, null, { timeout: 5000 });
  await page.waitForFunction(() => {
    const d=window.__r3AudioAutoNextV32Debug;
    return Boolean(d && (d.ok || d.reason === 'book-end-or-no-readable-next' || d.reason === 'prepare-next-failed' || d.reason === 'exception'));
  }, null, { timeout: 12000 });
  await page.waitForTimeout(500);

  const after = await snapshot();
  const debug = after.debug;
  console.log(JSON.stringify({ phase:'auto-next-v32', before:{signature:before.signature,href:before.href,cfi:before.cfi}, after, debug, postCount, posts, mediaGetCount, mediaRangeCount }));

  if (!debug?.ok || !debug?.prepared) throw new Error(`auto-next did not prepare next readable spine: ${JSON.stringify(debug)}`);
  if (debug.runs !== 1) throw new Error(`auto-next ran unexpected number of times: ${JSON.stringify(debug)}`);
  if (debug.moves < 1) throw new Error(`auto-next did not move Reader: ${JSON.stringify(debug)}`);
  if (!after.signature || after.signature === before.signature) throw new Error('Reader signature did not change after auto-next');
  if (!after.href || after.href === before.href) throw new Error(`Reader href did not advance: before=${before.href} after=${after.href}`);
  if (postCount !== 2) throw new Error(`auto-next audio POST count expected 2, got ${postCount}`);
  if (after.paused) throw new Error(`next chapter did not autoplay: ${JSON.stringify(after)}`);
  if (/Chưa lấy được nội dung chương/i.test(after.status)) throw new Error(`stale no-content status after auto-next: ${after.status}`);
  if (!/đang phát/i.test(after.status)) throw new Error(`unexpected auto-next status: ${after.status}`);
  if (posts.length !== 2 || posts[1].textLength < 80 || posts[1].tokenCount < 5) throw new Error(`next POST was not readable content: ${JSON.stringify(posts)}`);

  console.log(JSON.stringify({ phase:'auto-next-proof', ok:true, runtime, moves:debug.moves, postCount, fromHref:before.href, toHref:after.href, autoplay:!after.paused, skippedSparse:true, v31Preserved:true }));
  if (errors.length) throw new Error(`browser errors: ${JSON.stringify(errors.slice(0,5))}`);
} finally {
  await browser.close();
}
