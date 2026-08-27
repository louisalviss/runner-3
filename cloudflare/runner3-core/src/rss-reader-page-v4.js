import { renderReaderArticlePageV3 } from "./rss-reader-page-v3.js";

const READER_UX_CSS = `<style id="rss-reader-ux-v2">
.wrap{padding-bottom:calc(88px + env(safe-area-inset-bottom))!important}
.audio-slot{margin:12px 0 20px}
.audio-dock{display:grid;grid-template-columns:minmax(54px,1fr) auto;align-items:center;gap:8px;padding:7px 8px;border-radius:15px;box-shadow:none}
.audio-head{min-width:0;margin:0!important}
.audio-head strong{display:none}
.audio-state{display:block;margin:0!important;max-width:120px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px;line-height:1.2}
.audio-main{display:grid;grid-template-columns:38px 44px 38px 62px 36px;gap:5px;align-items:center}
.audio-main button,.audio-main select{height:38px;border-radius:10px}
.audio-main .play{width:44px;height:44px;border-radius:13px}
#audioDock #rateDown,#audioDock #rateUp{display:none}
#audioDock .rate{width:62px;min-width:62px;padding:0 3px;font-size:14px}
#audioMore{width:36px;padding:0;font-size:18px;letter-spacing:1px;line-height:1}
.audio-extra{grid-column:1/-1;display:none;margin-top:3px;gap:6px;flex-wrap:wrap}
.audio-extra #rateHint{display:none}
.audio-dock.expanded{grid-template-columns:1fr;padding:9px}
.audio-dock.expanded .audio-head{display:flex}
.audio-dock.expanded .audio-head strong{display:block}
.audio-dock.expanded .audio-state{margin-left:auto!important;max-width:58%}
.audio-dock.expanded .audio-main{grid-template-columns:38px 44px 38px 30px minmax(66px,78px) 30px 36px;justify-content:start}
.audio-dock.expanded #rateDown,.audio-dock.expanded #rateUp{display:flex}
.audio-dock.expanded .rate{width:100%;min-width:66px}
.audio-dock.expanded .audio-extra{display:flex!important}
.audio-dock.fixed{display:grid;grid-template-columns:minmax(48px,1fr) auto;align-items:center;gap:8px;left:50%;bottom:calc(7px + env(safe-area-inset-bottom));width:min(calc(100% - 20px),720px);padding:6px 7px;border-radius:17px;background:#101010ed;box-shadow:0 8px 28px #0008}
.audio-dock.fixed .audio-head{margin:0!important}
.audio-dock.fixed .audio-state{margin:0!important;max-width:100px}
.audio-dock.fixed:not(.expanded) .audio-extra{display:none!important}
.audio-dock.fixed.expanded{grid-template-columns:1fr;padding:9px}
.toast{bottom:calc(82px + env(safe-area-inset-bottom))}
@media(max-width:430px){
  .wrap{padding-left:13px;padding-right:13px;padding-bottom:calc(84px + env(safe-area-inset-bottom))!important}
  .audio-dock{grid-template-columns:minmax(44px,1fr) auto;gap:6px;padding:6px 7px}
  .audio-state{max-width:78px}
  .audio-main{grid-template-columns:36px 42px 36px 58px 34px;gap:4px}
  .audio-main button,.audio-main select{height:36px}
  .audio-main .play{width:42px;height:42px}
  #audioDock .rate{width:58px;min-width:58px;font-size:13px}
  #audioMore{width:34px}
  .audio-dock.fixed{width:calc(100% - 18px);grid-template-columns:minmax(40px,1fr) auto;gap:5px;padding:6px}
  .audio-dock.fixed .audio-state{max-width:70px}
  .audio-dock.expanded .audio-main{grid-template-columns:36px 42px 36px 28px minmax(62px,72px) 28px 34px;gap:4px}
}
</style>`;

const READER_UX_SCRIPT = `<script id="rss-reader-ux-v2-script">
(function(){
  var dock=document.querySelector('#audioDock');
  var main=dock&&dock.querySelector('.audio-main');
  if(!dock||!main||document.querySelector('#audioMore'))return;

  var more=document.createElement('button');
  more.type='button';
  more.id='audioMore';
  more.setAttribute('aria-label','Tuỳ chọn audio');
  more.setAttribute('aria-expanded','false');
  more.textContent='⋯';
  main.append(more);

  more.addEventListener('click',function(){
    var expanded=dock.classList.toggle('expanded');
    more.setAttribute('aria-expanded',expanded?'true':'false');
    more.textContent=expanded?'×':'⋯';
  });

  try{
    if(typeof chooseVoice==='function'){
      chooseVoice=function(){
        if(!('speechSynthesis' in window))return null;
        var voices=speechSynthesis.getVoices();
        var wanted=activeKind==='vi'?'vi-vn':'en-us';
        var prefix=activeKind==='vi'?'vi':'en';
        var matches=voices.filter(function(v){return String(v.lang||'').toLowerCase().indexOf(prefix)===0});
        matches.sort(function(a,b){
          function score(v){
            var lang=String(v.lang||'').toLowerCase();
            var name=String(v.name||'').toLowerCase();
            var n=0;
            if(lang===wanted)n+=8;
            if(v.localService)n+=3;
            if(name.indexOf('premium')>=0||name.indexOf('enhanced')>=0||name.indexOf('siri')>=0)n+=4;
            return n;
          }
          return score(b)-score(a);
        });
        return matches[0]||null;
      };
    }
  }catch(e){}
})();
</script>`;

function injectBefore(html, marker, value) {
  const index = html.lastIndexOf(marker);
  if (index < 0) return html;
  return html.slice(0, index) + value + html.slice(index);
}

export function repairGeneratedReaderHtml(html) {
  let source = String(html || "");
  const broken = "normalized.split(/\n{2,}/)";
  const fixed = "normalized.split('\\n\\n')";
  if (source.includes(broken)) source = source.replace(broken, fixed);
  if (!source.includes('id="rss-reader-ux-v2"')) {
    source = injectBefore(source, "</head>", READER_UX_CSS);
    source = injectBefore(source, "</body>", READER_UX_SCRIPT);
  }
  return source;
}

export async function renderReaderArticlePageV4(request, url) {
  const response = renderReaderArticlePageV3(request, url);
  if (!response) return null;
  const html = repairGeneratedReaderHtml(await response.text());
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  headers.set("cache-control", "no-store");
  headers.set("content-type", "text/html; charset=utf-8");
  return new Response(html, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
