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

    // Verify exact editor round trip without putting source in thrown errors/logs.
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
    if(await dlg.isVisible().catch(()=>false)){await pine.click().catch(()=>{});await p.waitForTimeout(2500)}

    // Wait for strategy history calculation and the report-only parity table.
    let lines=[];
    for(let i=0;i<30;i++){
      await p.waitForTimeout(1000);
      body=await p.locator('body').innerText().catch(()=>'');
      lines=body.split('\n').map(x=>x.trim()).filter(x=>x.startsWith('WRMETA|')||x.startsWith('WRP#'));
      if(lines.some(x=>x.startsWith('WRMETA|')) && lines.filter(x=>x.startsWith('WRP#')).length>=20) break;
    }
    fs.writeFileSync(`/tmp/tv-accounting-${sym}.txt`,lines.join('\n')+(lines.length?'\n':''));
    fs.writeFileSync(`/tmp/tv-accounting-body-${sym}.txt`,body);
    await p.screenshot({path:`/tmp/tv-accounting-${sym}.png`,fullPage:true}).catch(()=>{});
    const meta=lines.filter(x=>x.startsWith('WRMETA|'));
    const recs=lines.filter(x=>x.startsWith('WRP#'));
    log('META_LINES',meta.length); log('RECORD_CELLS',recs.length);
    if(meta.length<1||recs.length<20) throw new Error('parity table not captured');
  } catch(e){
    log('ERROR',String(e?.message||e).slice(0,240));
    fs.writeFileSync(`/tmp/tv-accounting-${sym}-run.txt`,out.join('\n')+'\n');
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
