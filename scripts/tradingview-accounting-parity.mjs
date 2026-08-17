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

function markersFromString(s){
  const out=[];
  if(typeof s!=='string')return out;
  const re=/(WRMETA\|[^"\r\n]+|WRP#\d+\|[^"\r\n]+)/g;
  for(const m of s.matchAll(re))out.push(m[1].replace(/\\u2192/g,'→').trim());
  return out;
}

function walkStrings(v,out){
  if(typeof v==='string'){
    for(const x of markersFromString(v))out.push(x);
  } else if(Array.isArray(v)){
    for(const x of v)walkStrings(x,out);
  } else if(v&&typeof v==='object'){
    for(const x of Object.values(v))walkStrings(x,out);
  }
}

function markersFromWsPayload(payload){
  let text='';
  try{text=typeof payload==='string'?payload:Buffer.from(payload).toString('utf8')}catch{return []}
  if(!text.includes('WRP#')&&!text.includes('WRMETA|'))return [];
  const found=[];
  const chunks=text.split(/~m~\d+~m~/).filter(Boolean);
  for(const chunk of chunks){
    try{
      const obj=JSON.parse(chunk);
      walkStrings(obj,found);
    }catch{
      for(const x of markersFromString(chunk))found.push(x);
    }
  }
  return found;
}

async function extractParityLinesFromDom(p){
  return await p.evaluate(()=>{
    const vals=[];
    const re=/(WRMETA\|[^"\r\n]+|WRP#\d+\|[^"\r\n]+)/g;
    for(const e of document.querySelectorAll('*')){
      const t=(e.innerText||e.textContent||'').trim();
      if(!t||(!t.includes('WRMETA|')&&!t.includes('WRP#')))continue;
      const childHas=[...e.children].some(c=>{const x=(c.innerText||c.textContent||'');return x.includes('WRMETA|')||x.includes('WRP#')});
      if(childHas)continue;
      for(const m of t.matchAll(re))vals.push(m[1].trim());
    }
    return [...new Set(vals)];
  });
}

async function closeEditor(p,dlg){
  if(!await dlg.isVisible().catch(()=>false))return;
  const close=dlg.locator('button[aria-label*="Close" i],button[title*="Close" i],[data-name*="close" i]').first();
  if(await close.count()>0)await close.click({force:true}).catch(()=>{});
  await p.waitForTimeout(500);
  if(await dlg.isVisible().catch(()=>false))await p.keyboard.press('Escape').catch(()=>{});
  await p.waitForTimeout(700);
}

async function runSymbol(sym){
  const p=await ctx.newPage(); p.setDefaultTimeout(25000);
  const out=[]; const log=(k,v)=>{const s=`${sym}_${k}=${v}`;console.log(s);out.push(s)};
  const wsMarkers=[];
  p.on('websocket',ws=>{
    ws.on('framereceived',evt=>{
      try{for(const x of markersFromWsPayload(evt.payload))wsMarkers.push(x)}catch{}
    });
  });

  try{
    await p.goto(`https://www.tradingview.com/chart/?symbol=BINANCE%3A${sym}.P&interval=5`,{waitUntil:'domcontentloaded',timeout:90000});
    await p.waitForTimeout(9000);
    let body=await p.locator('body').innerText().catch(()=>'');
    log('AUTH',/\bSign in\b/i.test(body)?'FAIL':'PASS');
    if(/\bSign in\b/i.test(body))throw new Error('TradingView auth missing');

    const pine=p.locator('[data-name="pine-dialog-button"]').first();
    await pine.click();
    const dlg=p.locator('[data-name="pine-dialog"]').first();
    await dlg.waitFor({state:'visible'});await p.waitForTimeout(2000);
    const ta=dlg.locator('.monaco-editor textarea.inputarea, .monaco-editor textarea').first();
    await ta.waitFor({state:'attached'});
    for(let i=0;i<30;i++){if(await ta.isEditable().catch(()=>false))break;await p.waitForTimeout(350)}
    await ta.evaluate(e=>e.focus());await p.keyboard.press('Control+A');
    await p.evaluate(async s=>navigator.clipboard.writeText(s),source);
    await p.keyboard.press('Control+V');await p.waitForTimeout(3500);

    await p.evaluate(async()=>navigator.clipboard.writeText('sentinel'));
    await ta.evaluate(e=>e.focus());await p.keyboard.press('Control+A');await p.keyboard.press('Control+C');await p.waitForTimeout(700);
    const rt=await p.evaluate(async()=>navigator.clipboard.readText());
    const got=crypto.createHash('sha256').update(rt,'utf8').digest('hex');
    log('EDITOR_HASH',got===want?'PASS':'FAIL');
    if(got!==want)throw new Error('editor hash mismatch');

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
    const dt=await dlg.innerText().catch(()=>'');
    if(!ok||/compilation error|cannot compile|error on bar|failed to add/i.test(dt))throw new Error('compile/add failed');
    log('COMPILE','PASS');

    for(let n=0;n<35;n++){
      await p.waitForTimeout(700);
      const u=[...new Set(wsMarkers)];
      if(u.some(x=>x.startsWith('WRMETA|'))&&u.filter(x=>x.startsWith('WRP#')).length>=10)break;
    }
    log('WS_MARKERS',new Set(wsMarkers).size);

    let lines=[...new Set(wsMarkers)];
    if(!lines.some(x=>x.startsWith('WRMETA|'))||lines.filter(x=>x.startsWith('WRP#')).length<10){
      await closeEditor(p,dlg);
      const dom=await extractParityLinesFromDom(p);
      lines=[...new Set([...lines,...dom])];
    }

    const meta=lines.filter(x=>x.startsWith('WRMETA|'));
    const recs=lines.filter(x=>x.startsWith('WRP#')).sort((a,b)=>Number(a.match(/^WRP#(\d+)/)?.[1]||0)-Number(b.match(/^WRP#(\d+)/)?.[1]||0));
    const canonical=[...(meta.slice(-1)),...recs];
    fs.writeFileSync(`/tmp/tv-accounting-${sym}.txt`,canonical.join('\n')+(canonical.length?'\n':''));
    await closeEditor(p,dlg);
    body=await p.locator('body').innerText().catch(()=>'');
    fs.writeFileSync(`/tmp/tv-accounting-body-${sym}.txt`,body);
    await p.screenshot({path:`/tmp/tv-accounting-${sym}.png`,fullPage:true}).catch(()=>{});
    log('META_LINES',meta.length);log('RECORD_CELLS',recs.length);
    if(meta.length<1||recs.length<10)throw new Error('WebSocket accounting messages not captured');
  }catch(e){
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
  for(const sym of ['BNBUSDT','TRXUSDT'])await runSymbol(sym);
}finally{
  await browser.close();
}
