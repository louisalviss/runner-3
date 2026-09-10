from pathlib import Path
R=Path('cloudflare/runner3-core')
v35=(R/'artifact-library-reader-v35-continuity-single-owner-entry.js').read_text(encoding='utf-8')
v34=(R/'artifact-library-reader-v34-continuous-range-sync-entry.js').read_text(encoding='utf-8')
for m in [
 "body.r3-audio-ui #viewer{bottom:calc(76px + env(safe-area-inset-bottom,0px))!important}",
 "body.r3-audio-ui.r3-audio-expanded #viewer{bottom:calc(210px + env(safe-area-inset-bottom,0px))!important}",
 "body.r3-audio-ui .bottom-status{bottom:calc(82px + env(safe-area-inset-bottom,0px))!important}",
 "body.r3-audio-ui.r3-audio-expanded .bottom-status{bottom:calc(216px + env(safe-area-inset-bottom,0px))!important}",
]:
 if m not in v35: raise SystemExit('READER_V80_LAYOUT_MISSING:'+m)
if 'body.r3-audio-ui #viewer,body.r3-audio-ui.r3-audio-expanded #viewer' in v35:
 raise SystemExit('READER_V80_COLLAPSED_EXPANDED_MUST_DIFFER')
if "headers.set('X-R3-Reader-Dock-Audio', 'stable-v80')" not in v35:
 raise SystemExit('READER_V80_LIVE_HEADER_MISSING')
combined=v34+'\n'+v35
for m in [
 "prefetch:false,clientVersion:'reader-audio-v80-warm-current-foreground'",
 "warmCurrentTimer=setTimeout(()=>warmCurrentChapter(),120);",
 "setTimeout(()=>warmCurrentChapter(),180)",
 "setTimeout(()=>warmCurrentChapter(),420)",
]:
 if m not in combined: raise SystemExit('READER_V80_WARM_MISSING:'+m)
if "prefetch:true,clientVersion:'reader-audio-v60-warm-current'" in combined:
 raise SystemExit('READER_V80_WARM_STILL_LOW_PRIORITY')
if "prefetch:true,clientVersion:'reader-audio-v60-prefetch'" not in combined:
 raise SystemExit('READER_V80_AHEAD_PREFETCH_REGRESSION')
print('READER_V80_DOCK_AND_FIRST_AUDIO_CHECK=PASS')
