from pathlib import Path

ROOT = Path('cloudflare/runner3-core')
V2 = (ROOT / 'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
V36 = (ROOT / 'artifact-library-reader-v36-home-screen-safe-area-entry.js').read_text(encoding='utf-8')
AUDIO = (ROOT / 'audio-entry.js').read_text(encoding='utf-8')
OUTER = (ROOT / 'opportunity-router-entry.js').read_text(encoding='utf-8')

for marker in [
    '__r3FullBleedV68',
    "owner:'full-bleed-autostretch-v68'",
    '--r3-screen-w-v68',
    '--r3-screen-h-v68',
    '--r3-screen-x-v68',
    '--r3-screen-y-v68',
    'html.r3-full-bleed-v68 #viewer{inset:0!important;width:100%!important;height:100%!important}',
    "r3InstallFullBleedV68();",
    "r3ApplyFullBleedV68('pre-render-enter',false)",
    "r3ApplyFullBleedV68('pre-render-sample-'+n,false)",
    "window.visualViewport.addEventListener('resize'",
    "window.visualViewport.addEventListener('scroll'",
    "rendition.resize(w,h)",
    "Math.max(8,Number(window.__r3FullBleedV68&&window.__r3FullBleedV68.safeTop||0)+8)",
    'const R3_EPUB_CACHE_LIMIT=12;',
    'postResizeDisplay:false',
    'postRenderGeometryWait:false',
]:
    if marker not in V2:
        raise SystemExit('READER_V68_V2_MISSING:' + marker)

for forbidden in [
    'body{position:fixed;inset:0;width:100%;height:100dvh;background:var(--bg)}',
    'body{position:fixed;inset:0;background:var(--bg)}',
    "body.style.setProperty('padding-top','8px','important');",
    'const r3BootGeometryV61=await r3NormalizeBootGeometryV61',
    'const r3BootGeometryV61=await r3WaitStableBootGeometryV61',
]:
    if forbidden in V2:
        raise SystemExit('READER_V68_V2_FORBIDDEN:' + forbidden)

for marker in [
    'content="full-bleed-v68"',
    'STARTUP_MARKER_OLD',
    'out.replace(OPAQUE, TRANSLUCENT)',
    '"X-R3-Reader-IOS-Startup-Viewport": "full-bleed-v68"',
    '"X-R3-Reader-IOS-Statusbar-Viewport": "full-bleed-v68"',
    '"X-R3-Reader-IOS-Forced-Inset": "disabled-v68"',
    "statusbar:'black-translucent'",
    '#viewer { top: 0 !important; }',
]:
    if marker not in V36:
        raise SystemExit('READER_V68_V36_MISSING:' + marker)

for forbidden in [
    'out.replace(TRANSLUCENT, OPAQUE)',
    '"X-R3-Reader-IOS-Startup-Viewport": "opaque-v39"',
    '"X-R3-Reader-IOS-Forced-Inset": "disabled-v39"',
    '48px',
    '--r3-ios-forced-top-v38',
]:
    if forbidden in V36:
        raise SystemExit('READER_V68_V36_FORBIDDEN:' + forbidden)

for marker in [
    'IOS_STARTUP_MARKER_OLD',
    'content="full-bleed-v68"',
    'out.replace(IOS_STATUS_BLACK, IOS_STATUS_TRANSLUCENT)',
    'headers.set("X-R3-Reader-IOS-Startup-Viewport", "full-bleed-v68")',
]:
    if marker not in AUDIO:
        raise SystemExit('READER_V68_AUDIO_MISSING:' + marker)

for forbidden in [
    'out.replace(IOS_STATUS_TRANSLUCENT, IOS_STATUS_BLACK)',
    'READER_VENDOR_CACHE_V67',
    'X-R3-Reader-Vendor-Cache',
]:
    if forbidden in AUDIO:
        raise SystemExit('READER_V68_AUDIO_FORBIDDEN:' + forbidden)

# The failed v67 parser cache experiment must not return in the wrangler owner.
for forbidden in [
    'READER_VENDOR_CACHE_V67_OUTERMOST',
    'applyReaderVendorCacheV67Outermost',
    'X-R3-Reader-Vendor-Cache',
]:
    if forbidden in OUTER:
        raise SystemExit('READER_V68_OUTER_FORBIDDEN:' + forbidden)

print('READER_V68_FULL_BLEED_AUTOSTRETCH_CHECK=PASS')
