from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
V35=ROOT/'artifact-library-reader-v35-continuity-single-owner-entry.js'
V34=ROOT/'artifact-library-reader-v34-continuous-range-sync-entry.js'

v35=V35.read_text(encoding='utf-8')
old="body.r3-audio-ui #viewer,body.r3-audio-ui.r3-audio-expanded #viewer{bottom:calc(76px + env(safe-area-inset-bottom,0px))!important}\nbody.r3-audio-ui .bottom-status,body.r3-audio-ui.r3-audio-expanded .bottom-status{bottom:calc(82px + env(safe-area-inset-bottom,0px))!important}"
new="body.r3-audio-ui #viewer{bottom:calc(76px + env(safe-area-inset-bottom,0px))!important}\nbody.r3-audio-ui.r3-audio-expanded #viewer{bottom:calc(210px + env(safe-area-inset-bottom,0px))!important}\nbody.r3-audio-ui .bottom-status{bottom:calc(82px + env(safe-area-inset-bottom,0px))!important}\nbody.r3-audio-ui.r3-audio-expanded .bottom-status{bottom:calc(216px + env(safe-area-inset-bottom,0px))!important}"
if old in v35:
    v35=v35.replace(old,new,1)
elif new not in v35:
    raise SystemExit('V80_V35_LAYOUT_ANCHOR_MISSING')
proof_line="      headers.set('X-R3-Reader-Patch-Proof', 'v34+v35:ahead-prefetch+range-follow+single-audio-owner');"
proof_new=proof_line+"\n      headers.set('X-R3-Reader-Dock-Audio', 'stable-v80');"
if proof_new not in v35:
    if proof_line not in v35: raise SystemExit('V80_V35_HEADER_ANCHOR_MISSING')
    v35=v35.replace(proof_line,proof_new,1)
V35.write_text(v35,encoding='utf-8')

v34=V34.read_text(encoding='utf-8')
oldwarm="prefetch:true,clientVersion:'reader-audio-v60-warm-current'"
newwarm="prefetch:false,clientVersion:'reader-audio-v80-warm-current-foreground'"
if oldwarm in v34:
    v34=v34.replace(oldwarm,newwarm,1)
elif newwarm not in v34:
    raise SystemExit('V80_WARM_PRIORITY_ANCHOR_MISSING')
oldrel="warmCurrentTimer=setTimeout(()=>warmCurrentChapter(),650);"
newrel="warmCurrentTimer=setTimeout(()=>warmCurrentChapter(),120);"
if oldrel in v34:
    v34=v34.replace(oldrel,newrel,1)
elif newrel not in v34:
    raise SystemExit('V80_RELOC_WARM_ANCHOR_MISSING')
oldboot="setTimeout(()=>{manualArmedAt=Date.now();tick();warmCurrentChapter();if(currentId())schedulePrefetch();},700);"
newboot="warmCurrentChapter();setTimeout(()=>warmCurrentChapter(),180);setTimeout(()=>warmCurrentChapter(),420);setTimeout(()=>{manualArmedAt=Date.now();tick();warmCurrentChapter();if(currentId())schedulePrefetch();},700);"
if oldboot in v34:
    v34=v34.replace(oldboot,newboot,1)
elif newboot not in v34:
    raise SystemExit('V80_BOOT_WARM_ANCHOR_MISSING')
V34.write_text(v34,encoding='utf-8')

v35=V35.read_text(encoding='utf-8')
if oldwarm in v35:
    v35=v35.replace(oldwarm,newwarm)
if oldrel in v35:
    v35=v35.replace(oldrel,newrel)
if oldboot in v35:
    v35=v35.replace(oldboot,newboot)
V35.write_text(v35,encoding='utf-8')
print('READER_V80_DOCK_AND_FIRST_AUDIO=PASS')
