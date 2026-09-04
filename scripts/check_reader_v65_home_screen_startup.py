from pathlib import Path

text = Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')

base = [
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">',
    '<meta name="apple-mobile-web-app-capable" content="yes">',
    '<meta name="mobile-web-app-capable" content="yes">',
]
for marker in base:
    if marker not in text:
        raise SystemExit('READER_LIBRARY_STARTUP_BASE_MISSING:' + marker)

v39 = [
    '<meta name="apple-mobile-web-app-status-bar-style" content="black">',
    '<meta name="r3-ios-home-screen-startup-policy" content="opaque-v39">',
    '"X-R3-Reader-IOS-Startup-Viewport": "opaque-v39"',
]
v68 = [
    '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">',
    '<meta name="r3-ios-home-screen-startup-policy" content="full-bleed-v68">',
    '"X-R3-Reader-IOS-Startup-Viewport": "full-bleed-v68"',
]
if not all(marker in text for marker in v39) and not all(marker in text for marker in v68):
    raise SystemExit('READER_LIBRARY_STARTUP_POLICY_INCOMPLETE')

for forbidden in [
    'r3-ios-standalone-forced-inset-v38',
    '--r3-ios-forced-top-v38',
]:
    if forbidden in text:
        raise SystemExit('READER_LIBRARY_OLD_INSET_PRESENT:' + forbidden)

print('READER_LIBRARY_STARTUP_POLICY_CHECK=PASS')
