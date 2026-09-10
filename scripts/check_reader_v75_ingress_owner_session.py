from pathlib import Path
s=Path('cloudflare/runner3-core/artifact-library-reader-v7-github-audio-entry.js').read_text(encoding='utf-8')
for m in ["R3_READER_INGRESS_SESSION_V75='v75'",'r3ExpectedLibrarySessionV75','r3HasOwnerSessionV75','v75-login-required',"url.pathname === '/artifact-library/read'"]:
    assert m in s,m
# Gate must execute before health/control/fallback routing.
i=s.index("url.pathname === '/artifact-library/read'")
j=s.index('if (request.method === "GET" && url.pathname === "/healthz")')
assert i<j
print('READER_V75_INGRESS_OWNER_SESSION_CHECK=PASS')
