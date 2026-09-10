from pathlib import Path
s=Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')
assert "R3_SESSION_BOUND_SYNC_V74='v74'" in s
assert 'v74-login-required' in s
# one browser-session guard in each public surface
for fn in ['publicReader','publicDelivery','publicList']:
    i=s.index('async function '+fn)
    block=s[i:i+1200]
    assert 'hasBrowserLibrarySession(request, env)' in block, fn
assert 'const inner = await internalRequest(request, env);' in s
print('READER_V74_SESSION_BOUND_SYNC_CHECK=PASS')
