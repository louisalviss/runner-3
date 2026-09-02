from pathlib import Path
import re

ROOT = Path('cloudflare/runner3-core')
SIMPLE = ROOT / 'artifact-library-simple-entry.js'
ROUTER = ROOT / 'opportunity-router-entry.js'
V2 = ROOT / 'artifact-library-reader-v2-entry.js'

simple = SIMPLE.read_text(encoding='utf-8')
router = ROUTER.read_text(encoding='utf-8')
v2 = V2.read_text(encoding='utf-8')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Fast, public, non-sensitive client-version endpoint. This lets a long-lived
# v51 live Reader tab notice a later deployment and reload once to the same URL;
# canonical CFI restore then returns the user to the saved reading position.
# ---------------------------------------------------------------------------
version_handler = r'''
function publicClientVersionV63(request) {
  if (request.method !== 'GET') {
    return new Response(JSON.stringify({ok:false,error:'METHOD_NOT_ALLOWED'}), {status:405,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store'}});
  }
  return new Response(JSON.stringify({ok:true,reader_client_version:'v63'}), {status:200,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-r3-reader-client-version':'v63'}});
}

'''
if 'function publicClientVersionV63' not in simple:
    simple = replace_once(simple, 'async function publicDelivery(request, env, ctx) {', version_handler + 'async function publicDelivery(request, env, ctx) {', 'v63 version handler')

raw_route = '    if (p === "/artifact-library/api/raw") return publicRawEpubV57(request, env);\n'
version_route = '    if (p === "/artifact-library/api/client-version") return publicClientVersionV63(request);\n'
if version_route not in simple:
    simple = replace_once(simple, raw_route, raw_route + version_route, 'v63 version route')

if '"/artifact-library/api/client-version"' not in router:
    router = replace_once(router, '    "/artifact-library/api/raw",\n', '    "/artifact-library/api/raw",\n    "/artifact-library/api/client-version",\n', 'v63 router fast version path')


# ---------------------------------------------------------------------------
# Reader live Library hardening.
# 1) one resilient list fetch retry for transient/non-JSON responses;
# 2) support both objects/items API shapes across historical versions;
# 3) isolate render/cover exceptions so one bad metadata record cannot blank Lib;
# 4) version handshake for future long-lived live-session tabs.
# ---------------------------------------------------------------------------
if 'R3_READER_CLIENT_VERSION_V63' not in v2:
    state_anchor = '  let r3LiveLibraryBooks=null;\n'
    state_inject = r'''  const R3_READER_CLIENT_VERSION_V63='v63';
  window.__R3_READER_CLIENT_VERSION=R3_READER_CLIENT_VERSION_V63;
  let r3LiveLibraryBooks=null;
'''
    v2 = replace_once(v2, state_anchor, state_inject, 'v63 reader version marker')

# Rename the existing rich renderer, then put a defensive wrapper in front of it.
if 'function r3RenderLiveLibraryCoreV63(){' not in v2:
    v2 = replace_once(v2, '  function r3RenderLiveLibrary(){', '  function r3RenderLiveLibraryCoreV63(){', 'v63 rename rich renderer')

if 'function r3RenderLiveLibrary(){try{return r3RenderLiveLibraryCoreV63()}' not in v2:
    load_marker = '  async function r3LoadLiveLibrary(){'
    fallback_renderer = r'''  function r3RenderLiveLibrary(){try{return r3RenderLiveLibraryCoreV63()}catch(error){
    try{console.warn('R3_LIBRARY_RENDER_RECOVERY_V63',error)}catch{}
    const root=$('r3LiveLibraryList');if(!root)return;root.textContent='';
    const q=String(r3LiveLibraryQuery||'').trim().toLocaleLowerCase('vi');
    let rows=(Array.isArray(r3LiveLibraryBooks)?r3LiveLibraryBooks:[]).filter(row=>{const bookKey=String(row&&row.key||'');const title=String(row&&row.title||row&&row.display_title||row&&row.name||row&&row.scope||bookKey.split('/').pop()||'Book').replace(/\.epub$/i,'');return !q||title.toLocaleLowerCase('vi').includes(q)||bookKey.toLocaleLowerCase('vi').includes(q)});
    if(!rows.length){const empty=document.createElement('div');empty.className='r3-live-library-empty';empty.textContent=r3LiveLibraryBooks?'No books found.':'Loading…';root.appendChild(empty);return;}
    for(const row of rows){try{const bookKey=String(row&&row.key||'');if(!bookKey)continue;const title=String(row&&row.title||row&&row.display_title||row&&row.name||row&&row.scope||bookKey.split('/').pop()||'Book').replace(/\.epub$/i,'');const article=document.createElement('article');article.className='r3-live-book';const same=bookKey===key;const link=document.createElement(same?'button':'a');link.className='r3-live-book-link';if(same){link.type='button';link.addEventListener('click',r3CloseLiveLibrary)}else link.href='/artifact-library/read?key='+encodeURIComponent(bookKey);const name=document.createElement('span');name.className='r3-live-book-name';name.textContent=title;link.appendChild(name);if(same){const badge=document.createElement('span');badge.className='r3-live-book-current';badge.textContent='Đang đọc';link.appendChild(badge)}article.appendChild(link);root.appendChild(article)}catch(rowError){try{console.warn('R3_LIBRARY_ROW_RECOVERY_V63',rowError)}catch{}}}
  }}
'''
    v2 = replace_once(v2, load_marker, fallback_renderer + load_marker, 'v63 defensive renderer')

# Replace the whole historical loader regardless of v54-v59 internal changes.
loader_pattern = re.compile(r"  async function r3LoadLiveLibrary\(\)\{.*?\n  \}\n(?=  function r3OpenLiveLibrary\(\)\{)", re.S)
loader_replacement = r'''  async function r3FetchLiveLibraryListV63(attempt=0){
    let response;
    try{response=await fetch('/artifact-library/api/list',{cache:'no-store',headers:{'accept':'application/json','x-runner3-library':'1'}})}catch(error){if(attempt<1){await new Promise(resolve=>setTimeout(resolve,400));return r3FetchLiveLibraryListV63(attempt+1)}throw error}
    const body=await response.text();let data=null;
    try{data=body?JSON.parse(body):null}catch(error){if(attempt<1){await new Promise(resolve=>setTimeout(resolve,400));return r3FetchLiveLibraryListV63(attempt+1)}throw new Error('Library API returned invalid data (HTTP '+response.status+')')}
    if((response.status===502||response.status===503||response.status===504)&&attempt<1){await new Promise(resolve=>setTimeout(resolve,400));return r3FetchLiveLibraryListV63(attempt+1)}
    if(!response.ok||!data||data.ok!==true)throw new Error(data&&data.error||('HTTP '+response.status));
    if(Array.isArray(data.items))return data.items;
    if(Array.isArray(data.objects))return data.objects;
    return [];
  }
  async function r3LoadLiveLibrary(){
    if(Array.isArray(r3LiveLibraryBooks)){r3LiveLibraryStatus('');r3RenderLiveLibrary();return;}
    r3LiveLibraryStatus('Loading…');r3RenderLiveLibrary();
    try{
      const rows=await r3FetchLiveLibraryListV63();
      r3LiveLibraryBooks=rows.filter(row=>/\.epub$/i.test(String(row&&row.key||'')));
      r3LiveLibraryStatus('');r3RenderLiveLibrary();
    }catch(error){const root=$('r3LiveLibraryList');if(root)root.textContent='';r3LiveLibraryStatus('Could not load Library: '+String(error&&error.message||error));}
  }
'''
v2, count = loader_pattern.subn(loader_replacement, v2, count=1)
if count != 1:
    raise SystemExit(f'v63 loader replacement: expected 1 match, got {count}')

# Replace panel-open function with a version check before exposing live Library.
open_pattern = re.compile(r"  function r3OpenLiveLibrary\(\)\{.*?\n  \}\n(?=  function r3ArmLiveLibraryHistory\(\)\{)", re.S)
open_replacement = r'''  async function r3EnsureFreshReaderClientV63(){
    try{
      const response=await fetch('/artifact-library/api/client-version?ts='+Date.now(),{cache:'no-store',headers:{'accept':'application/json'}});
      if(!response.ok)return true;
      const data=await response.json();const server=String(data&&data.reader_client_version||'');
      if(server&&server!==R3_READER_CLIENT_VERSION_V63){const once='r3-reader-client-reload:'+server+':'+key;try{if(sessionStorage.getItem(once)==='1')return true;sessionStorage.setItem(once,'1')}catch{}location.reload();return false}
    }catch(error){try{console.warn('R3_CLIENT_VERSION_CHECK_V63',error)}catch{}}
    return true;
  }
  async function r3OpenLiveLibrary(){
    if(!r3LiveLibraryNode)return;
    if(!(await r3EnsureFreshReaderClientV63()))return;
    try{document.getElementById('r3AudioElement')?.pause();}catch{}
    hideControls();document.body.classList.add('r3-live-library-open');r3LiveLibraryNode.hidden=false;
    window.__r3LiveReaderSessionV51={active:true,bookKey:key,openedAt:Date.now(),renditionAlive:!!rendition,clientVersion:R3_READER_CLIENT_VERSION_V63};
    r3LoadLiveLibrary();
  }
'''
v2, count = open_pattern.subn(open_replacement, v2, count=1)
if count != 1:
    raise SystemExit(f'v63 open replacement: expected 1 match, got {count}')

for marker in [
    "reader_client_version:'v63'",
    'p === "/artifact-library/api/client-version"',
]:
    if marker not in simple:
        raise SystemExit('V63_SIMPLE_MISSING:' + marker)
for marker in [
    '"/artifact-library/api/client-version"',
    'r3IsLibraryFastPathV57',
]:
    if marker not in router:
        raise SystemExit('V63_ROUTER_MISSING:' + marker)
for marker in [
    "R3_READER_CLIENT_VERSION_V63='v63'",
    'r3FetchLiveLibraryListV63',
    'R3_LIBRARY_RENDER_RECOVERY_V63',
    'r3EnsureFreshReaderClientV63',
    "cache:'no-store'",
    'Array.isArray(data.items)',
    'Array.isArray(data.objects)',
]:
    if marker not in v2:
        raise SystemExit('V63_READER_MISSING:' + marker)

SIMPLE.write_text(simple, encoding='utf-8')
ROUTER.write_text(router, encoding='utf-8')
V2.write_text(v2, encoding='utf-8')
print('READER_V63_LIBRARY_RECOVERY=PASS')
