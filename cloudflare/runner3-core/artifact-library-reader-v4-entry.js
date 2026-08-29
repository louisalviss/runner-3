import app from "./artifact-library-reader-v2-entry.js";

const ROBOTS = "noindex, nofollow, noarchive, nosnippet, noimageindex";

function injectHitZones(html) {
  if (!html.includes('id="viewer"') || html.includes('data-r3-hit-zones-v4="1"')) return html;

  const patch = `<style data-r3-hit-zones-v4="1">
.r3-hit-zone{position:fixed;top:0;bottom:0;height:100dvh;z-index:19;margin:0;padding:0;border:0;border-radius:0;outline:0;-webkit-appearance:none;appearance:none;background:rgba(255,255,255,.001);color:transparent;font-size:0;touch-action:none;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;cursor:default}
#r3HitLeft{left:0;width:33.3334vw}
#r3HitCenter{left:33.3333vw;width:33.3334vw}
#r3HitRight{right:0;width:33.3334vw}
body.controls .chrome{z-index:20}
body.settings #settingsSheet{z-index:30}
</style>
<button id="r3HitLeft" class="r3-hit-zone" type="button" aria-label="Vùng trang trước" tabindex="-1"></button>
<button id="r3HitCenter" class="r3-hit-zone" type="button" aria-label="Vùng điều khiển" tabindex="-1"></button>
<button id="r3HitRight" class="r3-hit-zone" type="button" aria-label="Vùng trang sau" tabindex="-1"></button>
<script data-r3-hit-zones-v4="1">
(()=>{
  const body=document.body;
  const zones=[
    {el:document.getElementById('r3HitLeft'),side:'left'},
    {el:document.getElementById('r3HitCenter'),side:'center'},
    {el:document.getElementById('r3HitRight'),side:'right'}
  ];
  const sheet=document.getElementById('settingsSheet');
  const topbar=document.querySelector('.topbar');
  let idleTimer=0;
  let suppressClickUntil=0;

  const navMode=()=>body.dataset.nav==='tap'?'tap':'swipe';
  const fireKey=key=>document.dispatchEvent(new KeyboardEvent('keydown',{key,bubbles:true}));
  const prev=()=>fireKey('ArrowLeft');
  const next=()=>fireKey('ArrowRight');

  function clearIdle(){if(idleTimer){clearTimeout(idleTimer);idleTimer=0;}}
  function hideAll(){clearIdle();body.classList.remove('controls','settings');}
  function armIdle(){
    clearIdle();
    if(body.classList.contains('controls')||body.classList.contains('settings')) idleTimer=setTimeout(hideAll,2000);
  }
  function showChrome(){body.classList.add('controls');armIdle();}
  function toggleChrome(){
    if(body.classList.contains('settings')){hideAll();return;}
    if(body.classList.contains('controls')) hideAll(); else showChrome();
  }

  function simpleTap(side){
    if(body.classList.contains('settings')){hideAll();return;}
    if(side==='center'){toggleChrome();return;}
    if(navMode()==='tap'){
      side==='left'?prev():next();
      hideAll();
    }
  }

  function bindZone(el,side){
    if(!el)return;
    let sx=0,sy=0,st=0,pid=null;

    el.addEventListener('pointerdown',e=>{
      if(e.pointerType==='mouse'&&e.button!==0)return;
      sx=e.clientX;sy=e.clientY;st=Date.now();pid=e.pointerId;
      try{el.setPointerCapture(e.pointerId);}catch{}
      if(body.classList.contains('controls')||body.classList.contains('settings'))armIdle();
    });

    el.addEventListener('pointerup',e=>{
      if(pid!==null&&e.pointerId!==pid)return;
      const dx=e.clientX-sx,dy=e.clientY-sy,dt=Date.now()-st;
      try{el.releasePointerCapture(e.pointerId);}catch{}
      pid=null;
      if(body.classList.contains('settings')){
        suppressClickUntil=Date.now()+500;
        hideAll();
        return;
      }
      if(navMode()==='swipe'&&Math.abs(dx)>=34&&Math.abs(dx)>Math.abs(dy)*1.05){
        suppressClickUntil=Date.now()+500;
        dx<0?next():prev();
        hideAll();
        return;
      }
      if(Math.abs(dx)<18&&Math.abs(dy)<18&&dt<700){
        suppressClickUntil=Date.now()+350;
        simpleTap(side);
      }
    });

    el.addEventListener('pointercancel',e=>{try{el.releasePointerCapture(e.pointerId);}catch{}pid=null;});

    // Click is the reliability fallback: these are real HTML buttons above the EPUB iframe.
    el.addEventListener('click',e=>{
      e.preventDefault();
      if(Date.now()<suppressClickUntil)return;
      simpleTap(side);
    });

    // iOS fallback for WebKit builds where Pointer Events are delayed or coalesced oddly.
    let tx=0,ty=0,tt=0;
    el.addEventListener('touchstart',e=>{
      if(typeof PointerEvent==='function')return;
      const t=e.changedTouches&&e.changedTouches[0];if(!t)return;
      tx=t.clientX;ty=t.clientY;tt=Date.now();
    },{passive:true});
    el.addEventListener('touchend',e=>{
      if(typeof PointerEvent==='function')return;
      const t=e.changedTouches&&e.changedTouches[0];if(!t)return;
      const dx=t.clientX-tx,dy=t.clientY-ty,dt=Date.now()-tt;
      if(body.classList.contains('settings')){hideAll();return;}
      if(navMode()==='swipe'&&Math.abs(dx)>=34&&Math.abs(dx)>Math.abs(dy)*1.05){dx<0?next():prev();hideAll();return;}
      if(Math.abs(dx)<18&&Math.abs(dy)<18&&dt<700)simpleTap(side);
    },{passive:true});
  }

  zones.forEach(z=>bindZone(z.el,z.side));

  // Any interaction inside the visible UI keeps it alive for two seconds.
  const keepAlive=e=>{e.stopPropagation();armIdle();};
  if(sheet){sheet.addEventListener('pointerdown',keepAlive);sheet.addEventListener('click',keepAlive);}
  if(topbar){topbar.addEventListener('pointerdown',keepAlive);topbar.addEventListener('click',keepAlive);}

  // Authoritative idle timer, including the settings sheet itself.
  const observer=new MutationObserver(()=>{
    if(body.classList.contains('controls')||body.classList.contains('settings'))armIdle();
    else clearIdle();
  });
  observer.observe(body,{attributes:true,attributeFilter:['class']});

  window.addEventListener('beforeunload',()=>{clearIdle();observer.disconnect();},{once:true});
})();
</script>`;

  return html.replace("</body>", patch + "</body>");
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const response = await app.fetch(request, env, ctx);
    if (url.pathname !== "/artifact-library/read" || request.method !== "GET") return response;
    const type = response.headers.get("Content-Type") || "";
    if (!type.toLowerCase().includes("text/html")) return response;
    const original = await response.text();
    const updated = injectHitZones(original);
    const h = new Headers(response.headers);
    h.delete("Content-Length");
    h.set("X-Robots-Tag", ROBOTS);
    h.set("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self' https:; img-src 'self' data: blob:; font-src 'self' data: blob:; media-src 'self' data: blob:; frame-src 'self' blob:; child-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'");
    return new Response(updated, { status: response.status, headers: h });
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
