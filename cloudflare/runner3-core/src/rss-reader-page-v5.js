import { renderReaderArticlePageV4 } from "./rss-reader-page-v4.js";

const NAM_MINH_CSS = `<style id="rss-reader-nam-minh-v1">
#audioDock[data-engine="nam-minh"] .audio-state{max-width:150px}
#audioDock[data-engine="nam-minh"].fixed .audio-state{max-width:112px}
#audioDock[data-engine="nam-minh"] #highlightToggle:after{content:""}
@media(max-width:430px){#audioDock[data-engine="nam-minh"] .audio-state{max-width:90px}#audioDock[data-engine="nam-minh"].fixed .audio-state{max-width:78px}}
</style>`;

const NAM_MINH_SCRIPT = `<script id="rss-reader-nam-minh-v1-script">
(function(){
  var dock=document.querySelector('#audioDock');
  var playButton=document.querySelector('#playAudio');
  var prevButton=document.querySelector('#prevAudio');
  var nextButton=document.querySelector('#nextAudio');
  var stopButton=document.querySelector('#stopAudio');
  var downButton=document.querySelector('#rateDown');
  var upButton=document.querySelector('#rateUp');
  if(!dock||!playButton||!prevButton||!nextButton||!stopButton||!rate)return;

  dock.setAttribute('data-engine','nam-minh');
  var audio=document.createElement('audio');
  audio.id='rssNamMinhAudio';
  audio.preload='metadata';
  audio.setAttribute('playsinline','');
  audio.style.display='none';
  document.body.appendChild(audio);

  var objectUrl='';
  var loadedView='';
  var loadingPromise=null;
  var pollTimer=0;
  var statusState='missing';

  function token(){return localStorage.getItem(KEY)||''}
  function endpoint(suffix){
    return '/reader/rss/articles/'+encodeURIComponent(id)+'/audio'+(suffix||'')+'?view='+encodeURIComponent(activeKind||'vi');
  }
  function formatTime(value){
    var n=Math.max(0,Number(value||0));
    var m=Math.floor(n/60);
    var s=Math.floor(n%60);
    return m+':'+String(s).padStart(2,'0');
  }
  function namState(label){updateAudioState(label||'Nam Minh')}
  function setPlay(playing){setIcon(playButton,playing?'pause':'play')}
  function revoke(){
    if(objectUrl){URL.revokeObjectURL(objectUrl);objectUrl=''}
    audio.removeAttribute('src');
    audio.load();
    loadedView='';
  }
  async function raw(path,opt){
    var headers=Object.assign({Authorization:'Bearer '+token()},opt&&opt.headers||{});
    return fetch(path,Object.assign({},opt||{},{headers:headers}));
  }
  async function stateRequest(method){
    var opt={method:method||'GET'};
    if(method==='POST'){
      opt.headers={'Content-Type':'application/json'};
      opt.body=JSON.stringify({view:activeKind||'vi'});
    }
    var response=await raw(endpoint(''),opt);
    var data=await response.json().catch(function(){return {}});
    if(!response.ok)throw new Error(data.error||String(response.status));
    return data;
  }
  function stopPolling(){if(pollTimer){clearTimeout(pollTimer);pollTimer=0}}
  async function pollReady(){
    stopPolling();
    var started=Date.now();
    while(Date.now()-started<240000){
      var state=await stateRequest('GET');
      statusState=state.status||'missing';
      if(statusState==='ready')return state;
      if(statusState==='error')throw new Error(state.error||'Không thể tạo audio');
      namState(statusState==='processing'?'Nam Minh · đang tạo…':'Nam Minh · đang chờ…');
      await new Promise(function(resolve){pollTimer=setTimeout(resolve,1400)});
      pollTimer=0;
    }
    throw new Error('Audio tạo quá lâu');
  }
  async function ensureReady(){
    var state=await stateRequest('GET');
    statusState=state.status||'missing';
    if(statusState==='ready')return state;
    if(statusState==='missing'||statusState==='error'){
      namState('Nam Minh · chuẩn bị…');
      state=await stateRequest('POST');
      statusState=state.status||'pending';
    }
    return pollReady();
  }
  async function loadAudio(){
    if(audio.src&&loadedView===(activeKind||'vi'))return audio;
    if(loadingPromise)return loadingPromise;
    loadingPromise=(async function(){
      await ensureReady();
      namState('Nam Minh · đang tải…');
      var response=await raw(endpoint('/media'),{method:'GET'});
      if(!response.ok){
        var data=await response.json().catch(function(){return {}});
        throw new Error(data.error||String(response.status));
      }
      var blob=await response.blob();
      revoke();
      objectUrl=URL.createObjectURL(blob);
      loadedView=activeKind||'vi';
      audio.src=objectUrl;
      audio.playbackRate=currentRate();
      await new Promise(function(resolve,reject){
        if(Number.isFinite(audio.duration)&&audio.duration>0)return resolve();
        var done=false;
        function ok(){if(done)return;done=true;cleanup();resolve()}
        function bad(){if(done)return;done=true;cleanup();reject(new Error('MP3 không phát được'))}
        function cleanup(){audio.removeEventListener('loadedmetadata',ok);audio.removeEventListener('error',bad)}
        audio.addEventListener('loadedmetadata',ok,{once:true});
        audio.addEventListener('error',bad,{once:true});
        audio.load();
      });
      return audio;
    })();
    try{return await loadingPromise}finally{loadingPromise=null}
  }
  function segmentWeight(index){return Math.max(1,String(segments[index]&&segments[index].text||'').length)}
  function totalWeight(){var total=0;for(var i=0;i<segments.length;i++)total+=segmentWeight(i);return Math.max(1,total)}
  function segmentAtTime(){
    if(!segments.length||!Number.isFinite(audio.duration)||audio.duration<=0)return 0;
    var target=(audio.currentTime/audio.duration)*totalWeight();
    var sum=0;
    for(var i=0;i<segments.length;i++){sum+=segmentWeight(i);if(target<=sum)return i}
    return segments.length-1;
  }
  function segmentStart(index){
    if(!Number.isFinite(audio.duration)||audio.duration<=0||!segments.length)return 0;
    var sum=0;
    for(var i=0;i<Math.max(0,index);i++)sum+=segmentWeight(i);
    return audio.duration*(sum/totalWeight());
  }
  function syncProgress(){
    if(Number.isFinite(audio.duration)&&audio.duration>0){
      audioIndex=segmentAtTime();
      if(highlightEnabled&&segments[audioIndex])highlightSegment(segments[audioIndex]);
      namState('Nam Minh · '+formatTime(audio.currentTime)+' / '+formatTime(audio.duration));
    }else namState('Nam Minh');
  }
  async function namToggle(){
    try{
      if(audio.src&&!audio.paused){audio.pause();return}
      await loadAudio();
      audio.playbackRate=currentRate();
      await audio.play();
    }catch(e){setPlay(false);namState('Audio lỗi');showToast(e&&e.message?e.message:'Không phát được audio')}
  }
  function namStop(reset){
    stopPolling();
    audio.pause();
    if(reset!==false&&Number.isFinite(audio.duration))audio.currentTime=0;
    setPlay(false);
    clearHighlight();
    if(reset!==false)namState(statusState==='ready'?'Nam Minh · sẵn sàng':'Nam Minh');
  }
  function namJump(delta){
    if(!audio.src||!Number.isFinite(audio.duration)||!segments.length)return namToggle();
    var current=segmentAtTime();
    var next=Math.max(0,Math.min(segments.length-1,current+delta));
    audio.currentTime=segmentStart(next);
    audioIndex=next;
    if(highlightEnabled&&segments[next])highlightSegment(segments[next]);
    if(audio.paused)audio.play().catch(function(){});
  }
  function namRate(value){
    var next=Math.round(Math.max(.5,Math.min(2.5,Number(value||1)))*100)/100;
    ensureRateOption(next);
    audio.playbackRate=next;
    syncProgress();
  }
  async function refreshStatus(){
    try{
      var state=await stateRequest('GET');
      statusState=state.status||'missing';
      if(statusState==='ready')namState('Nam Minh · sẵn sàng');
      else if(statusState==='processing')namState('Nam Minh · đang tạo…');
      else if(statusState==='pending')namState('Nam Minh · đang chờ…');
      else namState('Nam Minh');
    }catch(e){namState('Nam Minh')}
  }
  function namRebuild(){
    audio.pause();
    revoke();
    buildSegments();
    var saved=Number(localStorage.getItem(audioKey())||0);
    audioIndex=Number.isFinite(saved)&&saved>=0&&saved<segments.length?saved:0;
    statusState='missing';
    refreshStatus();
  }

  audio.addEventListener('play',function(){setPlay(true);syncProgress()});
  audio.addEventListener('pause',function(){setPlay(false);syncProgress()});
  audio.addEventListener('timeupdate',function(){syncProgress();if(segments.length)localStorage.setItem(audioKey(),String(audioIndex))});
  audio.addEventListener('ratechange',function(){if(Math.abs(audio.playbackRate-currentRate())>.001)audio.playbackRate=currentRate()});
  audio.addEventListener('ended',function(){audioIndex=0;localStorage.setItem(audioKey(),'0');clearHighlight();setPlay(false);namState('Nam Minh · đã đọc xong')});
  audio.addEventListener('error',function(){if(audio.src){setPlay(false);namState('Audio lỗi')}});

  try{if('speechSynthesis' in window)speechSynthesis.cancel()}catch(e){}
  stopSpeech=function(){namStop(true)};
  speakCurrent=namToggle;
  togglePlay=namToggle;
  jumpSegment=namJump;
  setRate=function(value){namRate(value)};
  rebuildAudio=namRebuild;

  playButton.onclick=namToggle;
  stopButton.onclick=function(){namStop(true)};
  prevButton.onclick=function(){namJump(-1)};
  nextButton.onclick=function(){namJump(1)};
  rate.onchange=function(){namRate(rate.value)};
  downButton.onclick=function(){namRate(currentRate()-.05)};
  upButton.onclick=function(){namRate(currentRate()+.05)};
  highlightToggle.onclick=function(){
    highlightEnabled=!highlightEnabled;
    syncHighlight();
    if(highlightEnabled&&segments.length){audioIndex=segmentAtTime();highlightSegment(segments[audioIndex])}
  };
  window.addEventListener('pagehide',function(){namStop(false);revoke()});

  var waitCount=0;
  var wait=setInterval(function(){
    waitCount+=1;
    if(typeof artifact!=='undefined'&&artifact){clearInterval(wait);namRebuild()}
    else if(waitCount>40)clearInterval(wait);
  },150);
})();
</script>`;

function injectBefore(html, marker, value) {
  const index = html.lastIndexOf(marker);
  if (index < 0) return html;
  return html.slice(0, index) + value + html.slice(index);
}

export function addNamMinhReaderAudio(html) {
  let source = String(html || "");
  if (!source.includes('id="rss-reader-nam-minh-v1"')) {
    source = injectBefore(source, "</head>", NAM_MINH_CSS);
    source = injectBefore(source, "</body>", NAM_MINH_SCRIPT);
  }
  return source;
}

export async function renderReaderArticlePageV5(request, url) {
  const response = await renderReaderArticlePageV4(request, url);
  if (!response) return null;
  const html = addNamMinhReaderAudio(await response.text());
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
