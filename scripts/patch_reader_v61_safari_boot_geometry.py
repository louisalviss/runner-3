from pathlib import Path

V2 = Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js')
v2 = V2.read_text(encoding='utf-8')

if "__r3SafariBootGeometryV61" in v2:
    print('READER_V61_SAFARI_BOOT_GEOMETRY=ALREADY_APPLIED')
    raise SystemExit(0)

anchor = """      async function r3WaitStableBootCfiV58(){
"""
if anchor not in v2:
    raise SystemExit('V61_MISSING_V58_CFI_WAIT_ANCHOR')

geometry = r'''      async function r3WaitStableBootGeometryV61(){
        const started=Date.now();
        let last='',stable=0,latest=null;
        for(let n=0;n<22;n++){
          const vv=window.visualViewport||null;
          const viewer=$('viewer');
          const sample={
            vw:Math.round(Number(vv&&vv.width||window.innerWidth||0)),
            vh:Math.round(Number(vv&&vv.height||window.innerHeight||0)),
            top:Math.round(Number(vv&&vv.offsetTop||0)),
            left:Math.round(Number(vv&&vv.offsetLeft||0)),
            w:Math.round(Number(viewer&&viewer.clientWidth||0)),
            h:Math.round(Number(viewer&&viewer.clientHeight||0)),
          };
          latest=sample;
          const valid=sample.vw>200&&sample.vh>300&&sample.w>180&&sample.h>180;
          const sig=valid?[sample.vw,sample.vh,sample.top,sample.left,sample.w,sample.h].join('|'):'';
          if(sig&&sig===last)stable++;else stable=0;
          last=sig||last;
          if(valid&&stable>=3&&Date.now()-started>=450)return sample;
          await new Promise(resolve=>setTimeout(resolve,75));
        }
        return latest;
      }

      async function r3NormalizeBootGeometryV61(anchorCfi){
        const before=await r3WaitStableBootGeometryV61();
        const viewer=$('viewer');
        if(!viewer||!rendition)return before;
        const width=Math.round(Number(viewer.clientWidth||0));
        const height=Math.round(Number(viewer.clientHeight||0));
        if(width>180&&height>180){
          try{rendition.resize(width,height);}catch{}
          const restore=String(anchorCfi||r3CurrentBootCfiV61()||'');
          if(restore){try{await rendition.display(restore);}catch{}}
          await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        }
        return await r3WaitStableBootGeometryV61();
      }

      function r3CurrentBootCfiV61(){
        try{const loc=rendition&&rendition.currentLocation&&rendition.currentLocation();return String(loc&&loc.start&&loc.start.cfi||'');}catch{return '';}
      }
'''
v2 = v2.replace(anchor, geometry + anchor, 1)

needle = """      async function r3WaitStableBootCfiV58(){
"""
# The geometry helper was inserted immediately before this marker. Now run it
# after the initial saved-CFI display but before the final CFI stability gate.
run_anchor = """      const stableCfiV58=await r3WaitStableBootCfiV58();
"""
if run_anchor not in v2:
    raise SystemExit('V61_MISSING_STABLE_CFI_CALL')
run_replacement = r'''      const r3BootAnchorV61=saved||r3CurrentBootCfiV61();
      const r3BootGeometryV61=await r3NormalizeBootGeometryV61(r3BootAnchorV61);
      window.__r3SafariBootGeometryV61={owner:'safari-boot-geometry-v61',geometry:r3BootGeometryV61||null,anchor:r3BootAnchorV61||'',settledAt:Date.now()};
      const stableCfiV58=await r3WaitStableBootCfiV58();
'''
v2 = v2.replace(run_anchor, run_replacement, 1)

# After geometry normalization, keep v5 out of the way just long enough for
# the final CFI reveal. This is shorter than v58's old 1.2 s blanket window.
quiet_old = "window.__R3_READER_BOOT_QUIET_UNTIL_V58=Date.now()+1200;"
quiet_new = "window.__R3_READER_BOOT_QUIET_UNTIL_V58=Date.now()+650;"
if quiet_old in v2:
    v2 = v2.replace(quiet_old, quiet_new, 1)
elif quiet_new not in v2:
    raise SystemExit('V61_MISSING_BOOT_QUIET_MARKER')

for marker in [
    '__r3SafariBootGeometryV61',
    'r3WaitStableBootGeometryV61',
    'r3NormalizeBootGeometryV61',
    "owner:'safari-boot-geometry-v61'",
    'Date.now()-started>=450',
    'rendition.resize(width,height)',
]:
    if marker not in v2:
        raise SystemExit('V61_MISSING:' + marker)

V2.write_text(v2, encoding='utf-8')
print('READER_V61_SAFARI_BOOT_GEOMETRY=PASS')
