from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
SIMPLE=ROOT/'artifact-library-simple-entry.js'
text=SIMPLE.read_text(encoding='utf-8')

# libraryPage() is itself a JavaScript template literal. The regex in the v56
# browser helper must therefore carry two escaping layers: the template source
# needs four backslashes so the emitted browser JS receives /\\/g.
old="replace(/\\\\/g,'/')"
new="replace(/\\\\\\\\/g,'/')"
count=text.count(old)
if count != 1:
    raise SystemExit('V66_INLINE_ESCAPE_ANCHOR_COUNT:'+str(count))
text=text.replace(old,new,1)

if new not in text:
    raise SystemExit('V66_INLINE_ESCAPE_REPAIR_MISSING')
SIMPLE.write_text(text,encoding='utf-8')
print('READER_V66_INLINE_ESCAPE_REPAIR=PASS')
