from pathlib import Path

root = Path('cloudflare/runner3-core')
v2 = (root / 'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
v36 = (root / 'artifact-library-reader-v36-home-screen-safe-area-entry.js').read_text(encoding='utf-8')
wrapper = (root / 'artifact-library-reader-v7-github-audio-entry.js').read_text(encoding='utf-8')
deploy = Path('.github/workflows/runner3-core-public-hosted-reader-deploy.yml').read_text(encoding='utf-8')

# Base Reader deliberately uses viewport-fit=cover + a translucent iOS status bar,
# while the EPUB viewer itself starts at inset:0. Home Screen mode therefore needs
# an explicit safe-area top reservation without changing normal Safari geometry.
for marker in [
    'viewport-fit=cover',
    'apple-mobile-web-app-status-bar-style" content="black-translucent',
    '#viewer{position:absolute;inset:0',
]:
    if marker not in v2:
        raise SystemExit('READER_V36_BASE_PREREQUISITE_MISSING:' + marker)

for marker in [
    'data-r3-home-screen-safe-area-v36="1"',
    '@media (display-mode: standalone)',
    'html.r3-home-screen-v36 #viewer',
    'top: env(safe-area-inset-top, 0px) !important',
    "navigator.standalone===true",
    "document.documentElement.classList.add('r3-home-screen-v36')",
    'X-R3-Reader-Home-Screen-Safe-Area',
]:
    if marker not in v36:
        raise SystemExit('READER_V36_PATCH_MISSING:' + marker)

if '#viewer { top: env(safe-area-inset-top, 0px) !important; }' not in v36:
    raise SystemExit('READER_V36_VIEWER_TOP_RULE_MISSING')
if 'body #viewer' in v36 or '#viewer { top:' not in v36:
    raise SystemExit('READER_V36_SCOPE_INVALID')
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
