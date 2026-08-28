import { renderReaderArticlePageV6 } from "./rss-reader-page-v6.js";

const PLAYER_CSS = `<style id="rss-reader-nam-minh-v8">
#audioDock[data-engine="nam-minh-v8"] .audio-state{max-width:190px}
#audioDock[data-engine="nam-minh-v8"].fixed .audio-state{max-width:140px}
@media(max-width:430px){#audioDock[data-engine="nam-minh-v8"] .audio-state{max-width:118px}#audioDock[data-engine="nam-minh-v8"].fixed .audio-state{max-width:100px}}
</style>`;

const PLAYER_SCRIPT = `<script id="rss-reader-nam-minh-v8-script">
(function(){
  var legacyDock=document.querySelector('#audioDock');
  var legacyAudio=document.querySelector('#rssNamMinhAudio');
  if(!legacyDock)return;

  var dock=legacyDock.cloneNode(true);
  legacyDock.replaceWith(dock);
  dock.setAttribute('data-engine','nam-minh-v8');

  var audio=document.createElement('audio');
  audio.id='rssNamMinhAudio';
  audio.preload='none';
  audio.setAttribute('playsinline','');
  audio.style.display='none';
  if(legacyAudio){legacyAudio.replaceWith(audio)}else{document.body.appendChild(audio)}

  var playButton=dock.querySelector('#playAudio');
  var prevButton=dock.querySelector('#prevAudio');
  var nextButton=dock.querySelector('#nextAudio');
  var stopButton=dock.querySelector('#stopAudio');
  var downButton=dock.querySelector('#rateDown');
  var upButton=dock.querySelector('#rateUp');
  var rateSelect=dock.querySelector('#rate');
  var highlightButton=dock.querySelector('#highlightToggle');
  var stateEl=dock.querySelector('#audioState');
  if(!playButton||!stateEl)return;

  var readyInfo=null;
  var readyView='';
  var loadedView='';
  var polling=false;
  var stopped=false;
  var timingRows=[];
  var timingView='';
  var lastParagraph=-1;

  function currentView(){
    try{return typeof activeKind!=='undefined'&&activeKind==='original'?'original':'vi'}catch(e){return 'vi'}
  }
  function articleId(){
    var parts=String(location.pathname||'').split('/');
    var value=parts.length>3?parts[3]:'';
    try{return decodeURIComponent(value)}catch(e){return ''}
  }
  function readerToken(){return localStorage.getItem('rssReaderToken')||''}
  function statusUrl(view){return '/reader/rss/articles/'+encodeURIComponent(articleId())+'/audio?view='+encodeURIComponent(view||currentView())}
  function timingUrl(view){return '/reader/rss/articles/'+encodeURIComponent(articleId())+'/audio/timing?view='+encodeURIComponent(view||currentView())}
  function state(label){stateEl.textContent=label||'Nam Minh'}
  function icon(playing){try{if(typeof setIcon==='function')setIcon(playButton,playing?'pause':'play')}catch(e){}}
  function toast(message){try{if(typeof showToast==='function')showToast(message)}catch(e){}}
  function rateValue(){
    var value=rateSelect?Number(rateSelect.value||1):1;
    return Math.max(.5,Math.min(2.5,Number.isFinite(value)?value:1));
  }
  function formatTime(value){
    var n=Math.max(0,Number(value||0));
    var m=Math.floor(n/60),s=Math.floor(n%60);
    return m+':'+String(s).padStart(2,'0');
  }
  async function request(url,opt){
    var headers=Object.assign({Authorization:'Bearer '+readerToken()},opt&&opt.headers||{});
    return fetch(url,Object.assign({},opt||{},{headers:headers}));
  }
  async function readState(method,view){
    var opt={method:method||'GET'};
    if(method==='POST'){
      opt.headers={'Content-Type':'application/json'};
      opt.body=JSON.stringify({view:view||currentView()});
    }
    var response=await request(statusUrl(view),opt);
    var data=await response.json().catch(function(){return {}});
    if(!response.ok)throw new Error(data.error||String(response.status));
    return data;
  }
  function rememberReady(info,view){
    if(!info||String(info.status||'')!=='ready'||!info.mediaUrl)return false;
    readyInfo=info;
    readyView=view||currentView();
    return true;
  }
  function resetMedia(){
    audio.pause();
    loadedView='';
    try{audio.removeAttribute('src');audio.load()}catch(e){}
    icon(false);
  }
  function mediaErrorLabel(){
    var code=audio&&audio.error?Number(audio.error.code||0):0;
    return code?'Audio lỗi E'+code:'Audio lỗi';
  }
  function playInstalled(){
    audio.playbackRate=rateValue();
    state('Nam Minh · bắt đầu…');
    var result;
    try{result=audio.play()}catch(error){state(mediaErrorLabel());toast(error&&error.message?error.message:'Không phát được audio');return}
    if(result&&typeof result.catch==='function')result.catch(function(error){
      icon(false);
      if(error&&error.name==='NotAllowedError')state('Nam Minh · bấm ▶ lại');
      else{state(mediaErrorLabel());toast(error&&error.message?error.message:'Không phát được audio')}
    });
  }
  function installAndPlay(info,view){
    var mediaUrl=String(info&&info.mediaUrl||'');
    if(!mediaUrl){state('Audio lỗi · thiếu URL');return}
    resetMedia();
    loadedView=view||currentView();
    audio.preload='auto';
    audio.src=mediaUrl;
    playInstalled();
  }
  async function loadTiming(view){
    view=view||currentView();
    if(timingRows.length&&timingView===view)return timingRows;
    var response=await request(timingUrl(view),{method:'GET'});
    if(!response.ok)return [];
    var data=await response.json().catch(function(){return {}});
    timingRows=(Array.isArray(data.paragraphs)?data.paragraphs:[]).filter(function(row){
      return row&&Number.isFinite(Number(row.start))&&Number.isFinite(Number(row.end));
    }).map(function(row){return {index:Number(row.index),start:Number(row.start),end:Number(row.end)}});
    timingView=view;
    return timingRows;
  }
  function paragraphAt(time){
    if(!timingRows.length)return -1;
    var value=Math.max(0,Number(time||0)),low=0,high=timingRows.length-1,best=0;
    while(low<=high){var mid=(low+high)>>1;if(timingRows[mid].start<=value){best=mid;low=mid+1}else high=mid-1}
    return best;
  }
  function highlightNow(scroll){
    try{
      if(typeof highlightEnabled==='undefined'||!highlightEnabled||!timingRows.length||typeof paragraphs==='undefined'||!paragraphs.length)return;
      var rowIndex=paragraphAt(audio.currentTime);if(rowIndex<0)return;
      var row=timingRows[rowIndex];var index=Number.isFinite(row.index)?row.index:rowIndex;
      index=Math.max(0,Math.min(paragraphs.length-1,index));
      if(index===lastParagraph&&paragraphs[index].classList.contains('reading'))return;
      lastParagraph=index;
      for(var i=0;i<paragraphs.length;i++)paragraphs[i].classList.toggle('reading',i===index);
      if(scroll!==false){var el=paragraphs[index],rect=el.getBoundingClientRect();if(rect.top<80||rect.bottom>innerHeight-dock.offsetHeight-28)el.scrollIntoView({behavior:'smooth',block:'center'})}
    }catch(e){}
  }
  async function poll(view){
    if(polling)return;
    polling=true;
    try{
      while(!stopped){
        var info=await readState('GET',view);
        var status=String(info.status||'missing');
        if(status==='ready'){
          if(rememberReady(info,view))state('Nam Minh · sẵn sàng · bấm ▶');
          else state('Audio lỗi · thiếu URL');
          return;
        }
        if(status==='error')throw new Error(info.error||'Không thể tạo audio');
        state(status==='processing'?'Nam Minh · đang tạo…':'Nam Minh · đang chờ…');
        await new Promise(function(resolve){setTimeout(resolve,1800)});
      }
    }catch(error){state('Audio lỗi');toast(error&&error.message?error.message:'Không tạo được audio')}
    finally{polling=false}
  }
  async function resolveStateFromTap(view){
    try{
      var info=await readState('GET',view);
      var status=String(info.status||'missing');
      if(status==='ready'){
        if(rememberReady(info,view))state('Nam Minh · sẵn sàng · bấm ▶');
        else state('Audio lỗi · thiếu URL');
        return;
      }
      if(status==='missing'||status==='error'){
        state('Nam Minh · chuẩn bị…');
        info=await readState('POST',view);
        status=String(info.status||'pending');
      }
      state(status==='processing'?'Nam Minh · đang tạo…':'Nam Minh · đang chờ…');
      poll(view);
    }catch(error){state('Audio lỗi');toast(error&&error.message?error.message:'Không chuẩn bị được audio')}
  }
  function handlePlay(event){
    if(event){event.preventDefault();event.stopPropagation()}
    var view=currentView();
    if(audio.src&&loadedView===view){
      if(!audio.paused){audio.pause();return}
      playInstalled();
      return;
    }
    if(readyInfo&&readyView===view&&readyInfo.mediaUrl){
      installAndPlay(readyInfo,view);
      return;
    }
    state('Nam Minh · kiểm tra…');
    resolveStateFromTap(view);
  }
  function jump(delta){
    if(!audio.src)return handlePlay();
    if(timingRows.length){
      var current=paragraphAt(audio.currentTime);var next=Math.max(0,Math.min(timingRows.length-1,current+delta));
      audio.currentTime=Math.max(0,Number(timingRows[next].start||0)+0.01);highlightNow(true);return;
    }
    if(Number.isFinite(audio.duration))audio.currentTime=Math.max(0,Math.min(audio.duration,audio.currentTime+delta*15));
  }
  function stop(){audio.pause();if(Number.isFinite(audio.duration))audio.currentTime=0;icon(false);state(readyInfo?'Nam Minh · sẵn sàng':'Nam Minh')}
  function changeRate(value){
    var next=Math.round(Math.max(.5,Math.min(2.5,Number(value||1)))*100)/100;
    if(rateSelect){
      var found=false;for(var i=0;i<rateSelect.options.length;i++)if(Math.abs(Number(rateSelect.options[i].value)-next)<.001)found=true;
      if(!found){var option=document.createElement('option');option.value=String(next);option.textContent=next.toFixed(2)+'×';rateSelect.appendChild(option)}
      rateSelect.value=String(next);
    }
    audio.playbackRate=next;
  }
  async function refresh(){
    var view=currentView();
    readyInfo=null;readyView='';timingRows=[];timingView='';lastParagraph=-1;resetMedia();
    try{
      var info=await readState('GET',view);var status=String(info.status||'missing');
      if(status==='ready'){
        if(rememberReady(info,view))state('Nam Minh · sẵn sàng');
        else state('Audio lỗi · thiếu URL');
      }else if(status==='processing'||status==='pending'){
        state(status==='processing'?'Nam Minh · đang tạo…':'Nam Minh · đang chờ…');poll(view);
      }else state('Nam Minh');
    }catch(e){state('Nam Minh')}
  }

  playButton.onclick=null;
  playButton.addEventListener('click',handlePlay);
  if(prevButton){prevButton.onclick=null;prevButton.addEventListener('click',function(e){e.preventDefault();jump(-1)})}
  if(nextButton){nextButton.onclick=null;nextButton.addEventListener('click',function(e){e.preventDefault();jump(1)})}
  if(stopButton){stopButton.onclick=null;stopButton.addEventListener('click',function(e){e.preventDefault();stop()})}
  if(rateSelect){rateSelect.onchange=function(){changeRate(rateSelect.value)}}
  if(downButton){downButton.onclick=function(){changeRate(rateValue()-.05)}}
  if(upButton){upButton.onclick=function(){changeRate(rateValue()+.05)}}
  if(highlightButton){highlightButton.onclick=function(){try{highlightEnabled=!highlightEnabled;highlightButton.classList.toggle('on',highlightEnabled);if(!highlightEnabled&&typeof clearHighlight==='function')clearHighlight();else highlightNow(true)}catch(e){}}}

  audio.addEventListener('loadstart',function(){state('Nam Minh · kết nối…')});
  audio.addEventListener('loadedmetadata',function(){state('Nam Minh · sẵn sàng');loadTiming(loadedView).then(function(){highlightNow(false)}).catch(function(){})});
  audio.addEventListener('canplay',function(){if(audio.paused)state('Nam Minh · sẵn sàng')});
  audio.addEventListener('playing',function(){icon(true);state('Nam Minh · đang đọc');loadTiming(loadedView).catch(function(){})});
  audio.addEventListener('pause',function(){icon(false);if(audio.src&&!audio.ended)state('Nam Minh · tạm dừng')});
  audio.addEventListener('timeupdate',function(){if(!audio.paused&&Number.isFinite(audio.duration))state('Nam Minh · '+formatTime(audio.currentTime)+' / '+formatTime(audio.duration));highlightNow(true)});
  audio.addEventListener('waiting',function(){if(!audio.paused)state('Nam Minh · đang đệm…')});
  audio.addEventListener('stalled',function(){if(!audio.paused)state('Nam Minh · mạng chậm…')});
  audio.addEventListener('error',function(){if(audio.src){icon(false);readyInfo=null;readyView='';state(mediaErrorLabel()+' · bấm lại')}});
  audio.addEventListener('ended',function(){icon(false);state('Nam Minh · đã đọc xong')});

  var viButton=document.querySelector('#vi'),originalButton=document.querySelector('#original');
  function viewChanged(){setTimeout(refresh,120)}
  if(viButton)viButton.addEventListener('click',viewChanged);
  if(originalButton)originalButton.addEventListener('click',viewChanged);
  window.addEventListener('pagehide',function(){stopped=true;resetMedia()});

  var count=0,timer=setInterval(function(){
    count+=1;
    try{if(typeof artifact!=='undefined'&&artifact){clearInterval(timer);refresh()}else if(count>60)clearInterval(timer)}catch(e){if(count>60)clearInterval(timer)}
  },150);
})();
</script>`;

function injectBefore(html, marker, value) {
  const index = html.lastIndexOf(marker);
  if (index < 0) return html;
  return html.slice(0, index) + value + html.slice(index);
}

export function addIsolatedNamMinhPlayer(html) {
  let source = String(html || "");
  if (!source.includes('id="rss-reader-nam-minh-v8"')) {
    source = injectBefore(source, "</head>", PLAYER_CSS);
    source = injectBefore(source, "</body>", PLAYER_SCRIPT);
  }
  return source;
}

export async function renderReaderArticlePageV8(request, url) {
  const response = await renderReaderArticlePageV6(request, url);
  if (!response) return null;
  const html = addIsolatedNamMinhPlayer(await response.text());
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
