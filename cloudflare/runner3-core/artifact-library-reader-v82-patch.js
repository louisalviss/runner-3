export function r3StableEarlyV82() {
  if (window.__r3StableEarlyV82) return;
  const root = document.documentElement;
  const standalone = Boolean((window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true);
  root.classList.add('r3-v82-stable');
  root.classList.add('r3-v82-restoring');
  if (standalone) root.classList.add('r3-v82-home');
  const text = fn => { try { return Function.prototype.toString.call(fn); } catch { return ''; } };
  const geometryFn = fn => /r3ScheduleFullBleedV68|r3ScheduleAudioDockInsetV69|r3ClampPaginatedVerticalV62/.test(text(fn));
  const state = window.__r3StableEarlyV82 = { owner: 'stable-shell-v82', standalone, blockedListeners: 0, blockedTimers: 0, blockedObservers: 0 };

  try {
    const vv = window.visualViewport;
    if (vv && typeof vv.addEventListener === 'function') {
      const native = vv.addEventListener.bind(vv);
      Object.defineProperty(vv, 'addEventListener', { configurable: true, value(type, listener, options) {
        if ((type === 'resize' || type === 'scroll') && geometryFn(listener)) { state.blockedListeners++; return; }
        return native(type, listener, options);
      }});
    }
  } catch {}

  try {
    const native = window.addEventListener.bind(window);
    window.addEventListener = function(type, listener, options) {
      if ((type === 'resize' || type === 'orientationchange') && geometryFn(listener)) { state.blockedListeners++; return; }
      return native(type, listener, options);
    };
  } catch {}

  try {
    const nativeTimeout = window.setTimeout.bind(window);
    const nativeInterval = window.setInterval.bind(window);
    window.setTimeout = function(fn, ms, ...args) {
      if (typeof fn === 'function' && /r3ClampPaginatedVerticalV62/.test(text(fn))) { state.blockedTimers++; return 0; }
      return nativeTimeout(fn, ms, ...args);
    };
    window.setInterval = function(fn, ms, ...args) {
      if (typeof fn === 'function' && /r3ClampPaginatedVerticalV62/.test(text(fn))) { state.blockedTimers++; return 0; }
      return nativeInterval(fn, ms, ...args);
    };
  } catch {}

  try {
    const NativeRO = window.ResizeObserver;
    if (typeof NativeRO === 'function') window.ResizeObserver = class extends NativeRO {
      constructor(cb) { if (geometryFn(cb)) { state.blockedObservers++; super(() => {}); } else super(cb); }
    };
  } catch {}

  try {
    const NativeMO = window.MutationObserver;
    if (typeof NativeMO === 'function') window.MutationObserver = class extends NativeMO {
      constructor(cb) { if (/r3ScheduleAudioDockInsetV69/.test(text(cb))) { state.blockedObservers++; super(() => {}); } else super(cb); }
    };
  } catch {}
}

export function r3StableRuntimeV82() {
  if (window.__r3StableRuntimeV82) return;
  const debug = window.__r3StableRuntimeV82 = { owner: 'stable-shell-v82', version: 'v82', chapterSource: '', chapterIndex: -1, navMoves: 0, navDrops: 0, restoreTarget: '', restoreAfter: '', restoreOk: false };
  const params = new URLSearchParams(location.search);
  const bookKey = params.get('key') || '';
  if (!bookKey) return;
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  const paint = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const cleanHref = value => { let raw = String(value || '').split('#')[0]; try { raw = decodeURIComponent(raw); } catch {} while (raw.startsWith('./')) raw = raw.slice(2); return raw.toLowerCase(); };
  const chapterNumber = value => { const m = String(value || '').match(/(?:chương|chapter)\s*([0-9]{1,6})/i); return m ? Number(m[1]) : -1; };

  function visibleHeading() {
    for (const frame of document.querySelectorAll('#viewer iframe')) {
      try {
        const doc = frame.contentDocument;
        const heading = doc && doc.querySelector('h1,h2,h3,.chapter-title');
        const value = String(heading && heading.textContent || doc && doc.title || '').replace(/\s+/g, ' ').trim();
        if (value) return value;
      } catch {}
    }
    return '';
  }

  async function waitBridge() {
    for (let n = 0; n < 180; n++) { if (window.r3ReaderBridge) return window.r3ReaderBridge; await delay(50); }
    return null;
  }

  async function waitBoot() {
    for (let n = 0; n < 180; n++) { if (window.__R3_BASE_READER_BOOT_DONE === true) return true; await delay(50); }
    return false;
  }

  async function remoteProgress() {
    try {
      const response = await fetch('/artifact-library/api/progress?key=' + encodeURIComponent(bookKey), { cache: 'no-store', headers: { accept: 'application/json', 'x-runner3-library': '1' } });
      if (!response.ok) return null;
      const data = await response.json();
      return data && data.ok === true ? data.progress : null;
    } catch { return null; }
  }

  function writeCanonicalLocal(remote) {
    if (!remote) return;
    try {
      localStorage.setItem('r3-reader-position:' + bookKey, String(remote.cfi || ''));
      localStorage.setItem('r3-reader-progress-v1:' + bookKey, JSON.stringify({ percent: remote.percent, cfi: String(remote.cfi || ''), updatedAt: Number(remote.updated_at || 0), lastOpenAt: Number(remote.last_open_at || 0), syncedBy: 'v82-server' }));
    } catch {}
  }

  function patchChapterInfo(bridge) {
    if (!bridge || bridge.__r3V82ChapterInfo) return;
    const originalInfo = typeof bridge.chapterInfo === 'function' ? bridge.chapterInfo.bind(bridge) : null;
    const originalChapters = typeof bridge.chapters === 'function' ? bridge.chapters.bind(bridge) : null;
    bridge.chapterInfo = async () => {
      let base = { index: -1, total: 0, chapter: null, chapters: [] };
      try { if (originalInfo) base = await originalInfo() || base; } catch {}
      let chapters = Array.isArray(base.chapters) && base.chapters.length ? base.chapters : [];
      try { if (!chapters.length && originalChapters) chapters = await originalChapters() || []; } catch {}
      if (!chapters.length) return base;
      let index = -1, source = '';
      const heading = visibleHeading();
      const number = chapterNumber(heading);
      if (number > 0) {
        const labelIndex = chapters.findIndex(row => chapterNumber(row && row.label) === number);
        if (labelIndex >= 0) { index = labelIndex; source = 'heading-label'; }
        else if (number <= chapters.length) { index = number - 1; source = 'heading-number'; }
      }
      if (index < 0) {
        const current = cleanHref(bridge.current && bridge.current()?.start?.href || '');
        if (current) {
          index = chapters.findIndex(row => { const candidate = cleanHref(row && row.href); return candidate === current || candidate.endsWith('/' + current) || current.endsWith('/' + candidate) || candidate.split('/').pop() === current.split('/').pop(); });
          if (index >= 0) source = 'href';
        }
      }
      if (index < 0 && Number(base.index) >= 0 && Number(base.index) < chapters.length) { index = Number(base.index); source = 'legacy'; }
      if (index < 0) index = 0;
      debug.chapterSource = source || 'fallback';
      debug.chapterIndex = index;
      return { index, total: chapters.length, chapter: chapters[index] || null, chapters, r3Source: debug.chapterSource, heading };
    };
    bridge.__r3V82ChapterInfo = true;
  }

  function refreshChapterUi(bridge) {
    Promise.resolve(bridge.chapterInfo && bridge.chapterInfo()).then(info => {
      if (!info || !info.total) return;
      const row = info.chapter || {};
      const label = String(row.label || visibleHeading() || ('Chương ' + (info.index + 1)));
      const shown = chapterNumber(label) > 0 ? chapterNumber(label) : info.index + 1;
      const meta = document.getElementById('r3AudioChapterMeta');
      const badge = document.getElementById('r3ReaderChapterBadge');
      const select = document.getElementById('r3AudioChapterSelect');
      const prev = document.getElementById('r3AudioChapterPrev');
      const next = document.getElementById('r3AudioChapterNext');
      if (meta) meta.textContent = 'Chương ' + shown + ' / ' + info.total;
      if (badge) badge.textContent = label + ' · ' + shown + '/' + info.total;
      if (select && select.options.length === info.total) select.value = String(info.index);
      if (prev) prev.disabled = info.index <= 0;
      if (next) next.disabled = info.index >= info.total - 1;
    }).catch(() => {});
  }

  function installNavigation(bridge) {
    if (window.__r3V82MovePage) return;
    const rawNext = bridge.next && bridge.next.bind(bridge);
    const rawPrev = bridge.prev && bridge.prev.bind(bridge);
    let busy = false;
    async function move(direction) {
      if (busy) { debug.navDrops++; return false; }
      const fn = direction > 0 ? rawNext : rawPrev;
      if (typeof fn !== 'function') return false;
      busy = true; debug.navMoves++;
      const before = String(bridge.current && bridge.current()?.start?.cfi || '');
      try {
        await Promise.resolve(fn());
        for (let n = 0; n < 20; n++) { await delay(n ? 45 : 80); const after = String(bridge.current && bridge.current()?.start?.cfi || ''); if (after && after !== before) break; }
        await paint(); refreshChapterUi(bridge); return true;
      } catch { return false; }
      finally { setTimeout(() => { busy = false; }, 140); }
    }
    bridge.next = () => move(1);
    bridge.prev = () => move(-1);
    window.__r3V82MovePage = move;

    const oldGesture = document.getElementById('r3GestureLayer');
    if (oldGesture) oldGesture.style.setProperty('pointer-events', 'none', 'important');
    for (const zone of document.querySelectorAll('.r3-hit-zone')) zone.style.setProperty('pointer-events', 'none', 'important');

    const layer = document.createElement('div');
    layer.id = 'r3V82GestureLayer';
    layer.setAttribute('aria-hidden', 'true');
    document.body.appendChild(layer);
    let sx = 0, sy = 0, st = 0, active = false;
    const begin = (x, y) => { sx = x; sy = y; st = Date.now(); active = true; };
    const finish = (x, y) => {
      if (!active) return; active = false;
      const dx = x - sx, dy = y - sy, dt = Date.now() - st;
      if (Math.abs(dx) >= 34 && Math.abs(dx) > Math.abs(dy) * 1.08) { move(dx < 0 ? 1 : -1); return; }
      if (Math.abs(dx) < 18 && Math.abs(dy) < 18 && dt < 650) {
        const ratio = x / Math.max(1, window.innerWidth);
        if (document.body.dataset.nav === 'tap' && ratio < .28) move(-1);
        else if (document.body.dataset.nav === 'tap' && ratio > .72) move(1);
        else if (ratio >= .28 && ratio <= .72) document.body.classList.toggle('controls');
      }
    };
    layer.addEventListener('pointerdown', event => { if (event.pointerType === 'mouse' && event.button !== 0) return; begin(event.clientX, event.clientY); try { layer.setPointerCapture(event.pointerId); } catch {} event.preventDefault(); }, { passive: false });
    layer.addEventListener('pointermove', event => { if (active) event.preventDefault(); }, { passive: false });
    layer.addEventListener('pointerup', event => { event.preventDefault(); finish(event.clientX, event.clientY); try { layer.releasePointerCapture(event.pointerId); } catch {} }, { passive: false });
    layer.addEventListener('pointercancel', () => { active = false; });
    document.addEventListener('keydown', event => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); event.stopImmediatePropagation(); move(event.key === 'ArrowRight' ? 1 : -1); } }, true);
  }

  async function finalRestore(bridge) {
    const remote = await remoteProgress();
    const target = String(remote && remote.cfi || localStorage.getItem('r3-reader-position:' + bookKey) || '');
    debug.restoreTarget = target;
    if (!target) { document.documentElement.classList.remove('r3-restore-pending-v45'); document.documentElement.classList.remove('r3-v82-restoring'); return; }
    const priorBoot = window.__R3_BASE_READER_BOOT_DONE;
    window.__R3_BASE_READER_BOOT_DONE = false;
    window.__R3_READER_RESTORE_PENDING = true;
    try {
      await Promise.resolve(bridge.display(target));
      await paint(); await delay(90); await paint();
      debug.restoreAfter = String(bridge.current && bridge.current()?.start?.cfi || '');
      debug.restoreOk = Boolean(debug.restoreAfter);
      writeCanonicalLocal(remote);
    } catch (error) { debug.restoreError = String(error && error.message || error).slice(0, 180); }
    finally {
      window.__R3_BASE_READER_BOOT_DONE = priorBoot !== false;
      window.__R3_READER_RESTORE_PENDING = false;
      document.documentElement.classList.remove('r3-restore-pending-v45');
      document.documentElement.classList.remove('r3-v82-restoring');
    }
    refreshChapterUi(bridge);
    const prepare = window.__r3AudioCorePrepareCurrent;
    if (typeof prepare === 'function') {
      setTimeout(() => Promise.resolve(prepare({ autoplay: false, allowSaved: true })).catch(() => {}), 0);
      setTimeout(() => Promise.resolve(prepare({ autoplay: false, allowSaved: true })).catch(() => {}), 220);
    }
  }

  (async () => {
    const bridge = await waitBridge();
    if (!bridge) return;
    patchChapterInfo(bridge);
    installNavigation(bridge);
    await waitBoot();
    await delay(120);
    await finalRestore(bridge);
    refreshChapterUi(bridge);
    setInterval(() => refreshChapterUi(bridge), 1200);
  })().catch(error => { debug.error = String(error && error.message || error).slice(0, 200); document.documentElement.classList.remove('r3-restore-pending-v45'); document.documentElement.classList.remove('r3-v82-restoring'); });
}

const STYLE = `<style data-r3-stable-shell-v82="1">
html.r3-v82-stable #r3GestureLayer,html.r3-v82-stable .r3-hit-zone{pointer-events:none!important}
html.r3-v82-stable body.r3-audio-ui #viewer,html.r3-v82-stable body.r3-audio-ui.r3-audio-expanded #viewer{bottom:calc(76px + env(safe-area-inset-bottom,0px))!important}
html.r3-v82-stable body.r3-audio-ui .bottom-status,html.r3-v82-stable body.r3-audio-ui.r3-audio-expanded .bottom-status{bottom:calc(82px + env(safe-area-inset-bottom,0px))!important}
html.r3-v82-restoring body::after{content:'Đang mở đúng trang đọc…';position:fixed;z-index:2147483601;inset:0;background:var(--bg,#0b0d10);color:var(--muted,#8f98a3);display:grid;place-items:center;font:600 13px/1.3 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;pointer-events:auto}
html.r3-v82-home #viewer{top:calc(max(env(safe-area-inset-top,0px),44px) + 54px)!important}
html.r3-v82-home .topbar{top:0!important;padding-top:calc(max(env(safe-area-inset-top,0px),44px) + 8px)!important}
html.r3-v82-home #r3ReaderChapterBadge{top:calc(max(env(safe-area-inset-top,0px),44px) + 58px)!important}
html.r3-v82-stable.r3-restore-pending-v45 body::before{content:'Đang mở đúng trang đọc…'!important;display:grid!important;place-items:center!important;color:var(--muted,#8f98a3)!important;font:600 13px/1.3 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif!important}
#r3V82GestureLayer{position:fixed;z-index:1000;left:0;right:0;top:94px;bottom:82px;background:rgba(0,0,0,.001);touch-action:none;-webkit-user-select:none;user-select:none}
body.r3-audio-expanded #r3V82GestureLayer{bottom:216px}
#r3AudioDock{z-index:1200!important}
body.settings #r3V82GestureLayer,body.r3-live-library-open #r3V82GestureLayer{display:none!important}
</style>`;

export function patchReaderV82(html) {
  let out = String(html || '');
  if (out.includes('data-r3-stable-shell-runtime-v82="1"')) return out;
  if (!out.includes('id="viewer"') || !out.includes('</head>') || !out.includes('</body>')) throw new Error('V82_READER_HTML_ANCHOR_MISSING');
  const early = STYLE + `<script data-r3-stable-shell-early-v82="1">(${r3StableEarlyV82.toString()})();</script>`;
  const late = `<script data-r3-stable-shell-runtime-v82="1">(${r3StableRuntimeV82.toString()})();</script>`;
  out = out.replace('</head>', early + '</head>');
  out = out.replace('</body>', late + '</body>');
  return out;
}
