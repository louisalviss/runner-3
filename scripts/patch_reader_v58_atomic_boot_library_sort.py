from pathlib import Path
import re

ROOT = Path('cloudflare/runner3-core')
V2 = ROOT / 'artifact-library-reader-v2-entry.js'
V5 = ROOT / 'artifact-library-reader-v5-entry.js'
SIMPLE = ROOT / 'artifact-library-simple-entry.js'
v2 = V2.read_text(encoding='utf-8')
v5 = V5.read_text(encoding='utf-8')
simple = SIMPLE.read_text(encoding='utf-8')


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return source.replace(old, new, 1)

# ---------------------------------------------------------------------------
# Reader boot: intermediate epub.js rendered events must never reveal the page.
# The base Reader waits for the final CFI to remain stable before BOOT_DONE,
# then reveals once. Also persist a true open timestamp for Library sorting.
# ---------------------------------------------------------------------------
old_rendered = "rendition.on('rendered',()=>{bindEpubContents();$('loading').classList.add('hidden');});"
new_rendered = "rendition.on('rendered',()=>{bindEpubContents();});"
if old_rendered in v2:
    v2 = replace_once(v2, old_rendered, new_rendered, 'v58 suppress intermediate rendered reveal')
elif new_rendered not in v2:
    raise SystemExit('v58 rendered handler marker missing')

boot_pattern = re.compile(
    r"      const saved=localStorage\.getItem\(keys\.position\)\|\|'';\n"
    r"      window\.__R3_BASE_READER_BOOT_PENDING=true;.*?"
    r"      bindEpubContents\(\);\$\('loading'\)\.classList\.add\('hidden'\);",
    re.S,
)
boot_replacement = r'''      const saved=localStorage.getItem(keys.position)||'';
      try{localStorage.setItem('r3-reader-last-open:'+key,String(Date.now()));}catch{}
      window.__R3_BASE_READER_BOOT_PENDING=true;
      window.__R3_BASE_READER_BOOT_DONE=false;
      window.__R3_READER_BOOT_QUIET_UNTIL_V58=Number.MAX_SAFE_INTEGER;
      window.__r3BaseReaderBootV47={phase:'display',target:saved||'',startedAt:Date.now(),after:'',error:'',owner:'atomic-v58'};
      try{
        await rendition.display(saved||undefined);
      }catch(error){
        window.__r3BaseReaderBootV47.error=String(error&&error.message||error||'display failed').slice(0,180);
        try{localStorage.removeItem(keys.position);}catch{}
        await rendition.display();
      }
      async function r3WaitStableBootCfiV58(){
        let last='',stable=0;
        for(let n=0;n<18;n++){
          await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
          let cfi='';
          try{const loc=rendition&&rendition.currentLocation&&rendition.currentLocation();cfi=String(loc&&loc.start&&loc.start.cfi||'');}catch{}
          if(cfi&&cfi===last)stable++;else stable=0;
          last=cfi||last;
          if(last&&stable>=3)return last;
          await new Promise(resolve=>setTimeout(resolve,70));
        }
        return last;
      }
      const stableCfiV58=await r3WaitStableBootCfiV58();
      try{window.__r3BaseReaderBootV47.after=stableCfiV58||String(rendition?.currentLocation?.()?.start?.cfi||'');}catch{window.__r3BaseReaderBootV47.after=stableCfiV58||'';}
      window.__r3BaseReaderBootV47.phase='done';
      window.__r3BaseReaderBootV47.finishedAt=Date.now();
      window.__R3_READER_BOOT_QUIET_UNTIL_V58=Date.now()+1200;
      window.__R3_BASE_READER_BOOT_PENDING=false;
      window.__R3_BASE_READER_BOOT_DONE=true;
      try{window.dispatchEvent(new CustomEvent('r3-base-reader-boot-done-v47',{detail:{target:saved||'',cfi:window.__r3BaseReaderBootV47.after||'',owner:'atomic-v58'}}));}catch{}
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      bindEpubContents();$('loading').classList.add('hidden');'''
v2, count = boot_pattern.subn(boot_replacement, v2, count=1)
if count != 1 and "owner:'atomic-v58'" not in v2:
    raise SystemExit(f'v58 base boot replacement expected 1 match, got {count}')

# v5 reflow must not re-display an anchor while iOS viewport/chrome is still
# settling immediately after base boot.
old_reflow_gate = "if(window.__R3_BASE_READER_BOOT_DONE&&anchor)r3ScheduleReflow(anchor);"
new_reflow_gate = "if(window.__R3_BASE_READER_BOOT_DONE&&Date.now()>=Number(window.__R3_READER_BOOT_QUIET_UNTIL_V58||0)&&anchor)r3ScheduleReflow(anchor);"
if old_reflow_gate in v5:
    v5 = replace_once(v5, old_reflow_gate, new_reflow_gate, 'v58 v5 quiescence gate')
elif new_reflow_gate not in v5:
    raise SystemExit('v58 v5 reflow gate missing')
old_timer_guard = "if(seq!==r3ReflowSeq||!rendition)return;"
new_timer_guard = "if(seq!==r3ReflowSeq||!rendition||Date.now()<Number(window.__R3_READER_BOOT_QUIET_UNTIL_V58||0))return;"
if old_timer_guard in v5:
    v5 = replace_once(v5, old_timer_guard, new_timer_guard, 'v58 v5 timer quiet guard')
elif new_timer_guard not in v5:
    raise SystemExit('v58 v5 timer guard missing')

# ---------------------------------------------------------------------------
# Main Library sort controls: Recent open / New added / A-Z.
# Reading-state filters stay independent.
# ---------------------------------------------------------------------------
sort_css = ".sort-row{display:flex;gap:7px;margin:-3px 0 12px;overflow-x:auto;scrollbar-width:none}.sort-row::-webkit-scrollbar{display:none}.sort-chip{appearance:none;border:1px solid #27313b;background:#0e1319;color:#9da9b6;border-radius:999px;height:34px;padding:0 12px;font:inherit;font-size:11px;font-weight:800;white-space:nowrap}.sort-chip.active{background:#dce4ec;color:#0b0f13;border-color:#dce4ec}"
if '.sort-row{' not in simple:
    simple = replace_once(simple, '\n</style>\n</head>', sort_css + '\n</style>\n</head>', 'v58 main sort css')

sort_html = '<div class="sort-row" aria-label="Sắp xếp"><button class="sort-chip active" data-sort="recent" type="button">Recent open</button><button class="sort-chip" data-sort="new" type="button">New added</button><button class="sort-chip" data-sort="az" type="button">A → Z</button></div>\n'
status_anchor = '<div id="status" class="status" aria-live="polite"></div><section id="list" class="list"></section></main>'
if 'data-sort="recent"' not in simple:
    simple = replace_once(simple, status_anchor, sort_html + status_anchor, 'v58 main sort html')

old_state = "const state={books:[],query:'',filter:'all',meta:new Map(),coverUrls:[]};"
new_state = "const state={books:[],query:'',filter:'all',sort:'recent',meta:new Map(),coverUrls:[]};"
if old_state in simple:
    simple = replace_once(simple, old_state, new_state, 'v58 main sort state')
elif new_state not in simple:
    raise SystemExit('v58 main state marker missing')

filtered_start = simple.find('  function filtered(){')
filtered_end = simple.find('  function clearCoverUrls(){', filtered_start)
if filtered_start < 0 or filtered_end < 0:
    raise SystemExit('v58 main filtered boundaries missing')
new_filtered = r'''  function lastOpenAtV58(b){let opened=0;try{opened=Number(localStorage.getItem('r3-reader-last-open:'+b.key)||0)}catch{}const p=progressFor(b);return Math.max(opened,Number(p.updatedAt||0))}
  function uploadedAtV58(b){return Date.parse(String(b&&b.uploaded||''))||0}
  function filtered(){const q=state.query.trim().toLocaleLowerCase('vi');let items=state.books.filter(b=>!q||titleFor(b).toLocaleLowerCase('vi').includes(q)||authorFor(b).toLocaleLowerCase('vi').includes(q)||String(b.key||'').toLocaleLowerCase('vi').includes(q));items=items.filter(b=>{const p=progressFor(b);if(state.filter==='reading')return p.started&&!p.done;if(state.filter==='unread')return !p.started;if(state.filter==='done')return p.done;return true});if(state.sort==='new')return items.sort((a,b)=>uploadedAtV58(b)-uploadedAtV58(a)||titleFor(a).localeCompare(titleFor(b),'vi'));if(state.sort==='az')return items.sort((a,b)=>titleFor(a).localeCompare(titleFor(b),'vi'));return items.sort((a,b)=>lastOpenAtV58(b)-lastOpenAtV58(a)||titleFor(a).localeCompare(titleFor(b),'vi'))}
'''
simple = simple[:filtered_start] + new_filtered + simple[filtered_end:]

listener_anchor = "document.querySelectorAll('.filter').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.filter').forEach(x=>x.classList.remove('active'));btn.classList.add('active');state.filter=btn.dataset.filter||'all';render()}));load();"
listener_replacement = "document.querySelectorAll('.filter').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.filter').forEach(x=>x.classList.remove('active'));btn.classList.add('active');state.filter=btn.dataset.filter||'all';render()}));document.querySelectorAll('.sort-chip').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.sort-chip').forEach(x=>x.classList.remove('active'));btn.classList.add('active');state.sort=btn.dataset.sort||'recent';render()}));load();"
if listener_anchor in simple:
    simple = replace_once(simple, listener_anchor, listener_replacement, 'v58 main sort listeners')
elif "document.querySelectorAll('.sort-chip')" not in simple:
    raise SystemExit('v58 main listeners marker missing')

# ---------------------------------------------------------------------------
# In-Reader persistent Library panel gets the same sort choices.
# ---------------------------------------------------------------------------
live_sort_css = ".r3-live-sort-row{display:flex;gap:7px;margin:0 0 10px;overflow-x:auto;scrollbar-width:none}.r3-live-sort-row::-webkit-scrollbar{display:none}.r3-live-sort-chip{appearance:none;border:1px solid #27313b;background:#0e1319;color:#9da9b6;border-radius:999px;height:32px;padding:0 11px;font:inherit;font-size:10px;font-weight:800;white-space:nowrap}.r3-live-sort-chip.active{background:#dce4ec;color:#0b0f13;border-color:#dce4ec}"
if '.r3-live-sort-row{' not in v2:
    v2 = replace_once(v2, '\n</style>\n</head>', live_sort_css + '\n</style>\n</head>', 'v58 live sort css')

live_search = '    <input id="r3LiveLibrarySearch" class="r3-live-library-search" type="search" placeholder="Search books" autocomplete="off" aria-label="Search books">\n'
live_sort_html = live_search + '    <div class="r3-live-sort-row" aria-label="Sắp xếp"><button class="r3-live-sort-chip active" data-r3-sort="recent" type="button">Recent open</button><button class="r3-live-sort-chip" data-r3-sort="new" type="button">New added</button><button class="r3-live-sort-chip" data-r3-sort="az" type="button">A → Z</button></div>\n'
if 'data-r3-sort="recent"' not in v2:
    v2 = replace_once(v2, live_search, live_sort_html, 'v58 live sort html')

old_live_state = "  let r3LiveLibraryQuery='';\n  let r3LiveLibraryHistoryArmed=false;"
new_live_state = "  let r3LiveLibraryQuery='';\n  let r3LiveLibrarySortV58='recent';\n  let r3LiveLibraryHistoryArmed=false;"
if old_live_state in v2:
    v2 = replace_once(v2, old_live_state, new_live_state, 'v58 live sort state')
elif "r3LiveLibrarySortV58='recent'" not in v2:
    raise SystemExit('v58 live sort state marker missing')

live_render_start = v2.find('  function r3RenderLiveLibrary(){')
live_render_end = v2.find('  async function r3LoadLiveLibrary(){', live_render_start)
if live_render_start < 0 or live_render_end < 0:
    raise SystemExit('v58 live render boundaries missing')
live_block = v2[live_render_start:live_render_end]
if 'r3SortLiveRowsV58' not in live_block:
    insert_after = "    const q=String(r3LiveLibraryQuery||'').trim().toLocaleLowerCase('vi');\n"
    helpers = "    const r3LastOpenAtV58=row=>{let opened=0;try{opened=Number(localStorage.getItem('r3-reader-last-open:'+row.key)||0)}catch{}const p=r3ProgressForBookV54(row);return Math.max(opened,Number(p.updatedAt||0));};\n    const r3UploadedAtV58=row=>Date.parse(String(row&&row.uploaded||''))||0;\n    const r3SortLiveRowsV58=rows=>{if(r3LiveLibrarySortV58==='new')return rows.sort((a,b)=>r3UploadedAtV58(b)-r3UploadedAtV58(a)||r3TitleFor(a).localeCompare(r3TitleFor(b),'vi'));if(r3LiveLibrarySortV58==='az')return rows.sort((a,b)=>r3TitleFor(a).localeCompare(r3TitleFor(b),'vi'));return rows.sort((a,b)=>r3LastOpenAtV58(b)-r3LastOpenAtV58(a)||r3TitleFor(a).localeCompare(r3TitleFor(b),'vi'));};\n"
    if insert_after not in live_block:
        raise SystemExit('v58 live q marker missing')
    live_block = live_block.replace(insert_after, insert_after + helpers, 1)
    # Preserve existing filtering/ranking first, then make requested sort authoritative.
    marker = "    if(!rows.length)"
    if marker not in live_block:
        raise SystemExit('v58 live rows marker missing')
    live_block = live_block.replace(marker, "    r3SortLiveRowsV58(rows);\n" + marker, 1)
    v2 = v2[:live_render_start] + live_block + v2[live_render_end:]

live_listener_anchor = "  $('r3LiveLibrarySearch')?.addEventListener('input',e=>{r3LiveLibraryQuery=e.target.value||'';r3RenderLiveLibrary();});"
live_listener_replacement = live_listener_anchor + "\n  document.querySelectorAll('.r3-live-sort-chip').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.r3-live-sort-chip').forEach(x=>x.classList.remove('active'));btn.classList.add('active');r3LiveLibrarySortV58=btn.dataset.r3Sort||'recent';r3RenderLiveLibrary();}));"
if "document.querySelectorAll('.r3-live-sort-chip')" not in v2:
    v2 = replace_once(v2, live_listener_anchor, live_listener_replacement, 'v58 live sort listeners')

for marker in [
    "owner:'atomic-v58'",
    '__R3_READER_BOOT_QUIET_UNTIL_V58',
    "'r3-reader-last-open:'+key",
    'r3WaitStableBootCfiV58',
    'data-sort="recent"',
    "sort:'recent'",
    'lastOpenAtV58',
]:
    target = v2 + simple
    if marker not in target:
        raise SystemExit('V58_MISSING:' + marker)
if old_rendered in v2:
    raise SystemExit('V58_EARLY_RENDER_REVEAL_REMAINS')
if old_reflow_gate in v5:
    raise SystemExit('V58_OLD_REFLOW_GATE_REMAINS')

V2.write_text(v2, encoding='utf-8')
V5.write_text(v5, encoding='utf-8')
SIMPLE.write_text(simple, encoding='utf-8')
print('READER_V58_ATOMIC_BOOT_LIBRARY_SORT=PASS')
