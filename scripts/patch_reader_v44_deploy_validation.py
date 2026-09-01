from pathlib import Path

p = Path('.github/workflows/runner3-core-public-hosted-reader-deploy.yml')
s = p.read_text(encoding='utf-8')
old = 'v34+v35:ahead-prefetch+range-follow+single-audio-owner'
new = 'v34+v35+v44:range-follow+single-audio+single-highlight-owner'
if old not in s:
    raise SystemExit('v44 deploy: old proof marker missing')
s = s.replace(old, new)
needle = "          grep -q 'data-r3-audio-continuity-v34' cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js\n"
insert = needle + "          grep -q 'data-r3-sentence-highlight-owner-v44' cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js\n          grep -q \"registry.clear\" cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js\n"
if needle not in s:
    raise SystemExit('v44 deploy: source validation marker missing')
s = s.replace(needle, insert, 1)
live = "grep -q 'data-r3-audio-continuity-v34=\"1\"' /tmp/reader"
if live not in s:
    raise SystemExit('v44 deploy: live reader marker missing')
s = s.replace(live, live + " && grep -q 'data-r3-sentence-highlight-owner-v44=\"1\"' /tmp/reader", 1)
p.write_text(s, encoding='utf-8')
