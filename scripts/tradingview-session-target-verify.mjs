import fs from 'node:fs';
import crypto from 'node:crypto';
import { chromium } from 'playwright-core';

const src=fs.readFileSync('/tmp/wr2513-session-target.pine','utf8');
const state=JSON.parse(fs.readFileSync('/tmp/tv-state.json','utf8'));
const want=crypto.createHash('sha256').update(src,'utf8').digest('hex');
const exes=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium-browser','/usr/bin/chromium'];
const executablePath=exes.find(fs.existsSync);
if(!executablePath) throw new Error('Chrome missing');
const browser=await chromium.launch({executablePath,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({storageState:state,viewport:{width:1920,height:1080},permissions:['clipboard-read','clipboard-write']});
const p=await ctx.newPage();p.setDefaultTimeout(25000);
const out=[];const log=(k,v)=>{const s=`${k}=${v}`;console.log(s);out.push(s)};

async function visibleInputs(scope){
  return await scope.locator('input:visible').evaluateAll(es=>es.map((e,i)=>({i,type:e.type||'',placeholder:e.placeholder||'',aria:e.getAttribute('aria-label')||'',value:e.value||'',name:e.name||''})));
}

async function goToTarget(){
  await p.keyboard.press('Alt+G'); await p.waitForTimeout(1500);
  const dialogs=p.locator('[role="dialog"]:visible');
  const n=await dialogs.count(); const scope=n?dialogs.nth(n-1):p.locator('body');
  const txt=(await scope.innerText().catch(()=>'' )).slice(0,2500); log('GOTO_DIALOGS',n); log('GOTO_TEXT',txt.replace(/\s+/g,' ').slice(0,800));
  let ins=await visibleInputs(scope); fs.writeFileSync('/tmp/goto-inputs.json',JSON.stringify(ins,null,2));
  let dateDone=false,timeDone=false;
  const li=scope.locator('input:visible');
  for(let i=0;i<await li.count();i++){
    const el=li.nth(i); const m=ins[i]||{}; const hint=`${m.type} ${m.placeholder} ${m.aria} ${m.name}`.toLowerCase();
    if(!dateDone && (/date|yyyy|dd|mm/.test(hint)||m.type==='date')){
      for(const v of ['2025-01-17','01/17/2025','17/01/2025']){try{await el.fill(v);dateDone=true;break}catch{}}
    } else if(!timeDone && /time|hh|hour/.test(hint)){
      for(const v of ['22:00','10:00 PM']){try{await el.fill(v);timeDone=true;break}catch{}}
    }
  }
  // Fallback: if exactly one textbox-like input exists, TradingView accepts a combined date string in some builds.
  if(!dateDone && await li.count()===1){for(const v of ['2025-01-17','Jan 17, 2025']){try{await li.first().fill(v);dateDone=true;break}catch{}}}
  log('GOTO_DATE_FILLED',dateDone?'YES':'NO'); log('GOTO_TIME_FILLED',timeDone?'YES':'NO');
  const buttons=scope.getByRole('button');
  const bmeta=await buttons.evaluateAll(bs=>bs.map((b,i)=>({i,text:(b.innerText||b.textContent||'').trim(),aria:b.getAttribute('aria-label')||'',title:b.title||''})).slice(0,100));
  fs.writeFileSync('/tmp/goto-buttons.json',JSON.stringify(bmeta,null,2));
  let clicked=false;
  for(const name of [/^Go to$/i,/^Apply$/i,/^OK$/i,/^Go$/i]){
    const b=scope.getByRole('button',{name}).first(); if(await b.count()&&await b.isVisible().catch(()=>false)){await b.click({force:true});clicked=true;break}
  }
  if(!clicked && dateDone){await p.keyboard.press('Enter').catch(()=>{});clicked=true}
  log('GOTO_SUBMIT',clicked?'YES':'NO');
  await p.waitForTimeout(12000);
  const body=await p.locator('body').innerText().catch(()=>'');
  fs.writeFileSync('/tmp/after-goto-body.txt',body);
  await p.screenshot({path:'/tmp/after-goto.png',fullPage:true}).catch(()=>{});
  return dateDone&&clicked;
}

try{
  await p.goto('https://www.tradingview.com/chart/?symbol=BINANCE%3ABNBUSDT.P&interval=5',{waitUntil:'domcontentloaded',timeout:90000});
  await p.waitForTimeout(9000);
  let body=await p.locator('body').innerText().catch(()=>''); if(/\bSign in\b/i.test(body))throw new Error('auth missing'); log('AUTH','PASS');
  const go=await goToTarget(); if(!go)throw new Error('go-to-date input not resolved');

  const pine=p.locator('[data-name="pine-dialog-button"]').first();await pine.click();
  const dlg=p.locator('[data-name="pine-dialog"]').first();await dlg.waitFor({state:'visible'});await p.waitForTimeout(2000);
  const ta=dlg.locator('.monaco-editor textarea.inputarea,.monaco-editor textarea').first();await ta.waitFor({state:'attached'});
  for(let i=0;i<30&&!await ta.isEditable().catch(()=>false);i++)await p.waitForTimeout(300);
  await ta.evaluate(e=>e.focus());await p.keyboard.press('Control+A');await p.evaluate(async s=>navigator.clipboard.writeText(s),src);await p.keyboard.press('Control+V');await p.waitForTimeout(3500);
  await p.evaluate(async()=>navigator.clipboard.writeText('sentinel'));await ta.evaluate(e=>e.focus());await p.keyboard.press('Control+A');await p.keyboard.press('Control+C');await p.waitForTimeout(700);
  const rt=await p.evaluate(async()=>navigator.clipboard.readText());const got=crypto.createHash('sha256').update(rt,'utf8').digest('hex');if(got!==want)throw new Error('editor hash mismatch');log('EDITOR_HASH','PASS');
  const net=[];p.on('response',r=>{/pine-facade/i.test(r.url())&&net.push({status:r.status(),url:r.url()})});
  const add=dlg.getByRole('button',{name:'Add to chart',exact:true}).first();await add.click();let ok=false;
  for(let i=0;i<90;i++){await p.waitForTimeout(700);const upd=await dlg.locator('[title="Update on chart"]').count()>0;const tr=net.some(x=>x.status===200&&/pine-facade\/translate\/USER%3B/i.test(x.url));if(upd&&tr){ok=true;break}}
  if(!ok)throw new Error('compile/add failed');log('COMPILE','PASS');
  if(await dlg.isVisible().catch(()=>false)){await pine.click({force:true}).catch(()=>{});await p.waitForTimeout(1500)}

  let trades=p.locator('[title="Trades"]').first();for(let i=0;i<20&&await trades.count()===0;i++){await p.waitForTimeout(500);trades=p.locator('[title="Trades"]').first()}
  if(!await trades.count())throw new Error('Trades button missing');await trades.click({force:true});await p.waitForTimeout(6000);
  // Scroll virtualized table and collect row texts.
  const rows={};const sc=p.locator('.ka-table-wrapper').first();if(!await sc.count())throw new Error('trade table scroller missing');
  const dims=await sc.evaluate(e=>({max:Math.max(0,e.scrollHeight-e.clientHeight)}));
  const poses=[];for(let f=0;f<=1.0001;f+=0.05)poses.push(Math.round(dims.max*Math.min(f,1)));poses.push(dims.max);
  for(const pos of [...new Set(poses)]){
    await sc.evaluate((e,y)=>{e.scrollTop=y;e.dispatchEvent(new Event('scroll',{bubbles:true}))},pos);await p.waitForTimeout(180);
    const rr=await p.locator('tr.ka-row').evaluateAll(rs=>rs.map(tr=>({text:(tr.innerText||tr.textContent||'').trim().replace(/\s+/g,' '),html:tr.outerHTML.slice(0,18000)})));
    for(const r of rr){const m=r.text.match(/^(\d+)(long|short)\b/i);if(m)rows[m[1]]=r}
  }
  const arr=Object.entries(rows).sort((a,b)=>Number(a[0])-Number(b[0])).map(([n,r])=>({n:Number(n),...r}));
  fs.writeFileSync('/tmp/session-target-rows.json',JSON.stringify(arr,null,2));
  const hits=arr.filter(r=>/Jan\s+17,\s+2025|2025[-\/]01[-\/]17/i.test(r.text)||/22:40|23:35/.test(r.text));
  fs.writeFileSync('/tmp/session-target-hits.json',JSON.stringify(hits,null,2));
  log('ROWS',arr.length);log('TARGET_HITS',hits.length);
  for(const h of hits.slice(0,8))console.log('TARGET_ROW='+h.text.slice(0,700));
  await p.screenshot({path:'/tmp/session-target-trades.png',fullPage:true}).catch(()=>{});
  if(!hits.length)throw new Error('target historical trade not found');
}catch(e){log('ERROR',String(e?.message||e));process.exitCode=8}
finally{fs.writeFileSync('/tmp/session-target-run.txt',out.join('\n')+'\n');await browser.close()}
