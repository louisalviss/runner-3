from pathlib import Path
s=Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')
for m in ["R3_SINGLE_OWNER_SESSION_V73='v73'","R3_SINGLE_OWNER_SESSION_SECONDS_V73=90*24*60*60","r3SingleOwnerCookieV73(ownerSession)","single-owner-v73"]:
    assert m in s,m
print('READER_V73_SINGLE_OWNER_SESSION_CHECK=PASS')
