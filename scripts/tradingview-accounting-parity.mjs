import fs from 'node:fs';
import crypto from 'node:crypto';
import { chromium } from 'playwright-core';

const source=fs.readFileSync('/tmp/wr2513-accounting-probe.pine','utf8');
const state=JSON.parse(fs.readFileSync('/tmp/tv-state.json','utf8'));
const want=crypto.createHash('sha256').update(source,'utf8').digest('hex');
const exes=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium-browser','/usr/bin/chromium'];
const executablePath=exes.find(fs.existsSync);
if(!executablePath) throw new Error('Chrome missing');
const browser=await chromium.launch({executablePath,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({storageState:state,viewport:{width:1920,height:1080},permissions:['clipboard-read','clipboard-write']});

async function extractParityLines(p){
  return await p.evaluate(()=>{
    const vals=[];
    const add=t=>{
      if(!t)return;
      for(const marker of ['WRMETA|','WRP#']){
        const i=t.indexOf(marker);
        if(i>=0){
          let s=t.slice(i).replace(/\r/g,'').trim();
          // UI rows can append unrelated controls on following lines; one parity record is one line.
          s=s.split('\n')[0].trim();
          if(s) vals.push(s);
        }
      }
    };
    for(const e of document.querySelectorAll('*')){
      const own=(e.innerText||e.textContent||'').trim();
      if(!own || (!own.includes('WRMETA|')&&!own.includes('WRP#'))) continue;
      const childHas=[...e.children].some(c=>{
        const x=(c.innerText||c.textContent||''); return x.includes('WRMETA|')||x.includes('WRP#');
      });
      if(!childHas) add(own);
    }
    return [...new Set(vals)];
  });
}

async function openPineLogs(p,dlg,log){
  // Prefer semantically-labelled More/overflow controls. If TradingView changes labels,
  // fall back to compact buttons in the editor's top-right toolbar.
  const meta=await dlg.locator('button,[role="button"]').evaluateAll(es=>es.map((e,i)=>{
    const r=e.getBoundingClientRect(), d=e.closest('[data-name="pine-dialog"]')?.getBoundingClientRect();
    return {i,text:(e.innerText||e.textContent||'').trim().replace(/\s+/g,' ').slice(0,80),aria:e.getAttribute('aria-label')||'',title:e.getAttribute('title')||'',data:e.getAttribute('data-name')||'',x:r.x,y:r.y,w:r.width,h:r.height,right:d?d.right:innerWidth,top:d?d.top:0};
  }));
  fs.writeFileSync('/tmp/pine-editor-buttons.json',JSON.stringify(meta,null,2));
  const ranked=meta.map(x=>{
    const s=[x.text,x.aria,x.title,x.data].join(' ').toLowerCase();
    let score=0;
    if(/more|menu|overflow|options/.test(s))score+=100;
    if(x.w<=55&&x.h<=55&&x.x>x.right-220&&x.y<x.top+120)score+=20;
    if(/publish|save|update|add to chart/.test(s))score-=80;
    return {...x,score};
  }).sort((a,b)=>b.score-a.score);

  const buttons=dlg.locator('button,[role="button"]');
  for(const cand of ranked.slice(0,10)){
    if(cand.score<=0)continue;
    await buttons.nth(cand.i).click({force:true}).catch(()=>{});
    await p.waitForTimeout(700);
    const item=p.getByText(/Pine logs/i).first();
    if(await item.count()>0 && await item.isVisible().catch(()=>false)){
      log('PINE_LOG_MENU','FOUND');
      await item.click({force:true});
      await p.waitForTimeout(2500);
      return true;
    }
    await p.keyboard.press('Escape').catch(()=>{});
  }
  log('PINE_LOG_MENU','NOT_FOUND');
  return false;
}

async function closeEditor(p,dlg){
  if(!await dlg.isVisible().catch(()=>false))return;
  const close=dlg.locator('button[aria-label*="Close" i],button[title*="Close" i],[data-name*="close" i]').first();
  if(await close.count()>0) await close.click({force:true}).catch(()=>{});
  await p.waitForTimeout(800);
  if(await dlg.isVisible().catch(()=>false)) await p.keyboard.press('Escape').catch(()=>{});
  await p.waitForTimeout(800);
}

async function runSymbol(sym){
  const p=await ctx.newPage(); p.setDefaultTimeout(25000);
  const out=[]; const log=(k,v)=>{const s=`${sym}_${k}=${v}`; console.log(s); out.push(s)};
  try{
    await p.goto(`https://www.tradingview.com/chart/?symbol=BINANCE%3A${sym}.P&interval=5`,{waitUntil:'domcontentloaded',timeout:90000});
    await p.waitForTimeout(10000);
    let body=await p.locator('body').innerText().catch(()=>'');
    log('AUTH',/\bSign in\b/i.test(body)?'FAIL':'PASS');
    if(/\bSign in\b/i.test(body)) throw new Error('TradingView auth missing');

    const pine=p.locator('[data-name="pine-dialog-button"]').first();
    await pine.click();
    const dlg=p.locator('[data-name="pine-dialog"]').first();
    await dlg.waitFor({state:'visible'}); await p.waitForTimeout(2500);
    const ta=dlg.locator('.monaco-editor textarea.inputarea, .monaco-editor textarea').first();
    await ta.waitFor({state:'attached'});
    for(let i=0;i<30;i++){if(await ta.isEditable().catch(()=>false))break;await p.waitForTimeout(400)}
    await ta.evaluate(e=>e.focus()); await p.keyboard.press('Control+A');
    await p.evaluate(async s=>navigator.clipboard.writeText(s),source);
    await p.keyboard.press('Control+V'); await p.waitForTimeout(4000);

    await p.evaluate(async()=>navigator.clipboard.writeText('sentinel'));
    await ta.evaluate(e=>e.focus()); await p.keyboard.press('Control+A'); await p.keyboard.press('Control+C'); await p.waitForTimeout(900);
    const rt=await p.evaluate(async()=>navigator.clipboard.readText());
    const got=crypto.createHash('sha256').update(rt,'utf8').digest('hex');
    log('EDITOR_HASH',got===want?'PASS':'FAIL');
    if(got!==want) throw new Error('editor hash mismatch');

    const net=[]; p.on('response',r=>{/pine-facade/i.test(r.url())&&net.push({status:r.status(),url:r.url()})});
    const add=dlg.getByRole('button',{name:'Add to chart',exact:true}).first();
    await add.click();
    let ok=false;
    for(let i=0;i<90;i++){
      await p.waitForTimeout(800);
      const upd=await dlg.locator('[title="Update on chart"]').count()>0;
      const translated=net.some(x=>x.status===200&&/pine-facade\/translate\/USER%3B/i.test(x.url));
      if(upd&&translated){ok=true;break}
    }
    const dt=await dlg.innerText().catch(()=>'');
    if(!ok||/compilation error|cannot compile|error on bar|failed to add/i.test(dt)) throw new Error('compile/add failed');
    log('COMPILE','PASS');
    await p.waitForTimeout(3500);

    let lines=[];
    const logsOpened=await openPineLogs(p,dlg,log);
    if(logsOpened){
      for(let n=0;n<20;n++){
        await p.waitForTimeout(700);
        lines=await extractParityLines(p);
        if(lines.some(x=>x.startsWith('WRMETA|'))&&lines.filter(x=>x.startsWith('WRP#')).length>=10)break;
      }
    }

    // Fallback: close Pine Editor and inspect page text/table if Pine Logs menu changed.
    if(!lines.some(x=>x.startsWith('WRMETA|'))||lines.filter(x=>x.startsWith('WRP#')).length<10){
      await closeEditor(p,dlg);
      for(let n=0;n<8;n++){
        await p.waitForTimeout(600);
        const x=await extractParityLines(p);
        if(x.length>lines.length)lines=x;
      }
    }

    // De-duplicate log entries by exact message. WRP order is chronological by native trade number.
    lines=[...new Set(lines)];
    const meta=lines.filter(x=>x.startsWith('WRMETA|'));
    const recs=lines.filter(x=>x.startsWith('WRP#')).sort((a,b)=>Number(a.match(/^WRP#(\d+)/)?.[1]||0)-Number(b.match(/^WRP#(\d+)/)?.[1]||0));
    const canonical=[...(meta.slice(-1)),...recs];
    fs.writeFileSync(`/tmp/tv-accounting-${sym}.txt`,canonical.join('\n')+(canonical.length?'\n':''));
    body=await p.locator('body').innerText().catch(()=>'');
    fs.writeFileSync(`/tmp/tv-accounting-body-${sym}.txt`,body);
    await p.screenshot({path:`/tmp/tv-accounting-${sym}.png`,fullPage:true}).catch(()=>{});
    log('META_LINES',meta.length); log('RECORD_CELLS',recs.length);
    if(meta.length<1||recs.length<10) throw new Error('Pine accounting messages not captured');
  } catch(e){
    log('ERROR',String(e?.message||e).slice(0,240));
    fs.writeFileSync(`/tmp/tv-accounting-${sym}-run.txt`,out.join('\n')+'\n');
    await p.screenshot({path:`/tmp/tv-accounting-${sym}.png`,fullPage:true}).catch(()=>{});
    await p.close().catch(()=>{});
    throw e;
  }
  fs.writeFileSync(`/tmp/tv-accounting-${sym}-run.txt`,out.join('\n')+'\n');
  await p.close();
}

try{
  for(const sym of ['BNBUSDT','TRXUSDT']) await runSymbol(sym);
} finally {
  await browser.close();
}
