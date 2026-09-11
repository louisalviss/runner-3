from pathlib import Path
v82_wrapper=Path('cloudflare/runner3-core/artifact-library-reader-v82-stable-shell-entry.js').read_text(encoding='utf-8')
v82_helper=Path('cloudflare/runner3-core/artifact-library-reader-v82-patch.js').read_text(encoding='utf-8')
v82=v82_wrapper+'\n'+v82_helper
v7=Path('cloudflare/runner3-core/artifact-library-reader-v7-github-audio-entry.js').read_text(encoding='utf-8')
for marker in [
    "owner: 'stable-shell-v82'",
    "X-R3-Reader-Stable-Shell', 'v82'",
    "X-R3-Reader-Pagination-Owner', 'v82'",
    'data-r3-stable-shell-early-v82',
    'data-r3-stable-shell-runtime-v82',
    'heading-label',
    'r3V82GestureLayer',
    'r3-v90-browser body.r3-audio-ui.r3-audio-expanded #viewer{bottom:210px!important}',
    'r3-v90-home body.r3-audio-ui.r3-audio-expanded #viewer{bottom:calc(210px + env(safe-area-inset-bottom,0px))!important}',
    "X-R3-Reader-Layout-Owner', 'converged-v90'",
    'data-r3-nonblocking-restore-v89="1"',
    '__r3AudioCorePrepareCurrent',
    "window.__R3_BASE_READER_BOOT_DONE = false",
    "r3-reader-position:' + bookKey",
]:
    assert marker in v82, marker
assert 'artifact-library-reader-v82-stable-shell-entry.js' in v7
assert 'artifact-library-reader-v82-patch.js' in v82_wrapper
assert 'patchReaderV82' in v82_wrapper
assert 'artifact-library-reader-v36-home-screen-safe-area-entry.js' not in v7.splitlines()[0]
print('READER_V82_STABLE_SHELL_CHECK=PASS')
