import { renderReaderArticlePageV6 } from "./rss-reader-page-v6.js";

const READY_CSS = `<style id="rss-reader-nam-minh-ready-v3">
#audioDock[data-engine="nam-minh-stream"] .audio-state{max-width:180px}
#audioDock[data-engine="nam-minh-stream"].fixed .audio-state{max-width:128px}
@media(max-width:430px){#audioDock[data-engine="nam-minh-stream"] .audio-state{max-width:112px}#audioDock[data-engine="nam-minh-stream"].fixed .audio-state{max-width:94px}}
</style>`;

const READY_SCRIPT = `<script id="rss-reader-nam-minh-ready-v3-script">
(function(){
  var dock=document.querySelector('#audioDock');
  var audio=document.querySelector('#rssNamMinhAudio');
  var playButton=document.querySelector('#playAudio');
  var rateSelect=document.querySelector('#rate');
  var viButton=document.querySelector('#vi');
  var originalButton=document.querySelector('#original');
  if(!dock||!audio||!playButton)return;

  dock.setAttribute('data-engine','nam-minh-stream');
  var loadedView='';
  var loadedMediaUrl='';
  var preparePromise=null;
  var stopped=false;

  function currentView(){
    try{return typeof activeKind!=='undefined'&&activeKind==='original'?'original':'vi'}catch(e){return 'vi'}
  }
  function articleId(){
    var parts=String(location.pathname||'').split('/');
    var value=parts.length>3?parts[3]:'';
    try{return decodeURIComponent(value)}catch(e){return ''}
  }
  function readerToken(){return localStorage.getItem('rssReaderToken')||''}
  function endpoint(view){
    return '/reader/rss/articles/'+encodeURIComponent(articleId())+'/audio?view='+encodeURIComponent(view||currentView());
  }
  function state(label){
    var el=document.querySelector('#audioState');
    if(el)el.textContent=label||'Nam Minh';
  }
  function icon(playing){
    try{if(typeof setIcon==='function')setIcon(playButton,playing?'pause':'play')}catch(e){}
  }
  function rateValue(){
    var value=rateSelect?Number(rateSelect.value||1):1;
    return Math.max(.5,Math.min(2.5,Number.isFinite(value)?value:1));
  }
  async function request(path,opt){
    var headers=Object.assign({Authorization:'Bearer '+readerToken()},opt&&opt.headers||{});
    return fetch(path,Object.assign({},opt||{},{headers:headers}));
  }
  async function readState(method,view){
    var opt={method:method||'GET'};
    if(method==='POST'){
      opt.headers={'Content-Type':'application/json'};
      opt.body=JSON.stringify({view:view||currentView()});
    }
    var response=await request(endpoint(view),opt);
    var data=await response.json().catch(function(){return {}});
    if(!response.ok)throw new Error(data.error||String(response.status));
    return data;
  }
  function clearMedia(){
    audio.pause();
    loadedView='';
    loadedMediaUrl='';
    try{audio.removeAttribute('src');audio.load()}catch(e){}
    icon(false);
  }
  function assignMedia(info,view){
    view=view||currentView();
    var url=String(info&&info.mediaUrl||'');
    if(!url)throw new Error('AUDIO_MEDIA_URL_MISSING');
    if(audio.src&&loadedView===view&&loadedMediaUrl===url)return true;
    clearMedia();
    loadedView=view;
    loadedMediaUrl=url;
    audio.preload='metadata';
    audio.playbackRate=rateValue();
    audio.src=url;
    audio.load();
    state('Nam Minh · sẵn sàng');
    return true;
  }
  async function waitUntilReady(view){
    view=view||currentView();
    var started=Date.now();
    while(!stopped&&Date.now()-started<20*60*1000){
      var info=await readState('GET',view);
      var status=String(info.status||'missing');
      if(status==='ready'){
        assignMedia(info,view);
        state('Nam Minh · sẵn sàng · bấm ▶');
        return true;
      }
      if(status==='error')throw new Error(info.error||'Không thể tạo audio');
      state(status==='processing'?'Nam Minh · đang tạo…':'Nam Minh · đang chờ…');
      await new Promise(function(resolve){setTimeout(resolve,1800)});
    }
    if(!stopped)state('Nam Minh · vẫn đang tạo…');
    return false;
  }
  function prepare(view){
    if(preparePromise)return preparePromise;
    preparePromise=waitUntilReady(view).catch(function(error){
      state('Audio lỗi');
      try{if(typeof showToast==='function')showToast(error&&error.message?error.message:'Không tạo được audio')}catch(e){}
      return false;
    }).finally(function(){preparePromise=null});
    return preparePromise;
  }
  async function refresh(){
    var view=currentView();
    try{
      var info=await readState('GET',view);
      var status=String(info.status||'missing');
      if(status==='ready'){
        assignMedia(info,view);
        state('Nam Minh · sẵn sàng');
      }else if(status==='processing'||status==='pending'){
        state(status==='processing'?'Nam Minh · đang tạo…':'Nam Minh · đang chờ…');
        prepare(view);
      }else state('Nam Minh');
    }catch(e){state('Nam Minh')}
  }
  async function startOrPlay(){
    var view=currentView();
    try{
      if(audio.src&&loadedView===view){
        if(!audio.paused){audio.pause();icon(false);return}
        audio.playbackRate=rateValue();
        state('Nam Minh · bắt đầu…');
        var result=audio.play();
        if(result&&typeof result.then==='function')await result;
        return;
      }

      var info=await readState('GET',view);
      var status=String(info.status||'missing');
      if(status==='ready'){
        assignMedia(info,view);
        state('Nam Minh · sẵn sàng · bấm ▶');
        return;
      }

      if(status==='missing'||status==='error'){
        state('Nam Minh · chuẩn bị…');
        info=await readState('POST',view);
        status=String(info.status||'pending');
      }
      state(status==='processing'?'Nam Minh · đang tạo…':'Nam Minh · đang chờ…');
      prepare(view);
    }catch(error){
      icon(false);
      state('Audio lỗi');
      try{if(typeof showToast==='function')showToast(error&&error.message?error.message:'Không phát được audio')}catch(e){}
    }
  }

  playButton.onclick=startOrPlay;
  try{togglePlay=startOrPlay;speakCurrent=startOrPlay}catch(e){}

  audio.addEventListener('loadstart',function(){if(loadedMediaUrl&&audio.paused)state('Nam Minh · kết nối…')});
  audio.addEventListener('loadedmetadata',function(){if(audio.paused)state('Nam Minh · sẵn sàng')});
  audio.addEventListener('canplay',function(){if(audio.paused)state('Nam Minh · sẵn sàng')});
  audio.addEventListener('playing',function(){icon(true);state('Nam Minh · đang đọc')});
  audio.addEventListener('play',function(){icon(true)});
  audio.addEventListener('pause',function(){icon(false);if(!audio.ended&&loadedMediaUrl)state('Nam Minh · tạm dừng')});
  audio.addEventListener('waiting',function(){if(!audio.paused)state('Nam Minh · đang đệm…')});
  audio.addEventListener('stalled',function(){if(!audio.paused)state('Nam Minh · mạng chậm…')});
  audio.addEventListener('ended',function(){icon(false);state('Nam Minh · đã đọc xong')});
  audio.addEventListener('error',function(){if(audio.src){icon(false);state('Audio lỗi')}});
  if(rateSelect)rateSelect.addEventListener('change',function(){audio.playbackRate=rateValue()});

  function viewChanged(){
    setTimeout(function(){
      clearMedia();
      preparePromise=null;
      refresh();
    },120);
  }
  if(viButton)viButton.addEventListener('click',viewChanged);
  if(originalButton)originalButton.addEventListener('click',viewChanged);

  window.addEventListener('pagehide',function(){stopped=true;clearMedia()});

  var waitCount=0;
  var wait=setInterval(function(){
    waitCount+=1;
    try{
      if(typeof artifact!=='undefined'&&artifact){clearInterval(wait);refresh()}
      else if(waitCount>60)clearInterval(wait);
    }catch(e){if(waitCount>60)clearInterval(wait)}
  },150);
})();
</script>`;

function injectBefore(html, marker, value) {
  const index = html.lastIndexOf(marker);
  if (index < 0) return html;
  return html.slice(0, index) + value + html.slice(index);
}

export function addReliableNamMinhPlayback(html) {
  let source = String(html || "");
  if (!source.includes('id="rss-reader-nam-minh-ready-v3"')) {
    source = injectBefore(source, "</head>", READY_CSS);
    source = injectBefore(source, "</body>", READY_SCRIPT);
  }
  return source;
}

export async function renderReaderArticlePageV7(request, url) {
  const response = await renderReaderArticlePageV6(request, url);
  if (!response) return null;
  const html = addReliableNamMinhPlayback(await response.text());
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
