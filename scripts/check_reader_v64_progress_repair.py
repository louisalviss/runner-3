from pathlib import Path

ROOT = Path('cloudflare/runner3-core')
simple = (ROOT / 'artifact-library-simple-entry.js').read_text(encoding='utf-8')
v2 = (ROOT / 'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')

for marker in ["reader_client_version:'v64'", "'x-r3-reader-client-version':'v64'"]:
    if marker not in simple:
        raise SystemExit('V64_SIMPLE_MISSING:' + marker)

for marker in [
    "R3_READER_CLIENT_VERSION_V63='v64'",
    'function r3StructuralPercentV64(loc)',
    'const structural=r3StructuralPercentV64(loc);',
    'if(precise===0&&Number.isFinite(structural)&&structural>0)return structural;',
    'if(Number.isFinite(native)&&native>0)',
    'repairCurrentProgressV64',
    'Promise.resolve(r3EnsureLocationsV55()).then(()=>repairCurrentProgressV64())',
]:
    if marker not in v2:
        raise SystemExit('V64_READER_MISSING:' + marker)

if "if(Number.isFinite(loc?.start?.percentage))return" in v2:
    raise SystemExit('V64_ZERO_PERCENT_LEGACY_FALLBACK_REMAINS')

print('READER_V64_PROGRESS_REPAIR_CHECK=PASS')
