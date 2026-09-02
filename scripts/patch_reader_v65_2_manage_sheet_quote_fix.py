from pathlib import Path
import json
import re

ROOT=Path('cloudflare/runner3-core')
SIMPLE=ROOT/'artifact-library-simple-entry.js'
V2=ROOT/'artifact-library-reader-v2-entry.js'


def convert_static_template(text: str, lhs_pattern: str, label: str) -> str:
    pattern=re.compile(r'('+lhs_pattern+r')=`(.*?)`;',re.S)
    match=pattern.search(text)
    if not match:
        raise SystemExit('V652_TEMPLATE_NOT_FOUND:'+label)
    literal=json.dumps(match.group(2),ensure_ascii=False)
    return text[:match.start()]+match.group(1)+'='+literal+';'+text[match.end():]

simple=SIMPLE.read_text(encoding='utf-8')
v2=V2.read_text(encoding='utf-8')

simple=convert_static_template(simple,r"style\.id='r3ManageStyleV651';style\.textContent",'simple-style')
simple=convert_static_template(simple,r"layer\.innerHTML",'simple-html')
v2=convert_static_template(v2,r"style\.id='r3ReaderManageStyleV651';style\.textContent",'reader-style')
v2=convert_static_template(v2,r"layer\.innerHTML",'reader-html')

for source,label in [(simple,'simple'),(v2,'reader')]:
    if 'style.textContent=`' in source and ('r3ManageStyleV651' in source or 'r3ReaderManageStyleV651' in source):
        raise SystemExit('V652_BACKTICK_STYLE_REMAINS:'+label)
    if 'r3ManageLayerV651' not in source and 'r3ReaderManageLayerV651' not in source:
        raise SystemExit('V652_MANAGE_LAYER_MISSING:'+label)

SIMPLE.write_text(simple,encoding='utf-8')
V2.write_text(v2,encoding='utf-8')
print('READER_V65_2_MANAGE_SHEET_QUOTE_FIX=PASS')
