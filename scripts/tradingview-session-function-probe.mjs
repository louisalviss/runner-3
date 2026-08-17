import fs from 'node:fs';
import crypto from 'node:crypto';
import { chromium } from 'playwright-core';

const src=fs.readFileSync('/tmp/wr-session-function-probe.pine','utf8');
const state=JSON.parse(fs.readFileSync('/tmp/tv-state.json','utf8'));
const want=crypto.createHash('sha256').update(src,'utf8').digest('hex');
const exes=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium-browser','/usr/bin/chromium'];
const executablePath=exes.find(fs.existsSync);
if(!executablePath)throw new Error('Chrome missing');
const browser=await chromium.launch({executablePath,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({storageState:state,viewport:{width:2200,height:1300},permissions:['clipboard-read','clipboard-write']});
const p=await ctx.newPage();p.setDefaultTimeout(25000);
const out=[];const log=(k,v)=>{const s=`${k}=${v}`;console.log(s);out.push(s)};
try{
  await p.goto('https://www.tradingview.com/chart/?symbol=BINANCE%3ABNBUSDT.P&interval=5',{waitUntil:'domcontentloaded',timeout:90000});
  await p.waitForTimeout(9000);const body=await p.locator('body').innerText().catch(()=>'');if(/\bSign in\b/i.test(body))throw new Error('auth missing');log('AUTH','PASS');
  const pine=p.locator('[data-name="pine-dialog-button"]').first();await pine.click();const dlg=p.locator('[data-name="pine-dialog"]').first();await dlg.waitFor({state:'visible'});await p.waitForTimeout(1800);
  const ta=dlg.locator('.monaco-editor textarea.inputarea,.monaco-editor textarea').first();await ta.waitFor({state:'attached'});for(let i=0;i<30&&!await ta.isEditable().catch(()=>false);i++)await p.waitForTimeout(300);
  await ta.evaluate(e=>e.focus());await p.keyboard.press('Control+A');await p.evaluate(async s=>navigator.clipboard.writeText(s),src);await p.keyboard.press('Control+V');await p.waitForTimeout(3000);
  await p.evaluate(async()=>navigator.clipboard.writeText('sentinel'));await ta.evaluate(e=>e.focus());await p.keyboard.press('Control+A');await p.keyboard.press('Control+C');await p.waitForTimeout(600);const rt=await p.evaluate(async()=>navigator.clipboard.readText());if(crypto.createHash('sha256').update(rt,'utf8').digest('hex')!==want)throw new Error('editor hash mismatch');log('EDITOR_HASH','PASS');
  const net=[];p.on('response',r=>{/pine-facade/i.test(r.url())&&net.push({status:r.status(),url:r.url()})});const add=dlg.getByRole('button',{name:'Add to chart',exact:true}).first();await add.click();let ok=false;
  for(let i=0;i<90;i++){await p.waitForTimeout(650);const upd=await dlg.locator('[title="Update on chart"]').count()>0;const tr=net.some(x=>x.status===200&&/pine-facade\/translate\/USER%3B/i.test(x.url));if(upd&&tr){ok=true;break}}
  const dt=await dlg.innerText().catch(()=>'');if(!ok||/compilation error|cannot compile|error on bar|failed to add/i.test(dt))throw new Error('compile/add failed');log('COMPILE','PASS');
  if(await dlg.isVisible().catch(()=>false)){await pine.click({force:true}).catch(()=>{});await p.waitForTimeout(1500)}
  await p.waitForTimeout(4000);
  const txt=await p.locator('body').innerText().catch(()=>'');fs.writeFileSync('/tmp/session-function-body.txt',txt);await p.screenshot({path:'/tmp/session-function.png',fullPage:true});log('SCREENSHOT','PASS');
}catch(e){log('ERROR',String(e?.message||e));await p.screenshot({path:'/tmp/session-function.png',fullPage:true}).catch(()=>{});process.exitCode=8}
finally{fs.writeFileSync('/tmp/session-function-run.txt',out.join('\n')+'\n');await browser.close()}
