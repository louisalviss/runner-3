from pathlib import Path

p=Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js')
s=p.read_text(encoding='utf-8')
start=s.find("rendition.on('rendered'")
if start<0:
    raise SystemExit('V58_RENDERED_HANDLER_NOT_FOUND')
end=s.find('});',start)
if end<0:
    raise SystemExit('V58_RENDERED_HANDLER_END_NOT_FOUND')
end+=3
block=s[start:end]
needle="$('loading').classList.add('hidden');"
if needle in block:
    block=block.replace(needle,'')
# Normalize the common post-patch handler so the main v58 patch can assert it.
if 'bindEpubContents()' in block:
    block="rendition.on('rendered',()=>{bindEpubContents();});"
s=s[:start]+block+s[end:]
p.write_text(s,encoding='utf-8')
print('READER_V58_RENDERED_NORMALIZE=PASS')
