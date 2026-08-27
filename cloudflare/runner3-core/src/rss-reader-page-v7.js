import { renderReaderArticlePageV6 } from "./rss-reader-page-v6.js";

const READY_CSS = `<style id="rss-reader-nam-minh-ready-v3">
#audioDock[data-engine="nam-minh-ready"] .audio-state{max-width:180px}
#audioDock[data-engine="nam-minh-ready"].fixed .audio-state{max-width:128px}
@media(max-width:430px){#audioDock[data-engine="nam-minh-ready"] .audio-state{max-width:112px}#audioDock[data-engine="nam-minh-ready"].fixed .audio-state{max-width:94px}}
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

  dock.setAttribute('data-engine','nam-minh-ready');
  var mediaObjectUrl='';
  var loadedView='';
  var preloadPromise=null;
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
  function endpoint(suffix,view){
    return '/reader/rss/articles/'+encodeURIComponent(articleId())+'/audio'+(suffix||'')+'?view='+encodeURIComponent(view||currentView());
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
    var response=await request(endpoint('',view),opt);
    var data=await response.json().catch(function(){return {}});
    if(!response.ok)throw new Error(data.error||String(response.status));
    return data;
  }
  function clearMedia(){
    audio.pause();
    if(mediaObjectUrl){URL.revokeObjectURL(mediaObjectUrl);mediaObjectUrl=''}
    loadedView='';
    try{audio.removeAttribute('src');audio.load()}catch(e){}
    icon(false);
  }
  async function preload(view){
    view=view||currentView();
    if(audio.src&&loadedView===view)return true;
    if(preloadPromise)return preloadPromise;
    preloadPromise=(async function(){
      state('Nam Minh · đang tải…');
      var response=await request(endpoint('/media',view),{method:'GET'});
      if(!response.ok){
        var data=await response.json().catch(function(){return {}});
        throw new Error(data.error||String(response.status));
      }
      var blob=await response.blob();
      if(stopped)return false;
      clearMedia();
      mediaObjectUrl=URL.createObjectURL(blob);
      loadedView=view;
      audio.src=mediaObjectUrl;
      audio.preload='auto';
      audio.playbackRate=rateValue();
      await new Promise(function(resolve,reject){
        var done=false;
        function finish(ok){
          if(done)return;done=true;
          audio.removeEventListener('loadedmetadata',onMeta);
          audio.removeEventListener('canplay',onMeta);
          audio.removeEventListener('error',onError);
          ok?resolve():reject(new Error('MP3 không phát được'));
        }
        function onMeta(){finish(true)}
        function onError(){finish(false)}
        audio.addEventListener('loadedmetadata',onMeta);
        audio.addEventListener('canplay',onMeta);
        audio.addEventListener('error',onError);
        audio.load();
        setTimeout(function(){if(!done&&audio.readyState>=1)finish(true)},2500);
      });
      state('Nam Minh · sẵn sàng');
      return true;
    })();
    try{return await preloadPromise}finally{preloadPromise=null}
  }
  async function waitUntilReady(view){
    view=view||currentView();
    var started=Date.now();
    while(!stopped&&Date.now()-started<20*60*1000){
      var info=await readState('GET',view);
      var status=String(info.status||'missing');
      if(status==='ready'){
        await preload(view);
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
        await preload(view);
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
        var result=audio.play();
        if(result&&typeof result.then==='function')await result;
        icon(true);
        return;
      }

      var info=await readState('GET',view);
      var status=String(info.status||'missing');
      if(status==='ready'){
        await preload(view);
        try{
          audio.playbackRate=rateValue();
          var playResult=audio.play();
          if(playResult&&typeof playResult.then==='function')await playResult;
          icon(true);
        }catch(playError){
          icon(false);
          state('Nam Minh · sẵn sàng · bấm ▶');
        }
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

  audio.addEventListener('play',function(){icon(true)});
  audio.addEventListener('pause',function(){icon(false)});
  audio.addEventListener('ended',function(){icon(false);state('Nam Minh · đã đọc xong')});

  function viewChanged(){
    setTimeout(function(){
      clearMedia();
      preloadPromise=null;
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
