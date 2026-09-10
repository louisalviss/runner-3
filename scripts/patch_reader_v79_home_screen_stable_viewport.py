from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
V36=ROOT/'artifact-library-reader-v36-home-screen-safe-area-entry.js'
AUDIO=ROOT/'audio-entry.js'
V2=ROOT/'artifact-library-reader-v2-entry.js'

v36=V36.read_text(encoding='utf-8')
# v68 intentionally made Home Screen translucent; v79 reverses only the PWA document policy.
trans="  if (out.includes(OPAQUE)) out = out.replace(OPAQUE, TRANSLUCENT);\n  else if (!out.includes(TRANSLUCENT)) out = ensureHeadMeta(out, TRANSLUCENT);"
opaque="  if (out.includes(TRANSLUCENT)) out = out.replace(TRANSLUCENT, OPAQUE);\n  else if (!out.includes(OPAQUE)) out = ensureHeadMeta(out, OPAQUE);"
if v36.count(trans)!=2: raise SystemExit(f'V79_V36_POLICY_COUNT:{v36.count(trans)}')
v36=v36.replace(trans,opaque)
# Keep the previous policy marker removable, then install the new stable marker.
v36=v36.replace("const STARTUP_MARKER_OLD = '<meta name=\"r3-ios-home-screen-startup-policy\" content=\"full-bleed-v68\">';","const STARTUP_MARKER_OLD = '<meta name=\"r3-ios-home-screen-startup-policy\" content=\"full-bleed-v68\">';")
v36=v36.replace("const STARTUP_MARKER = '<meta name=\"r3-ios-home-screen-startup-policy\" content=\"full-bleed-v68\">';","const STARTUP_MARKER = '<meta name=\"r3-ios-home-screen-startup-policy\" content=\"stable-opaque-v79\">';")
v36=v36.replace("version:'v68-full-bleed-autostretch'","version:'v79-standalone-stable'")
v36=v36.replace("statusbar:'black-translucent'","statusbar:'black'")
v36=v36.replace('"X-R3-Reader-IOS-Startup-Viewport": "full-bleed-v68"','"X-R3-Reader-IOS-Startup-Viewport": "stable-opaque-v79"')
v36=v36.replace('"X-R3-Reader-IOS-Statusbar-Viewport": "full-bleed-v68"','"X-R3-Reader-IOS-Statusbar-Viewport": "stable-opaque-v79"')
v36=v36.replace('"X-R3-Reader-IOS-Forced-Inset": "disabled-v68"','"X-R3-Reader-IOS-Forced-Inset": "opaque-owned-v79"')
needle='          "X-R3-Reader-Home-Screen-Safe-Area": "v36",\n'
if needle not in v36: raise SystemExit('V79_V36_HEADER_ANCHOR')
v36=v36.replace(needle,needle+'          "X-R3-Reader-Home-Screen-Layout": "stable-v79",\n',1)
V36.write_text(v36,encoding='utf-8')

audio=AUDIO.read_text(encoding='utf-8')
trans_audio="  if (out.includes(IOS_STATUS_BLACK)) out = out.replace(IOS_STATUS_BLACK, IOS_STATUS_TRANSLUCENT);\n  else out = ensureHeadMeta(out, IOS_STATUS_TRANSLUCENT);"
opaque_audio="  if (out.includes(IOS_STATUS_TRANSLUCENT)) out = out.replace(IOS_STATUS_TRANSLUCENT, IOS_STATUS_BLACK);\n  else if (!out.includes(IOS_STATUS_BLACK)) out = ensureHeadMeta(out, IOS_STATUS_BLACK);"
if trans_audio not in audio: raise SystemExit('V79_AUDIO_POLICY_ANCHOR')
audio=audio.replace(trans_audio,opaque_audio,1)
audio=audio.replace('content="full-bleed-v68"','content="stable-opaque-v79"')
audio=audio.replace('headers.set("X-R3-Reader-IOS-Startup-Viewport", "full-bleed-v68");','headers.set("X-R3-Reader-IOS-Startup-Viewport", "stable-opaque-v79");')
AUDIO.write_text(audio,encoding='utf-8')

v2=V2.read_text(encoding='utf-8')
# Stable PWA shell: layout viewport owns geometry; no double visualViewport offsets.
old='body{position:fixed;left:var(--r3-screen-x-v68,0px);top:var(--r3-screen-y-v68,0px);right:auto;bottom:auto;width:var(--r3-screen-w-v68,100vw);height:var(--r3-screen-h-v68,100vh);background:var(--bg)}'
new='body{position:fixed;inset:0;width:100%;height:100%;background:var(--bg)}'
if old not in v2: raise SystemExit('V79_BODY_SHELL_ANCHOR')
v2=v2.replace(old,new,1)
# The opaque statusbar already reserves the top safe area; do not add it again inside EPUB content.
oldpad="body.style.setProperty('padding-top',String(Math.max(8,Number(window.__r3FullBleedV68&&window.__r3FullBleedV68.safeTop||0)+8))+'px','important');"
if oldpad not in v2: raise SystemExit('V79_INNER_TOP_ANCHOR')
v2=v2.replace(oldpad,"body.style.setProperty('padding-top','8px','important');",1)
# Runtime proof marker, useful for physical-device diagnostics.
install="  function r3InstallFullBleedV68(){\n    if(!r3IosV68())return false;"
repl="  function r3InstallFullBleedV68(){\n    if(!r3IosV68())return false;\n    if(r3StandaloneV68())window.__r3HomeScreenStableV79={owner:'home-screen-stable-v79',dynamicViewport:false,audioReserve:76,installedAt:Date.now()};"
if install not in v2: raise SystemExit('V79_RUNTIME_MARKER_ANCHOR')
v2=v2.replace(install,repl,1)
V2.write_text(v2,encoding='utf-8')
print('READER_V79_HOME_SCREEN_STABLE_VIEWPORT=PASS')
