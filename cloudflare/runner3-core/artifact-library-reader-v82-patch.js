export function r3StableEarlyV82() {
  if (window.__r3StableEarlyV82) return;
  const root = document.documentElement;
  const standalone = Boolean((window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true);
  root.classList.add('r3-v82-stable');
  if (standalone) { root.classList.add('r3-v90-home'); root.classList.remove('r3-v90-browser'); }
  else { root.classList.add('r3-v90-browser'); root.classList.remove('r3-v90-home'); }
  if (standalone) root.classList.add('r3-v82-home');
  const text = fn => { try { return Function.prototype.toString.call(fn); } catch { return ''; } };
  const geometryFn = fn => /r3ScheduleFullBleedV68|r3ScheduleAudioDockInsetV69|r3ClampPaginatedVerticalV62/.test(text(fn));
  const nativeSetTimeoutV88 = window.setTimeout.bind(window);
  const state = window.__r3StableEarlyV82 = { owner: 'stable-shell-v82', standalone, blockedListeners: 0, blockedTimers: 0, blockedObservers: 0, restoreGuard: 'nonblocking-v89', layoutOwner: 'v90', interactionOwner: 'v91', restoreShieldReleased: '', restoreWatchdogFired: false };
  const releaseRestoreShieldV88 = reason => {
    state.restoreShieldReleased = state.restoreShieldReleased || String(reason || 'released');
    root.classList.remove('r3-restore-pending-v45');
    root.classList.remove('r3-v82-restoring');
  };
  state.releaseRestoreShield = releaseRestoreShieldV88;
  nativeSetTimeoutV88(() => {
    if (root.classList.contains('r3-v82-restoring') || root.classList.contains('r3-restore-pending-v45')) {
      state.restoreWatchdogFired = true;
      releaseRestoreShieldV88('watchdog-8000ms');
    }
  }, 8000);

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
  const debug = window.__r3StableRuntimeV82 = { owner: 'stable-shell-v82', version: 'v82', restoreGuard: 'nonblocking-v89', layoutOwner: 'v90', interactionOwner: 'v91', geometryMode: '', geometryApplies: 0, geometryRestores: 0, chapterSource: '', chapterIndex: -1, navMoves: 0, navDrops: 0, restoreTarget: '', restoreAfter: '', restoreOk: false, restoreReleasedBy: '', restoreError: '' };
  const releaseRestoreShield = reason => {
    debug.restoreReleasedBy = debug.restoreReleasedBy || String(reason || 'released');
    try { window.__r3StableEarlyV82?.releaseRestoreShield?.(reason); } catch {}
    document.documentElement.classList.remove('r3-restore-pending-v45');
    document.documentElement.classList.remove('r3-v82-restoring');
  };
  const params = new URLSearchParams(location.search);
  const bookKey = params.get('key') || '';
  if (!bookKey) { releaseRestoreShield('missing-book-key'); return; }
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
    const controller = typeof AbortController === 'function' ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort('v88-progress-timeout'), 2500) : 0;
    try {
      const response = await fetch('/artifact-library/api/progress?key=' + encodeURIComponent(bookKey), { cache: 'no-store', headers: { accept: 'application/json', 'x-runner3-library': '1' }, ...(controller ? { signal: controller.signal } : {}) });
      if (!response.ok) return null;
      const data = await response.json();
      return data && data.ok === true ? data.progress : null;
    } catch { return null; }
    finally { if (timer) clearTimeout(timer); }
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

  function installGeometryV90(bridge) {
    if (window.__r3GeometryOwnerV90) return window.__r3GeometryOwnerV90;
    const root = document.documentElement;
    const body = document.body;
    const viewer = document.getElementById('viewer');
    if (!body || !viewer) return null;
    const standalone = Boolean((window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true);
    const state = window.__r3GeometryOwnerV90 = { owner: 'layout-convergence-v90', standalone, expanded: false, signature: '', applies: 0, restores: 0, lastReason: '', lastCfi: '' };
    if (standalone) { root.classList.add('r3-v90-home'); root.classList.remove('r3-v90-browser'); }
    else { root.classList.add('r3-v90-browser'); root.classList.remove('r3-v90-home'); }
    debug.geometryMode = standalone ? 'home' : 'browser';

    const set = (node, prop, value) => { try { node && node.style && node.style.setProperty(prop, value, 'important'); } catch {} };
    const currentCfi = () => { try { return String(bridge.current && bridge.current()?.start?.cfi || ''); } catch { return ''; } };
    let restoreTimer = 0;
    let restoring = false;

    function styleGeometry(reason='apply') {
      const expanded = Boolean(body.classList && body.classList.contains('r3-audio-expanded'));
      const signature = (standalone ? 'home' : 'browser') + ':' + (expanded ? 'expanded' : 'collapsed');
      const top = standalone ? 'calc(max(env(safe-area-inset-top,0px),44px) + 8px)' : '0px';
      const bottom = expanded
        ? (standalone ? 'calc(210px + env(safe-area-inset-bottom,0px))' : '210px')
        : (standalone ? 'calc(76px + env(safe-area-inset-bottom,0px))' : '76px');
      const statusBottom = expanded
        ? (standalone ? 'calc(216px + env(safe-area-inset-bottom,0px))' : '216px')
        : (standalone ? 'calc(82px + env(safe-area-inset-bottom,0px))' : '82px');
      set(body, 'position', 'fixed'); set(body, 'inset', '0px'); set(body, 'width', '100%'); set(body, 'height', '100%');
      set(viewer, 'top', top); set(viewer, 'right', '0px'); set(viewer, 'bottom', bottom); set(viewer, 'left', '0px'); set(viewer, 'width', 'auto'); set(viewer, 'height', 'auto');
      const dock = document.getElementById('r3AudioDock');
      if (dock) set(dock, 'bottom', standalone ? 'max(6px,env(safe-area-inset-bottom,0px))' : '6px');
      const badge = document.getElementById('r3ReaderChapterBadge');
      if (badge) set(badge, 'top', standalone ? 'calc(max(env(safe-area-inset-top,0px),44px) + 18px)' : '40px');
      const topbar = document.querySelector && document.querySelector('.topbar');
      if (topbar) { set(topbar, 'top', '0px'); set(topbar, 'padding-top', standalone ? 'calc(max(env(safe-area-inset-top,0px),44px) + 8px)' : '10px'); }
      const bottomStatus = document.querySelector && document.querySelector('.bottom-status');
      if (bottomStatus) set(bottomStatus, 'bottom', statusBottom);
      const layer = document.getElementById('r3V82GestureLayer');
      if (layer) { set(layer, 'top', top); set(layer, 'bottom', statusBottom); }
      state.expanded = expanded; state.signature = signature; state.applies++; state.lastReason = String(reason || '');
      debug.geometryApplies = state.applies;
      return signature;
    }

    async function restoreAfterGeometry(anchor, reason) {
      if (!anchor || restoring || typeof bridge.display !== 'function') return;
      restoring = true;
      const priorPending = window.__R3_READER_RESTORE_PENDING;
      window.__R3_READER_RESTORE_PENDING = true;
      try {
        await paint();
        await Promise.race([Promise.resolve(bridge.display(anchor)), delay(1800)]);
        await paint();
        state.restores++; state.lastCfi = anchor; debug.geometryRestores = state.restores;
        refreshChapterUi(bridge);
      } catch {}
      finally { window.__R3_READER_RESTORE_PENDING = priorPending === true; restoring = false; }
    }

    function apply(reason='apply', preserve=false) {
      const beforeSig = state.signature;
      const anchor = preserve ? currentCfi() : '';
      const nextSig = styleGeometry(reason);
      if (preserve && anchor && nextSig !== beforeSig) {
        clearTimeout(restoreTimer);
        restoreTimer = setTimeout(() => restoreAfterGeometry(anchor, reason), 80);
      }
      return nextSig;
    }

    apply('install', false);
    try {
      const observer = new MutationObserver(records => {
        for (const record of records) {
          if (record.type === 'attributes' && record.attributeName === 'class') { apply('body-class', true); break; }
        }
      });
      observer.observe(body, { attributes: true, attributeFilter: ['class'] });
      state.observer = observer;
    } catch {}
    try { window.addEventListener('pageshow', () => apply('pageshow', false), { passive: true }); } catch {}
    try { window.addEventListener('orientationchange', () => setTimeout(() => apply('orientationchange', true), 220), { passive: true }); } catch {}
    try { document.addEventListener('visibilitychange', () => { if (!document.hidden) apply('visible', false); }); } catch {}
    state.apply = apply;
    return state;
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
    layer.style.setProperty('pointer-events', 'none', 'important');
    document.body.appendChild(layer);

    const boundFrames = new WeakSet();
    const boundDocs = new WeakSet();
    const interactiveTarget = target => {
      try { return Boolean(target && target.closest && target.closest('a,button,input,select,textarea,label,[contenteditable="true"]')); } catch { return false; }
    };
    const selectionActive = doc => {
      try { return Boolean(String(doc && doc.getSelection && doc.getSelection() || '').trim()); } catch { return false; }
    };
    function bindReaderDocument(doc) {
      if (!doc || boundDocs.has(doc)) return;
      boundDocs.add(doc);
      let sx = 0, sy = 0, st = 0, active = false, horizontal = false;
      doc.addEventListener('pointerdown', event => {
        if (event.pointerType === 'mouse' && event.button !== 0) return;
        if (interactiveTarget(event.target)) return;
        sx = event.clientX; sy = event.clientY; st = Date.now(); active = true; horizontal = false;
      }, { passive: true });
      doc.addEventListener('pointermove', event => {
        if (!active) return;
        const dx = event.clientX - sx, dy = event.clientY - sy;
        if (!horizontal && Math.abs(dx) >= 18 && Math.abs(dx) > Math.abs(dy) * 1.12) horizontal = true;
        if (horizontal && event.cancelable) event.preventDefault();
      }, { passive: false });
      doc.addEventListener('pointerup', event => {
        if (!active) return;
        const dx = event.clientX - sx, dy = event.clientY - sy, dt = Date.now() - st;
        active = false;
        if (interactiveTarget(event.target) || selectionActive(doc)) return;
        if ((horizontal || Math.abs(dx) >= 34) && Math.abs(dx) >= 34 && Math.abs(dx) > Math.abs(dy) * 1.08) {
          move(dx < 0 ? 1 : -1);
          return;
        }
        if (Math.abs(dx) < 18 && Math.abs(dy) < 18 && dt < 650) {
          const width = Math.max(1, Number(doc.defaultView && doc.defaultView.innerWidth || doc.documentElement && doc.documentElement.clientWidth || window.innerWidth));
          const ratio = event.clientX / width;
          if (document.body.dataset.nav === 'tap' && ratio < .28) move(-1);
          else if (document.body.dataset.nav === 'tap' && ratio > .72) move(1);
          else if (ratio >= .28 && ratio <= .72) document.body.classList.toggle('controls');
        }
      }, { passive: true });
      doc.addEventListener('pointercancel', () => { active = false; horizontal = false; }, { passive: true });
    }
    function bindReaderFrames() {
      for (const frame of document.querySelectorAll('#viewer iframe')) {
        if (!boundFrames.has(frame)) {
          boundFrames.add(frame);
          try { frame.addEventListener('load', () => { try { bindReaderDocument(frame.contentDocument); } catch {} }, { passive: true }); } catch {}
        }
        try { bindReaderDocument(frame.contentDocument); } catch {}
      }
    }
    bindReaderFrames();
    try {
      const viewer = document.getElementById('viewer');
      if (viewer) new MutationObserver(bindReaderFrames).observe(viewer, { childList: true, subtree: true });
    } catch {}
    try { window.addEventListener('pageshow', bindReaderFrames, { passive: true }); } catch {}
    window.__r3BindReaderFramesV91 = bindReaderFrames;
    document.addEventListener('keydown', event => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); event.stopImmediatePropagation(); move(event.key === 'ArrowRight' ? 1 : -1); } }, true);
  }

  async function finalRestore(bridge) {
    const remote = await remoteProgress();
    const target = String(remote && remote.cfi || localStorage.getItem('r3-reader-position:' + bookKey) || '');
    debug.restoreTarget = target;
    if (!target) { releaseRestoreShield('no-target'); return; }
    const priorBoot = window.__R3_BASE_READER_BOOT_DONE;
    window.__R3_BASE_READER_BOOT_DONE = false;
    window.__R3_READER_RESTORE_PENDING = true;
    try {
      await Promise.race([
        Promise.resolve(bridge.display(target)),
        delay(4500).then(() => { throw new Error('RESTORE_DISPLAY_TIMEOUT_V88'); }),
      ]);
      await paint(); await delay(90); await paint();
      debug.restoreAfter = String(bridge.current && bridge.current()?.start?.cfi || '');
      debug.restoreOk = Boolean(debug.restoreAfter);
      writeCanonicalLocal(remote);
    } catch (error) { debug.restoreError = String(error && error.message || error).slice(0, 180); }
    finally {
      window.__R3_BASE_READER_BOOT_DONE = priorBoot !== false;
      window.__R3_READER_RESTORE_PENDING = false;
      releaseRestoreShield(debug.restoreOk ? 'restore-complete' : (debug.restoreError ? 'restore-error' : 'restore-finally'));
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
    if (!bridge) { debug.restoreError = 'READER_BRIDGE_TIMEOUT_V88'; releaseRestoreShield('bridge-timeout'); return; }
    patchChapterInfo(bridge);
    installNavigation(bridge);
    const geometry = installGeometryV90(bridge);
    await waitBoot();
    geometry && geometry.apply && geometry.apply('pre-restore', false);
    await delay(120);
    await finalRestore(bridge);
    geometry && geometry.apply && geometry.apply('post-restore', false);
    refreshChapterUi(bridge);
    setInterval(() => refreshChapterUi(bridge), 1200);
  })().catch(error => { debug.error = String(error && error.message || error).slice(0, 200); releaseRestoreShield('runtime-error'); });
}

const STYLE = `<style data-r3-stable-shell-v82="1" data-r3-nonblocking-restore-v89="1">
html.r3-v82-stable #r3GestureLayer,html.r3-v82-stable .r3-hit-zone{pointer-events:none!important}
html.r3-v82-stable.r3-v90-browser body.r3-audio-ui #viewer{top:0!important;right:0!important;bottom:76px!important;left:0!important;width:auto!important;height:auto!important}
html.r3-v82-stable.r3-v90-browser body.r3-audio-ui.r3-audio-expanded #viewer{bottom:210px!important}
html.r3-v82-stable.r3-v90-home body.r3-audio-ui #viewer{top:calc(max(env(safe-area-inset-top,0px),44px) + 8px)!important;right:0!important;bottom:calc(76px + env(safe-area-inset-bottom,0px))!important;left:0!important;width:auto!important;height:auto!important}
html.r3-v82-stable.r3-v90-home body.r3-audio-ui.r3-audio-expanded #viewer{bottom:calc(210px + env(safe-area-inset-bottom,0px))!important}
html.r3-v82-stable.r3-v90-browser body.r3-audio-ui .bottom-status{bottom:82px!important}
html.r3-v82-stable.r3-v90-browser body.r3-audio-ui.r3-audio-expanded .bottom-status{bottom:216px!important}
html.r3-v82-stable.r3-v90-home body.r3-audio-ui .bottom-status{bottom:calc(82px + env(safe-area-inset-bottom,0px))!important}
html.r3-v82-stable.r3-v90-home body.r3-audio-ui.r3-audio-expanded .bottom-status{bottom:calc(216px + env(safe-area-inset-bottom,0px))!important}
html.r3-v82-stable.r3-v90-browser #r3AudioDock{bottom:6px!important}
html.r3-v82-stable.r3-v90-home #r3AudioDock{bottom:max(6px,env(safe-area-inset-bottom,0px))!important}
html.r3-v82-stable.r3-restore-pending-v45 #viewer{visibility:visible!important;opacity:1!important}
html.r3-v82-stable.r3-restore-pending-v45 #r3AudioDock{opacity:1!important;pointer-events:auto!important}
html.r3-v82-stable.r3-restore-pending-v45 body::before,html.r3-v82-stable.r3-v82-restoring body::after{content:none!important;display:none!important;pointer-events:none!important}
html.r3-v82-stable.r3-v90-home .topbar{top:0!important;padding-top:calc(max(env(safe-area-inset-top,0px),44px) + 8px)!important}
html.r3-v82-stable.r3-v90-home #r3ReaderChapterBadge{top:calc(max(env(safe-area-inset-top,0px),44px) + 18px)!important}
#r3V82GestureLayer{position:fixed;z-index:1000;left:0;right:0;top:0;bottom:82px;background:transparent;pointer-events:none!important;touch-action:auto;-webkit-user-select:none;user-select:none}
html.r3-v82-stable.r3-v90-home #r3V82GestureLayer{top:calc(max(env(safe-area-inset-top,0px),44px) + 8px)!important;bottom:calc(82px + env(safe-area-inset-bottom,0px))!important}
html.r3-v82-stable.r3-v90-browser body.r3-audio-expanded #r3V82GestureLayer{bottom:216px!important}
html.r3-v82-stable.r3-v90-home body.r3-audio-expanded #r3V82GestureLayer{bottom:calc(216px + env(safe-area-inset-bottom,0px))!important}
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
