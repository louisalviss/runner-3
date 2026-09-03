from pathlib import Path

root = Path('cloudflare/runner3-core')
v2 = (root / 'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
v36 = (root / 'artifact-library-reader-v36-home-screen-safe-area-entry.js').read_text(encoding='utf-8')
wrapper = (root / 'artifact-library-reader-v7-github-audio-entry.js').read_text(encoding='utf-8')
deploy = Path('.github/workflows/runner3-core-public-hosted-reader-deploy.yml').read_text(encoding='utf-8')

for marker in [
    'viewport-fit=cover',
    'apple-mobile-web-app-status-bar-style" content="black-translucent',
    '#viewer{position:absolute;inset:0',
]:
    if marker not in v2:
        raise SystemExit('READER_V36_BASE_PREREQUISITE_MISSING:' + marker)

for marker in [
    'data-r3-home-screen-safe-area-v36="1"',
    'data-r3-ios-statusbar-viewport-v39="1"',
    'r3-ios-home-screen-startup-policy',
    'opaque-v39',
    'patchLibraryStartup',
    'patchReader',
    'apple-mobile-web-app-capable',
    'mobile-web-app-capable',
    'X-R3-Reader-IOS-Startup-Viewport',
    'X-R3-Reader-IOS-Forced-Inset',
    'disabled-v39',
    '#viewer { top: 0 !important; }',
]:
    if marker not in v36:
        raise SystemExit('READER_V39_PATCH_MISSING:' + marker)

# v38 caused a double inset on real iPhone Home Screen and must stay removed.
for forbidden in [
    'r3-ios-standalone-forced-inset-v38',
    '--r3-ios-forced-top-v38',
    '48px',
    'screenHeight-height',
    'forcedInsetV38',
]:
    if forbidden in v36:
        raise SystemExit('READER_V39_OLD_FORCED_INSET_STILL_PRESENT:' + forbidden)

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

print('READER_V39_HOME_SCREEN_STARTUP_VIEWPORT_CHECK=PASS')
