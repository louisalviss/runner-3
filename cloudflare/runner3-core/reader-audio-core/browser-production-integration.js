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
  const rates = [1, 1.25, 1.5, 1.75, 2];
  const debug = window.__r3AudioCoreV33Debug = {
    owner: 'reader-audio-core-v33',
    legacy: { v6: Boolean(window.__r3AudioLegacyV6Suppressed), v8: Boolean(window.__r3AudioLegacyV8Suppressed), v11: Boolean(window.__r3AudioLegacyV11Suppressed), v29: Boolean(window.__r3AudioLegacyV29Suppressed), v31Clock: Boolean(window.__r3AudioLegacyV31ClockSuppressed) },
    prepares: 0,
    advances: 0,
    displayCalls: 0,
    maxDisplayConcurrent: 0,
    displayConcurrent: 0,
    lastError: '',
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
      const doc = el.ownerDocument;
      const win = doc.defaultView;
      const width = win?.innerWidth || doc.documentElement.clientWidth || 1;
      const height = win?.innerHeight || doc.documentElement.clientHeight || 1;
      return [...el.getClientRects()].some((rect) => rect.right > 2 && rect.left < width - 2 && rect.bottom > 2 && rect.top < height - 2);
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
      await b.display(cfi);
      try { b.persist?.(); } catch {}
      await sleep(60);
      return true;
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
    const el = mappedElements.get(String(target?.cfi || ''));
    if (!el || el === activeBlock) return;
    clearHighlight();
    activeBlock = el;
    try { el.setAttribute('data-r3-audio-reading-v11', '1'); } catch {}
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

  async function prepareCurrent({ autoplay = false, allowSaved = true } = {}) {
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
      };
      if (!sameSaved) {
        context.time = visible?.start || 0;
        context.cfi = visible?.cfi || '';
        context.playingIntent = false;
        context.playbackRate = saved.playbackRate || 1;
      }
      await adapter.mount(context);
      if (autoplay) {
        const rate = Math.max(1, Number(saved.playbackRate) || 1);
        const effectiveSeconds = Math.max(0, Number(prepared.state.durationSeconds) || 0) / rate;
        if (effectiveSeconds > 0 && effectiveSeconds < 18) {
          setStatus('Nam Minh · chuẩn bị liền mạch…');
          await warmAhead(Math.min(10000, Math.max(1500, Math.round((18 - effectiveSeconds) * 1000))));
        }
        await adapter.play();
      }
      syncUi(adapter.snapshot());
      setStatus(autoplay ? 'Nam Minh · đang phát' : 'Nam Minh · sẵn sàng');
      return adapter.snapshot();
    } catch (error) {
      debug.lastError = String(error?.message || error || 'reader audio error').slice(0, 240);
      setStatus(debug.lastError);
      setMain('play');
      return null;
    } finally {
      busy = false;
    }
  }

  async function onMain(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    if (busy) return;
    const payload = framePayload();
    if (!adapter || !payload || adapter.snapshot().chapter !== payload.chapter || !audio.getAttribute('src')) {
      warmAhead(0);
      const ready = await prepareCurrent({ autoplay: true, allowSaved: true });
      if (!ready) return;
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
      setStatus('Nam Minh · nhấn phát lại');
    }
  }

  function cycleRate(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    const state = adapter?.snapshot?.() || loadState();
    const currentRate = Number(state.playbackRate) || 1;
    let index = rates.findIndex((value) => Math.abs(value - currentRate) < 0.01);
    if (index < 0) index = 0;
    const next = rates[(index + 1) % rates.length];
    if (adapter) adapter.setRate(next);
    else saveState({ ...state, playbackRate: next });
    if (speed) speed.textContent = `${next}×`;
    setStatus(`Nam Minh · tốc độ ${next}×`);
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
      for (let n = 0; n < 100; n++) {
        const loc = bridge()?.current?.();
        if (loc?.start?.cfi || loc?.start?.href) break;
        await sleep(100);
      }
      if (saved.cfi && bridge()?.display) {
        try { await bridge().display(saved.cfi); } catch {}
      }
      if (saved.mediaId) {
        let ready = false;
        for (let n = 0; n < 120; n++) {
          const loc = bridge()?.current?.();
          const payload = framePayload();
          const locationReady = Boolean(loc?.start?.cfi || loc?.start?.href);
          const chapterReady = Boolean(payload && (!saved.chapter || payload.chapter === saved.chapter));
          if (locationReady && chapterReady) {
            ready = true;
            break;
          }
          await sleep(100);
        }
        if (!ready) throw new Error('READER_CHAPTER_NOT_READY');
        await prepareCurrent({ autoplay: false, allowSaved: true });
      } else syncUi(saved);
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