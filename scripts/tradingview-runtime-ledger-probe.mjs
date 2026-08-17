import fs from 'node:fs';
import crypto from 'node:crypto';
import { chromium } from 'playwright-core';

const source=fs.readFileSync('/tmp/wr2513-base.pine','utf8');
const state=JSON.parse(fs.readFileSync('/tmp/tv-state.json','utf8'));
const want=crypto.createHash('sha256').update(source,'utf8').digest('hex');
const exes=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium-browser','/usr/bin/chromium'];
const executablePath=exes.find(fs.existsSync);
if(!executablePath) throw new Error('Chrome missing');

const browser=await chromium.launch({executablePath,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({storageState:state,viewport:{width:1920,height:1080},permissions:['clipboard-read','clipboard-write']});

function payloadText(payload){
  try{return typeof payload==='string'?payload:Buffer.from(payload).toString('utf8')}catch{return ''}
}
function interestingMeta(text,sym){
  if(!text.includes(sym)) return false;
  return /(minmov|pricescale|pointvalue|mincontract|currency_code|session|description)/i.test(text);
}
function parseTradeText(t){
  const text=t.trim().replace(/\s+/g,' ');
  const m=text.match(/^(\d+)(long|short)\b/i);
  if(!m)return null;
  return {n:Number(m[1]),side:m[2].toLowerCase(),text};
}
async function closePine(p,dlg){
  if(!await dlg.isVisible().catch(()=>false))return;
  const c=dlg.locator('button[aria-label*="Close" i],button[title*="Close" i],[data-name*="close" i]').first();
  if(await c.count())await c.click({force:true}).catch(()=>{});
  await p.waitForTimeout(500);
  if(await dlg.isVisible().catch(()=>false))await p.keyboard.press('Escape').catch(()=>{});
  await p.waitForTimeout(900);
}

async function runSymbol(sym){
  const p=await ctx.newPage();p.setDefaultTimeout(25000);
  const metaFrames=[];
  p.on('websocket',ws=>ws.on('framereceived',evt=>{
    const t=payloadText(evt.payload);
    if(interestingMeta(t,sym) && metaFrames.length<250) metaFrames.push(t.slice(0,120000));
  }));
  const log=(k,v)=>console.log(`${sym}_${k}=${v}`);
  await p.goto(`https://www.tradingview.com/chart/?symbol=BINANCE%3A${sym}.P&interval=5`,{waitUntil:'domcontentloaded',timeout:90000});
  await p.waitForTimeout(9000);
  const body0=await p.locator('body').innerText().catch(()=>'');
  if(/\bSign in\b/i.test(body0))throw new Error(`${sym} auth missing`);
  log('AUTH','PASS');

  const pine=p.locator('[data-name="pine-dialog-button"]').first();
  await pine.click();
  const dlg=p.locator('[data-name="pine-dialog"]').first();
  await dlg.waitFor({state:'visible'});
  const ta=dlg.locator('.monaco-editor textarea.inputarea, .monaco-editor textarea').first();
  await ta.waitFor({state:'attached'});
  for(let i=0;i<30;i++){if(await ta.isEditable().catch(()=>false))break;await p.waitForTimeout(300)}
  await ta.evaluate(e=>e.focus());await p.keyboard.press('Control+A');
  await p.evaluate(async s=>navigator.clipboard.writeText(s),source);
  await p.keyboard.press('Control+V');await p.waitForTimeout(3000);
  await p.evaluate(async()=>navigator.clipboard.writeText('sentinel'));
  await ta.evaluate(e=>e.focus());await p.keyboard.press('Control+A');await p.keyboard.press('Control+C');await p.waitForTimeout(700);
  const rt=await p.evaluate(async()=>navigator.clipboard.readText());
  const got=crypto.createHash('sha256').update(rt,'utf8').digest('hex');
  if(got!==want)throw new Error(`${sym} source hash mismatch`);
  log('EDITOR_HASH','PASS');

  const net=[];p.on('response',r=>{/pine-facade/i.test(r.url())&&net.push({status:r.status(),url:r.url()})});
  const add=dlg.getByRole('button',{name:'Add to chart',exact:true}).first();
  await add.click();
  let ok=false;
  for(let i=0;i<90;i++){
    await p.waitForTimeout(700);
    const upd=await dlg.locator('[title="Update on chart"]').count()>0;
    const translated=net.some(x=>x.status===200&&/pine-facade\/translate\/USER%3B/i.test(x.url));
    if(upd&&translated){ok=true;break}
  }
  if(!ok)throw new Error(`${sym} compile/add failed`);
  log('COMPILE','PASS');
  await closePine(p,dlg);

  const tester=p.getByText('Strategy Tester',{exact:true}).first();
  if(await tester.count())await tester.click({force:true}).catch(()=>{});
  await p.waitForTimeout(3500);
  const list=p.getByText(/List of trades/i).first();
  if(await list.count())await list.click({force:true}).catch(()=>{});
  await p.waitForTimeout(2500);

  const scrollers=await p.locator('*').evaluateAll(els=>els.map((e,i)=>{const r=e.getBoundingClientRect();const t=(e.innerText||'').slice(0,4000);let score=0;if(/List of trades/i.test(t))score+=20;if(/\bEntry\b/i.test(t)&&/\bExit\b/i.test(t))score+=10;if(/\b(?:long|short)\b/i.test(t))score+=5;return {i,score,scrollHeight:e.scrollHeight,clientHeight:e.clientHeight,x:r.x,y:r.y,w:r.width,h:r.height};}).filter(x=>x.scrollHeight>x.clientHeight+20&&x.w>250&&x.h>70&&x.x<1100&&x.y>450).sort((a,b)=>b.score-a.score||(b.scrollHeight-b.clientHeight)-(a.scrollHeight-a.clientHeight)).slice(0,5));

  const rows={};
  for(const s of scrollers){
    const loc=p.locator('*').nth(s.i);
    const max=Math.max(0,s.scrollHeight-s.clientHeight);
    for(let f=0;f<=1.001;f+=0.04){
      const pos=Math.round(max*Math.min(f,1));
      await loc.evaluate((e,y)=>{e.scrollTop=y;e.dispatchEvent(new Event('scroll',{bubbles:true}))},pos).catch(()=>{});
      await p.waitForTimeout(140);
      const rr=await p.locator('tr.ka-row').evaluateAll(rs=>rs.map(tr=>({text:(tr.innerText||tr.textContent||'').trim().replace(/\s+/g,' '),cells:[...tr.querySelectorAll(':scope > td')].map(td=>(td.innerText||td.textContent||'').trim().replace(/\s+/g,' '))})));
      for(const r of rr){const q=parseTradeText(r.text);if(q)rows[q.n]={...q,cells:r.cells};}
    }
    if(Object.keys(rows).length>=10)break;
  }

  const arr=Object.values(rows).sort((a,b)=>a.n-b.n);
  fs.writeFileSync(`/tmp/tv-runtime-${sym}.json`,JSON.stringify({symbol:sym,rows:arr,metaFrames},null,2));
  log('ROWS',arr.length);log('META_FRAMES',metaFrames.length);
  await p.screenshot({path:`/tmp/tv-runtime-${sym}.png`,fullPage:true}).catch(()=>{});
  await p.close();
}

try{for(const s of ['BNBUSDT','TRXUSDT'])await runSymbol(s)}finally{await browser.close()}
