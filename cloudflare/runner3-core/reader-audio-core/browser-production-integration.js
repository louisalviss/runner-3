import { ReaderAudioAdapter } from './reader-audio-adapter.js';
import { normalizePlaybackState } from './state-contract.js';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function bootReaderAudioCore() {
  if (typeof window === 'undefined' || !window.__R3_READER_AUDIO_CORE_OWNER || window.__r3AudioCoreProductionV33) return;
  window.__r3AudioCoreProductionV33 = true;

  const params = new URLSearchParams(location.search);
  const bookKey = params.get('key') || '';
  if (!bookKey) return;

  const audio = document.getElementById('r3AudioElement');
  const main = document.getElementById('r3AudioMain');
  const back = document.getElementById('r3AudioBack');
  const forward = document.getElementById('r3AudioForward');
  const speed = document.getElementById('r3AudioSpeed');
  const expand = document.getElementById('r3AudioExpand');
  const seek = document.getElementById('r3AudioSeek');
  const current = document.getElementById('r3AudioCurrent');
  const duration = document.getElementById('r3AudioDuration');
  const title = document.getElementById('r3AudioTitle');
  const status = document.getElementById('r3AudioStatus');
  const dock = document.getElementById('r3AudioDock');
  if (!audio || !main || !status) return;

  const STATE_KEY = `r3-reader-audio-core-v1:${bookKey}`;
  const LEGACY_KEY = `r3-reader-audio-state-v11:${bookKey}`;
  const READER_POSITION_KEY = `r3-reader-position:${bookKey}`;
  const rates = [0.75, 1, 1.25, 1.5, 1.75, 2, 2.25, 2.5, 2.75, 3];
  const debug = window.__r3AudioCoreV33Debug = {
    owner: 'reader-audio-core-v33',
    legacy: { v6: Boolean(window.__r3AudioLegacyV6Suppressed), v8: Boolean(window.__r3AudioLegacyV8Suppressed), v11: Boolean(window.__r3AudioLegacyV11Suppressed), v29: Boolean(window.__r3AudioLegacyV29Suppressed), v31Clock: Boolean(window.__r3AudioLegacyV31ClockSuppressed) },
    prepares: 0,
    advances: 0,
    displayCalls: 0,
    maxDisplayConcurrent: 0,
    displayConcurrent: 0,
    lastError: '',
    iosFirstPlayFix: 'v70',
    currentChapterPrewarm: true,
    blockingWarmAhead: false,
    stateKey: STATE_KEY,
  };

  let adapter = null;
  let busy = false;
  let seeking = false;
  let activeBlock = null;
  let mappedElements = new Map();
  let currentPayload = null;
  let currentTiming = [];

  const bridge = () => window.r3ReaderBridge || null;
  const warmAhead = async (waitMs = 0) => {
    try {
      const prime = window.__r3AudioContinuityV34?.primePrefetch;
      if (typeof prime !== 'function') return null;
      const task = Promise.resolve(prime());
      if (!(Number(waitMs) > 0)) { task.catch(() => {}); return null; }
      return await Promise.race([task, sleep(Math.max(0, Number(waitMs) || 0)).then(() => null)]);
    } catch { return null; }
  };
  const setStatus = (text) => { status.textContent = String(text || 'Nam Minh').slice(0, 120); };
  const setTitle = (text) => { if (title) title.textContent = String(text || 'Chương hiện tại').slice(0, 120); };
  const formatTime = (value) => {
    const seconds = Math.max(0, Number(value) || 0);
    if (!Number.isFinite(seconds)) return '--:--';
    const whole = Math.floor(seconds);
    const h = Math.floor(whole / 3600);
    const m = Math.floor((whole % 3600) / 60);
    const s = whole % 60;
    return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
  };
  const setMain = (mode) => {
    if (mode === 'loading') {
      main.textContent = '…';
      main.disabled = true;
      main.setAttribute('aria-label', 'Đang chuẩn bị audio');
      return;
    }
    main.disabled = false;
    if (mode === 'pause') {
      main.textContent = 'Ⅱ';
      main.setAttribute('aria-label', 'Tạm dừng audio');
    } else {
      main.textContent = '▶';
      main.setAttribute('aria-label', 'Phát audio');
    }
  };
  const syncTimeline = () => {
    const total = Number(audio.duration);
    const now = Number(audio.currentTime) || 0;
    if (current) current.textContent = formatTime(now);
    if (duration) duration.textContent = Number.isFinite(total) && total > 0 ? formatTime(total) : '--:--';
    if (seek) {
      if (!seeking) seek.value = Number.isFinite(total) && total > 0 ? String(Math.max(0, Math.min(1000, Math.round(now / total * 1000)))) : '0';
      seek.disabled = !(Number.isFinite(total) && total > 0);
    }
  };
  const syncUi = (state = adapter?.snapshot?.() || loadState()) => {
    const normalized = normalizePlaybackState(state || {});
    if (speed) speed.textContent = `${normalized.playbackRate}×`;
    setMain(!audio.paused && !audio.ended ? 'pause' : 'play');
    syncTimeline();
  };

  function loadState() {
    try {
      const canonical = JSON.parse(localStorage.getItem(STATE_KEY) || 'null');
      if (canonical && typeof canonical === 'object') return normalizePlaybackState(canonical);
    } catch {}
    try {
      const legacy = JSON.parse(localStorage.getItem(LEGACY_KEY) || 'null');
      if (legacy && typeof legacy === 'object') {
        const migrated = normalizePlaybackState({
          bookKey,
          chapter: '',
          mediaId: legacy.id || '',
          time: legacy.time,
          cfi: legacy.cfi || '',
          playbackRate: legacy.rate,
          playingIntent: false,
        });
        localStorage.setItem(STATE_KEY, JSON.stringify(migrated));
        return migrated;
      }
    } catch {}
    return normalizePlaybackState({ bookKey });
  }

  function saveState(state) {
    const normalized = normalizePlaybackState({ ...state, bookKey });
    try { localStorage.setItem(STATE_KEY, JSON.stringify(normalized)); } catch {}
    try { bridge()?.persist?.(); } catch {}
    syncUi(normalized);
  }

  function normalizeText(value) {
    return String(value || '').normalize('NFC').replace(/\r/g, '').replace(/\u00a0/g, ' ').replace(/[\u200b-\u200d\u2060\ufeff]/g, '').replace(/https?:\/\/\S+/g, '').replace(/\s+/g, ' ').trim();
  }

  function tokensOf(value) {
    const text = normalizeText(value).normalize('NFKC').toLocaleLowerCase('vi-VN');
    if (!text) return [];
    try { return text.match(/[\p{L}\p{M}\p{N}]+/gu) || []; } catch { return text.split(/[^A-Za-z0-9À-ỹ]+/).filter(Boolean); }
  }

  function framePayload() {
    const frames = [...document.querySelectorAll('#viewer iframe')];
    let best = null;
    for (const frame of frames) {
      try {
        const doc = frame.contentDocument;
        const body = doc?.body;
        const text = String(body?.innerText || '').trim();
        if (text.length < 80) continue;
        if (!best || text.length > best.text.length) {
          const heading = doc.querySelector('h1,h2,h3');
          best = { frame, doc, body, text, chapterTitle: String(heading?.textContent || doc.title || '').trim().slice(0, 240) };
        }
      } catch {}
    }
    if (!best) return null;
    const loc = bridge()?.current?.();
    best.chapterHref = String(loc?.start?.href || best.frame.getAttribute('src') || '').slice(0, 700);
    best.signature = `${best.text.length}|${best.text.slice(0, 180)}|${best.text.slice(-180)}`;
    best.chapter = best.chapterHref || best.signature;
    return best;
  }

  function collectBlocks(payload) {
    let blocks = [...payload.doc.querySelectorAll('p,li,h1,h2,h3,h4,h5,h6,blockquote')].filter((el) => normalizeText(el.innerText || el.textContent).length > 0);
    blocks = blocks.filter((el) => String(el.tagName || '').toUpperCase() !== 'BLOCKQUOTE' || !el.querySelector('p,li,h1,h2,h3,h4,h5,h6'));
    if (!blocks.length) blocks = [...payload.body.children].filter((el) => normalizeText(el.innerText || el.textContent).length > 0);
    if (!blocks.length) blocks = [payload.body];
    return blocks;
  }

  function blockVisible(el) {
    try {
      const doc = el?.ownerDocument;
      if (!doc) return false;
      const payload = framePayload();
      const frame = payload?.doc === doc ? payload.frame : null;
      const viewer = document.getElementById('viewer');
      return [...el.getClientRects()].some((rect) => {
        if (frame && viewer) {
          const fr = frame.getBoundingClientRect();
          const vr = viewer.getBoundingClientRect();
          const left = fr.left + rect.left;
          const top = fr.top + rect.top;
          const right = fr.left + rect.right;
          const bottom = fr.top + rect.bottom;
          return right > vr.left + 2 && left < vr.right - 2 && bottom > vr.top + 2 && top < vr.bottom - 2;
        }
        const win = doc.defaultView;
        const width = win?.innerWidth || doc.documentElement.clientWidth || 1;
        const height = win?.innerHeight || doc.documentElement.clientHeight || 1;
        return rect.right > 2 && rect.left < width - 2 && rect.bottom > 2 && rect.top < height - 2;
      });
    } catch { return false; }
  }

  function buildSegments(payload, timingWords) {
    mappedElements = new Map();
    const blocks = collectBlocks(payload);
    const ranges = blocks.map((el, index) => ({ el, index, first: null, last: null, matches: 0 }));
    const timingTokens = [];
    for (let wi = 0; wi < timingWords.length; wi++) {
      for (const token of tokensOf(timingWords[wi]?.text)) timingTokens.push({ token, wi });
    }
    const domTokens = [];
    for (let bi = 0; bi < blocks.length; bi++) {
      for (const token of tokensOf(blocks[bi].innerText || blocks[bi].textContent)) domTokens.push({ token, bi });
    }
    let ti = 0;
    let matched = 0;
    const LOOKAHEAD = 18;
    for (const row of domTokens) {
      if (ti >= timingTokens.length) break;
      let found = -1;
      if (timingTokens[ti].token === row.token) found = ti;
      else {
        const end = Math.min(timingTokens.length, ti + LOOKAHEAD + 1);
        for (let probe = ti + 1; probe < end; probe++) if (timingTokens[probe].token === row.token) { found = probe; break; }
      }
      if (found < 0) continue;
      const wi = timingTokens[found].wi;
      const range = ranges[row.bi];
      if (range.first === null) range.first = wi;
      range.last = wi;
      range.matches++;
      matched++;
      ti = found + 1;
    }
    const segments = [];
    for (const range of ranges) {
      if (range.first === null || range.last === null) continue;
      let cfi = '';
      try { cfi = String(bridge()?.cfiFromNode?.(range.el) || ''); } catch {}
      if (!cfi) continue;
      const first = timingWords[range.first] || {};
      const last = timingWords[range.last] || first;
      const start = Math.max(0, Number(first.startMs) || 0) / 1000;
      const end = Math.max(start, (Math.max(0, Number(last.startMs) || 0) + Math.max(20, Number(last.durationMs) || 20)) / 1000);
      segments.push({ index: segments.length, start, end, cfi, token: tokensOf(range.el.innerText || range.el.textContent)[0] || '' });
      mappedElements.set(cfi, range.el);
    }
    const visible = segments.find((segment) => blockVisible(mappedElements.get(segment.cfi))) || segments[0] || null;
    const coverage = matched / Math.max(1, Math.min(domTokens.length, timingTokens.length));
    return { segments, visible, coverage };
  }

  function rebuildCurrentMapping(expectedChapter = '') {
    try {
      if (!currentTiming.length) return null;
      const payload = framePayload();
      if (!payload) return null;
      if (expectedChapter && payload.chapter !== expectedChapter) return null;
      currentPayload = payload;
      const alignment = buildSegments(payload, currentTiming);
      return alignment.segments.length ? alignment : null;
    } catch { return null; }
  }

  async function readAudioState(id) {
    const q = new URLSearchParams({ id, bookKey });
    const response = await fetch(`/artifact-library/audio?${q.toString()}`, { cache: 'no-store' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP_${response.status}`);
    return data;
  }

  async function waitReady(id) {
    for (let n = 0; n < 240; n++) {
      const data = await readAudioState(id);
      if (data.status === 'ready') return data;
      if (data.status === 'error') throw new Error(data.error || 'AUDIO_PREPARE_FAILED');
      setStatus(data.status === 'processing' ? 'Nam Minh · đang tổng hợp…' : 'Nam Minh · đang xếp hàng…');
      await sleep(1500);
    }
    throw new Error('AUDIO_READY_TIMEOUT');
  }

  async function timingFor(state) {
    if (!state?.timingUrl) return [];
    const response = await fetch(state.timingUrl, { cache: 'no-store' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !Array.isArray(data.words)) throw new Error('AUDIO_TIMING_INVALID');
    return data.words;
  }

  async function resolveAudio(payload, { allowSaved = true } = {}) {
    debug.prepares++;
    const saved = loadState();
    if (allowSaved && saved.mediaId) {
      try {
        const existing = await readAudioState(saved.mediaId);
        if (existing.status === 'ready' && existing.mediaUrl && existing.timingUrl && (!saved.chapter || saved.chapter === payload.chapter)) {
          const timingWords = await timingFor(existing);
          const alignment = buildSegments(payload, timingWords);
          if (alignment.segments.length) return { state: existing, timingWords, alignment, resumed: true };
        }
      } catch {}
    }
    const response = await fetch('/artifact-library/audio', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ bookKey, text: payload.text, chapterTitle: payload.chapterTitle, chapterHref: payload.chapterHref, bookTitle: document.title || 'Ebook', clientVersion: 'reader-audio-core-v33' }),
    });
    let state = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(state.error || `HTTP_${response.status}`);
    if (!state.id) throw new Error('AUDIO_ID_MISSING');
    if (state.status !== 'ready') state = await waitReady(state.id);
    if (!state?.mediaUrl) throw new Error('AUDIO_MEDIA_URL_MISSING');
    const timingWords = await timingFor(state);
    const alignment = buildSegments(payload, timingWords);
    if (!alignment.segments.length) throw new Error('AUDIO_ALIGNMENT_EMPTY');
    return { state, timingWords, alignment, resumed: false };
  }

  async function displayCfi(cfi) {
    const b = bridge();
    if (!b?.display || !cfi) return false;
    debug.displayCalls++;
    debug.displayConcurrent++;
    debug.maxDisplayConcurrent = Math.max(debug.maxDisplayConcurrent, debug.displayConcurrent);
    try {
      const expectedChapter = String(currentPayload?.chapter || '');
      await b.display(cfi);
      try { b.persist?.(); } catch {}
      for (let attempt = 0; attempt < 18; attempt++) {
        await sleep(attempt === 0 ? 80 : 50);
        rebuildCurrentMapping(expectedChapter);
        const el = mappedElements.get(String(cfi));
        if (el && blockVisible(el)) return true;
      }
      return false;
    } finally {
      debug.displayConcurrent = Math.max(0, debug.displayConcurrent - 1);
    }
  }

  function clearHighlight() {
    if (activeBlock) {
      try { activeBlock.removeAttribute('data-r3-audio-reading-v11'); } catch {}
    }
    activeBlock = null;
  }

  function highlight(target) {
    // v43: sentence continuity is the only visual highlight owner.
    window.__R3_READER_SENTENCE_HIGHLIGHT_OWNER = true;
    clearHighlight();
  }

  function isVisible(target) {
    return blockVisible(mappedElements.get(String(target?.cfi || '')));
  }

  async function advanceToNextReadable(currentChapter) {
    debug.advances++;
    const b = bridge();
    if (!b?.next) return null;
    const before = framePayload();
    const beforeChapter = String(before?.chapter || currentChapter || '');
    let stagnant = 0;
    for (let step = 0; step < 32; step++) {
      const beforeCfi = String(b.current?.()?.start?.cfi || '');
      try { await Promise.race([Promise.resolve(b.next()), sleep(900)]); } catch {}
      await sleep(170);
      const afterCfi = String(b.current?.()?.start?.cfi || '');
      const payload = framePayload();
      if (payload?.chapter && payload.chapter !== beforeChapter && payload.text.length >= 80) {
        try { b.persist?.(); } catch {}
        setStatus('Nam Minh · đang chuẩn bị phần tiếp…');
        const prepared = await resolveAudio(payload, { allowSaved: false });
        currentPayload = payload;
        currentTiming = prepared.timingWords;
        const visible = prepared.alignment.visible || prepared.alignment.segments[0];
        return {
          chapter: payload.chapter,
          mediaId: prepared.state.id,
          src: prepared.state.mediaUrl,
          segments: prepared.alignment.segments,
          time: visible?.start || 0,
          cfi: visible?.cfi || '',
          payload,
          alignment: prepared.alignment,
        };
      }
      stagnant = afterCfi && beforeCfi && afterCfi === beforeCfi ? stagnant + 1 : 0;
      if (stagnant >= 2) break;
    }
    setStatus('Đã hết sách');
    return null;
  }

  function makeAdapter() {
    return new ReaderAudioAdapter({
      audio,
      loadState,
      saveState,
      displayCfi,
      isVisible,
      highlight,
      clearHighlight,
      resolveNextReadable: async (chapter) => ({ chapter, kind: 'advance-reader' }),
      prepareNext: async () => advanceToNextReadable(adapter?.snapshot?.().chapter || ''),
      activateChapter: async (next) => {
        if (next?.alignment) mappedElements = new Map(next.alignment.segments.map((segment) => [segment.cfi, mappedElements.get(segment.cfi)]).filter(([, el]) => el));
        if (next?.payload) {
          currentPayload = next.payload;
          setTitle(next.payload.chapterTitle || 'Chương hiện tại');
        }
        setStatus('Nam Minh · đang phát');
        return next;
      },
      continuous: true,
      prefetchOnMount: false,
      prefetchAfterAdvance: false,
      onState: syncUi,
    });
  }

  async function prepareCurrent({ autoplay = false, allowSaved = true, followOnMount = autoplay } = {}) {
    if (busy) return adapter?.snapshot?.() || null;
    busy = true;
    setMain('loading');
    try {
      const payload = framePayload();
      if (!payload) throw new Error('READER_CHAPTER_NOT_READY');
      setTitle(payload.chapterTitle || 'Chương hiện tại');
      setStatus('Nam Minh · đang chuẩn bị chương…');
      const prepared = await resolveAudio(payload, { allowSaved });
      currentPayload = payload;
      currentTiming = prepared.timingWords;
      mappedElements = new Map();
      const rebuilt = buildSegments(payload, currentTiming);
      const visible = rebuilt.visible || rebuilt.segments[0];
      if (!adapter) adapter = makeAdapter();
      const saved = loadState();
      const sameSaved = Boolean(saved.mediaId && saved.mediaId === prepared.state.id && (!saved.chapter || saved.chapter === payload.chapter));
      const context = {
        bookKey,
        chapter: payload.chapter,
        mediaId: prepared.state.id,
        src: prepared.state.mediaUrl,
        segments: rebuilt.segments,
        autoplay: false,
        followOnMount: Boolean(followOnMount),
      };
      if (!sameSaved) {
        context.time = visible?.start || 0;
        context.cfi = visible?.cfi || '';
        context.playingIntent = false;
        context.playbackRate = saved.playbackRate || 1;
      }
      await adapter.mount(context);
      // v70: next-chapter warm-ahead is fire-and-forget. Never delay current playback for it.
      warmAhead(0);
      if (autoplay) {
        await adapter.play();
      }
      syncUi(adapter.snapshot());
      setStatus(autoplay ? 'Nam Minh · đang phát' : 'Nam Minh · sẵn sàng');
      return adapter.snapshot();
    } catch (error) {
      debug.lastError = String(error?.message || error || 'reader audio error').slice(0, 240);
      const blocked = String(error?.name || '').toLowerCase() === 'notallowederror' || /not allowed|user gesture|user activation/i.test(debug.lastError);
      setStatus(blocked ? 'Nam Minh · sẵn sàng · nhấn ▶ để phát' : 'Nam Minh · chưa tạo được audio · nhấn ▶ thử lại');
      setMain('play');
      return null;
    } finally {
      busy = false;
    }
  }

  window.__r3AudioCorePrepareCurrent = prepareCurrent;

  async function onMain(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    if (busy) return;
    const payload = framePayload();
    if (!adapter || !payload || adapter.snapshot().chapter !== payload.chapter || !audio.getAttribute('src')) {
      // v70 iOS: a network/synthesis wait outlives the original tap activation.
      // Prepare only; do not attempt delayed autoplay after the async wait.
      const ready = await prepareCurrent({ autoplay: false, allowSaved: true, followOnMount: false });
      if (ready) setStatus('Nam Minh · sẵn sàng · nhấn ▶ để phát');
      return;
    }
    if (!audio.paused && !audio.ended) {
      adapter.pause();
      setStatus('Nam Minh · tạm dừng');
      return;
    }
    if (audio.ended) await adapter.seek(0);
    try {
      await adapter.play();
      setStatus('Nam Minh · đang phát');
    } catch (error) {
      debug.lastError = String(error?.message || error || 'play failed').slice(0, 240);
      const blocked = String(error?.name || '').toLowerCase() === 'notallowederror' || /not allowed|user gesture|user activation/i.test(debug.lastError);
      setStatus(blocked ? 'Nam Minh · nhấn ▶ lại để phát' : 'Nam Minh · chưa phát được · nhấn ▶ thử lại');
    }
  }

  function setRateValue(value) {
    const rounded = Math.round((Number(value) || 1) * 4) / 4;
    const next = Math.max(rates[0], Math.min(rates[rates.length - 1], rounded));
    const state = adapter?.snapshot?.() || loadState();
    if (adapter) adapter.setRate(next);
    else saveState({ ...state, playbackRate: next });
    audio.playbackRate = next;
    if (speed) speed.textContent = `${next}×`;
    setStatus(`Nam Minh · tốc độ ${next}×`);
    return next;
  }
  window.__r3AudioCoreSetRate = setRateValue;

  function cycleRate(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    const state = adapter?.snapshot?.() || loadState();
    const currentRate = Number(state.playbackRate) || 1;
    let index = rates.findIndex((value) => Math.abs(value - currentRate) < 0.01);
    if (index < 0) index = 0;
    setRateValue(rates[(index + 1) % rates.length]);
  }

  main.addEventListener('click', onMain, true);
  back?.addEventListener('click', (event) => {
    event.preventDefault(); event.stopImmediatePropagation();
    if (adapter) adapter.seek(Math.max(0, (Number(audio.currentTime) || 0) - 15));
  }, true);
  forward?.addEventListener('click', (event) => {
    event.preventDefault(); event.stopImmediatePropagation();
    if (adapter) adapter.seek(Math.min(Number.isFinite(audio.duration) ? audio.duration : Infinity, (Number(audio.currentTime) || 0) + 15));
  }, true);
  speed?.addEventListener('click', cycleRate, true);
  expand?.addEventListener('click', (event) => {
    event.preventDefault(); event.stopImmediatePropagation();
    const ui = window.__r3AudioUiV6;
    if (ui?.setExpanded) ui.setExpanded(!dock?.classList.contains('r3-expanded'));
    else {
      const expanded = !dock?.classList.contains('r3-expanded');
      dock?.classList.toggle('r3-expanded', expanded);
      document.body.classList.toggle('r3-audio-expanded', expanded);
    }
  }, true);
  seek?.addEventListener('input', () => {
    seeking = true;
    const total = Number(audio.duration);
    if (current && Number.isFinite(total) && total > 0) current.textContent = formatTime(total * Number(seek.value) / 1000);
  });
  seek?.addEventListener('change', async () => {
    const total = Number(audio.duration);
    if (adapter && Number.isFinite(total) && total > 0) await adapter.seek(total * Number(seek.value) / 1000);
    seeking = false;
    syncTimeline();
  });

  audio.addEventListener('loadedmetadata', syncTimeline);
  audio.addEventListener('durationchange', syncTimeline);
  audio.addEventListener('timeupdate', syncTimeline);
  audio.addEventListener('play', () => { setMain('pause'); setStatus('Nam Minh · đang phát'); });
  audio.addEventListener('pause', () => { if (!audio.ended) { setMain('play'); setStatus('Nam Minh · tạm dừng'); } });
  audio.addEventListener('ended', () => setStatus('Nam Minh · chuyển sang phần tiếp…'));
  window.addEventListener('pagehide', () => adapter?.persist?.(), { once: true });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') adapter?.persist?.(); });

  async function initialRestore() {
  try {
    const saved = loadState();
    for (let n = 0; n < 140; n++) {
      const loc = bridge()?.current?.();
      const ready = Boolean(loc?.start?.cfi || loc?.start?.href);
      if (ready && !window.__R3_READER_RESTORE_PENDING) break;
      await sleep(80);
    }
    const loc = bridge()?.current?.();
    const liveCfi = String(loc?.start?.cfi || '');
    let readerCfi = '';
    try { readerCfi = String(localStorage.getItem(READER_POSITION_KEY) || ''); } catch {}
    const restoreCfi = liveCfi || readerCfi || saved.cfi || '';
    if (saved.mediaId) {
      let payload = null;
      let locationReady = false;
      for (let n = 0; n < 80; n++) {
        const currentLoc = bridge()?.current?.();
        payload = framePayload();
        locationReady = Boolean(currentLoc?.start?.cfi || currentLoc?.start?.href);
        if (locationReady && payload) break;
        await sleep(80);
      }
      if (!locationReady || !payload) throw new Error('READER_CHAPTER_NOT_READY');
      const sameAudioChapter = Boolean(!saved.chapter || payload.chapter === saved.chapter);
      if (sameAudioChapter) await prepareCurrent({ autoplay: false, allowSaved: true, followOnMount: false });
      else syncUi({ ...saved, chapter: payload.chapter, mediaId: '', time: 0, cfi: restoreCfi, playingIntent: false });
    } else {
      syncUi({ ...saved, cfi: restoreCfi, playingIntent: false });
      // v70: synth/load current chapter as soon as Reader is stable, before the user's first Play tap.
      // This moves cold-start latency into idle reading time and preserves iOS user activation for playback.
      await prepareCurrent({ autoplay: false, allowSaved: true, followOnMount: false });
    }
  } catch (error) {
    debug.lastError = String(error?.message || error || 'restore failed').slice(0, 240);
  }
}

  initialRestore();
}

if (typeof window !== 'undefined') {
  try { bootReaderAudioCore(); } catch (error) {
    window.__r3AudioCoreV33BootError = String(error?.stack || error || 'boot failed').slice(0, 1200);
  }
}