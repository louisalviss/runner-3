from pathlib import Path

ROOT = Path('cloudflare/runner3-core')
V2 = ROOT / 'artifact-library-reader-v2-entry.js'
text = V2.read_text(encoding='utf-8')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)

# v51: keep the current epub.js Book/Rendition alive while browsing Library.
# Reopening the same book becomes a panel close, not a navigation/re-init.
if 'id="r3LiveLibraryButton"' not in text:
    text = replace_once(
        text,
        '<a class="back" href="/artifact-library">‹ Library</a>',
        '<button id="r3LiveLibraryButton" class="back" type="button">‹ Library</button>',
        'replace hard library navigation',
    )

css = r'''
.r3-live-library{position:fixed;z-index:2147482500;inset:0;background:#080a0d;color:#f2f5f8;overflow:auto;-webkit-overflow-scrolling:touch;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.r3-live-library[hidden]{display:none!important}.r3-live-library-shell{max-width:860px;margin:0 auto;padding:max(12px,env(safe-area-inset-top)) 12px max(28px,env(safe-area-inset-bottom))}.r3-live-library-head{display:grid;grid-template-columns:auto minmax(0,1fr) 44px;gap:8px;align-items:center;margin-bottom:12px}.r3-live-library-back,.r3-live-library-close{appearance:none;border:1px solid #29313a;background:#12171d;color:#e8edf3;border-radius:12px;height:44px;padding:0 13px;font:inherit;font-weight:750}.r3-live-library-close{width:44px;padding:0;font-size:22px}.r3-live-library-title{text-align:center;font-size:16px;font-weight:800}.r3-live-library-search{width:100%;border:1px solid #29313a;background:#0e1217;color:#f5f7fa;border-radius:12px;padding:12px 13px;font-size:16px;outline:none;margin-bottom:10px}.r3-live-library-status{color:#8793a0;font-size:12px;padding:4px 2px 10px}.r3-live-library-list{display:grid;gap:8px}.r3-live-book{border:1px solid #202832;background:#0e1217;border-radius:14px;overflow:hidden}.r3-live-book-link{width:100%;appearance:none;border:0;background:transparent;color:#f3f6fa;text-decoration:none;padding:16px 14px;display:flex;align-items:center;justify-content:space-between;gap:10px;text-align:left;font:inherit}.r3-live-book-name{min-width:0;font-size:17px;line-height:1.25;font-weight:750;overflow-wrap:anywhere}.r3-live-book-current{flex:0 0 auto;color:#8fa2b5;font-size:11px;font-weight:750}.r3-live-library-empty{color:#7f8b98;text-align:center;padding:42px 12px;font-size:14px}body.r3-live-library-open #r3AudioDock{pointer-events:none!important}
'''
if '.r3-live-library{position:fixed' not in text:
    text = replace_once(text, '\n</style>\n</head>', css + '\n</style>\n</head>', 'inject live library css')

panel = r'''
<section id="r3LiveLibrary" class="r3-live-library" hidden aria-label="Library">
  <div class="r3-live-library-shell">
    <header class="r3-live-library-head"><button id="r3LiveLibraryBack" class="r3-live-library-back" type="button">‹ Reader</button><div class="r3-live-library-title">Library</div><button id="r3LiveLibraryClose" class="r3-live-library-close" type="button" aria-label="Đóng">×</button></header>
    <input id="r3LiveLibrarySearch" class="r3-live-library-search" type="search" placeholder="Search books" autocomplete="off" aria-label="Search books">
    <div id="r3LiveLibraryStatus" class="r3-live-library-status"></div>
    <div id="r3LiveLibraryList" class="r3-live-library-list"></div>
  </div>
</section>
'''
if 'id="r3LiveLibrary" class="r3-live-library"' not in text:
    text = replace_once(
        text,
        '<script src="/artifact-library/vendor/jszip.min.js"></script>',
        panel + '<script src="/artifact-library/vendor/jszip.min.js"></script>',
        'inject live library panel',
    )

old_interactive = "function targetIsInteractive(target){return !!(target&&target.closest&&target.closest('a,button,input,textarea,select,label'))}"
new_interactive = "function targetIsInteractive(target){return !!(target&&target.closest&&target.closest('a,button,input,textarea,select,label,#r3LiveLibrary'))}"
if old_interactive in text:
    text = replace_once(text, old_interactive, new_interactive, 'protect live library from reader gestures')

live_js = r'''
  // v51 live-session Library: keep book + rendition mounted for same-book reopen.
  let r3LiveLibraryBooks=null;
  let r3LiveLibraryQuery='';
  let r3LiveLibraryHistoryArmed=false;
  const r3LiveLibraryNode=$('r3LiveLibrary');
  const r3Humanize=s=>String(s||'').replace(/[-_]+/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
  const r3TitleFor=b=>r3Humanize((b&&b.scope)||((b&&b.key||'').split('/')[2])||(((b&&b.key||'').split('/').pop()||'Book').replace(/\.epub$/i,'')));
  function r3LiveLibraryVisible(){return !!(r3LiveLibraryNode&&!r3LiveLibraryNode.hidden);}
  function r3LiveLibraryStatus(message){const node=$('r3LiveLibraryStatus');if(node)node.textContent=String(message||'');}
  function r3RenderLiveLibrary(){
    const root=$('r3LiveLibraryList');if(!root)return;root.textContent='';
    const q=String(r3LiveLibraryQuery||'').trim().toLocaleLowerCase('vi');
    const rows=(Array.isArray(r3LiveLibraryBooks)?r3LiveLibraryBooks:[]).filter(b=>!q||r3TitleFor(b).toLocaleLowerCase('vi').includes(q)||String(b&&b.key||'').toLocaleLowerCase('vi').includes(q)).sort((a,b)=>r3TitleFor(a).localeCompare(r3TitleFor(b),'vi'));
    if(!rows.length){const empty=document.createElement('div');empty.className='r3-live-library-empty';empty.textContent=r3LiveLibraryBooks?'No books found.':'Loading…';root.appendChild(empty);return;}
    for(const row of rows){
      const article=document.createElement('article');article.className='r3-live-book';
      const same=String(row&&row.key||'')===key;
      const link=document.createElement(same?'button':'a');link.className='r3-live-book-link';
      if(same){link.type='button';link.addEventListener('click',r3CloseLiveLibrary);}else link.href='/artifact-library/read?key='+encodeURIComponent(String(row&&row.key||''));
      const name=document.createElement('span');name.className='r3-live-book-name';name.textContent=r3TitleFor(row);
      link.appendChild(name);
      if(same){const badge=document.createElement('span');badge.className='r3-live-book-current';badge.textContent='Đang đọc';link.appendChild(badge);}
      article.appendChild(link);root.appendChild(article);
    }
  }
  async function r3LoadLiveLibrary(){
    if(Array.isArray(r3LiveLibraryBooks)){r3RenderLiveLibrary();return;}
    r3LiveLibraryStatus('Loading…');r3RenderLiveLibrary();
    try{
      const response=await fetch('/artifact-library/api/list',{cache:'no-store'});
      const data=await response.json();
      if(!response.ok||data.ok!==true)throw new Error(data.error||('HTTP '+response.status));
      r3LiveLibraryBooks=Array.isArray(data.objects)?data.objects:[];
      r3LiveLibraryStatus('');r3RenderLiveLibrary();
    }catch(error){r3LiveLibraryStatus('Could not load Library: '+String(error&&error.message||error));}
  }
  function r3OpenLiveLibrary(){
    if(!r3LiveLibraryNode)return;
    try{document.getElementById('r3AudioElement')?.pause();}catch{}
    hideControls();document.body.classList.add('r3-live-library-open');r3LiveLibraryNode.hidden=false;
    window.__r3LiveReaderSessionV51={active:true,bookKey:key,openedAt:Date.now(),renditionAlive:!!rendition};
    r3LoadLiveLibrary();
  }
  function r3ArmLiveLibraryHistory(){
    if(r3LiveLibraryHistoryArmed)return;
    try{history.pushState(Object.assign({},history.state||{},{r3ReaderFrontV51:true}),'',location.href);r3LiveLibraryHistoryArmed=true;}catch{}
  }
  function r3CloseLiveLibrary(){
    if(!r3LiveLibraryNode)return;
    r3LiveLibraryNode.hidden=true;document.body.classList.remove('r3-live-library-open');
    if(window.__r3LiveReaderSessionV51)window.__r3LiveReaderSessionV51.active=false;
    r3ArmLiveLibraryHistory();
  }
  $('r3LiveLibraryButton')?.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();r3OpenLiveLibrary();});
  $('r3LiveLibraryBack')?.addEventListener('click',r3CloseLiveLibrary);
  $('r3LiveLibraryClose')?.addEventListener('click',r3CloseLiveLibrary);
  $('r3LiveLibrarySearch')?.addEventListener('input',e=>{r3LiveLibraryQuery=e.target.value||'';r3RenderLiveLibrary();});
  try{history.replaceState(Object.assign({},history.state||{},{r3ReaderBaseV51:true}),'',location.href);r3ArmLiveLibraryHistory();}catch{}
  window.addEventListener('popstate',()=>{
    if(r3LiveLibraryHistoryArmed){r3LiveLibraryHistoryArmed=false;r3OpenLiveLibrary();return;}
    if(!r3LiveLibraryVisible())r3OpenLiveLibrary();
  });
'''
if 'window.__r3LiveReaderSessionV51=' not in text:
    text = replace_once(
        text,
        '  bindGestureTarget(document,()=>window.innerWidth);',
        live_js + '\n  bindGestureTarget(document,()=>window.innerWidth);',
        'inject live library runtime',
    )

for marker in [
    'id="r3LiveLibraryButton"',
    'id="r3LiveLibrary" class="r3-live-library"',
    'window.__r3LiveReaderSessionV51=',
    "r3LiveLibraryHistoryArmed=false",
    "document.getElementById('r3AudioElement')?.pause()",
    "same?'button':'a'",
]:
    if marker not in text:
        raise SystemExit('READER_V51_MISSING:'+marker)
if '<a class="back" href="/artifact-library">‹ Library</a>' in text:
    raise SystemExit('READER_V51_HARD_LIBRARY_NAV_REMAINS')

V2.write_text(text, encoding='utf-8')
print('READER_V51_LIVE_SESSION_LIBRARY=PASS')
