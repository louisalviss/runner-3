from pathlib import Path
S=Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')
P=Path('cloudflare/runner3-core/artifact-library-pin-v2-entry.js').read_text(encoding='utf-8')
H=Path('cloudflare/runner3-core/artifact-library-hardening-entry.js').read_text(encoding='utf-8')
V7=Path('cloudflare/runner3-core/artifact-library-reader-v7-github-audio-entry.js').read_text(encoding='utf-8')
for marker in [
    "R3_PERSISTENT_OWNER_SESSION_V87='v87'",
    'R3_PERSISTENT_OWNER_SESSION_SECONDS_V87=10*365*24*60*60',
    'R3_SINGLE_OWNER_SESSION_SECONDS_V73=R3_PERSISTENT_OWNER_SESSION_SECONDS_V87',
    'single-owner-v87-persistent',
    'X-R3-Owner-Session-Max-Age',
]: assert marker in S, marker
for name,text in [('pin',P),('hard',H)]:
    assert 'const REMEMBER_SECONDS = 10 * 365 * 24 * 60 * 60;' in text, name
    assert 'const REMEMBER_SECONDS = 30 * 24 * 60 * 60;' not in text, name
assert '30 days after a successful login' not in P

for marker in [
    "R3_READER_PERSISTENT_SESSION_V87='v87'",
    'R3_READER_PERSISTENT_SESSION_SECONDS_V87=10*365*24*60*60',
    'r3PersistentOwnerCookieV87',
    "url.pathname === '/artifact-library/read'",
    "X-R3-Owner-Session', 'single-owner-v87-persistent'",
]: assert marker in V7, marker
print('READER_V87_PERSISTENT_OWNER_SESSION_CHECK=PASS')
