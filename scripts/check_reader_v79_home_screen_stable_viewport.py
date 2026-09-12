from pathlib import Path
R=Path('cloudflare/runner3-core')
v2=(R/'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
v35=(R/'artifact-library-reader-v35-continuity-single-owner-entry.js').read_text(encoding='utf-8')
v36=(R/'artifact-library-reader-v36-home-screen-safe-area-entry.js').read_text(encoding='utf-8')
audio=(R/'audio-entry.js').read_text(encoding='utf-8')
required_v2=[
 "r3StandaloneV68()?null:(window.visualViewport||null)",
 "!r3StandaloneV68()&&window.visualViewport&&window.visualViewport.addEventListener('resize'",
 "!r3StandaloneV68()&&window.visualViewport&&window.visualViewport.addEventListener('scroll'",
 "if(!r3StandalonePaginatedV79())setTimeout(()=>r3ClampPaginatedVerticalV62('rendered'),0)",
 "if(!r3StandalonePaginatedV79()){runColdBootGuardV62();coldBootGuardTimer=setInterval(runColdBootGuardV62,100);}",
 "calc(76px + env(safe-area-inset-bottom,0px))",
 "owner:'home-screen-stable-v79'",
 "body{position:fixed;inset:0;width:100%;height:100%;background:var(--bg)}",
 "body.style.setProperty('padding-top','8px','important')",
]
for m in required_v2:
 if m not in v2: raise SystemExit('READER_V79_V2_MISSING:'+m)
for m in ['bottom:calc(76px','bottom:calc(82px','bottom:calc(210px','bottom:calc(216px']:
 if m not in v35: raise SystemExit('READER_V79_RESERVE_MISSING:'+m)
for m in ['content="stable-opaque-v79"',"statusbar:'black'",'"X-R3-Reader-Home-Screen-Layout": "stable-v79"','"X-R3-Reader-IOS-Statusbar-Viewport": "stable-opaque-v79"','"X-R3-Reader-IOS-Forced-Inset": "opaque-owned-v79"']:
 if m not in v36: raise SystemExit('READER_V79_V36_MISSING:'+m)
if 'out.replace(OPAQUE, TRANSLUCENT)' in v36: raise SystemExit('READER_V79_V36_TRANSLUCENT_REGRESSION')
for m in ['content="stable-opaque-v79"','IOS_STATUS_TRANSLUCENT)) out = out.replace(IOS_STATUS_TRANSLUCENT, IOS_STATUS_BLACK)','stable-opaque-v79']:
 if m not in audio: raise SystemExit('READER_V79_AUDIO_MISSING:'+m)
print('READER_V79_HOME_SCREEN_STABLE_VIEWPORT_CHECK=PASS')
