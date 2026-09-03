from pathlib import Path

V2 = Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js')
V5 = Path('cloudflare/runner3-core/artifact-library-reader-v5-entry.js')
v2 = V2.read_text(encoding='utf-8')
v5 = V5.read_text(encoding='utf-8')

if '__r3PaginatedVerticalClampV62' in v2:
    print('READER_V62_PAGINATED_VERTICAL_CLAMP=ALREADY_APPLIED')
    raise SystemExit(0)

anchor = r'''      function r3CurrentBootCfiV61(){
        try{const loc=rendition&&rendition.currentLocation&&rendition.currentLocation();return String(loc&&loc.start&&loc.start.cfi||'');}catch{return '';}
      }
'''
if anchor not in v2:
    raise SystemExit('V62_MISSING_V61_CURRENT_CFI_ANCHOR')

helper = anchor + r'''
      function r3ClampPaginatedVerticalV62(reason=''){
        let fixed=0;
        const zero=node=>{
          try{
            if(node&&Math.abs(Number(node.scrollTop||0))>.5){node.scrollTop=0;fixed++;}
          }catch{}
        };
        zero($('viewer'));
        try{zero(rendition&&rendition.manager&&rendition.manager.container);}catch{}
        try{zero(rendition&&rendition.manager&&rendition.manager.stage&&rendition.manager.stage.container);}catch{}
        for(const frame of document.querySelectorAll('#viewer iframe')){
          try{
            const doc=frame.contentDocument;
            const win=frame.contentWindow;
            zero(doc&&doc.documentElement);
            zero(doc&&doc.body);
            if(win&&Math.abs(Number(win.scrollY||0))>.5){win.scrollTo(Number(win.scrollX||0),0);fixed++;}
          }catch{}
        }
        const state=window.__r3PaginatedVerticalClampV62||(window.__r3PaginatedVerticalClampV62={owner:'paginated-vertical-clamp-v62',calls:0,fixes:0,lastReason:'',lastAt:0,coldBootGuardTicks:0,coldBootGuardActive:false});
        state.calls++;state.fixes+=fixed;state.lastReason=String(reason||'');state.lastAt=Date.now();
        if(reason==='cold-boot-guard')state.coldBootGuardTicks=(Number(state.coldBootGuardTicks)||0)+1;
        return fixed;
      }
      window.__r3ClampPaginatedVerticalV62=r3ClampPaginatedVerticalV62;
'''
v2 = v2.replace(anchor, helper, 1)

render_old = "rendition.on('rendered',()=>{bindEpubContents();});"
render_new = "rendition.on('rendered',()=>{bindEpubContents();setTimeout(()=>r3ClampPaginatedVerticalV62('rendered'),0);});"
if render_old in v2:
    v2 = v2.replace(render_old, render_new, 1)
elif render_new not in v2:
    raise SystemExit('V62_RENDERED_HANDLER_ANCHOR_MISSING')

geometry_anchor = r'''      window.__r3SafariBootGeometryV61={owner:'safari-boot-geometry-v61',geometry:r3BootGeometryV61||null,anchor:r3BootAnchorV61||'',settledAt:Date.now()};
      const stableCfiV58=await r3WaitStableBootCfiV58();
'''
geometry_new = r'''      window.__r3SafariBootGeometryV61={owner:'safari-boot-geometry-v61',geometry:r3BootGeometryV61||null,anchor:r3BootAnchorV61||'',settledAt:Date.now()};
      r3ClampPaginatedVerticalV62('post-geometry');
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      r3ClampPaginatedVerticalV62('post-geometry-raf');
      const stableCfiV58=await r3WaitStableBootCfiV58();
'''
if geometry_anchor not in v2:
    raise SystemExit('V62_GEOMETRY_SETTLE_ANCHOR_MISSING')
v2 = v2.replace(geometry_anchor, geometry_new, 1)

reveal_anchor = "      bindEpubContents();$('loading').classList.add('hidden');"
reveal_new = "      r3ClampPaginatedVerticalV62('pre-reveal');bindEpubContents();$('loading').classList.add('hidden');"
if reveal_anchor not in v2:
    raise SystemExit('V62_REVEAL_ANCHOR_MISSING')
v2 = v2.replace(reveal_anchor, reveal_new, 1)

# Any later v5 resize/display must also clear accidental vertical scroll before
# the page becomes visible. Preserve horizontal/page position and the CFI.
v5_anchor = '''      if(anchor){
        try{await rendition.display(anchor);}catch{}
      }
'''
v5_new = '''      if(anchor){
        try{await rendition.display(anchor);}catch{}
      }
      try{if(typeof window.__r3ClampPaginatedVerticalV62==='function')window.__r3ClampPaginatedVerticalV62('v5-reflow');}catch{}
'''
if v5_anchor not in v5:
    raise SystemExit('V62_V5_REFLOW_ANCHOR_MISSING')
v5 = v5.replace(v5_anchor, v5_new, 1)

# iOS Safari may introduce paginated iframe vertical drift without emitting a
# visualViewport resize. Previously that could remain visible until the final
# four-second clamp. During cold boot, clamp only vertical drift every 100 ms;
# never call rendition.display() or resize from this guard, so CFI/page position
# and horizontal pagination remain untouched.
reveal_new2 = reveal_new + r'''
      try{
        const vv=window.visualViewport||null;
        let clampTimer=0;
        let coldBootGuardTimer=0;
        const coldBootGuardStarted=Date.now();
        const clampStateV62=window.__r3PaginatedVerticalClampV62;
        if(clampStateV62){clampStateV62.coldBootGuardActive=true;clampStateV62.coldBootGuardStartedAt=coldBootGuardStarted;}
        const runColdBootGuardV62=()=>{
          r3ClampPaginatedVerticalV62('cold-boot-guard');
          if(Date.now()-coldBootGuardStarted>=4200&&coldBootGuardTimer){
            clearInterval(coldBootGuardTimer);coldBootGuardTimer=0;
            if(clampStateV62)clampStateV62.coldBootGuardActive=false;
          }
        };
        runColdBootGuardV62();
        coldBootGuardTimer=setInterval(runColdBootGuardV62,100);
        const onBootViewportV62=()=>{clearTimeout(clampTimer);clampTimer=setTimeout(()=>r3ClampPaginatedVerticalV62('visual-viewport'),80);};
        if(vv)vv.addEventListener('resize',onBootViewportV62,{passive:true});
        setTimeout(()=>{
          try{if(vv)vv.removeEventListener('resize',onBootViewportV62);}catch{}
          clearTimeout(clampTimer);
          if(coldBootGuardTimer){clearInterval(coldBootGuardTimer);coldBootGuardTimer=0;}
          if(clampStateV62){clampStateV62.coldBootGuardActive=false;clampStateV62.coldBootGuardEndedAt=Date.now();}
          r3ClampPaginatedVerticalV62('boot-window-end');
        },4200);
      }catch{}'''
v2 = v2.replace(reveal_new, reveal_new2, 1)

for marker in [
    '__r3PaginatedVerticalClampV62',
    "owner:'paginated-vertical-clamp-v62'",
    "r3ClampPaginatedVerticalV62('pre-reveal')",
    "r3ClampPaginatedVerticalV62('post-geometry')",
    "r3ClampPaginatedVerticalV62('visual-viewport')",
    "r3ClampPaginatedVerticalV62('cold-boot-guard')",
    'coldBootGuardTimer=setInterval(runColdBootGuardV62,100)',
    'coldBootGuardActive=true',
]:
    if marker not in v2:
        raise SystemExit('V62_MISSING:' + marker)
if "__r3ClampPaginatedVerticalV62('v5-reflow')" not in v5:
    raise SystemExit('V62_V5_CLAMP_MISSING')

V2.write_text(v2, encoding='utf-8')
V5.write_text(v5, encoding='utf-8')
print('READER_V62_PAGINATED_VERTICAL_CLAMP=PASS')
