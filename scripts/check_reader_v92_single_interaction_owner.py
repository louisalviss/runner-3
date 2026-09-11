from pathlib import Path
ROOT=Path('cloudflare/runner3-core')
v2=(ROOT/'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
v3=(ROOT/'artifact-library-reader-v3-entry.js').read_text(encoding='utf-8')
v4=(ROOT/'artifact-library-reader-v4-entry.js').read_text(encoding='utf-8')
v82=(ROOT/'artifact-library-reader-v82-patch.js').read_text(encoding='utf-8')
shell=(ROOT/'artifact-library-reader-v82-stable-shell-entry.js').read_text(encoding='utf-8')
assert "window.__R3_INTERACTION_OWNER_V92" in v82
assert "interactionOwner: 'v92'" in v82
assert "__r3LegacyGestureV2Suppressed" in v2
assert "__r3LegacyGestureV3Suppressed" in v3
assert "__r3LegacyHitZonesV4Suppressed" in v4
assert "display:none!important;pointer-events:none!important" in v82
assert "#r3SettingsBackdrop{display:none!important;pointer-events:none!important}" in v82
assert "X-R3-Reader-Interaction-Owner', 'single-v92'" in shell
print('READER_V92_SINGLE_INTERACTION_OWNER_CHECK=PASS')
