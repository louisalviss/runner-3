from pathlib import Path

ROOT = Path('cloudflare/runner3-core')
V2 = ROOT / 'artifact-library-reader-v2-entry.js'
V3 = ROOT / 'artifact-library-reader-v3-entry.js'
V4 = ROOT / 'artifact-library-reader-v4-entry.js'
V82 = ROOT / 'artifact-library-reader-v82-patch.js'
SHELL = ROOT / 'artifact-library-reader-v82-stable-shell-entry.js'


def once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise SystemExit(label)
    return text.replace(old, new, 1)

v2 = V2.read_text(encoding='utf-8')
v3 = V3.read_text(encoding='utf-8')
v4 = V4.read_text(encoding='utf-8')
v82 = V82.read_text(encoding='utf-8')
shell = SHELL.read_text(encoding='utf-8')

v2 = once(
    v2,
    "  function bindGestureTarget(doc, widthFn){\n    if(!doc||doc.documentElement?.dataset?.r3GestureV2==='1')return;",
    "  function bindGestureTarget(doc, widthFn){\n    if(window.__R3_INTERACTION_OWNER_V92){window.__r3LegacyGestureV2Suppressed=true;return;}\n    if(!doc||doc.documentElement?.dataset?.r3GestureV2==='1')return;",
    'V92_V2_GUARD_ANCHOR_MISSING',
)

v3 = once(
    v3,
    "(()=>{\n  const layer=document.getElementById('r3GestureLayer');",
    "(()=>{\n  if(window.__R3_INTERACTION_OWNER_V92){window.__r3LegacyGestureV3Suppressed=true;return;}\n  const layer=document.getElementById('r3GestureLayer');",
    'V92_V3_GUARD_ANCHOR_MISSING',
)

v4 = once(
    v4,
    "(()=>{\n  const body=document.body;",
    "(()=>{\n  if(window.__R3_INTERACTION_OWNER_V92){window.__r3LegacyHitZonesV4Suppressed=true;return;}\n  const body=document.body;",
    'V92_V4_GUARD_ANCHOR_MISSING',
)

v82 = v82.replace("interactionOwner: 'v91'", "interactionOwner: 'v92'")
state_anchor = "  const state = window.__r3StableEarlyV82 = { owner: 'stable-shell-v82', standalone, blockedListeners: 0, blockedTimers: 0, blockedObservers: 0, restoreGuard: 'nonblocking-v89', layoutOwner: 'v90', interactionOwner: 'v92', restoreShieldReleased: '', restoreWatchdogFired: false };\n"
if "window.__R3_INTERACTION_OWNER_V92 = 'single-owner-v92';" not in v82:
    if state_anchor not in v82:
        raise SystemExit('V92_EARLY_STATE_ANCHOR_MISSING')
    v82 = v82.replace(state_anchor, state_anchor + "  window.__R3_INTERACTION_OWNER_V92 = 'single-owner-v92';\n", 1)

old_css = "html.r3-v82-stable #r3GestureLayer,html.r3-v82-stable .r3-hit-zone{pointer-events:none!important}"
new_css = "html.r3-v82-stable #r3GestureLayer,html.r3-v82-stable .r3-hit-zone{display:none!important;pointer-events:none!important}\nhtml.r3-v82-stable #r3SettingsBackdrop{display:none!important;pointer-events:none!important}"
v82 = once(v82, old_css, new_css, 'V92_LEGACY_LAYER_CSS_ANCHOR_MISSING')

shell = once(
    shell,
    "headers.set('X-R3-Reader-Interaction-Owner', 'frame-v91');",
    "headers.set('X-R3-Reader-Interaction-Owner', 'single-v92');",
    'V92_HEADER_ANCHOR_MISSING',
)

for marker in [
    '__R3_INTERACTION_OWNER_V92',
    '__r3LegacyGestureV2Suppressed',
]:
    if marker not in v2 + v82:
        raise SystemExit('V92_MARKER_MISSING:' + marker)
if '__r3LegacyGestureV3Suppressed' not in v3:
    raise SystemExit('V92_V3_MARKER_MISSING')
if '__r3LegacyHitZonesV4Suppressed' not in v4:
    raise SystemExit('V92_V4_MARKER_MISSING')
if "'single-v92'" not in shell:
    raise SystemExit('V92_HEADER_MARKER_MISSING')

V2.write_text(v2, encoding='utf-8')
V3.write_text(v3, encoding='utf-8')
V4.write_text(v4, encoding='utf-8')
V82.write_text(v82, encoding='utf-8')
SHELL.write_text(shell, encoding='utf-8')
print('READER_V92_SINGLE_INTERACTION_OWNER=PASS')
