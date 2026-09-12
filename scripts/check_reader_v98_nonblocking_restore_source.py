from pathlib import Path
s=Path('cloudflare/runner3-core/artifact-library-reader-v28-prime-base-position-entry.js').read_text()
assert 'z-index:2147483600' not in s
assert "html.r3-restore-pending-v45 body::before{content:none!important;display:none!important;pointer-events:none!important}" in s
assert "html.r3-restore-pending-v45 #viewer{visibility:visible!important;opacity:1!important" in s
assert "html.r3-restore-pending-v45 #r3AudioDock{opacity:1!important;pointer-events:auto!important" in s
print('READER_V98_NONBLOCKING_RESTORE_SOURCE=PASS')
