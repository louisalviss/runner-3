from pathlib import Path

ROOT = Path('cloudflare/runner3-core')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return text.replace(old, new, 1)


# v2: the base EPUB renderer becomes the authoritative boot completion owner.
v2_path = ROOT / 'artifact-library-reader-v2-entry.js'
v2 = v2_path.read_text(encoding='utf-8')
old_v2 = """      const saved=localStorage.getItem(keys.position)||'';
      try{await rendition.display(saved||undefined);}catch{localStorage.removeItem(keys.position);await rendition.display();}
      bindEpubContents();$('loading').classList.add('hidden');"""
new_v2 = """      const saved=localStorage.getItem(keys.position)||'';
      window.__R3_BASE_READER_BOOT_PENDING=true;
      window.__R3_BASE_READER_BOOT_DONE=false;
      window.__r3BaseReaderBootV47={phase:'display',target:saved||'',startedAt:Date.now(),after:'',error:''};
      try{
        await rendition.display(saved||undefined);
      }catch(error){
        window.__r3BaseReaderBootV47.error=String(error&&error.message||error||'display failed').slice(0,180);
        localStorage.removeItem(keys.position);
        await rendition.display();
      }
      // Do not reveal the reader merely because currentLocation() looked stable for a moment.
      // The authoritative signal is the resolved display() promise plus two paint frames.
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      try{
        const loc=rendition&&rendition.currentLocation&&rendition.currentLocation();
        window.__r3BaseReaderBootV47.after=String(loc&&loc.start&&loc.start.cfi||'');
      }catch{}
      window.__r3BaseReaderBootV47.phase='done';
      window.__r3BaseReaderBootV47.finishedAt=Date.now();
      window.__R3_BASE_READER_BOOT_PENDING=false;
      window.__R3_BASE_READER_BOOT_DONE=true;
      try{window.dispatchEvent(new CustomEvent('r3-base-reader-boot-done-v47',{detail:{target:saved||'',cfi:window.__r3BaseReaderBootV47.after||''}}));}catch{}
      bindEpubContents();$('loading').classList.add('hidden');"""
if 'window.__R3_BASE_READER_BOOT_DONE=true' not in v2:
    v2 = replace_once(v2, old_v2, new_v2, 'v2 boot completion')
v2_path.write_text(v2, encoding='utf-8')


# v5: initial settings application must not schedule a resize/display while base display(savedCFI) is in flight.
v5_path = ROOT / 'artifact-library-reader-v5-entry.js'
v5 = v5_path.read_text(encoding='utf-8')
old_v5 = """    r3ScheduleReflow(anchor);
  }`;"""
new_v5 = """    // During initial boot, rendition.display(savedCFI) owns pagination exclusively.
    // Reflow is only allowed after the base reader has declared BOOT_DONE.
    if(window.__R3_BASE_READER_BOOT_DONE&&anchor)r3ScheduleReflow(anchor);
  }`;"""
if 'if(window.__R3_BASE_READER_BOOT_DONE&&anchor)r3ScheduleReflow(anchor);' not in v5:
    v5 = replace_once(v5, old_v5, new_v5, 'v5 boot reflow guard')
v5_path.write_text(v5, encoding='utf-8')


# v27: hidden restore overlay must wait for the authoritative base display promise, not a short CFI plateau.
v27_path = ROOT / 'artifact-library-reader-v27-boot-cfi-restore-entry.js'
v27 = v27_path.read_text(encoding='utf-8')
old_wait = """  async function waitReaderStable(){
    let last='';
    let stable=0;
    for(let n=0;n<70;n++){
      const cfi=currentCfi();
      if(cfi){
        stable=cfi===last?stable+1:0;
        if(stable>=3)return cfi;
        last=cfi;
      }else stable=0;
      await delay(80);
    }
    return currentCfi();
  }
  async function waitLayoutStable(){"""
new_wait = """  async function waitBaseBootDone(){
    for(let n=0;n<140;n++){
      if(window.__R3_BASE_READER_BOOT_DONE===true)return true;
      await delay(80);
    }
    return window.__R3_BASE_READER_BOOT_DONE===true;
  }
  async function waitReaderStable(){
    let last='';
    let stable=0;
    for(let n=0;n<70;n++){
      const cfi=currentCfi();
      if(cfi){
        stable=cfi===last?stable+1:0;
        if(stable>=3)return cfi;
        last=cfi;
      }else stable=0;
      await delay(80);
    }
    return currentCfi();
  }
  async function waitLayoutStable(){"""
if 'async function waitBaseBootDone()' not in v27:
    v27 = replace_once(v27, old_wait, new_wait, 'v27 wait base boot')
old_flow = """    const initial=currentCfi();
    const stable=await waitReaderStable();
    if(!stable){
      window.__r3AudioBootCfiV27Debug={phase:'timeout',target:debug.target||'',initial,current:'',reason:'base-reader'};
      finish('base-reader-timeout');
      return;
    }
    debug.after=stable;
    await waitLayoutStable();"""
new_flow = """    const initial=currentCfi();
    debug.phase='wait-base-display-promise';
    const bootDone=await waitBaseBootDone();
    if(!bootDone){
      window.__r3AudioBootCfiV27Debug={phase:'timeout',target:debug.target||'',initial,current:currentCfi(),reason:'base-display-promise'};
      finish('base-display-timeout');
      return;
    }
    debug.phase='wait-final-cfi';
    const stable=await waitReaderStable();
    if(!stable){
      window.__r3AudioBootCfiV27Debug={phase:'timeout',target:debug.target||'',initial,current:'',reason:'base-reader'};
      finish('base-reader-timeout');
      return;
    }
    debug.after=stable;
    await waitLayoutStable();"""
if "debug.phase='wait-base-display-promise';" not in v27:
    v27 = replace_once(v27, old_flow, new_flow, 'v27 authoritative boot flow')
v27_path.write_text(v27, encoding='utf-8')


smoke = ROOT / 'reader-audio-core' / 'reader-v47-base-boot-smoke.mjs'
smoke.write_text("""import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve('cloudflare/runner3-core');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const v2=read('artifact-library-reader-v2-entry.js');
const v5=read('artifact-library-reader-v5-entry.js');
const v27=read('artifact-library-reader-v27-boot-cfi-restore-entry.js');
if(!v2.includes('window.__R3_BASE_READER_BOOT_DONE=true'))throw new Error('base boot completion marker missing');
if(!v2.includes("await rendition.display(saved||undefined)"))throw new Error('base saved CFI display missing');
if(!v2.includes("r3-base-reader-boot-done-v47"))throw new Error('base boot event missing');
if(!v5.includes('if(window.__R3_BASE_READER_BOOT_DONE&&anchor)r3ScheduleReflow(anchor);'))throw new Error('v5 boot reflow guard missing');
if(!v27.includes('async function waitBaseBootDone()'))throw new Error('v27 boot promise wait missing');
if(!v27.includes("debug.phase='wait-base-display-promise';"))throw new Error('v27 overlay still uses heuristic-only readiness');
const baseDisplayAt=v2.indexOf('await rendition.display(saved||undefined)');
const doneAt=v2.indexOf('window.__R3_BASE_READER_BOOT_DONE=true');
if(baseDisplayAt<0||doneAt<baseDisplayAt)throw new Error('BOOT_DONE occurs before display resolves');
console.log('READER_V47_BASE_BOOT_PROMISE=PASS');
""", encoding='utf-8')

print('READER_V47_PATCH=PASS')
