import fs from 'node:fs';
import crypto from 'node:crypto';
import { chromium } from 'playwright-core';

const sym='TRXUSDT';
const source=fs.readFileSync('/tmp/wr2513-accounting-probe.pine','utf8');
const state=JSON.parse(fs.readFileSync('/tmp/tv-state.json','utf8'));
const want=crypto.createHash('sha256').update(source,'utf8').digest('hex');
const exes=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium-browser','/usr/bin/chromium'];
const executablePath=exes.find(fs.existsSync);
if(!executablePath)throw new Error('Chrome missing');

function extractMarkers(text){
  const out=[];
  if(typeof text!=='string'||(!text.includes('WRP#')&&!text.includes('WRMETA|')))return out;
  const row=/WRP#\d+\|entryMs=\d+\|exitMs=\d+\|qty=[^|"\\]+\|risk=[^|"\\]+\|planE=[^|"\\]+\|planS=[^|"\\]+\|planT=[^|"\\]+\|actualE=[^|"\\]+\|actualX=[^|"\\]+\|canonR=[^|"\\]+\|exit=[^|"\\]+\|report=1\|eqBefore=[^|"\\]+\|nativePnl=[^|"\\]+\|both=[01]/g;
  for(const m of text.matchAll(row))out.push(m[0].replace(/\\u2192/g,'→'));
  const meta=/WRMETA\|firstMs=\d+\|lastMs=\d+\|mintick=[^|"\\]+\|mincontract=[^|"\\]+\|pointvalue=[^|"\\]+\|rows=\d+\|canonEq=[^|"\\]+\|canonTrades=\d+\|windowTrades=\d+\|windowR=[^|"\\\]\}]+/g;
  for(const m of text.matchAll(meta))out.push(m[0]);
  return out;
}

const browser=await chromium.launch({executablePath,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
try{
  const ctx=await browser.newContext({storageState:state,viewport:{width:1920,height:1080},permissions:['clipboard-read','clipboard-write']});
  const p=await ctx.newPage();p.setDefaultTimeout(25000);
  const cdp=await ctx.newCDPSession(p);
  await cdp.send('Network.enable');
  const found=[];const raw=[];
  cdp.on('Network.webSocketFrameReceived',ev=>{
    const s=ev?.response?.payloadData||'';
    if(s.includes('WRP#')||s.includes('WRMETA|')){
      raw.push(s);
      for(const x of extractMarkers(s))found.push(x);
    }
  });

  await p.goto(`https://www.tradingview.com/chart/?symbol=BINANCE%3A${sym}.P&interval=5`,{waitUntil:'domcontentloaded',timeout:90000});
  await p.waitForTimeout(9000);
  let body=await p.locator('body').innerText().catch(()=>'');
  console.log('TRX_AUTH='+(/\bSign in\b/i.test(body)?'FAIL':'PASS'));
  if(/\bSign in\b/i.test(body))throw new Error('auth missing');

  const pine=p.locator('[data-name="pine-dialog-button"]').first();await pine.click();
  const dlg=p.locator('[data-name="pine-dialog"]').first();await dlg.waitFor({state:'visible'});await p.waitForTimeout(1800);
  const ta=dlg.locator('.monaco-editor textarea.inputarea, .monaco-editor textarea').first();await ta.waitFor({state:'attached'});
  for(let i=0;i<30;i++){if(await ta.isEditable().catch(()=>false))break;await p.waitForTimeout(300)}
  await ta.evaluate(e=>e.focus());await p.keyboard.press('Control+A');
  await p.evaluate(async s=>navigator.clipboard.writeText(s),source);await p.keyboard.press('Control+V');await p.waitForTimeout(3000);
  await p.evaluate(async()=>navigator.clipboard.writeText('sentinel'));await ta.evaluate(e=>e.focus());await p.keyboard.press('Control+A');await p.keyboard.press('Control+C');await p.waitForTimeout(700);
  const rt=await p.evaluate(async()=>navigator.clipboard.readText());
  const got=crypto.createHash('sha256').update(rt,'utf8').digest('hex');
  console.log('TRX_EDITOR_HASH='+(got===want?'PASS':'FAIL'));if(got!==want)throw new Error('editor hash mismatch');

  const net=[];p.on('response',r=>{/pine-facade/i.test(r.url())&&net.push({status:r.status(),url:r.url()})});
  await dlg.getByRole('button',{name:'Add to chart',exact:true}).first().click();
  let compile=false;
  for(let i=0;i<90;i++){await p.waitForTimeout(650);const upd=await dlg.locator('[title="Update on chart"]').count()>0;const tr=net.some(x=>x.status===200&&/pine-facade\/translate\/USER%3B/i.test(x.url));if(upd&&tr){compile=true;break}}
  console.log('TRX_COMPILE='+(compile?'PASS':'FAIL'));if(!compile)throw new Error('compile failed');

  for(let i=0;i<50;i++){
    await p.waitForTimeout(600);
    const u=[...new Set(found)];
    if(u.some(x=>x.startsWith('WRMETA|'))&&u.filter(x=>x.startsWith('WRP#')).length>=14)break;
  }
  const u=[...new Set(found)];
  const metas=u.filter(x=>x.startsWith('WRMETA|'));
  const rows=u.filter(x=>x.startsWith('WRP#')).sort((a,b)=>Number(a.match(/^WRP#(\d+)/)?.[1]||0)-Number(b.match(/^WRP#(\d+)/)?.[1]||0));
  console.log('TRX_CDP_META='+metas.length);console.log('TRX_CDP_ROWS='+rows.length);console.log('TRX_RAW_FRAMES='+raw.length);
  fs.writeFileSync('/tmp/tv-accounting-TRXUSDT.txt',[...(metas.slice(-1)),...rows].join('\n')+'\n');
  fs.writeFileSync('/tmp/tv-accounting-TRXUSDT-raw.txt',raw.join('\n---FRAME---\n'));
  await p.screenshot({path:'/tmp/tv-accounting-TRXUSDT.png',fullPage:true}).catch(()=>{});
  if(metas.length<1||rows.length<14)throw new Error('incomplete TRX CDP ledger');
}finally{
  await browser.close();
}
