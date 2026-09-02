from pathlib import Path

ROOT = Path('cloudflare/runner3-core')
V2 = ROOT / 'artifact-library-reader-v2-entry.js'
text = V2.read_text(encoding='utf-8')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)

css = '.r3-live-library-tools{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;margin-bottom:10px}.r3-live-library-tools .r3-live-library-search{margin-bottom:0}.r3-live-library-upload{appearance:none;border:1px solid #29313a;background:#151b22;color:#edf2f7;border-radius:12px;height:44px;padding:0 12px;font:inherit;font-weight:800;white-space:nowrap}.r3-live-library-upload:disabled{opacity:.55}'
if '.r3-live-library-tools{' not in text:
    text = replace_once(
        text,
        'body.r3-live-library-open #r3AudioDock{pointer-events:none!important}',
        'body.r3-live-library-open #r3AudioDock{pointer-events:none!important}' + css,
        'live library upload css',
    )

old_search = '<input id="r3LiveLibrarySearch" class="r3-live-library-search" type="search" placeholder="Search books" autocomplete="off" aria-label="Search books">'
new_search = '<div class="r3-live-library-tools"><input id="r3LiveLibrarySearch" class="r3-live-library-search" type="search" placeholder="Search books" autocomplete="off" aria-label="Search books"><button id="r3LiveLibraryUpload" class="r3-live-library-upload" type="button">＋ EPUB</button><input id="r3LiveLibraryUploadInput" type="file" accept=".epub,application/epub+zip" hidden></div>'
if 'id="r3LiveLibraryUploadInput"' not in text:
    text = replace_once(text, old_search, new_search, 'live library upload controls')

runtime = r'''
  function r3LiveUploadEpub(file){
    if(!file)return;
    if(!/\.epub$/i.test(file.name||'')){window.alert('Chỉ nhận file .epub');return;}
    if(Number(file.size||0)>90*1024*1024){window.alert('EPUB vượt giới hạn 90 MiB.');return;}
    const button=$('r3LiveLibraryUpload');
    if(button){button.disabled=true;button.textContent='Uploading…';}
    r3LiveLibraryStatus('Uploading '+file.name+'…');
    const xhr=new XMLHttpRequest();
    xhr.open('POST','/artifact-library/api/upload',true);
    xhr.setRequestHeader('x-runner3-library','1');
    xhr.setRequestHeader('x-r3-filename',encodeURIComponent(file.name));
    xhr.setRequestHeader('content-type','application/epub+zip');
    xhr.upload.onprogress=e=>{if(e.lengthComputable){const pct=Math.max(0,Math.min(100,Math.round((e.loaded/e.total)*100)));r3LiveLibraryStatus('Uploading '+file.name+' · '+pct+'%');}};
    xhr.onerror=()=>{if(button){button.disabled=false;button.textContent='＋ EPUB';}r3LiveLibraryStatus('Upload failed: network error');window.alert('Upload failed: network error');};
    xhr.onload=()=>{let body={};try{body=JSON.parse(xhr.responseText||'{}')}catch(_){}if(xhr.status===401){location.reload();return;}if(xhr.status<200||xhr.status>=300||body.ok!==true){if(button){button.disabled=false;button.textContent='＋ EPUB';}const message=body.error==='EPUB_ALREADY_EXISTS'?'File này đã có trong R2.':(body.error||('HTTP '+xhr.status));r3LiveLibraryStatus('Upload failed: '+message);window.alert('Upload failed: '+message);return;}if(button){button.disabled=false;button.textContent='＋ EPUB';}r3LiveLibraryStatus('Uploaded to R2');r3LiveLibraryBooks=null;r3LoadLiveLibrary();};
    xhr.send(file);
  }
'''
if 'function r3LiveUploadEpub(file)' not in text:
    text = replace_once(
        text,
        "  $('r3LiveLibraryButton')?.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();r3OpenLiveLibrary();});",
        runtime + "\n  $('r3LiveLibraryUpload')?.addEventListener('click',()=>$('r3LiveLibraryUploadInput')?.click());\n  $('r3LiveLibraryUploadInput')?.addEventListener('change',e=>{const file=e.target.files&&e.target.files[0];e.target.value='';r3LiveUploadEpub(file);});\n  $('r3LiveLibraryButton')?.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();r3OpenLiveLibrary();});",
        'live library upload runtime',
    )

for marker in [
    'id="r3LiveLibraryUpload"',
    'id="r3LiveLibraryUploadInput"',
    'function r3LiveUploadEpub(file)',
    "'/artifact-library/api/upload'",
    'EPUB_ALREADY_EXISTS',
    'r3LiveLibraryBooks=null',
]:
    if marker not in text:
        raise SystemExit('READER_V52_UPLOAD_MISSING:' + marker)

V2.write_text(text, encoding='utf-8')
print('READER_V52_R2_UPLOAD=PASS')
