import fs from 'node:fs';
import crypto from 'node:crypto';
import { chromium } from 'playwright-core';

const source=fs.readFileSync('/tmp/wr2513-accounting-visual.pine','utf8');
const state=JSON.parse(fs.readFileSync('/tmp/tv-state.json','utf8'));
const want=crypto.createHash('sha256').update(source,'utf8').digest('hex');
const exes=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium-browser','/usr/bin/chromium'];
const executablePath=exes.find(fs.existsSync);
if(!executablePath) throw new Error('Chrome missing');
const browser=await chromium.launch({executablePath,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({storageState:state,viewport:{width:2560,height:1600},permissions:['clipboard-read','clipboard-write']});

async function runSymbol(sym){
  const p=await ctx.newPage(); p.setDefaultTimeout(30000);
  const out=[]; const log=(k,v)=>{const s=`${sym}_${k}=${v}`;console.log(s);out.push(s)};
  try{
    await p.goto(`https://www.tradingview.com/chart/?symbol=BINANCE%3A${sym}.P&interval=5`,{waitUntil:'domcontentloaded',timeout:90000});
    await p.waitForTimeout(9000);
    let body=await p.locator('body').innerText().catch(()=>'');
    if(/\bSign in\b/i.test(body)) throw new Error('auth missing');
    log('AUTH','PASS');

    const pine=p.locator('[data-name="pine-dialog-button"]').first();
    await pine.click();
    const dlg=p.locator('[data-name="pine-dialog"]').first();
    await dlg.waitFor({state:'visible'}); await p.waitForTimeout(1800);
    const ta=dlg.locator('.monaco-editor textarea.inputarea, .monaco-editor textarea').first();
    await ta.waitFor({state:'attached'});
    for(let i=0;i<30;i++){if(await ta.isEditable().catch(()=>false))break;await p.waitForTimeout(300)}
    await ta.evaluate(e=>e.focus()); await p.keyboard.press('Control+A');
    await p.evaluate(async s=>navigator.clipboard.writeText(s),source);
    await p.keyboard.press('Control+V'); await p.waitForTimeout(3500);

    await p.evaluate(async()=>navigator.clipboard.writeText('sentinel'));
    await ta.evaluate(e=>e.focus()); await p.keyboard.press('Control+A'); await p.keyboard.press('Control+C'); await p.waitForTimeout(700);
    const rt=await p.evaluate(async()=>navigator.clipboard.readText());
    const got=crypto.createHash('sha256').update(rt,'utf8').digest('hex');
    if(got!==want) throw new Error('editor hash mismatch');
    log('EDITOR_HASH','PASS');

    const net=[]; p.on('response',r=>{/pine-facade/i.test(r.url())&&net.push({status:r.status(),url:r.url()})});
    const add=dlg.getByRole('button',{name:'Add to chart',exact:true}).first();
    await add.click();
    let ok=false;
    for(let i=0;i<90;i++){
      await p.waitForTimeout(650);
      const upd=await dlg.locator('[title="Update on chart"]').count()>0;
      const translated=net.some(x=>x.status===200&&/pine-facade\/translate\/USER%3B/i.test(x.url));
      if(upd&&translated){ok=true;break}
    }
    const dt=await dlg.innerText().catch(()=>'');
    if(!ok||/compilation error|cannot compile|error on bar|failed to add/i.test(dt)) throw new Error('compile/add failed');
    log('COMPILE','PASS');

    // TradingView's Pine button is the reliable toggle for the editor surface.
    if(await dlg.isVisible().catch(()=>false)){
      await pine.click({force:true}).catch(()=>{});
      await p.waitForTimeout(1200);
    }
    if(await dlg.isVisible().catch(()=>false)){
      await p.keyboard.press('Escape').catch(()=>{}); await p.waitForTimeout(900);
    }
    log('EDITOR_HIDDEN',String(!(await dlg.isVisible().catch(()=>false))).toUpperCase());

    // Close the caution toast if it covers the lower report, but do not mutate strategy state.
    for(const b of await p.locator('button').all()){
      const txt=(await b.innerText().catch(()=>''))?.trim();
      if(txt==='Close') await b.click({force:true}).catch(()=>{});
    }
    await p.waitForTimeout(5000);
    body=await p.locator('body').innerText().catch(()=>'');
    const tradeCount=(body.match(/\b(?:long|short)\b/gi)||[]).length;
    log('BODY_TRADE_TOKENS',tradeCount);
    fs.writeFileSync(`/tmp/tv-accounting-visual-${sym}-body.txt`,body);
    await p.screenshot({path:`/tmp/tv-accounting-visual-${sym}.png`,fullPage:true});
    log('SCREENSHOT','PASS');
  }catch(e){
    log('ERROR',String(e?.message||e));
    await p.screenshot({path:`/tmp/tv-accounting-visual-${sym}.png`,fullPage:true}).catch(()=>{});
    throw e;
  }finally{
    fs.writeFileSync(`/tmp/tv-accounting-visual-${sym}-run.txt`,out.join('\n')+'\n');
    await p.close().catch(()=>{});
  }
}

try{
  for(const sym of ['BNBUSDT','TRXUSDT']) await runSymbol(sym);
}finally{
  await browser.close();
}
