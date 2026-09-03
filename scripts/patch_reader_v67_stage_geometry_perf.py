from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
V2=ROOT/'artifact-library-reader-v2-entry.js'
V36=ROOT/'artifact-library-reader-v36-home-screen-safe-area-entry.js'

v2=V2.read_text(encoding='utf-8')
v36=V36.read_text(encoding='utf-8')

if '__r3StageGeometryV67' in v2:
    print('READER_V67_STAGE_GEOMETRY_PERF=ALREADY_APPLIED')
    raise SystemExit(0)


def one(text,old,new,label):
    count=text.count(old)
    if count!=1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return text.replace(old,new,1)

# 1) Fixed + inset already owns the viewport. 100dvh creates a second dynamic
# height owner on iOS Safari / standalone and is the source of cold-load reflow.
v2=one(v2,
    'body{position:fixed;inset:0;width:100%;height:100dvh;background:var(--bg)}',
    'body{position:fixed;inset:0;background:var(--bg)}',
    'V67_REMOVE_DYNAMIC_DVH')

# Hide only EPUB iframes during initial pagination. Loading UI remains visible.
v2=one(v2,
    '#loading{position:absolute;',
    'html.r3-stage-boot-v67 #viewer iframe{opacity:0!important}#loading{position:absolute;',
    'V67_STAGE_BOOT_CSS')

# 2) Normalize the top of the EPUB document through epub.js themes, not delayed
# DOM mutation. Apply in all display modes so Browser and Home Screen converge.
first_rule="'body > :first-child,body > :first-child > :first-child,body > :first-child > :first-child > :first-child':{'margin-top':'8px !important','padding-top':'0 !important'}"
for theme,bg,fg,alink in [
    ('light','#f7f5ef','#1d1c1a','#365b7b'),
    ('dark','#0b0d10','#edf0f3','#8eb9e4'),
    ('brown','#e9dcc0','#49382a','#765432'),
]:
    old=f"rendition.themes.register('{theme}',{{'html,body':{{'background':'{bg} !important','color':'{fg} !important'}},'a':{{'color':'{alink} !important'}}}});"
    new=f"rendition.themes.register('{theme}',{{'html,body':{{'background':'{bg} !important','color':'{fg} !important','margin-top':'0 !important','padding-top':'0 !important'}},{first_rule},'a':{{'color':'{alink} !important'}}}});"
    v2=one(v2,old,new,f'V67_THEME_{theme.upper()}')

# 3) Let viewport stabilization run in parallel with EPUB cache/network I/O and
# create epub.js only after the real viewer rectangle has settled.
helper_anchor='  async function r3LoadEpubBuffer(){\n'
if helper_anchor not in v2:
    raise SystemExit('V67_LOAD_BUFFER_ANCHOR_MISSING')
helper=r'''  async function r3WaitPreRenderStageV67(){
    const viewer=$('viewer');
    const started=performance.now();
    let last='',stable=0,latest=null;
    try{document.documentElement.classList.add('r3-stage-boot-v67')}catch{}
    for(let n=0;n<10;n++){
      const vv=window.visualViewport||null;
      const rect=viewer&&viewer.getBoundingClientRect?viewer.getBoundingClientRect():null;
      const sample={
        w:Math.round(Number(rect&&rect.width||viewer&&viewer.clientWidth||0)),
        h:Math.round(Number(rect&&rect.height||viewer&&viewer.clientHeight||0)),
        vw:Math.round(Number(vv&&vv.width||window.innerWidth||0)),
        vh:Math.round(Number(vv&&vv.height||window.innerHeight||0)),
        top:Math.round(Number(vv&&vv.offsetTop||0)),
      };
      latest=sample;
      const valid=sample.w>180&&sample.h>300&&sample.vw>180&&sample.vh>300;
      const sig=valid?[sample.w,sample.h,sample.vw,sample.vh,sample.top].join('|'):'';
      if(sig&&sig===last)stable++;else stable=0;
      last=sig||last;
      if(valid&&stable>=2&&performance.now()-started>=140)break;
      await new Promise(resolve=>setTimeout(resolve,55));
    }
    const state=window.__r3StageGeometryV67={owner:'stage-geometry-v67',preRender:latest||null,waitMs:Math.round(performance.now()-started),postResizeDisplay:false,dvhOwner:false,ready:false};
    return latest;
  }

'''
v2=v2.replace(helper_anchor,helper+helper_anchor,1)

load_old='      const buffer=await r3LoadEpubBuffer();\n      book=window.ePub(buffer);'
load_new="      const r3StagePromiseV67=r3WaitPreRenderStageV67();\n      const buffer=await r3LoadEpubBuffer();\n      await r3StagePromiseV67;\n      book=window.ePub(buffer);"
v2=one(v2,load_old,load_new,'V67_PARALLEL_STAGE_WAIT')

# v61 currently resizes and redisplays *after* the first render. That is visible
# as the browser cold-load layout break. v67 only samples after render; no second
# resize/display is allowed during boot.
v2=one(v2,
    'const r3BootGeometryV61=await r3NormalizeBootGeometryV61(r3BootAnchorV61);',
    'const r3BootGeometryV61=await r3WaitStableBootGeometryV61();',
    'V67_DISABLE_POST_RENDER_REDISPLAY')

# Reveal only after the existing final boot gates have completed.
reveal="r3ClampPaginatedVerticalV62('pre-reveal');bindEpubContents();$('loading').classList.add('hidden');"
reveal_new="r3ClampPaginatedVerticalV62('pre-reveal');try{document.documentElement.classList.remove('r3-stage-boot-v67');if(window.__r3StageGeometryV67)window.__r3StageGeometryV67.ready=true}catch{}bindEpubContents();$('loading').classList.add('hidden');"
v2=one(v2,reveal,reveal_new,'V67_ATOMIC_STAGE_REVEAL')

# 4) Keep more EPUBs in persistent IDB. The Library currently contains many more
# than four books, so LRU=4 causes avoidable network misses when switching books.
v2=one(v2,"const R3_EPUB_CACHE_LIMIT=4;","const R3_EPUB_CACHE_LIMIT=12;",'V67_EPUB_CACHE_LIMIT')

# Start immutable parser dependencies as early as possible.
script_anchor='<script src="/artifact-library/vendor/jszip.min.js"></script>\n<script src="/artifact-library/vendor/epub.min.js"></script>'
preloads='<link rel="preload" href="/artifact-library/vendor/jszip.min.js" as="script">\n<link rel="preload" href="/artifact-library/vendor/epub.min.js" as="script">\n'+script_anchor
v2=one(v2,script_anchor,preloads,'V67_VENDOR_PRELOAD')

# Cache static vendor parser files at the outer response owner. HTML and private
# library data remain no-store. One day is long enough to speed cold starts while
# still allowing unversioned vendor files to be replaced safely.
cache_anchor='    const response = await app.fetch(request, env, ctx);\n    if (request.method !== "GET") return response;\n'
cache_patch='''    const response = await app.fetch(request, env, ctx);\n    if (request.method !== "GET") return response;\n    if ((url.pathname === "/artifact-library/vendor/jszip.min.js" || url.pathname === "/artifact-library/vendor/epub.min.js") && response.status === 200) {\n      const h = new Headers(response.headers);\n      h.set("Cache-Control", "public, max-age=86400, stale-while-revalidate=604800");\n      h.delete("Pragma");\n      return new Response(response.body, { status: response.status, headers: h });\n    }\n'''
v36=one(v36,cache_anchor,cache_patch,'V67_VENDOR_CACHE_HEADERS')

for required in [
    '__r3StageGeometryV67',
    "owner:'stage-geometry-v67'",
    'postResizeDisplay:false',
    'dvhOwner:false',
    "document.documentElement.classList.add('r3-stage-boot-v67')",
    "document.documentElement.classList.remove('r3-stage-boot-v67')",
    'const R3_EPUB_CACHE_LIMIT=12;',
    'rel="preload" href="/artifact-library/vendor/jszip.min.js"',
    'rel="preload" href="/artifact-library/vendor/epub.min.js"',
    "const r3BootGeometryV61=await r3WaitStableBootGeometryV61();",
    first_rule,
]:
    if required not in v2:
        raise SystemExit('V67_REQUIRED_V2_MISSING:'+required)

for forbidden in [
    'body{position:fixed;inset:0;width:100%;height:100dvh;background:var(--bg)}',
    'const r3BootGeometryV61=await r3NormalizeBootGeometryV61(r3BootAnchorV61);',
    'const R3_EPUB_CACHE_LIMIT=4;',
]:
    if forbidden in v2:
        raise SystemExit('V67_FORBIDDEN_V2_PRESENT:'+forbidden)

if 'max-age=86400, stale-while-revalidate=604800' not in v36:
    raise SystemExit('V67_VENDOR_CACHE_PATCH_MISSING')

V2.write_text(v2,encoding='utf-8')
V36.write_text(v36,encoding='utf-8')
print('READER_V67_STAGE_GEOMETRY_PERF=PASS')
