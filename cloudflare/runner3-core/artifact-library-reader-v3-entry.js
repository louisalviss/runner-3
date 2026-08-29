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
  if (!html.includes('id="viewer"') || html.includes('data-r3-touch-layer-v4="1"')) return html;

  const patch = `<style data-r3-touch-layer-v4="1">
#r3GestureLayer{position:fixed;left:0;top:0;width:100vw;height:100dvh;z-index:1000;background:rgba(0,0,0,.001);pointer-events:auto;touch-action:none;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;transform:translateZ(0)}
.chrome{z-index:1100!important}
body.settings #settingsSheet{z-index:1200!important}
</style>
<div id="r3GestureLayer" aria-hidden="true"></div>
<script data-r3-touch-layer-v4="1">
(()=>{
  const layer=document.getElementById('r3GestureLayer');
  const sheet=document.getElementById('settingsSheet');
  if(!layer)return;

  let sx=0,sy=0,st=0,active=false,pointerId=null,lastPointerUp=0,hideTimer=0;
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
    if(document.body.classList.contains('settings')){hideControls();return;}
    const ratio=x/Math.max(1,window.innerWidth);
    if(navMode()==='tap'){
      if(ratio<.33){prev();hideControls();return;}
      if(ratio>.67){next();hideControls();return;}
    }
    // The middle third always reveals/hides the reader chrome and gear button.
    if(ratio>=.33&&ratio<=.67)toggleControls();
  }

  function begin(x,y,id){
    sx=x;sy=y;st=Date.now();active=true;pointerId=id??null;
    if(document.body.classList.contains('controls')||document.body.classList.contains('settings'))scheduleHide();
  }
  function finish(x,y){
    if(!active)return;
    active=false;lastPointerUp=Date.now();
    const dx=x-sx,dy=y-sy,dt=Date.now()-st;
    if(document.body.classList.contains('settings')){hideControls();return;}
    if(navMode()==='swipe'&&Math.abs(dx)>=34&&Math.abs(dx)>Math.abs(dy)*1.05){
      dx<0?next():prev();hideControls();return;
    }
    if(Math.abs(dx)<20&&Math.abs(dy)<20&&dt<700)actTap(x);
  }

  // Pointer Events are the primary path on modern iPhone WebKit/Chrome/Safari.
  if('PointerEvent' in window){
    layer.addEventListener('pointerdown',e=>{
      if(e.pointerType==='mouse'&&e.button!==0)return;
      begin(e.clientX,e.clientY,e.pointerId);
      try{layer.setPointerCapture(e.pointerId);}catch{}
      if(e.cancelable)e.preventDefault();
    },{passive:false});
    layer.addEventListener('pointermove',e=>{
      if(!active||pointerId!==e.pointerId)return;
      if(e.cancelable)e.preventDefault();
    },{passive:false});
    layer.addEventListener('pointerup',e=>{
      if(!active||pointerId!==e.pointerId)return;
      if(e.cancelable)e.preventDefault();
      finish(e.clientX,e.clientY);
      try{layer.releasePointerCapture(e.pointerId);}catch{}
      pointerId=null;
    },{passive:false});
    layer.addEventListener('pointercancel',()=>{active=false;pointerId=null;});
  }else{
    // Fallback for older WebKit.
    layer.addEventListener('touchstart',e=>{
      const t=e.changedTouches&&e.changedTouches[0];if(!t)return;
      begin(t.clientX,t.clientY,null);
      if(e.cancelable)e.preventDefault();
    },{passive:false});
    layer.addEventListener('touchmove',e=>{if(e.cancelable)e.preventDefault();},{passive:false});
    layer.addEventListener('touchend',e=>{
      const t=e.changedTouches&&e.changedTouches[0];if(!t)return;
      if(e.cancelable)e.preventDefault();
      finish(t.clientX,t.clientY);
    },{passive:false});
  }

  // Desktop/click fallback; suppressed after a pointer/touch release.
  layer.addEventListener('click',e=>{
    if(Date.now()-lastPointerUp<800)return;
    actTap(e.clientX);
  });

  // The panel lives above the gesture layer; interaction inside keeps it open briefly.
  if(sheet){
    const keepAlive=e=>{e.stopPropagation();scheduleHide();};
    sheet.addEventListener('pointerdown',keepAlive);
    sheet.addEventListener('touchstart',keepAlive,{passive:true});
    sheet.addEventListener('click',keepAlive);
  }

  // Settings and chrome both disappear after 2 seconds of no interaction.
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
