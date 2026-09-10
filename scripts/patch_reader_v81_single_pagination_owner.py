from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
V2=ROOT/'artifact-library-reader-v2-entry.js'
V28=ROOT/'artifact-library-reader-v28-prime-base-position-entry.js'
V34=ROOT/'artifact-library-reader-v34-continuous-range-sync-entry.js'
V35=ROOT/'artifact-library-reader-v35-continuity-single-owner-entry.js'

v2=V2.read_text(encoding='utf-8')

old_nav="  function pagePrev(){if(rendition)rendition.prev();hideControls();}\n  function pageNext(){if(rendition)rendition.next();hideControls();}"
new_nav=r'''  let r3PageMoveBusyV81=false,r3LastPageMoveAtV81=0,r3NavSeqV81=0;
  function r3MarkReaderIntentV81(reason,ttl=2200){
    const now=Date.now();
    const token={seq:++r3NavSeqV81,reason:String(reason||'user-nav'),at:now,until:now+Math.max(700,Number(ttl)||2200),consumed:false};
    window.__r3ReaderNavIntentV81=token;
    setTimeout(()=>{try{if(window.__r3ReaderNavIntentV81===token&&!token.consumed)window.__r3ReaderNavIntentV81=null}catch{}},Math.max(900,Number(ttl)||2200));
    return token;
  }
  window.__r3MarkReaderIntentV81=r3MarkReaderIntentV81;
  async function r3MovePageV81(direction){
    const now=Date.now();
    if(!rendition||r3PageMoveBusyV81||now-r3LastPageMoveAtV81<260)return false;
    r3PageMoveBusyV81=true;r3LastPageMoveAtV81=now;
    r3MarkReaderIntentV81(direction<0?'page-prev':'page-next');
    try{if(direction<0)await rendition.prev();else await rendition.next();return true}
    catch{return false}
    finally{setTimeout(()=>{r3PageMoveBusyV81=false},180)}
  }
  function pagePrev(){void r3MovePageV81(-1);hideControls();}
  function pageNext(){void r3MovePageV81(1);hideControls();}'''
if old_nav in v2:v2=v2.replace(old_nav,new_nav,1)
elif 'r3PageMoveBusyV81' not in v2:raise SystemExit('V81_NAV_ANCHOR_MISSING')

old_sync="  function r3ScheduleProgressSyncV65(percent,cfi){clearTimeout(r3ProgressSyncTimerV65);if(r3ProgrammaticSyncV72||window.__R3_BASE_READER_BOOT_DONE!==true)return;const now=Date.now();r3ProgressSyncTimerV65=setTimeout(async()=>{const saved=await r3PostProgressV65({key,cfi:String(cfi||''),percent,last_open_at:now,updated_at:now});if(saved)r3ApplyRemoteProgressV65(key,saved,false)},700)}"
new_sync="  function r3ScheduleProgressSyncV65(percent,cfi){if(r3ProgrammaticSyncV72||window.__R3_BASE_READER_BOOT_DONE!==true)return;const intent=window.__r3ReaderNavIntentV81;const scheduledAt=Date.now();if(!intent||intent.consumed||scheduledAt>Number(intent.until||0))return;clearTimeout(r3ProgressSyncTimerV65);r3ProgressSyncTimerV65=setTimeout(async()=>{const now=Date.now(),active=window.__r3ReaderNavIntentV81;if(active!==intent||intent.consumed||now>Number(intent.until||0))return;intent.consumed=true;const row={percent,cfi:String(cfi||''),updatedAt:now,lastOpenAt:now};try{localStorage.setItem(R3_READER_PROGRESS_PREFIX_V54+key,JSON.stringify(row));if(cfi)localStorage.setItem(keys.position,String(cfi))}catch{}const saved=await r3PostProgressV65({key,cfi:String(cfi||''),percent,last_open_at:now,updated_at:now});if(saved)r3ApplyRemoteProgressV65(key,saved,false)},180)}"
if old_sync in v2:v2=v2.replace(old_sync,new_sync,1)
elif 'active!==intent' not in v2:raise SystemExit('V81_PROGRESS_INTENT_ANCHOR_MISSING')

clamp_anchor="      function r3ClampPaginatedVerticalV62(reason=''){\n        let fixed=0;"
clamp_new=r'''      function r3ClampPaginatedVerticalV62(reason=''){
        const r3IosClampBlockedV81=(()=>{try{return /iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1)}catch{return false}})();
        if(r3IosClampBlockedV81){const s=window.__r3PaginatedVerticalClampV62||(window.__r3PaginatedVerticalClampV62={owner:'paginated-vertical-clamp-v62',calls:0,fixes:0,lastReason:'',lastAt:0,coldBootGuardTicks:0,coldBootGuardActive:false});s.calls++;s.lastReason='suppressed-v81:'+String(reason||'');s.lastAt=Date.now();return 0;}
        let fixed=0;'''
if clamp_anchor in v2:v2=v2.replace(clamp_anchor,clamp_new,1)
elif 'suppressed-v81:' not in v2:raise SystemExit('V81_CLAMP_ANCHOR_MISSING')

resize_anchor="      if(resizeStage&&changed&&rendition&&typeof rendition.resize==='function'){"
resize_new="      if(resizeStage&&changed&&rendition&&typeof rendition.resize==='function'&&String(reason||'').includes('orientationchange')){"
if resize_anchor in v2:v2=v2.replace(resize_anchor,resize_new,1)
elif resize_new not in v2:raise SystemExit('V81_VIEWPORT_RESIZE_ANCHOR_MISSING')

dock_resize="      if(resizeStage&&changed)requestAnimationFrame(()=>r3ResizeReadingStageV69(reason));"
dock_resize_new="      if(resizeStage&&changed&&(String(reason||'')==='dock-resize'||String(reason||'').includes('orientationchange')))requestAnimationFrame(()=>r3ResizeReadingStageV69(reason));"
if dock_resize in v2:v2=v2.replace(dock_resize,dock_resize_new,1)
elif dock_resize_new not in v2:raise SystemExit('V81_DOCK_RESIZE_ANCHOR_MISSING')

# Programmatic relocation must not mutate local canonical cache either. The debounced
# navigation-intent scheduler above owns both local position and D1 persistence.
writer_old="  function r3WriteProgressV55(percent,cfi){\n    const n=Number(percent);const value=Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(n))):null;\n    try{localStorage.setItem(R3_READER_PROGRESS_PREFIX_V54+key,JSON.stringify({percent:value,cfi:cfi||'',updatedAt:Date.now()}));}catch{}\n    r3ScheduleProgressSyncV65(value,cfi||'');\n    return value;\n  }"
writer_new="  function r3WriteProgressV55(percent,cfi){\n    const n=Number(percent);const value=Number.isFinite(n)?Math.max(0,Math.min(100,Math.round(n))):null;\n    r3ScheduleProgressSyncV65(value,cfi||'');\n    return value;\n  }"
if writer_old in v2:v2=v2.replace(writer_old,writer_new,1)
elif writer_new not in v2:raise SystemExit('V81_LOCAL_WRITER_ANCHOR_MISSING')
reloc_old="rendition.on('relocated',loc=>{const cfi=loc?.start?.cfi;if(cfi)persist(keys.position,cfi);const pct=r3PercentFromCfiV55(cfi,loc);r3WriteProgressV55(pct,cfi||'');$('position').textContent=pct===null?'Đã lưu vị trí':pct+'% · đã lưu';if(!r3LocationsReadyV55)setTimeout(()=>r3EnsureLocationsV55(),250);setTimeout(bindEpubContents,0);});"
reloc_new="rendition.on('relocated',loc=>{const cfi=loc?.start?.cfi;const pct=r3PercentFromCfiV55(cfi,loc);r3WriteProgressV55(pct,cfi||'');$('position').textContent=pct===null?'Đang đọc':pct+'%';if(!r3LocationsReadyV55)setTimeout(()=>r3EnsureLocationsV55(),250);setTimeout(bindEpubContents,0);});"
if reloc_old in v2:v2=v2.replace(reloc_old,reloc_new,1)
elif reloc_new not in v2:raise SystemExit('V81_RELOCATED_OWNER_ANCHOR_MISSING')
V2.write_text(v2,encoding='utf-8')

v28=V28.read_text(encoding='utf-8')
old_blank='"html.r3-restore-pending-v45 body::before{content:\'\';position:fixed;z-index:2147483600;inset:0;background:var(--bg,#fff);pointer-events:auto}"'
new_blank='"html.r3-restore-pending-v45 body::before{content:\'Đang mở đúng vị trí…\';position:fixed;z-index:2147483600;inset:0;background:var(--bg,#fff);color:var(--muted,#999);display:grid;place-items:center;font:600 13px/1.4 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;pointer-events:auto}"'
if old_blank in v28:v28=v28.replace(old_blank,new_blank,1)
elif 'Đang mở đúng vị trí…' not in v28:raise SystemExit('V81_RESTORE_SHIELD_ANCHOR_MISSING')
V28.write_text(v28,encoding='utf-8')

v34=V34.read_text(encoding='utf-8')
old_follow="      await b.display(cfi);"
new_follow="      try{window.__r3MarkReaderIntentV81&&window.__r3MarkReaderIntentV81('audio-follow',2600)}catch{}\n      await b.display(cfi);"
if old_follow in v34:v34=v34.replace(old_follow,new_follow,1)
elif "r3MarkReaderIntentV81('audio-follow'" not in v34:raise SystemExit('V81_AUDIO_FOLLOW_ANCHOR_MISSING')
V34.write_text(v34,encoding='utf-8')

v35=V35.read_text(encoding='utf-8')
anchor="const V35_PLAYER_CHAPTERS = `<style data-r3-player-chapters-v38=\"1\">"
if 'data-r3-pagination-owner-v81="1"' not in v35:
    if anchor not in v35:raise SystemExit('V81_V35_RUNTIME_ANCHOR_MISSING')
    runtime=r'''const V81_PAGINATION_OWNER = `<style data-r3-pagination-owner-v81="1">
html.r3-home-screen-v81{--r3-reader-safe-top-v81:calc(max(env(safe-area-inset-top,0px),44px) + 54px)}
html.r3-home-screen-v81 #viewer{top:var(--r3-reader-safe-top-v81)!important}
html.r3-home-screen-v81.r3-full-bleed-v68 #viewer{top:var(--r3-reader-safe-top-v81)!important}
html.r3-home-screen-v81.r3-full-bleed-v68.r3-audio-dock-inset-v69 #viewer{top:var(--r3-reader-safe-top-v81)!important}
html.r3-home-screen-v81 .r3-hit-zone{top:var(--r3-reader-safe-top-v81)!important;height:auto!important}
html.r3-home-screen-v81 body.controls .topbar{background:linear-gradient(to bottom,var(--bg) 0%,var(--bg) 78%,transparent 100%)}
html.r3-home-screen-v81 body.controls[data-nav="tap"] .tap-hint{opacity:0!important}
</style><script data-r3-pagination-owner-v81="1">
(()=>{
  if(window.__r3PaginationOwnerV81)return;
  const standalone=Boolean((window.matchMedia&&window.matchMedia('(display-mode: standalone)').matches)||navigator.standalone===true);
  if(standalone)document.documentElement.classList.add('r3-home-screen-v81');
  const state=window.__r3PaginationOwnerV81={owner:'single-pagination-owner-v81',standalone,chapterSource:'',installs:0};
  const norm=value=>String(value||'').normalize('NFC').replace(/\\s+/g,' ').trim().toLowerCase();
  const cleanHref=value=>{let raw=String(value||'').split('#')[0];try{raw=decodeURIComponent(raw)}catch{}while(raw.startsWith('./'))raw=raw.slice(2);return raw.toLowerCase()};
  function renderedHeading(b){try{for(const c of b.contents?b.contents():[]){const d=c&&c.document;if(!d)continue;const h=d.querySelector('h1,h2,h3');const text=String(h&&h.textContent||d.title||'').replace(/\\s+/g,' ').trim();if(text)return text}}catch{}return ''}
  function install(){
    const b=window.r3ReaderBridge;if(!b||b.__r3PaginationOwnerV81)return Boolean(b);
    const originalInfo=typeof b.chapterInfo==='function'?b.chapterInfo.bind(b):null;
    const originalChapters=typeof b.chapters==='function'?b.chapters.bind(b):null;
    const originalStep=typeof b.stepChapter==='function'?b.stepChapter.bind(b):null;
    const originalDisplayChapter=typeof b.displayChapter==='function'?b.displayChapter.bind(b):null;
    const originalNext=typeof b.next==='function'?b.next.bind(b):null;
    const originalPrev=typeof b.prev==='function'?b.prev.bind(b):null;
    b.chapterInfo=async()=>{
      const chapters=originalChapters?await originalChapters():[];
      if(!chapters.length)return originalInfo?await originalInfo():{index:-1,total:0,chapter:null,chapters:[]};
      const heading=renderedHeading(b);let index=-1,source='';
      if(heading){const hn=norm(heading);index=chapters.findIndex(row=>{const label=norm(row&&row.label);return label===hn||label.endsWith(hn)||hn.endsWith(label)});if(index>=0)source='heading-label';if(index<0){const m=heading.match(/(?:chương|chapter)\\s*([0-9]{1,6})/i);const n=m?Number(m[1]):0;if(n>=1&&n<=chapters.length){index=n-1;source='heading-number'}}}
      if(index<0){const loc=b.current?b.current():null;const current=cleanHref(loc&&loc.start&&loc.start.href||'');if(current){index=chapters.findIndex(row=>{const candidate=cleanHref(row&&row.href);return candidate===current||candidate.endsWith('/'+current)||current.endsWith('/'+candidate)||candidate.split('/').pop()===current.split('/').pop()});if(index>=0)source='href'}}
      if(index<0&&originalInfo){const prior=await originalInfo();if(prior&&Number(prior.index)>=0){index=Math.min(chapters.length-1,Number(prior.index));source='legacy-fallback'}}
      state.chapterSource=source||'unknown';return {index,total:chapters.length,chapter:index>=0?chapters[index]:null,chapters,r3Source:source||'unknown'};
    };
    if(originalDisplayChapter)b.displayChapter=async target=>{try{window.__r3MarkReaderIntentV81&&window.__r3MarkReaderIntentV81('chapter-select',3000)}catch{}return originalDisplayChapter(target)};
    if(originalStep)b.stepChapter=async delta=>{try{window.__r3MarkReaderIntentV81&&window.__r3MarkReaderIntentV81(Number(delta)<0?'chapter-prev':'chapter-next',3000)}catch{}return originalStep(delta)};
    if(originalNext)b.next=async()=>{try{window.__r3MarkReaderIntentV81&&window.__r3MarkReaderIntentV81('bridge-next',2400)}catch{}return originalNext()};
    if(originalPrev)b.prev=async()=>{try{window.__r3MarkReaderIntentV81&&window.__r3MarkReaderIntentV81('bridge-prev',2400)}catch{}return originalPrev()};
    b.__r3PaginationOwnerV81=true;state.installs++;return true;
  }
  if(!install()){let tries=0;const timer=setInterval(()=>{if(install()||++tries>80)clearInterval(timer)},50)}
})();
</script>`;

'''
    v35=v35.replace(anchor,runtime+anchor,1)
compose="  out = out.replace('</body>', V35_FLAG + V35_LAYOUT_STABILIZER + V35_PLAYER_CHAPTERS + '</body>');"
compose_new="  out = out.replace('</body>', V35_FLAG + V35_LAYOUT_STABILIZER + V81_PAGINATION_OWNER + V35_PLAYER_CHAPTERS + '</body>');"
if compose in v35:v35=v35.replace(compose,compose_new,1)
elif compose_new not in v35:raise SystemExit('V81_V35_COMPOSE_ANCHOR_MISSING')
header="      headers.set('X-R3-Reader-Dock-Audio', 'stable-v80');"
if header in v35 and "X-R3-Reader-Pagination-Owner" not in v35:v35=v35.replace(header,header+"\n      headers.set('X-R3-Reader-Pagination-Owner', 'v81');",1)
elif "X-R3-Reader-Pagination-Owner" not in v35:raise SystemExit('V81_HEADER_ANCHOR_MISSING')
V35.write_text(v35,encoding='utf-8')
print('READER_V81_SINGLE_PAGINATION_OWNER=PASS')
