from pathlib import Path

root = Path('cloudflare/runner3-core')
v2 = (root / 'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
v36 = (root / 'artifact-library-reader-v36-home-screen-safe-area-entry.js').read_text(encoding='utf-8')
wrapper = (root / 'artifact-library-reader-v7-github-audio-entry.js').read_text(encoding='utf-8')
deploy = Path('.github/workflows/runner3-core-public-hosted-reader-deploy.yml').read_text(encoding='utf-8')

# Base Reader deliberately uses viewport-fit=cover + translucent iOS status bar.
# v36 now fixes Home Screen at the viewport policy layer: turn the status bar
# opaque so WebKit allocates the document viewport below it, rather than trying
# to compensate an overlay with env(safe-area-inset-top).
for marker in [
    'viewport-fit=cover',
    'apple-mobile-web-app-status-bar-style" content="black-translucent',
    '#viewer{position:absolute;inset:0',
]:
    if marker not in v2:
        raise SystemExit('READER_V36_BASE_PREREQUISITE_MISSING:' + marker)

for marker in [
    'data-r3-home-screen-safe-area-v36="1"',
    'data-r3-ios-statusbar-viewport-v37="1"',
    'apple-mobile-web-app-status-bar-style" content="black-translucent',
    'apple-mobile-web-app-status-bar-style" content="black',
    'out = out.replace(TRANSLUCENT, OPAQUE)',
    '#viewer { top: 0 !important; }',
    "navigator.standalone===true",
    "version:'v36-opaque-statusbar'",
    "statusbar:'black'",
    'X-R3-Reader-Home-Screen-Safe-Area',
    'X-R3-Reader-IOS-Statusbar-Viewport',
]:
    if marker not in v36:
        raise SystemExit('READER_V36_PATCH_MISSING:' + marker)

# The old env(safe-area-inset-top) compensation was the ineffective strategy.
if 'top: env(safe-area-inset-top' in v36:
    raise SystemExit('READER_V36_OLD_TOP_INSET_COMPENSATION_STILL_PRESENT')
if 'artifact-library-reader-v36-home-screen-safe-area-entry.js' not in wrapper:
    raise SystemExit('READER_V36_WRAPPER_NOT_CANONICAL')
for marker in [
    'artifact-library-reader-v36-home-screen-safe-area-entry.js',
    "home_safe=\"$(grep -i '^x-r3-reader-home-screen-safe-area:'",
    "[ \"$home_safe\" = 'v36' ]",
    'data-r3-home-screen-safe-area-v36="1"',
]:
    if marker not in deploy:
        raise SystemExit('READER_V36_DEPLOY_GATE_MISSING:' + marker)

print('READER_V36_HOME_SCREEN_SAFE_AREA_CHECK=PASS')
