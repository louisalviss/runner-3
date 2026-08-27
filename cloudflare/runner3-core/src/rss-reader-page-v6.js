import { renderReaderArticlePageV5 } from "./rss-reader-page-v5.js";

const TIMING_CSS = `<style id="rss-reader-nam-minh-timing-v2">
.reader-paragraph.reading{transition:background .1s,border-color .1s,padding .1s}
</style>`;

const TIMING_SCRIPT = `<script id="rss-reader-nam-minh-timing-v2-script">
(function(){
  var audio=document.querySelector('#rssNamMinhAudio');
  var prevButton=document.querySelector('#prevAudio');
  var nextButton=document.querySelector('#nextAudio');
  if(!audio||!prevButton||!nextButton)return;

  var timingRows=[];
  var timingView='';
  var timingLoading=null;
  var lastParagraph=-1;
  var fallbackHighlight=highlightSegment;

  function tokenV2(){return localStorage.getItem(KEY)||''}
  function timingEndpoint(){
    return '/reader/rss/articles/'+encodeURIComponent(id)+'/audio/timing?view='+encodeURIComponent(activeKind||'vi');
  }
  function resetTiming(){
    timingRows=[];
    timingView='';
    lastParagraph=-1;
    timingLoading=null;
  }
  async function loadTiming(){
    var view=activeKind||'vi';
    if(timingRows.length&&timingView===view)return timingRows;
    if(timingLoading)return timingLoading;
    timingLoading=(async function(){
      var response=await fetch(timingEndpoint(),{headers:{Authorization:'Bearer '+tokenV2()}});
      if(!response.ok)return [];
      var data=await response.json().catch(function(){return {}});
      var rows=Array.isArray(data.paragraphs)?data.paragraphs:[];
      timingRows=rows.filter(function(row){
        return row&&Number.isFinite(Number(row.start))&&Number.isFinite(Number(row.end));
      }).map(function(row){
        return {index:Number(row.index),start:Number(row.start),end:Number(row.end)};
      });
      timingView=view;
      return timingRows;
    })();
    try{return await timingLoading}finally{timingLoading=null}
  }
  function paragraphAtTime(time){
    if(!timingRows.length)return -1;
    var value=Math.max(0,Number(time||0));
    var low=0,high=timingRows.length-1,best=0;
    while(low<=high){
      var mid=(low+high)>>1;
      if(timingRows[mid].start<=value){best=mid;low=mid+1}else high=mid-1;
    }
    return Math.max(0,Math.min(timingRows.length-1,best));
  }
  function exactHighlight(scroll){
    if(!highlightEnabled||!timingRows.length||!paragraphs.length)return false;
    var index=paragraphAtTime(audio.currentTime);
    if(index<0)return false;
    var row=timingRows[index];
    var paragraphIndex=Number.isFinite(row.index)?row.index:index;
    paragraphIndex=Math.max(0,Math.min(paragraphs.length-1,paragraphIndex));
    if(paragraphIndex===lastParagraph&&paragraphs[paragraphIndex].classList.contains('reading'))return true;
    lastParagraph=paragraphIndex;
    for(var i=0;i<paragraphs.length;i++)paragraphs[i].classList.toggle('reading',i===paragraphIndex);
    if(scroll!==false){
      var el=paragraphs[paragraphIndex];
      var rect=el.getBoundingClientRect();
      var dockH=audioDock.classList.contains('fixed')?audioDock.offsetHeight+26:26;
      if(rect.top<80||rect.bottom>innerHeight-dockH)el.scrollIntoView({behavior:'smooth',block:'center'});
    }
    return true;
  }
  function exactJump(delta){
    if(!timingRows.length||!Number.isFinite(audio.duration))return false;
    var current=paragraphAtTime(audio.currentTime);
    var next=Math.max(0,Math.min(timingRows.length-1,current+delta));
    audio.currentTime=Math.max(0,Number(timingRows[next].start||0)+0.01);
    exactHighlight(true);
    if(audio.paused)audio.play().catch(function(){});
    return true;
  }

  highlightSegment=function(seg){
    if(timingRows.length){exactHighlight(true);return}
    return fallbackHighlight(seg);
  };

  audio.addEventListener('loadedmetadata',function(){
    loadTiming().then(function(){exactHighlight(false)}).catch(function(){});
  });
  audio.addEventListener('play',function(){
    loadTiming().then(function(){exactHighlight(true)}).catch(function(){});
  });
  audio.addEventListener('timeupdate',function(){if(timingRows.length)exactHighlight(true)});
  audio.addEventListener('seeked',function(){if(timingRows.length)exactHighlight(true)});

  prevButton.onclick=function(){if(!exactJump(-1))jumpSegment(-1)};
  nextButton.onclick=function(){if(!exactJump(1))jumpSegment(1)};

  var viButton=document.querySelector('#vi');
  var originalButton=document.querySelector('#original');
  if(viButton)viButton.addEventListener('click',resetTiming);
  if(originalButton)originalButton.addEventListener('click',resetTiming);

  window.addEventListener('pagehide',resetTiming);
})();
</script>`;

function injectBefore(html, marker, value) {
  const index = html.lastIndexOf(marker);
  if (index < 0) return html;
  return html.slice(0, index) + value + html.slice(index);
}

export function addNamMinhTiming(html) {
  let source = String(html || "");
  if (!source.includes('id="rss-reader-nam-minh-timing-v2"')) {
    source = injectBefore(source, "</head>", TIMING_CSS);
    source = injectBefore(source, "</body>", TIMING_SCRIPT);
  }
  return source;
}

export async function renderReaderArticlePageV6(request, url) {
  const response = await renderReaderArticlePageV5(request, url);
  if (!response) return null;
  const html = addNamMinhTiming(await response.text());
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
