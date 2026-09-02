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

# Advertise v64 so any already-open v63 live Reader reloads once and restores its CFI.
simple = replace_once(simple, "reader_client_version:'v63'", "reader_client_version:'v64'", 'v64 server client version')
simple = replace_once(simple, "'x-r3-reader-client-version':'v63'", "'x-r3-reader-client-version':'v64'", 'v64 server version header')
v2 = replace_once(v2, "const R3_READER_CLIENT_VERSION_V63='v63';", "const R3_READER_CLIENT_VERSION_V63='v64';", 'v64 reader client version')

# epub.js can report start.percentage=0 before Locations are ready. That zero was
# historically persisted as real progress. Use the live rendition structure as a
# non-blocking fallback: spine index plus displayed page/total for the current spine.
old_percent = r'''  function r3PercentFromCfiV55(cfi,loc){
    if(r3LocationsReadyV55&&cfi&&book&&book.locations){
      try{const p=book.locations.percentageFromCfi(cfi);if(Number.isFinite(p))return Math.max(0,Math.min(100,Math.round(p*100)));}catch{}
    }
    if(Number.isFinite(loc?.start?.percentage))return Math.max(0,Math.min(100,Math.round(loc.start.percentage*100)));
    return null;
  }'''
new_percent = r'''  function r3StructuralPercentV64(loc){
    try{
      const start=loc&&loc.start||{};
      const spine=(book&&book.spine)||null;
      const items=(spine&&Array.isArray(spine.spineItems)&&spine.spineItems)||(spine&&Array.isArray(spine.items)&&spine.items)||[];
      const totalSpines=Number(items.length||0);
      const index=Number(start.index);
      if(!(totalSpines>0)||!Number.isFinite(index)||index<0)return null;
      const displayed=start.displayed||{};
      const page=Number(displayed.page),total=Number(displayed.total);
      let within=0;
      if(Number.isFinite(page)&&Number.isFinite(total)&&page>0&&total>0)within=Math.max(0,Math.min(1,page/total));
      const raw=(Math.max(0,Math.min(totalSpines-1,index))+within)/totalSpines;
      return Math.max(0,Math.min(100,Math.round(raw*100)));
    }catch{return null}
  }
  function r3PercentFromCfiV55(cfi,loc){
    const structural=r3StructuralPercentV64(loc);
    if(r3LocationsReadyV55&&cfi&&book&&book.locations){
      try{
        const p=book.locations.percentageFromCfi(cfi);
        if(Number.isFinite(p)){
          const precise=Math.max(0,Math.min(100,Math.round(p*100)));
          if(precise===0&&Number.isFinite(structural)&&structural>0)return structural;
          return precise;
        }
      }catch{}
    }
    const native=Number(loc&&loc.start&&loc.start.percentage);
    if(Number.isFinite(native)&&native>0)return Math.max(0,Math.min(100,Math.round(native*100)));
    if(Number.isFinite(structural))return structural;
    if(Number.isFinite(native))return Math.max(0,Math.min(100,Math.round(native*100)));
    return null;
  }'''
v2 = replace_once(v2, old_percent, new_percent, 'v64 structural progress fallback')

# Repair any stale 0% record for the currently mounted book immediately when the
# Library panel opens, then refine it once generated Locations become available.
open_tail = r'''    window.__r3LiveReaderSessionV51={active:true,bookKey:key,openedAt:Date.now(),renditionAlive:!!rendition,clientVersion:R3_READER_CLIENT_VERSION_V63};
    r3LoadLiveLibrary();
  }'''
open_replacement = r'''    window.__r3LiveReaderSessionV51={active:true,bookKey:key,openedAt:Date.now(),renditionAlive:!!rendition,clientVersion:R3_READER_CLIENT_VERSION_V63};
    r3LoadLiveLibrary();
    const repairCurrentProgressV64=()=>{try{const current=(rendition&&rendition.currentLocation&&rendition.currentLocation())||null;const cfi=(current&&current.start&&current.start.cfi)||localStorage.getItem(keys.position)||'';const pct=r3PercentFromCfiV55(cfi,current);if(pct!==null)r3WriteProgressV55(pct,cfi);if(r3LiveLibraryVisible())r3RenderLiveLibrary()}catch(error){try{console.warn('R3_PROGRESS_REPAIR_V64',error)}catch{}}};
    repairCurrentProgressV64();
    Promise.resolve(r3EnsureLocationsV55()).then(()=>repairCurrentProgressV64()).catch(()=>{});
  }'''
v2 = replace_once(v2, open_tail, open_replacement, 'v64 live library progress repair')

for marker in ["reader_client_version:'v64'", "'x-r3-reader-client-version':'v64'"]:
    if marker not in simple: raise SystemExit('V64_SIMPLE_MISSING:'+marker)
for marker in ["R3_READER_CLIENT_VERSION_V63='v64'", 'function r3StructuralPercentV64', 'repairCurrentProgressV64', 'R3_PROGRESS_REPAIR_V64']:
    if marker not in v2: raise SystemExit('V64_READER_MISSING:'+marker)

SIMPLE.write_text(simple, encoding='utf-8')
V2.write_text(v2, encoding='utf-8')
print('READER_V64_PROGRESS_REPAIR=PASS')
