from pathlib import Path

ROOT = Path('cloudflare/runner3-core')
V2 = ROOT / 'artifact-library-reader-v2-entry.js'
V36 = ROOT / 'artifact-library-reader-v36-home-screen-safe-area-entry.js'
AUDIO = ROOT / 'audio-entry.js'

v2 = V2.read_text(encoding='utf-8')
v36 = V36.read_text(encoding='utf-8')
audio = AUDIO.read_text(encoding='utf-8')

if '__r3FullBleedV68' in v2:
    print('READER_V68_FULL_BLEED_AUTOSTRETCH=ALREADY_APPLIED')
    raise SystemExit(0)


def one(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return text.replace(old, new, 1)


def exact_count_replace(text, old, new, expected, label):
    count = text.count(old)
    if count != expected:
        raise SystemExit(f'{label}: expected {expected} matches, got {count}')
    return text.replace(old, new)

# v67 removed 100dvh but still leaves the fixed shell sized by the layout viewport.
# v68 makes the shell explicitly follow visualViewport. Defaults remain standards-safe
# on non-iOS platforms until the JS owner writes the measured dimensions.
v2 = one(
    v2,
    'body{position:fixed;inset:0;background:var(--bg)}',
    'body{position:fixed;left:var(--r3-screen-x-v68,0px);top:var(--r3-screen-y-v68,0px);right:auto;bottom:auto;width:var(--r3-screen-w-v68,100vw);height:var(--r3-screen-h-v68,100vh);background:var(--bg)}',
    'V68_FIXED_SHELL_AUTOSTRETCH',
)

v2 = one(
    v2,
    'html.r3-stage-boot-v67 #viewer iframe{opacity:0!important}',
    'html.r3-full-bleed-v68 #viewer{inset:0!important;width:100%!important;height:100%!important}html.r3-stage-boot-v67 #viewer iframe{opacity:0!important}',
    'V68_VIEWER_FILL_RULE',
)

anchor = '  async function r3WaitPreRenderStageV67(){\n'
if anchor not in v2:
    raise SystemExit('V68_STAGE_HELPER_ANCHOR_MISSING')

helper = r'''  function r3IosV68(){
    try{return /iPhone|iPad|iPod/i.test(String(navigator.userAgent||''));}catch{return false;}
  }
  function r3StandaloneV68(){
    try{return Boolean((window.matchMedia&&window.matchMedia('(display-mode: standalone)').matches)||navigator.standalone===true);}catch{return false;}
  }
  function r3MeasureSafeAreaV68(){
    try{
      let probe=document.getElementById('r3-safe-area-probe-v68');
      if(!probe){
        probe=document.createElement('div');
        probe.id='r3-safe-area-probe-v68';
        probe.setAttribute('aria-hidden','true');
        probe.style.cssText='position:fixed;left:0;top:0;width:0;height:0;visibility:hidden;pointer-events:none;padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom);padding-left:env(safe-area-inset-left);padding-right:env(safe-area-inset-right);';
        document.documentElement.appendChild(probe);
      }
      const cs=getComputedStyle(probe),num=v=>{const n=parseFloat(String(v||'0'));return Number.isFinite(n)?n:0;};
      return {top:num(cs.paddingTop),bottom:num(cs.paddingBottom),left:num(cs.paddingLeft),right:num(cs.paddingRight)};
    }catch{return {top:0,bottom:0,left:0,right:0};}
  }
  function r3ApplyFullBleedV68(reason='apply',resizeStage=false){
    try{
      if(!r3IosV68())return false;
      const vv=window.visualViewport||null;
      const w=Math.max(1,Math.round(Number(vv&&vv.width||window.innerWidth||document.documentElement.clientWidth||0)));
      const h=Math.max(1,Math.round(Number(vv&&vv.height||window.innerHeight||document.documentElement.clientHeight||0)));
      const x=Math.round(Number(vv&&vv.offsetLeft||0));
      const y=Math.round(Number(vv&&vv.offsetTop||0));
      const safe=r3StandaloneV68()?r3MeasureSafeAreaV68():{top:0,bottom:0,left:0,right:0};
      const root=document.documentElement;
      root.classList.add('r3-full-bleed-v68');
      root.style.setProperty('--r3-screen-w-v68',w+'px');
      root.style.setProperty('--r3-screen-h-v68',h+'px');
      root.style.setProperty('--r3-screen-x-v68',x+'px');
      root.style.setProperty('--r3-screen-y-v68',y+'px');
      root.style.setProperty('--r3-safe-top-v68',safe.top+'px');
      root.style.setProperty('--r3-safe-bottom-v68',safe.bottom+'px');
      const state=window.__r3FullBleedV68||(window.__r3FullBleedV68={owner:'full-bleed-autostretch-v68',installed:false,w:0,h:0,x:0,y:0,safeTop:0,safeBottom:0,applyCalls:0,resizeCalls:0,lastReason:'',standalone:false});
      const changed=Math.abs(Number(state.w||0)-w)>1||Math.abs(Number(state.h||0)-h)>1||Math.abs(Number(state.x||0)-x)>1||Math.abs(Number(state.y||0)-y)>1;
      state.w=w;state.h=h;state.x=x;state.y=y;state.safeTop=safe.top;state.safeBottom=safe.bottom;state.applyCalls++;state.lastReason=String(reason||'');state.standalone=r3StandaloneV68();
      if(resizeStage&&changed&&rendition&&typeof rendition.resize==='function'){
        try{rendition.resize(w,h);state.resizeCalls++;}catch{}
      }
      return changed;
    }catch{return false;}
  }
  let r3FullBleedTimerV68=0;
  function r3ScheduleFullBleedV68(reason='viewport'){
    clearTimeout(r3FullBleedTimerV68);
    r3FullBleedTimerV68=setTimeout(()=>r3ApplyFullBleedV68(reason,true),140);
  }
  function r3InstallFullBleedV68(){
    if(!r3IosV68())return false;
    const state=window.__r3FullBleedV68||(window.__r3FullBleedV68={owner:'full-bleed-autostretch-v68',installed:false,w:0,h:0,x:0,y:0,safeTop:0,safeBottom:0,applyCalls:0,resizeCalls:0,lastReason:'',standalone:false});
    if(state.installed){r3ApplyFullBleedV68('reinstall',false);return true;}
    state.installed=true;
    r3ApplyFullBleedV68('install',false);
    try{window.visualViewport&&window.visualViewport.addEventListener('resize',()=>r3ScheduleFullBleedV68('visualViewport.resize'),{passive:true});}catch{}
    try{window.visualViewport&&window.visualViewport.addEventListener('scroll',()=>r3ScheduleFullBleedV68('visualViewport.scroll'),{passive:true});}catch{}
    window.addEventListener('resize',()=>r3ScheduleFullBleedV68('window.resize'),{passive:true});
    window.addEventListener('orientationchange',()=>setTimeout(()=>r3ScheduleFullBleedV68('orientationchange'),180),{passive:true});
    return true;
  }

'''
v2 = v2.replace(anchor, helper + anchor, 1)

v2 = one(
    v2,
    "  async function r3WaitPreRenderStageV67(){\n    const viewer=$('viewer');",
    "  async function r3WaitPreRenderStageV67(){\n    r3InstallFullBleedV68();\n    r3ApplyFullBleedV68('pre-render-enter',false);\n    const viewer=$('viewer');",
    'V68_INSTALL_BEFORE_STAGE',
)

v2 = one(
    v2,
    "    for(let n=0;n<10;n++){\n      const vv=window.visualViewport||null;",
    "    for(let n=0;n<10;n++){\n      r3ApplyFullBleedV68('pre-render-sample-'+n,false);\n      const vv=window.visualViewport||null;",
    'V68_REFRESH_DURING_STAGE_STABILIZE',
)

# v66 previously hard-coded 8px for standalone EPUB content. With a true
# full-bleed status bar we keep one safe-area inset plus the 8px reading gap.
v2 = one(
    v2,
    "body.style.setProperty('padding-top','8px','important');",
    "body.style.setProperty('padding-top',String(Math.max(8,Number(window.__r3FullBleedV68&&window.__r3FullBleedV68.safeTop||0)+8))+'px','important');",
    'V68_SINGLE_SAFE_READING_INSET',
)

# Switch the outer Home Screen document from opaque/reserved status bar to
# translucent/full-bleed. The safe area is now owned only by content/controls.
v36 = one(
    v36,
    'const STARTUP_MARKER = \'<meta name="r3-ios-home-screen-startup-policy" content="opaque-v39">\';',
    'const STARTUP_MARKER_OLD = \'<meta name="r3-ios-home-screen-startup-policy" content="opaque-v39">\';\nconst STARTUP_MARKER = \'<meta name="r3-ios-home-screen-startup-policy" content="full-bleed-v68">\';',
    'V68_V36_STARTUP_MARKER',
)
v36 = exact_count_replace(
    v36,
    '  let out = String(html || "");\n',
    '  let out = String(html || "");\n  out = out.replace(STARTUP_MARKER_OLD, "");\n',
    2,
    'V68_V36_REMOVE_OLD_STARTUP_MARKER',
)
v36 = exact_count_replace(
    v36,
    '  if (out.includes(TRANSLUCENT)) out = out.replace(TRANSLUCENT, OPAQUE);\n  else if (!out.includes(OPAQUE)) out = ensureHeadMeta(out, OPAQUE);',
    '  if (out.includes(OPAQUE)) out = out.replace(OPAQUE, TRANSLUCENT);\n  else if (!out.includes(TRANSLUCENT)) out = ensureHeadMeta(out, TRANSLUCENT);',
    2,
    'V68_V36_TRANSLUCENT_POLICY',
)
v36 = v36.replace("version:'v39-startup-opaque'", "version:'v68-full-bleed-autostretch'")
v36 = v36.replace("statusbar:'black'", "statusbar:'black-translucent'")
v36 = v36.replace('"opaque-v39"', '"full-bleed-v68"')
v36 = v36.replace('"disabled-v39"', '"disabled-v68"')

# audio-entry is outside the Reader wrapper for /artifact-library startup and
# must not turn the translucent status bar back into opaque.
audio = one(
    audio,
    'const IOS_STARTUP_MARKER = \'<meta name="r3-ios-home-screen-startup-policy" content="opaque-v39">\';',
    'const IOS_STARTUP_MARKER_OLD = \'<meta name="r3-ios-home-screen-startup-policy" content="opaque-v39">\';\nconst IOS_STARTUP_MARKER = \'<meta name="r3-ios-home-screen-startup-policy" content="full-bleed-v68">\';',
    'V68_AUDIO_STARTUP_MARKER',
)
audio = one(
    audio,
    '  let out = String(html || "");\n  if (!out.includes(\'<meta name="viewport"\') || !out.includes("viewport-fit=cover")) return out;',
    '  let out = String(html || "");\n  out = out.replace(IOS_STARTUP_MARKER_OLD, "");\n  if (!out.includes(\'<meta name="viewport"\') || !out.includes("viewport-fit=cover")) return out;',
    'V68_AUDIO_REMOVE_OLD_STARTUP_MARKER',
)
audio = one(
    audio,
    '  if (out.includes(IOS_STATUS_TRANSLUCENT)) out = out.replace(IOS_STATUS_TRANSLUCENT, IOS_STATUS_BLACK);\n  else out = ensureHeadMeta(out, IOS_STATUS_BLACK);',
    '  if (out.includes(IOS_STATUS_BLACK)) out = out.replace(IOS_STATUS_BLACK, IOS_STATUS_TRANSLUCENT);\n  else out = ensureHeadMeta(out, IOS_STATUS_TRANSLUCENT);',
    'V68_AUDIO_TRANSLUCENT_POLICY',
)
audio = audio.replace('headers.set("X-R3-Reader-IOS-Startup-Viewport", "opaque-v39");', 'headers.set("X-R3-Reader-IOS-Startup-Viewport", "full-bleed-v68");')

for required in [
    '__r3FullBleedV68',
    "owner:'full-bleed-autostretch-v68'",
    '--r3-screen-w-v68',
    '--r3-screen-h-v68',
    "r3InstallFullBleedV68();",
    "r3ApplyFullBleedV68('pre-render-enter',false)",
    "rendition.resize(w,h)",
    "window.visualViewport.addEventListener('resize'",
    "window.__r3FullBleedV68&&window.__r3FullBleedV68.safeTop",
]:
    if required not in v2:
        raise SystemExit('V68_REQUIRED_V2_MISSING:' + required)

for required in [
    'content="full-bleed-v68"',
    'out.replace(OPAQUE, TRANSLUCENT)',
    '"X-R3-Reader-IOS-Startup-Viewport": "full-bleed-v68"',
    '"X-R3-Reader-IOS-Forced-Inset": "disabled-v68"',
    "statusbar:'black-translucent'",
]:
    if required not in v36:
        raise SystemExit('V68_REQUIRED_V36_MISSING:' + required)

for required in [
    'content="full-bleed-v68"',
    'out.replace(IOS_STATUS_BLACK, IOS_STATUS_TRANSLUCENT)',
    'headers.set("X-R3-Reader-IOS-Startup-Viewport", "full-bleed-v68")',
]:
    if required not in audio:
        raise SystemExit('V68_REQUIRED_AUDIO_MISSING:' + required)

for forbidden in [
    'out.replace(TRANSLUCENT, OPAQUE)',
    'r3-ios-standalone-forced-inset-v38',
    '--r3-ios-forced-top-v38',
]:
    if forbidden in v36:
        raise SystemExit('V68_FORBIDDEN_V36_PRESENT:' + forbidden)

if 'out.replace(IOS_STATUS_TRANSLUCENT, IOS_STATUS_BLACK)' in audio:
    raise SystemExit('V68_AUDIO_OPAQUE_OVERRIDE_STILL_PRESENT')

V2.write_text(v2, encoding='utf-8')
V36.write_text(v36, encoding='utf-8')
AUDIO.write_text(audio, encoding='utf-8')
print('READER_V68_FULL_BLEED_AUTOSTRETCH=PASS')
