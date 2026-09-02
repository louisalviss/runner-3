from pathlib import Path

ROOT = Path('cloudflare/runner3-core')
SIMPLE = ROOT / 'artifact-library-simple-entry.js'
V2 = ROOT / 'artifact-library-reader-v2-entry.js'

simple = SIMPLE.read_text(encoding='utf-8')
v2 = V2.read_text(encoding='utf-8')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Main Library: collapse reading-state filters + sort chips into one funnel menu.
# Persist both choices in localStorage so the view survives reload/reopen.
# ---------------------------------------------------------------------------
main_css = r'''.view-menu-wrap{position:relative;flex:0 0 auto}.view-menu-button{appearance:none;border:1px solid #29313a;background:#12171d;color:#e8edf3;border-radius:11px;width:36px;height:36px;display:grid;place-items:center;padding:0;cursor:pointer}.view-menu-button svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.view-menu-button.active{background:#e9eef4;color:#0a0d10;border-color:#e9eef4}.view-menu{position:absolute;z-index:2147482000;left:0;top:42px;width:min(280px,calc(100vw - 24px));padding:8px;background:#12171d;border:1px solid #303a45;border-radius:14px;box-shadow:0 14px 38px rgba(0,0,0,.45)}.view-menu[hidden]{display:none!important}.view-menu-title{padding:7px 9px 5px;color:#7f8c99;font-size:10px;font-weight:850;letter-spacing:.07em;text-transform:uppercase}.view-choice{width:100%;appearance:none;border:0;background:transparent;color:#e7edf3;border-radius:9px;min-height:39px;padding:0 9px;display:flex;align-items:center;justify-content:space-between;gap:12px;text-align:left;font:inherit;font-size:13px;font-weight:720}.view-choice.selected{background:#202832;color:#fff}.view-choice-check{opacity:0;font-weight:900}.view-choice.selected .view-choice-check{opacity:1}.view-menu-divider{height:1px;background:#29323c;margin:6px 4px}.action-row{overflow:visible}'''
if '.view-menu-wrap{' not in simple:
    simple = replace_once(simple, '\n</style>\n</head>', main_css + '\n</style>\n</head>', 'v59 main compact menu css')

old_action = '<div class="action-row"><button class="filter active" data-filter="all" type="button">Tất cả</button><button class="filter" data-filter="reading" type="button">Đang đọc</button><button class="filter" data-filter="unread" type="button">Chưa đọc</button><button class="filter" data-filter="done" type="button">Đã đọc</button><button id="uploadEpub" class="upload-epub" type="button">＋ EPUB</button><input id="uploadEpubInput" type="file" accept=".epub,application/epub+zip" hidden></div>'
new_action = r'''<div class="action-row"><div class="view-menu-wrap"><button id="viewMenuButton" class="view-menu-button" type="button" aria-label="Bộ lọc và sắp xếp" aria-expanded="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16"></path><path d="M7 12h10"></path><path d="M10 18h4"></path></svg></button><div id="viewMenu" class="view-menu" hidden><div class="view-menu-title">Trạng thái</div><button class="view-choice" data-filter-choice="all" type="button">Tất cả<span class="view-choice-check">✓</span></button><button class="view-choice" data-filter-choice="reading" type="button">Đang đọc<span class="view-choice-check">✓</span></button><button class="view-choice" data-filter-choice="unread" type="button">Chưa đọc<span class="view-choice-check">✓</span></button><button class="view-choice" data-filter-choice="done" type="button">Đã đọc<span class="view-choice-check">✓</span></button><div class="view-menu-divider"></div><div class="view-menu-title">Sắp xếp</div><button class="view-choice" data-sort-choice="recent" type="button">Recent open<span class="view-choice-check">✓</span></button><button class="view-choice" data-sort-choice="new" type="button">New added<span class="view-choice-check">✓</span></button><button class="view-choice" data-sort-choice="az" type="button">A → Z<span class="view-choice-check">✓</span></button></div></div><button id="uploadEpub" class="upload-epub" type="button">＋ EPUB</button><input id="uploadEpubInput" type="file" accept=".epub,application/epub+zip" hidden></div>'''
if 'id="viewMenuButton"' not in simple:
    simple = replace_once(simple, old_action, new_action, 'v59 main action row')

sort_row = '<div class="sort-row" aria-label="Sắp xếp"><button class="sort-chip active" data-sort="recent" type="button">Recent open</button><button class="sort-chip" data-sort="new" type="button">New added</button><button class="sort-chip" data-sort="az" type="button">A → Z</button></div>\n'
if sort_row in simple:
    simple = replace_once(simple, sort_row, '', 'v59 remove main visible sort row')

state_anchor = "  const state={books:[],query:'',filter:'all',sort:'recent',meta:new Map(),coverUrls:[]};\n  const $=id=>document.getElementById(id);"
state_replacement = r'''  const state={books:[],query:'',filter:'all',sort:'recent',meta:new Map(),coverUrls:[]};
  const VIEW_PREF_KEY_V59='r3-library-view-pref-v59';
  function readViewPrefV59(){try{const p=JSON.parse(localStorage.getItem(VIEW_PREF_KEY_V59)||'null')||{};return {filter:['all','reading','unread','done'].includes(p.filter)?p.filter:'all',sort:['recent','new','az'].includes(p.sort)?p.sort:'recent'}}catch{return {filter:'all',sort:'recent'}}}
  function saveViewPrefV59(){try{localStorage.setItem(VIEW_PREF_KEY_V59,JSON.stringify({filter:state.filter,sort:state.sort}))}catch{}}
  function syncViewMenuV59(){document.querySelectorAll('[data-filter-choice]').forEach(x=>x.classList.toggle('selected',x.dataset.filterChoice===state.filter));document.querySelectorAll('[data-sort-choice]').forEach(x=>x.classList.toggle('selected',x.dataset.sortChoice===state.sort));const b=document.getElementById('viewMenuButton');if(b)b.classList.toggle('active',state.filter!=='all'||state.sort!=='recent')}
  const $=id=>document.getElementById(id);'''
if 'VIEW_PREF_KEY_V59' not in simple:
    simple = replace_once(simple, state_anchor, state_replacement, 'v59 main preference runtime')

old_listeners = "document.querySelectorAll('.filter').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.filter').forEach(x=>x.classList.remove('active'));btn.classList.add('active');state.filter=btn.dataset.filter||'all';render()}));document.querySelectorAll('.sort-chip').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.sort-chip').forEach(x=>x.classList.remove('active'));btn.classList.add('active');state.sort=btn.dataset.sort||'recent';render()}));load();"
new_listeners = r'''const savedViewPrefV59=readViewPrefV59();state.filter=savedViewPrefV59.filter;state.sort=savedViewPrefV59.sort;syncViewMenuV59();const viewMenuV59=$('viewMenu'),viewMenuButtonV59=$('viewMenuButton');function closeViewMenuV59(){if(viewMenuV59)viewMenuV59.hidden=true;if(viewMenuButtonV59)viewMenuButtonV59.setAttribute('aria-expanded','false')}viewMenuButtonV59?.addEventListener('click',e=>{e.stopPropagation();const willOpen=!!viewMenuV59?.hidden;if(viewMenuV59)viewMenuV59.hidden=!willOpen;viewMenuButtonV59.setAttribute('aria-expanded',willOpen?'true':'false')});viewMenuV59?.addEventListener('click',e=>e.stopPropagation());document.addEventListener('click',closeViewMenuV59);document.querySelectorAll('[data-filter-choice]').forEach(btn=>btn.addEventListener('click',()=>{state.filter=btn.dataset.filterChoice||'all';saveViewPrefV59();syncViewMenuV59();render();closeViewMenuV59()}));document.querySelectorAll('[data-sort-choice]').forEach(btn=>btn.addEventListener('click',()=>{state.sort=btn.dataset.sortChoice||'recent';saveViewPrefV59();syncViewMenuV59();render();closeViewMenuV59()}));load();'''
if "savedViewPrefV59=readViewPrefV59()" not in simple:
    simple = replace_once(simple, old_listeners, new_listeners, 'v59 main compact menu listeners')

# ---------------------------------------------------------------------------
# In-Reader Library panel: same funnel menu and same persisted preference key.
# It now supports reading-state filtering too, not only sort.
# ---------------------------------------------------------------------------
live_css = r'''.r3-live-library-tools{display:flex!important;justify-content:flex-end;gap:8px;position:relative}.r3-live-view-button{appearance:none;border:1px solid #29313a;background:#12171d;color:#e8edf3;border-radius:12px;width:44px;height:44px;display:grid;place-items:center;padding:0}.r3-live-view-button svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.r3-live-view-button.active{background:#e9eef4;color:#0a0d10;border-color:#e9eef4}.r3-live-view-menu{position:absolute;z-index:2147483000;right:0;top:50px;width:min(280px,calc(100vw - 24px));padding:8px;background:#12171d;border:1px solid #303a45;border-radius:14px;box-shadow:0 14px 38px rgba(0,0,0,.5)}.r3-live-view-menu[hidden]{display:none!important}.r3-live-view-title{padding:7px 9px 5px;color:#7f8c99;font-size:10px;font-weight:850;letter-spacing:.07em;text-transform:uppercase}.r3-live-view-choice{width:100%;appearance:none;border:0;background:transparent;color:#e7edf3;border-radius:9px;min-height:39px;padding:0 9px;display:flex;align-items:center;justify-content:space-between;gap:12px;text-align:left;font:inherit;font-size:13px;font-weight:720}.r3-live-view-choice.selected{background:#202832;color:#fff}.r3-live-view-check{opacity:0;font-weight:900}.r3-live-view-choice.selected .r3-live-view-check{opacity:1}.r3-live-view-divider{height:1px;background:#29323c;margin:6px 4px}'''
if '.r3-live-view-button{' not in v2:
    v2 = replace_once(v2, '\n</style>\n</head>', live_css + '\n</style>\n</head>', 'v59 live compact menu css')

live_sort_row = '    <div class="r3-live-sort-row" aria-label="Sắp xếp"><button class="r3-live-sort-chip active" data-r3-sort="recent" type="button">Recent open</button><button class="r3-live-sort-chip" data-r3-sort="new" type="button">New added</button><button class="r3-live-sort-chip" data-r3-sort="az" type="button">A → Z</button></div>\n'
if live_sort_row in v2:
    v2 = replace_once(v2, live_sort_row, '', 'v59 remove live visible sort row')

old_live_tools = '<div class="r3-live-library-tools"><button id="r3LiveLibraryUpload" class="r3-live-library-upload" type="button">＋ EPUB</button><input id="r3LiveLibraryUploadInput" type="file" accept=".epub,application/epub+zip" hidden></div>'
new_live_tools = r'''<div class="r3-live-library-tools"><button id="r3LiveViewButton" class="r3-live-view-button" type="button" aria-label="Bộ lọc và sắp xếp" aria-expanded="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16"></path><path d="M7 12h10"></path><path d="M10 18h4"></path></svg></button><div id="r3LiveViewMenu" class="r3-live-view-menu" hidden><div class="r3-live-view-title">Trạng thái</div><button class="r3-live-view-choice" data-r3-filter-choice="all" type="button">Tất cả<span class="r3-live-view-check">✓</span></button><button class="r3-live-view-choice" data-r3-filter-choice="reading" type="button">Đang đọc<span class="r3-live-view-check">✓</span></button><button class="r3-live-view-choice" data-r3-filter-choice="unread" type="button">Chưa đọc<span class="r3-live-view-check">✓</span></button><button class="r3-live-view-choice" data-r3-filter-choice="done" type="button">Đã đọc<span class="r3-live-view-check">✓</span></button><div class="r3-live-view-divider"></div><div class="r3-live-view-title">Sắp xếp</div><button class="r3-live-view-choice" data-r3-sort-choice="recent" type="button">Recent open<span class="r3-live-view-check">✓</span></button><button class="r3-live-view-choice" data-r3-sort-choice="new" type="button">New added<span class="r3-live-view-check">✓</span></button><button class="r3-live-view-choice" data-r3-sort-choice="az" type="button">A → Z<span class="r3-live-view-check">✓</span></button></div><button id="r3LiveLibraryUpload" class="r3-live-library-upload" type="button">＋ EPUB</button><input id="r3LiveLibraryUploadInput" type="file" accept=".epub,application/epub+zip" hidden></div>'''
if 'id="r3LiveViewButton"' not in v2:
    v2 = replace_once(v2, old_live_tools, new_live_tools, 'v59 live compact menu html')

old_live_state = "  let r3LiveLibrarySortV58='recent';\n  let r3LiveLibraryHistoryArmed=false;"
new_live_state = r'''  let r3LiveLibrarySortV58='recent';
  let r3LiveLibraryFilterV59='all';
  const r3LiveViewPrefKeyV59='r3-library-view-pref-v59';
  function r3ReadLiveViewPrefV59(){try{const p=JSON.parse(localStorage.getItem(r3LiveViewPrefKeyV59)||'null')||{};return {filter:['all','reading','unread','done'].includes(p.filter)?p.filter:'all',sort:['recent','new','az'].includes(p.sort)?p.sort:'recent'}}catch{return {filter:'all',sort:'recent'}}}
  function r3SaveLiveViewPrefV59(){try{localStorage.setItem(r3LiveViewPrefKeyV59,JSON.stringify({filter:r3LiveLibraryFilterV59,sort:r3LiveLibrarySortV58}))}catch{}}
  function r3SyncLiveViewMenuV59(){document.querySelectorAll('[data-r3-filter-choice]').forEach(x=>x.classList.toggle('selected',x.dataset.r3FilterChoice===r3LiveLibraryFilterV59));document.querySelectorAll('[data-r3-sort-choice]').forEach(x=>x.classList.toggle('selected',x.dataset.r3SortChoice===r3LiveLibrarySortV58));const b=$('r3LiveViewButton');if(b)b.classList.toggle('active',r3LiveLibraryFilterV59!=='all'||r3LiveLibrarySortV58!=='recent')}
  let r3LiveLibraryHistoryArmed=false;'''
if 'r3LiveViewPrefKeyV59' not in v2:
    v2 = replace_once(v2, old_live_state, new_live_state, 'v59 live preference state')

# Change rows to mutable and apply the shared reading-state filter before sort.
live_render_start = v2.find('  function r3RenderLiveLibrary(){')
live_render_end = v2.find('  async function r3LoadLiveLibrary(){', live_render_start)
if live_render_start < 0 or live_render_end < 0:
    raise SystemExit('v59 live render boundaries missing')
live_block = v2[live_render_start:live_render_end]
if 'r3LiveLibraryFilterV59' not in live_block:
    live_block = live_block.replace('    const rows=', '    let rows=', 1)
    marker = '    r3SortLiveRowsV58(rows);\n'
    filter_code = "    rows=rows.filter(row=>{const p=r3ProgressForBookV54(row);if(r3LiveLibraryFilterV59==='reading')return p.started&&!p.done;if(r3LiveLibraryFilterV59==='unread')return !p.started;if(r3LiveLibraryFilterV59==='done')return p.done;return true;});\n"
    if marker not in live_block:
        raise SystemExit('v59 live sort marker missing')
    live_block = live_block.replace(marker, filter_code + marker, 1)
    v2 = v2[:live_render_start] + live_block + v2[live_render_end:]

old_live_listener = "  document.querySelectorAll('.r3-live-sort-chip').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.r3-live-sort-chip').forEach(x=>x.classList.remove('active'));btn.classList.add('active');r3LiveLibrarySortV58=btn.dataset.r3Sort||'recent';r3RenderLiveLibrary();}));"
new_live_listener = r'''  const r3SavedViewPrefV59=r3ReadLiveViewPrefV59();r3LiveLibraryFilterV59=r3SavedViewPrefV59.filter;r3LiveLibrarySortV58=r3SavedViewPrefV59.sort;r3SyncLiveViewMenuV59();
  const r3LiveViewMenuV59=$('r3LiveViewMenu'),r3LiveViewButtonV59=$('r3LiveViewButton');
  function r3CloseLiveViewMenuV59(){if(r3LiveViewMenuV59)r3LiveViewMenuV59.hidden=true;if(r3LiveViewButtonV59)r3LiveViewButtonV59.setAttribute('aria-expanded','false')}
  r3LiveViewButtonV59?.addEventListener('click',e=>{e.stopPropagation();const willOpen=!!r3LiveViewMenuV59?.hidden;if(r3LiveViewMenuV59)r3LiveViewMenuV59.hidden=!willOpen;r3LiveViewButtonV59.setAttribute('aria-expanded',willOpen?'true':'false')});
  r3LiveViewMenuV59?.addEventListener('click',e=>e.stopPropagation());document.addEventListener('click',r3CloseLiveViewMenuV59);
  document.querySelectorAll('[data-r3-filter-choice]').forEach(btn=>btn.addEventListener('click',()=>{r3LiveLibraryFilterV59=btn.dataset.r3FilterChoice||'all';r3SaveLiveViewPrefV59();r3SyncLiveViewMenuV59();r3RenderLiveLibrary();r3CloseLiveViewMenuV59()}));
  document.querySelectorAll('[data-r3-sort-choice]').forEach(btn=>btn.addEventListener('click',()=>{r3LiveLibrarySortV58=btn.dataset.r3SortChoice||'recent';r3SaveLiveViewPrefV59();r3SyncLiveViewMenuV59();r3RenderLiveLibrary();r3CloseLiveViewMenuV59()}));'''
if 'r3SavedViewPrefV59=r3ReadLiveViewPrefV59()' not in v2:
    v2 = replace_once(v2, old_live_listener, new_live_listener, 'v59 live compact menu listeners')

for marker in [
    'id="viewMenuButton"',
    'VIEW_PREF_KEY_V59',
    'data-filter-choice="reading"',
    'data-sort-choice="recent"',
    'id="r3LiveViewButton"',
    'r3LiveViewPrefKeyV59',
    'data-r3-filter-choice="reading"',
    'data-r3-sort-choice="recent"',
]:
    if marker not in simple + v2:
        raise SystemExit('V59_MISSING:' + marker)

if 'class="sort-row"' in simple:
    raise SystemExit('V59_MAIN_VISIBLE_SORT_ROW_REMAINS')
if 'class="r3-live-sort-row"' in v2:
    raise SystemExit('V59_LIVE_VISIBLE_SORT_ROW_REMAINS')

SIMPLE.write_text(simple, encoding='utf-8')
V2.write_text(v2, encoding='utf-8')
print('READER_V59_COMPACT_LIBRARY_FILTER=PASS')
