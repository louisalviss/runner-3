from pathlib import Path
s=Path("cloudflare/runner3-core/artifact-library-pin-v2-entry.js").read_text(encoding="utf-8")
assert 'R3_PIN_FORM_V77 = "v77"' in s
assert 'async function formParamsV77' in s
assert 'await request.formData()' not in s
assert 'PIN_STATE_READ_FAILED' in s
assert 'PIN_FORM_PARSE_FAILED' in s
assert 'X-R3-PIN-Form' in s
print('READER_V77_PIN_FORM_CHECK=PASS')
