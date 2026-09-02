from pathlib import Path

root = Path('cloudflare/runner3-core')
v27 = root / 'artifact-library-reader-v27-boot-cfi-restore-entry.js'
v28 = root / 'artifact-library-reader-v28-prime-base-position-entry.js'
v34 = root / 'artifact-library-reader-v34-continuous-range-sync-entry.js'

s27 = v27.read_text(encoding='utf-8')
s28 = v28.read_text(encoding='utf-8')
s34 = v34.read_text(encoding='utf-8')


def replace_region(source: str, start: str, end: str, replacement: str, label: str) -> str:
    a = source.find(start)
    if a < 0:
        raise SystemExit(f'{label}: start marker missing')
    b = source.find(end, a + len(start))
    if b < 0:
        raise SystemExit(f'{label}: end marker missing')
    return source[:a] + replacement + source[b:]

prime = r'''const PRIME = `<script data-r3-audio-prime-base-position-v28="1" data-r3-direct-restore-v45="1">
(()=>{
  window.__r3AudioPrimeBasePositionV28=true;
  const params=new URLSearchParams(location.search);
  const bookKey=params.get('key')||'';
  if(!bookKey)return;
  const baseKey='r3-reader-position:'+bookKey;
  let target='';
  try{target=String(localStorage.getItem(baseKey)||'');}catch{}
  let source='reader-position';
  if(!target){
    let saved=null;
    try{saved=JSON.parse(localStorage.getItem('r3-reader-audio-state-v11:'+bookKey)||'null');}catch{}
    target=String(saved&&saved.cfi||'');
    source='audio-fallback';
    if(target)try{localStorage.setItem(baseKey,target);}catch{}
  }
  window.__r3AudioPrimeBasePositionV28Debug={phase:target?'restore-pending':'no-target',baseKey,target,source};
  if(!target)return;

  window.__R3_READER_RESTORE_PENDING=true;
  window.__r3ReaderRestoreTargetV45=target;
  document.documentElement.classList.add('r3-restore-pending-v45');
  const style=document.createElement('style');
  style.id='r3ReaderDirectRestoreV45Style';
  style.textContent=`
    html.r3-restore-pending-v45 #viewer{visibility:hidden!important;opacity:0!important}
    html.r3-restore-pending-v45 #r3AudioDock{opacity:0!important;pointer-events:none!important}
    html.r3-restore-pending-v45 body::before{content:'';position:fixed;z-index:2147483600;inset:0;background:var(--bg,#fff);pointer-events:auto}
    html.r3-restore-pending-v45 body::after{content:'Đang mở vị trí gần nhất…';position:fixed;z-index:2147483601;left:50%;top:48%;transform:translate(-50%,-50%);padding:11px 16px;border-radius:999px;background:color-mix(in srgb,var(--fg,#222) 8%,var(--bg,#fff));color:var(--fg,#333);font:600 13px/1.2 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;white-space:nowrap;box-shadow:0 8px 30px rgba(0,0,0,.08);pointer-events:none}
  `;
  (document.head||document.documentElement).appendChild(style);
  window.__r3ReaderDirectRestoreV45={phase:'primed',bookKey,target,source,startedAt:Date.now(),after:'',error:''};
})();
</script>`;'''

s28 = replace_region(
    s28,
    'const PRIME = `',
    '\n\nfunction patchPrimeBasePosition',
    prime,
    'v28 PRIME',
)

boot = r'''const BOOT_SCRIPT = `<script data-r3-audio-boot-cfi-v27="1" data-r3-direct-restore-v45="1">
(()=>{
  if(window.__r3AudioBootCfiRestoreV27)return;
  window.__r3AudioBootCfiRestoreV27=true;
  const params=new URLSearchParams(location.search);
  const bookKey=params.get('key')||'';
  if(!bookKey)return;
  const baseKey='r3-reader-position:'+bookKey;
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const debug=window.__r3ReaderDirectRestoreV45||{phase:'boot',bookKey,startedAt:Date.now(),target:'',after:'',error:''};
  window.__r3ReaderDirectRestoreV45=debug;

  function readCfi(key){
    try{const row=JSON.parse(localStorage.getItem(key)||'null');return String(row&&row.cfi||'');}catch{return '';}
  }
  function uniqueTargets(){
    const out=[];
    const push=value=>{value=String(value||'');if(value&&!out.includes(value))out.push(value);};
    push(window.__r3ReaderRestoreTargetV45);
    try{push(localStorage.getItem(baseKey)||'');}catch{}
    push(readCfi('r3-reader-audio-state-v11:'+bookKey));
    push(readCfi('r3-reader-audio-core-v1:'+bookKey));
    return out.slice(0,3);
  }
  function currentCfi(){
    try{
      const b=window.r3ReaderBridge;
      const loc=b&&typeof b.current==='function'?b.current():null;
      return String(loc&&loc.start&&loc.start.cfi||'');
    }catch{return '';}
  }
  async function waitBridge(){
    for(let n=0;n<45;n++){
      const b=window.r3ReaderBridge;
      if(b&&typeof b.display==='function')return b;
      await delay(70);
    }
    return window.r3ReaderBridge||null;
  }
  async function waitLayoutStable(){
    for(let n=0;n<34;n++){
      const state=window.__r3ReaderLayoutStabilizeV35;
      if(state&&state.phase==='stable')return true;
      await delay(80);
    }
    return false;
  }
  function finish(phase){
    debug.phase=phase;
    debug.after=currentCfi();
    debug.finishedAt=Date.now();
    window.__R3_READER_RESTORE_PENDING=false;
    document.documentElement.classList.remove('r3-restore-pending-v45');
    try{window.dispatchEvent(new CustomEvent('r3-reader-restore-ready-v45',{detail:{phase,cfi:debug.after,target:debug.target||''}}));}catch{}
  }

  (async()=>{
    const targets=uniqueTargets();
    if(!targets.length){finish('no-target');return;}
    const b=await waitBridge();
    if(!b||typeof b.display!=='function'){
      window.__r3AudioBootCfiV27Debug={phase:'timeout',target:targets[0]||'',current:currentCfi(),reason:'bridge'};
      finish('bridge-timeout');
      return;
    }

    const initial=currentCfi();
    let restored=false;
    let error='';
    for(const candidate of targets){
      debug.phase='direct-display';
      debug.target=candidate;
      try{
        // One direct CFI relocation per candidate. Never walk pages with next()/prev().
        await Promise.resolve(b.display(candidate));
        await delay(120);
        const after=currentCfi();
        if(after){
          restored=true;
          debug.after=after;
          try{if(typeof b.persist==='function')b.persist();}catch{}
          break;
        }
      }catch(err){error=String(err&&err.message||err||'display failed').slice(0,180);}
    }

    debug.error=error;
    if(restored){
      window.__r3AudioBootCfiV27Debug={phase:'restored',attempt:0,target:debug.target,initial,before:initial,after:debug.after,stable:debug.after,direct:true};
      await waitLayoutStable();
      await delay(80);
      finish('ready');
      return;
    }

    window.__r3AudioBootCfiV27Debug={phase:'timeout',target:targets[0]||'',initial,current:currentCfi(),reason:'display',error};
    await waitLayoutStable();
    finish('fallback-current-page');
  })().catch(error=>{
    debug.error=String(error&&error.message||error||'restore failed').slice(0,180);
    window.__r3AudioBootCfiV27Debug={phase:'timeout',target:debug.target||'',current:currentCfi(),reason:'exception',error:debug.error};
    finish('fallback-current-page');
  });
})();
</script>`;'''

s27 = replace_region(
    s27,
    'const BOOT_SCRIPT = `',
    '\n\nfunction patchBootCfiRestore',
    boot,
    'v27 BOOT_SCRIPT',
)

# Suspend sentence highlight/page-follow while the hidden restore transaction owns the viewport.
guard = "  async function syncWord(index,force=false){\n    if(window.__R3_READER_RESTORE_PENDING)return false;\n"
if 'if(window.__R3_READER_RESTORE_PENDING)return false;' not in s34:
    marker = '  async function syncWord(index,force=false){\n'
    if marker not in s34:
        raise SystemExit('v34 syncWord marker missing')
    s34 = s34.replace(marker, guard, 1)

# Acceptance gates.
checks = [
    ('v28', s28, 'data-r3-direct-restore-v45="1"'),
    ('v28', s28, 'window.__R3_READER_RESTORE_PENDING=true'),
    ('v28', s28, 'Đang mở vị trí gần nhất…'),
    ('v27', s27, 'Never walk pages with next()/prev().'),
    ('v27', s27, "window.__r3AudioBootCfiV27Debug={phase:'restored'"),
    ('v27', s27, "document.documentElement.classList.remove('r3-restore-pending-v45')"),
    ('v34', s34, 'if(window.__R3_READER_RESTORE_PENDING)return false;'),
]
for label, source, needle in checks:
    if needle not in source:
        raise SystemExit(f'{label}: missing v45 marker {needle}')
if 'for(let n=0;n<36;n++)' in s27:
    raise SystemExit('v27: legacy repeated restore loop still present')
if 'b.next()' in boot or 'b.prev()' in boot:
    raise SystemExit('v27: page stepping present in restore boot')

v27.write_text(s27, encoding='utf-8')
v28.write_text(s28, encoding='utf-8')
v34.write_text(s34, encoding='utf-8')
print('READER_V45_DIRECT_RESTORE_PATCH=PASS')
