from pathlib import Path

text = Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')

for marker in [
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">',
    '<meta name="apple-mobile-web-app-capable" content="yes">',
    '<meta name="mobile-web-app-capable" content="yes">',
    '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">',
    '<meta name="r3-ios-home-screen-startup-policy" content="full-bleed-v68">',
    '<style data-r3-library-full-bleed-v68="1">body{padding-top:env(safe-area-inset-top)!important;padding-bottom:env(safe-area-inset-bottom)!important}</style>',
    '"X-R3-Reader-IOS-Startup-Viewport": "full-bleed-v68"',
]:
    if marker not in text:
        raise SystemExit('READER_V68_LIBRARY_FULL_BLEED_MISSING:' + marker)

for forbidden in [
    '<meta name="apple-mobile-web-app-status-bar-style" content="black">',
    '<meta name="r3-ios-home-screen-startup-policy" content="opaque-v39">',
    '"X-R3-Reader-IOS-Startup-Viewport": "opaque-v39"',
    'r3-ios-standalone-forced-inset-v38',
    '--r3-ios-forced-top-v38',
]:
    if forbidden in text:
        raise SystemExit('READER_V68_LIBRARY_FULL_BLEED_FORBIDDEN:' + forbidden)

print('READER_V68_LIBRARY_FULL_BLEED_OWNER_CHECK=PASS')
