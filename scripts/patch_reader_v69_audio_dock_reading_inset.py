from pathlib import Path

V2 = Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js')
text = V2.read_text(encoding='utf-8')

if '__r3AudioDockInsetV69' in text:
    print('READER_V69_AUDIO_DOCK_READING_INSET=ALREADY_APPLIED')
    raise SystemExit(0)


def one(source, old, new, label):
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)

# v68 deliberately keeps the application shell full-bleed. v69 only shortens the
# EPUB reading stage, using the actual dock top instead of a hard-coded player height.
text = one(
    text,
    'html.r3-full-bleed-v68 #viewer{inset:0!important;width:100%!important;height:100%!important}html.r3-stage-boot-v67 #viewer iframe{opacity:0!important}',
    'html.r3-full-bleed-v68 #viewer{inset:0!important;width:100%!important;height:100%!important}html.r3-full-bleed-v68.r3-audio-dock-inset-v69 #viewer{top:0!important;right:0!important;bottom:var(--r3-reading-bottom-v69,0px)!important;left:0!important;width:100%!important;height:auto!important}html.r3-stage-boot-v67 #viewer iframe{opacity:0!important}',
    'V69_DYNAMIC_VIEWER_BOTTOM',
)

anchor = '  async function r3WaitPreRenderStageV67(){\n'
if anchor not in text:
    raise SystemExit('V69_STAGE_HELPER_ANCHOR_MISSING')

helper = r'''  function r3AudioDockV69(){
    try{return document.getElementById('r3AudioDock');}catch{return null;}
  }
  function r3MeasureAudioDockInsetV69(){
    try{
      const dock=r3AudioDockV69();
      if(!dock)return 0;
      const cs=getComputedStyle(dock);
      if(cs.display==='none'||cs.visibility==='hidden')return 0;
      const rect=dock.getBoundingClientRect();
      if(!(rect&&Number.isFinite(rect.top))||rect.height<=0)return 0;
      const vv=window.visualViewport||null;
      const viewportBottom=Number(vv&&vv.offsetTop||0)+Number(vv&&vv.height||window.innerHeight||document.documentElement.clientHeight||0);
      const overlap=Math.max(0,viewportBottom-Number(rect.top||0));
      return overlap>0?Math.ceil(overlap+8):0;
    }catch{return 0;}
  }
  function r3ResizeReadingStageV69(reason='resize-stage'){
    try{
      const viewer=$('viewer');
      if(!viewer||!rendition||typeof rendition.resize!=='function')return false;
      const stageW=Math.max(1,Math.round(Number(viewer.clientWidth||viewer.getBoundingClientRect().width||0)));
      const stageH=Math.max(1,Math.round(Number(viewer.clientHeight||viewer.getBoundingClientRect().height||0)));
      rendition.resize(stageW,stageH);
      const state=window.__r3AudioDockInsetV69;
      if(state){state.resizeCalls++;state.stageW=stageW;state.stageH=stageH;state.lastResizeReason=String(reason||'');}
      return true;
    }catch{return false;}
  }
  function r3BindAudioDockObserverV69(){
    try{
      const state=window.__r3AudioDockInsetV69;
      if(!state)return false;
      const dock=r3AudioDockV69();
      if(!dock||state.observedDock===dock)return Boolean(dock);
      try{state.resizeObserver&&state.resizeObserver.disconnect();}catch{}
      if(typeof ResizeObserver==='function'){
        state.resizeObserver=new ResizeObserver(()=>r3ScheduleAudioDockInsetV69('dock-resize'));
        state.resizeObserver.observe(dock);
      }
      state.observedDock=dock;
      return true;
    }catch{return false;}
  }
  function r3ApplyAudioDockInsetV69(reason='apply',resizeStage=false){
    try{
      if(!r3IosV68())return false;
      const root=document.documentElement;
      const inset=r3MeasureAudioDockInsetV69();
      const state=window.__r3AudioDockInsetV69||(window.__r3AudioDockInsetV69={owner:'audio-dock-reading-inset-v69',installed:false,inset:-1,applyCalls:0,resizeCalls:0,stageW:0,stageH:0,lastReason:'',lastResizeReason:'',observedDock:null,resizeObserver:null,mutationObserver:null});
      const changed=Math.abs(Number(state.inset||0)-inset)>1;
      state.inset=inset;state.applyCalls++;state.lastReason=String(reason||'');
      root.classList.add('r3-audio-dock-inset-v69');
      root.style.setProperty('--r3-reading-bottom-v69',inset+'px');
      r3BindAudioDockObserverV69();
      if(resizeStage&&changed)requestAnimationFrame(()=>r3ResizeReadingStageV69(reason));
      return changed;
    }catch{return false;}
  }
  let r3AudioDockTimerV69=0;
  function r3ScheduleAudioDockInsetV69(reason='dock-change'){
    clearTimeout(r3AudioDockTimerV69);
    r3AudioDockTimerV69=setTimeout(()=>r3ApplyAudioDockInsetV69(reason,true),60);
  }
  function r3InstallAudioDockInsetV69(){
    if(!r3IosV68())return false;
    const state=window.__r3AudioDockInsetV69||(window.__r3AudioDockInsetV69={owner:'audio-dock-reading-inset-v69',installed:false,inset:-1,applyCalls:0,resizeCalls:0,stageW:0,stageH:0,lastReason:'',lastResizeReason:'',observedDock:null,resizeObserver:null,mutationObserver:null});
    if(state.installed){r3ApplyAudioDockInsetV69('reinstall',false);return true;}
    state.installed=true;
    r3ApplyAudioDockInsetV69('install',false);
    if(typeof MutationObserver==='function'){
      try{
        state.mutationObserver=new MutationObserver(()=>r3ScheduleAudioDockInsetV69('dock-mutation'));
        state.mutationObserver.observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['style','class','hidden']});
      }catch{}
    }
    window.addEventListener('orientationchange',()=>setTimeout(()=>r3ScheduleAudioDockInsetV69('orientationchange'),180),{passive:true});
    return true;
  }

'''
text = text.replace(anchor, helper + anchor, 1)

text = one(
    text,
    "  async function r3WaitPreRenderStageV67(){\n    r3InstallFullBleedV68();\n    r3ApplyFullBleedV68('pre-render-enter',false);\n    const viewer=$('viewer');",
    "  async function r3WaitPreRenderStageV67(){\n    r3InstallFullBleedV68();\n    r3ApplyFullBleedV68('pre-render-enter',false);\n    r3InstallAudioDockInsetV69();\n    r3ApplyAudioDockInsetV69('pre-render-enter',false);\n    const viewer=$('viewer');",
    'V69_PRE_RENDER_DOCK_INSET',
)

# v68 owns physical viewport changes. When v69 is present, translate those changes
# into the current viewer dimensions rather than resizing EPUB back under the dock.
text = one(
    text,
    "      if(resizeStage&&changed&&rendition&&typeof rendition.resize==='function'){\n        try{rendition.resize(w,h);state.resizeCalls++;}catch{}\n      }",
    "      if(resizeStage&&changed&&rendition&&typeof rendition.resize==='function'){\n        if(window.__r3AudioDockInsetV69){\n          try{r3ApplyAudioDockInsetV69('v68-viewport',false);r3ResizeReadingStageV69('v68-viewport');state.resizeCalls++;}catch{}\n        }else{\n          try{rendition.resize(w,h);state.resizeCalls++;}catch{}\n        }\n      }",
    'V69_V68_RESIZE_DELEGATION',
)

for marker in [
    '__r3AudioDockInsetV69',
    "owner:'audio-dock-reading-inset-v69'",
    "document.getElementById('r3AudioDock')",
    'dock.getBoundingClientRect()',
    '--r3-reading-bottom-v69',
    'bottom:var(--r3-reading-bottom-v69,0px)!important',
    'height:auto!important',
    'new ResizeObserver',
    'new MutationObserver',
    "r3InstallAudioDockInsetV69();",
    "r3ApplyAudioDockInsetV69('pre-render-enter',false)",
    'rendition.resize(stageW,stageH)',
    "r3ApplyAudioDockInsetV69('v68-viewport',false)",
    'rendition.resize(w,h)',
]:
    if marker not in text:
        raise SystemExit('READER_V69_REQUIRED_MISSING:' + marker)

segment = text[text.index('  function r3AudioDockV69()'):text.index('  async function r3WaitPreRenderStageV67()')]
if 'rendition.display(' in segment:
    raise SystemExit('READER_V69_FORBIDDEN_REDISPLAY')

V2.write_text(text, encoding='utf-8')
print('READER_V69_AUDIO_DOCK_READING_INSET=PASS')
