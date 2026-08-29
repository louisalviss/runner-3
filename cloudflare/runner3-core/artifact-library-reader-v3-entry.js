import app from "./artifact-library-reader-v2-entry.js";

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

function injectReliableTouchLayer(html) {
  if (!html.includes('id="viewer"') || html.includes('data-r3-touch-layer-v3="1"')) return html;

  const patch = `<style data-r3-touch-layer-v3="1">
#r3GestureLayer{position:fixed;inset:0;z-index:19;background:transparent;pointer-events:auto;touch-action:none;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none}
body.controls .topbar,body.controls .bottom-status{z-index:21}
body.settings #settingsSheet{z-index:30}
</style>
<div id="r3GestureLayer" aria-hidden="true"></div>
<script data-r3-touch-layer-v3="1">
(()=>{
  const layer=document.getElementById('r3GestureLayer');
  const sheet=document.getElementById('settingsSheet');
  if(!layer)return;
  let sx=0,sy=0,st=0,lastTouch=0,hideTimer=0;

  const navMode=()=>document.body.dataset.nav==='tap'?'tap':'swipe';
  const fireKey=key=>document.dispatchEvent(new KeyboardEvent('keydown',{key,bubbles:true}));
  const prev=()=>fireKey('ArrowLeft');
  const next=()=>fireKey('ArrowRight');

  function clearHide(){if(hideTimer){clearTimeout(hideTimer);hideTimer=0;}}
  function hideControls(){clearHide();document.body.classList.remove('controls','settings');}
  function scheduleHide(){
    clearHide();
    if(document.body.classList.contains('controls')||document.body.classList.contains('settings')){
      hideTimer=setTimeout(hideControls,2000);
    }
  }
  function showControls(){document.body.classList.add('controls');scheduleHide();}
  function toggleControls(){
    if(document.body.classList.contains('settings')){hideControls();return;}
    if(document.body.classList.contains('controls'))hideControls();else showControls();
  }

  function actTap(x){
    // When settings are open, any tap outside the panel closes everything immediately.
    if(document.body.classList.contains('settings')){hideControls();return;}
    const ratio=x/Math.max(1,window.innerWidth);
    if(navMode()==='tap'){
      if(ratio<.33){prev();hideControls();return;}
      if(ratio>.67){next();hideControls();return;}
    }
    // Middle third always controls the reader chrome, independent of EPUB iframe content.
    if(ratio>=.33&&ratio<=.67)toggleControls();
  }

  layer.addEventListener('touchstart',e=>{
    const t=e.changedTouches&&e.changedTouches[0];if(!t)return;
    sx=t.clientX;sy=t.clientY;st=Date.now();
    if(document.body.classList.contains('controls')||document.body.classList.contains('settings'))scheduleHide();
  },{passive:true});

  layer.addEventListener('touchmove',e=>{
    if(e.cancelable)e.preventDefault();
  },{passive:false});

  layer.addEventListener('touchend',e=>{
    const t=e.changedTouches&&e.changedTouches[0];if(!t)return;
    lastTouch=Date.now();
    const dx=t.clientX-sx,dy=t.clientY-sy,dt=Date.now()-st;
    if(document.body.classList.contains('settings')){
      if(e.cancelable)e.preventDefault();
      hideControls();
      return;
    }
    if(navMode()==='swipe'&&Math.abs(dx)>=34&&Math.abs(dx)>Math.abs(dy)*1.05){
      if(e.cancelable)e.preventDefault();
      dx<0?next():prev();hideControls();return;
    }
    if(Math.abs(dx)<20&&Math.abs(dy)<20&&dt<700)actTap(t.clientX);
  },{passive:false});

  layer.addEventListener('click',e=>{
    if(Date.now()-lastTouch<800)return;
    actTap(e.clientX);
  });

  // Settings panel is above the gesture layer. Any interaction inside it keeps it alive for 2s.
  if(sheet){
    const keepAlive=e=>{e.stopPropagation();scheduleHide();};
    sheet.addEventListener('touchstart',keepAlive,{passive:true});
    sheet.addEventListener('click',keepAlive);
  }

  // Authoritative timer: controls and the settings panel both auto-hide after 2s idle.
  const observer=new MutationObserver(()=>{
    if(document.body.classList.contains('controls')||document.body.classList.contains('settings'))scheduleHide();
    else clearHide();
  });
  observer.observe(document.body,{attributes:true,attributeFilter:['class']});

  window.addEventListener('beforeunload',()=>{clearHide();observer.disconnect();},{once:true});
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
    const updated = injectReliableTouchLayer(original);
    const h = new Headers(response.headers);
    h.delete("Content-Length");
    h.set("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self' https:; img-src 'self' data: blob:; font-src 'self' data: blob:; media-src 'self' data: blob:; frame-src 'self' blob:; child-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'");
    return new Response(updated, { status: response.status, headers: h });
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
