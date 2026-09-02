import app from "./artifact-library-simple-entry.js";

const ROOT = "core/ebook/";
const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

function headers(base = {}) {
  const h = new Headers(base);
  h.set("X-Robots-Tag", ROBOTS);
  h.set("Cache-Control", "private, no-store, max-age=0");
  h.set("Pragma", "no-cache");
  h.set("Referrer-Policy", "no-referrer");
  h.set("X-Frame-Options", "DENY");
  return h;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: headers({ "Content-Type": "application/json; charset=utf-8" }),
  });
}

function isFinalEpub(key) {
  return typeof key === "string" && key.startsWith(ROOT) && key.includes("/final/") && key.toLowerCase().endsWith(".epub");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function displayName(key) {
  const raw = String(key).split("/").filter(Boolean).pop() || "EPUB";
  try { return decodeURIComponent(raw).replace(/\.epub$/i, ""); } catch { return raw.replace(/\.epub$/i, ""); }
}

function readerPage(key) {
  const safeTitle = escapeHtml(displayName(key));
  const keyJson = JSON.stringify(key).replaceAll("<", "\\u003c");
  return `<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive,nosnippet,noimageindex">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>${safeTitle}</title>
<style>
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--bg:#f7f5ef;--fg:#1d1c1a;--panel:rgba(252,251,248,.96);--line:rgba(40,38,34,.18);--muted:#77736b;--shadow:0 14px 45px rgba(0,0,0,.18)}*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--fg);overscroll-behavior:none}body{position:fixed;inset:0;width:100%;height:100dvh;background:var(--bg)}body[data-theme="dark"]{--bg:#0b0d10;--fg:#edf0f3;--panel:rgba(20,23,28,.96);--line:rgba(240,244,248,.16);--muted:#a2a8b1;--shadow:0 14px 50px rgba(0,0,0,.5)}body[data-theme="brown"]{--bg:#e9dcc0;--fg:#49382a;--panel:rgba(241,229,204,.97);--line:rgba(83,61,42,.2);--muted:#806c58;--shadow:0 14px 45px rgba(73,54,37,.2)}#viewer{position:absolute;inset:0;background:var(--bg);overflow:hidden;touch-action:pan-y}#loading{position:absolute;inset:0;display:grid;place-items:center;padding:28px;color:var(--muted);font-size:13px;text-align:center;z-index:2;pointer-events:none}.hidden{display:none!important}.chrome{position:fixed;inset:0;z-index:20;pointer-events:none;opacity:0;transition:opacity .16s ease}.chrome::before{content:"";position:absolute;inset:0;background:linear-gradient(to bottom,rgba(0,0,0,.18),transparent 18%,transparent 82%,rgba(0,0,0,.14));pointer-events:none}body.controls .chrome{opacity:1}.topbar{position:absolute;left:0;right:0;top:0;padding:max(10px,env(safe-area-inset-top)) 12px 10px;display:flex;align-items:center;justify-content:space-between;gap:10px;pointer-events:none}.topbar>*{pointer-events:auto}.round,.back{appearance:none;border:1px solid var(--line);background:var(--panel);color:var(--fg);height:42px;border-radius:13px;display:inline-flex;align-items:center;justify-content:center;box-shadow:var(--shadow);text-decoration:none;font:inherit;font-weight:750}.round{width:42px;padding:0;font-size:21px}.back{padding:0 13px;font-size:13px}.book-title{position:absolute;left:78px;right:78px;text-align:center;color:var(--fg);font-size:12px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-shadow:0 1px 6px rgba(255,255,255,.5)}body[data-theme="dark"] .book-title{text-shadow:0 1px 6px rgba(0,0,0,.7)}.bottom-status{position:absolute;left:50%;bottom:max(10px,env(safe-area-inset-bottom));transform:translateX(-50%);background:var(--panel);border:1px solid var(--line);box-shadow:var(--shadow);border-radius:999px;padding:7px 11px;color:var(--muted);font-size:11px;white-space:nowrap;pointer-events:none}.sheet{position:fixed;z-index:30;left:10px;right:10px;bottom:calc(max(10px,env(safe-area-inset-bottom)) + 4px);max-width:520px;margin:0 auto;background:var(--panel);border:1px solid var(--line);box-shadow:var(--shadow);border-radius:20px;padding:14px 14px 16px;transform:translateY(calc(100% + 40px));opacity:0;transition:transform .18s ease,opacity .18s ease;pointer-events:none;backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)}body.settings .sheet{transform:translateY(0);opacity:1;pointer-events:auto}.sheet-head{display:flex;align-items:center;justify-content:space-between;margin:0 0 10px}.sheet-head b{font-size:14px}.close{appearance:none;border:0;background:transparent;color:var(--muted);font-size:24px;padding:4px 7px}.section{border-top:1px solid var(--line);padding-top:11px;margin-top:11px}.label{font-size:11px;color:var(--muted);font-weight:700;margin-bottom:8px}.seg{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:6px}.choice{appearance:none;border:1px solid var(--line);background:transparent;color:var(--fg);border-radius:10px;min-height:38px;padding:7px 8px;font:inherit;font-size:12px;font-weight:700}.choice.active{background:var(--fg);color:var(--bg)}.fontrow{display:grid;grid-template-columns:44px 1fr 44px;gap:8px;align-items:center}.fontbtn{appearance:none;border:1px solid var(--line);background:transparent;color:var(--fg);border-radius:10px;height:38px;font:inherit;font-size:16px;font-weight:800}.fontvalue{text-align:center;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}.theme-dot{display:inline-block;width:13px;height:13px;border-radius:50%;vertical-align:-2px;margin-right:5px;border:1px solid var(--line)}.theme-dot.light{background:#faf9f5}.theme-dot.dark{background:#111318}.theme-dot.brown{background:#b98d5d}.tap-hint{position:fixed;z-index:5;inset:0;pointer-events:none;opacity:0;transition:opacity .2s}.tap-hint span{position:absolute;top:50%;transform:translateY(-50%);color:var(--muted);font-size:11px;background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:6px 8px}.tap-hint .left{left:10px}.tap-hint .right{right:10px}body.controls[data-nav="tap"] .tap-hint{opacity:.72}@media(min-width:700px){.sheet{left:50%;right:auto;width:500px;transform:translate(-50%,calc(100% + 40px))}body.settings .sheet{transform:translate(-50%,0)}}
</style>
</head>
<body data-theme="light" data-nav="swipe">
<main id="viewer"><div id="loading">Đang mở EPUB…</div></main>
<div class="tap-hint" aria-hidden="true"><span class="left">‹ chạm</span><span class="right">chạm ›</span></div>
<div class="chrome" id="chrome">
  <div class="topbar"><a class="back" href="/artifact-library">‹ Library</a><div class="book-title">${safeTitle}</div><button id="settingsButton" class="round" type="button" aria-label="Cài đặt">⚙</button></div>
  <div id="position" class="bottom-status">Đang mở…</div>
</div>
<section id="settingsSheet" class="sheet" aria-label="Reader settings">
  <div class="sheet-head"><b>Cài đặt đọc</b><button id="closeSettings" class="close" type="button" aria-label="Đóng">×</button></div>
  <div class="section" style="border-top:0;padding-top:0;margin-top:0"><div class="label">Chuyển trang</div><div class="seg"><button class="choice nav-choice" data-nav="swipe" type="button">Vuốt</button><button class="choice nav-choice" data-nav="tap" type="button">Chạm trái / phải</button></div></div>
  <div class="section"><div class="label">Giao diện</div><div class="seg"><button class="choice theme-choice" data-theme="light" type="button"><span class="theme-dot light"></span>Sáng</button><button class="choice theme-choice" data-theme="dark" type="button"><span class="theme-dot dark"></span>Tối</button><button class="choice theme-choice" data-theme="brown" type="button"><span class="theme-dot brown"></span>Nâu</button></div></div>
  <div class="section"><div class="label">Cỡ chữ</div><div class="fontrow"><button id="fontDown" class="fontbtn" type="button">A−</button><div id="fontValue" class="fontvalue">100%</div><button id="fontUp" class="fontbtn" type="button">A+</button></div></div>
  <div class="section"><div class="label">Lề trang</div><div class="seg"><button class="choice margin-choice" data-margin="2" type="button">Hẹp</button><button class="choice margin-choice" data-margin="5" type="button">Vừa</button><button class="choice margin-choice" data-margin="9" type="button">Rộng</button></div></div>
  <div class="section"><div class="label">Dãn dòng</div><div class="seg"><button class="choice line-choice" data-line="1.35" type="button">1.35</button><button class="choice line-choice" data-line="1.55" type="button">1.55</button><button class="choice line-choice" data-line="1.8" type="button">1.8</button><button class="choice line-choice" data-line="2" type="button">2.0</button></div></div>
</section>
<script src="/artifact-library/vendor/jszip.min.js"></script>
<script src="/artifact-library/vendor/epub.min.js"></script>
<script>
(() => {
  const key=${keyJson};
  const keys={
    font:'r3-reader-font-size',theme:'r3-reader-theme',nav:'r3-reader-navigation',margin:'r3-reader-margin',line:'r3-reader-line-height',position:'r3-reader-position:'+key
  };
  const valid=(v,a,f)=>a.includes(v)?v:f;
  let font=Math.min(180,Math.max(70,parseInt(localStorage.getItem(keys.font)||'100',10)||100));
  let theme=valid(localStorage.getItem(keys.theme),['light','dark','brown'],'light');
  let nav=valid(localStorage.getItem(keys.nav),['swipe','tap'],'swipe');
  let margin=Number(valid(localStorage.getItem(keys.margin),['2','5','9'],'5'));
  let line=Number(valid(localStorage.getItem(keys.line),['1.35','1.55','1.8','2'],'1.55'));
  let book=null,rendition=null,hideTimer=0,lastTouchAt=0;
  const $=id=>document.getElementById(id);

  function persist(k,v){try{localStorage.setItem(k,String(v));}catch{}}
  function resetHide(){clearTimeout(hideTimer);if(!document.body.classList.contains('settings')&&document.body.classList.contains('controls'))hideTimer=setTimeout(hideControls,3000);}
  function showControls(){document.body.classList.add('controls');resetHide();}
  function hideControls(){clearTimeout(hideTimer);document.body.classList.remove('controls','settings');}
  function toggleControls(){if(document.body.classList.contains('controls'))hideControls();else showControls();}
  function openSettings(){document.body.classList.add('controls','settings');clearTimeout(hideTimer);}
  function closeSettings(){document.body.classList.remove('settings');resetHide();}

  function syncUi(){
    document.body.dataset.theme=theme;document.body.dataset.nav=nav;
    $('fontValue').textContent=font+'%';
    document.querySelectorAll('.theme-choice').forEach(b=>b.classList.toggle('active',b.dataset.theme===theme));
    document.querySelectorAll('.nav-choice').forEach(b=>b.classList.toggle('active',b.dataset.nav===nav));
    document.querySelectorAll('.margin-choice').forEach(b=>b.classList.toggle('active',Number(b.dataset.margin)===margin));
    document.querySelectorAll('.line-choice').forEach(b=>b.classList.toggle('active',Number(b.dataset.line)===line));
  }

  function registerThemes(){
    rendition.themes.register('light',{'html,body':{'background':'#f7f5ef !important','color':'#1d1c1a !important'},'a':{'color':'#365b7b !important'}});
    rendition.themes.register('dark',{'html,body':{'background':'#0b0d10 !important','color':'#edf0f3 !important'},'a':{'color':'#8eb9e4 !important'}});
    rendition.themes.register('brown',{'html,body':{'background':'#e9dcc0 !important','color':'#49382a !important'},'a':{'color':'#765432 !important'}});
  }

  function applyReaderSettings(){
    syncUi();
    if(!rendition)return;
    rendition.themes.select(theme);
    rendition.themes.fontSize(font+'%');
    rendition.themes.override('line-height',String(line),true);
    rendition.themes.override('padding-left',margin+'%',true);
    rendition.themes.override('padding-right',margin+'%',true);
    rendition.themes.override('margin-left','0',true);
    rendition.themes.override('margin-right','0',true);
  }

  function pagePrev(){if(rendition)rendition.prev();hideControls();}
  function pageNext(){if(rendition)rendition.next();hideControls();}
  function targetIsInteractive(target){return !!(target&&target.closest&&target.closest('a,button,input,textarea,select,label'))}
  function actTap(x,width,target){
    if(targetIsInteractive(target))return;
    const ratio=x/Math.max(1,width);
    if(nav==='tap'){
      if(ratio<.33){pagePrev();return;}
      if(ratio>.67){pageNext();return;}
    }
    if(ratio>=.33&&ratio<=.67)toggleControls();
  }

  function bindGestureTarget(doc, widthFn){
    if(!doc||doc.documentElement?.dataset?.r3GestureV2==='1')return;
    if(doc.documentElement)doc.documentElement.dataset.r3GestureV2='1';
    let sx=0,sy=0,st=0,target=null;
    doc.addEventListener('touchstart',e=>{const t=e.changedTouches&&e.changedTouches[0];if(!t)return;sx=t.clientX;sy=t.clientY;st=Date.now();target=e.target;},{passive:true});
    doc.addEventListener('touchend',e=>{
      const t=e.changedTouches&&e.changedTouches[0];if(!t)return;lastTouchAt=Date.now();
      const dx=t.clientX-sx,dy=t.clientY-sy,dt=Date.now()-st;
      if(nav==='swipe'&&Math.abs(dx)>=38&&Math.abs(dx)>Math.abs(dy)*1.12){dx<0?pageNext():pagePrev();return;}
      if(Math.abs(dx)<18&&Math.abs(dy)<18&&dt<650)actTap(t.clientX,widthFn(),target);
    },{passive:true});
    doc.addEventListener('click',e=>{if(Date.now()-lastTouchAt<700)return;actTap(e.clientX,widthFn(),e.target);});
  }

  function bindEpubContents(){
    if(!rendition)return;
    let contents=[];try{contents=rendition.getContents()||[];}catch{}
    contents.forEach(c=>{try{bindGestureTarget(c.document,()=>c.window?.innerWidth||c.document?.documentElement?.clientWidth||window.innerWidth);}catch{}});
  }

  async function signedUrl(){
    const r=await fetch('/artifact-library/api/delivery',{method:'POST',headers:{'content-type':'application/json','x-runner3-library':'1'},body:JSON.stringify({key,ttl_seconds:3600})});
    const data=await r.json();if(!r.ok||data.ok!==true||!data.delivery?.url)throw new Error(data.error||('HTTP '+r.status));return data.delivery.url;
  }

  async function openBook(){
    try{
      if(typeof window.ePub!=='function')throw new Error('Reader engine failed to load');
      const url=await signedUrl();
      const response=await fetch(url);if(!response.ok)throw new Error('EPUB HTTP '+response.status);
      const buffer=await response.arrayBuffer();
      book=window.ePub(buffer);
      rendition=book.renderTo('viewer',{width:'100%',height:'100%',spread:'none',flow:'paginated',manager:'default'});
      registerThemes();applyReaderSettings();
      rendition.on('rendered',()=>{bindEpubContents();$('loading').classList.add('hidden');});
      rendition.on('relocated',loc=>{const cfi=loc?.start?.cfi;if(cfi)persist(keys.position,cfi);const pct=Number.isFinite(loc?.start?.percentage)?Math.round(loc.start.percentage*100):null;$('position').textContent=pct===null?'Đã lưu vị trí':pct+'% · đã lưu';setTimeout(bindEpubContents,0);});
      const saved=localStorage.getItem(keys.position)||'';
      window.__R3_BASE_READER_BOOT_PENDING=true;
      window.__R3_BASE_READER_BOOT_DONE=false;
      window.__r3BaseReaderBootV47={phase:'display',target:saved||'',startedAt:Date.now(),after:'',error:''};
      try{
        await rendition.display(saved||undefined);
      }catch(error){
        window.__r3BaseReaderBootV47.error=String(error&&error.message||error||'display failed').slice(0,180);
        localStorage.removeItem(keys.position);
        await rendition.display();
      }
      // Do not reveal the reader merely because currentLocation() looked stable for a moment.
      // The authoritative signal is the resolved display() promise plus two paint frames.
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      try{
        const loc=rendition&&rendition.currentLocation&&rendition.currentLocation();
        window.__r3BaseReaderBootV47.after=String(loc&&loc.start&&loc.start.cfi||'');
      }catch{}
      window.__r3BaseReaderBootV47.phase='done';
      window.__r3BaseReaderBootV47.finishedAt=Date.now();
      window.__R3_BASE_READER_BOOT_PENDING=false;
      window.__R3_BASE_READER_BOOT_DONE=true;
      try{window.dispatchEvent(new CustomEvent('r3-base-reader-boot-done-v47',{detail:{target:saved||'',cfi:window.__r3BaseReaderBootV47.after||''}}));}catch{}
      bindEpubContents();$('loading').classList.add('hidden');
    }catch(error){$('loading').classList.remove('hidden');$('loading').textContent='Không mở được EPUB: '+String(error?.message||error);$('position').textContent='Reader error';showControls();}
  }

  $('settingsButton').addEventListener('click',e=>{e.stopPropagation();openSettings();});
  $('closeSettings').addEventListener('click',closeSettings);
  $('fontDown').addEventListener('click',()=>{font=Math.max(70,font-10);persist(keys.font,font);applyReaderSettings();});
  $('fontUp').addEventListener('click',()=>{font=Math.min(180,font+10);persist(keys.font,font);applyReaderSettings();});
  document.querySelectorAll('.theme-choice').forEach(b=>b.addEventListener('click',()=>{theme=b.dataset.theme;persist(keys.theme,theme);applyReaderSettings();}));
  document.querySelectorAll('.nav-choice').forEach(b=>b.addEventListener('click',()=>{nav=b.dataset.nav;persist(keys.nav,nav);applyReaderSettings();}));
  document.querySelectorAll('.margin-choice').forEach(b=>b.addEventListener('click',()=>{margin=Number(b.dataset.margin);persist(keys.margin,margin);applyReaderSettings();}));
  document.querySelectorAll('.line-choice').forEach(b=>b.addEventListener('click',()=>{line=Number(b.dataset.line);persist(keys.line,line);applyReaderSettings();}));
  $('settingsSheet').addEventListener('click',()=>{clearTimeout(hideTimer);});

  bindGestureTarget(document,()=>window.innerWidth);
  document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')pagePrev();if(e.key==='ArrowRight')pageNext();if(e.key==='Escape')hideControls();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)hideControls();});
  window.addEventListener('beforeunload',()=>{try{book?.destroy();}catch{}});
  syncUi();hideControls();openBook();
})();
</script>
</body>
</html>`;
}

async function reader(request, env) {
  if (request.method !== "GET") return json({ ok: false, error: "METHOD_NOT_ALLOWED" }, 405);
  const url = new URL(request.url);
  const key = String(url.searchParams.get("key") || "");
  if (!isFinalEpub(key)) return new Response(null, { status: 303, headers: headers({ Location: "/artifact-library" }) });
  if (!env.ARTIFACTS) return json({ ok: false, error: "ARTIFACTS_BINDING_MISSING" }, 503);
  const object = await env.ARTIFACTS.head(key);
  if (!object) return json({ ok: false, error: "EPUB_NOT_FOUND" }, 404);
  return new Response(readerPage(key), {
    status: 200,
    headers: headers({
      "Content-Type": "text/html; charset=utf-8",
      "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self' https:; img-src 'self' data: blob:; font-src 'self' data: blob:; media-src 'self' data: blob:; frame-src 'self' blob:; child-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    }),
  });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/artifact-library/read") return reader(request, env);
    return app.fetch(request, env, ctx);
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
