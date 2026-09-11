from pathlib import Path
ROOT=Path('cloudflare/runner3-core')
v82=(ROOT/'artifact-library-reader-v82-patch.js').read_text(encoding='utf-8')
pin=(ROOT/'artifact-library-pin-v2-entry.js').read_text(encoding='utf-8')
hard=(ROOT/'artifact-library-hardening-entry.js').read_text(encoding='utf-8')
simple=(ROOT/'artifact-library-simple-entry.js').read_text(encoding='utf-8')
v7=(ROOT/'artifact-library-reader-v7-github-audio-entry.js').read_text(encoding='utf-8')
# v91 owns WebKit session compatibility and frame-interaction primitives.
# The interaction owner itself is intentionally superseded by v92 single-owner,
# so this compatibility check must not force the runtime back to v91.
assert ("interactionOwner: 'v91'" in v82 or "interactionOwner: 'v92'" in v82), 'interaction owner v91/v92'
for marker in ['window.__r3BindReaderFramesV91','bindReaderDocument(frame.contentDocument)','pointer-events:none!important','interactiveTarget(event.target)']:
    assert marker in v82, marker
assert "layer.addEventListener('pointerdown'" not in v82
for marker in ['data-r3-pin-autofill-v91="1"','autocomplete="username"','SameSite=Lax','Expires=${expires}']:
    assert marker in pin, marker
for name,text in [('hard',hard),('simple',simple),('v7',v7)]:
    assert 'SameSite=Lax' in text, name
    assert 'Expires=${expires}' in text, name
print('READER_V91_INTERACTION_SESSION_CHECK=PASS')
