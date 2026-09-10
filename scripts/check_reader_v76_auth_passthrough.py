from pathlib import Path
s=Path("cloudflare/runner3-core/artifact-library-simple-entry.js").read_text(encoding="utf-8")
assert "R3_AUTH_PASSTHROUGH_V76='v76'" in s
assert 'includes(p)) return redirectHome();' not in s
for route in ['/artifact-library/login','/artifact-library/setup-pin','/artifact-library/reset-pin','/artifact-library/api/magic-link']:
    assert route in s, route
assert 'return app.fetch(request, env, ctx);' in s
print('READER_V76_AUTH_PASSTHROUGH_CHECK=PASS')
