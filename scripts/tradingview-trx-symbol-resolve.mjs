import fs from 'node:fs';
import { chromium } from 'playwright-core';
const state=JSON.parse(fs.readFileSync('/tmp/tv-state.json','utf8'));
const exes=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium-browser','/usr/bin/chromium'];
const executablePath=exes.find(fs.existsSync);if(!executablePath)throw new Error('Chrome missing');
const browser=await chromium.launch({executablePath,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
try{
  const ctx=await browser.newContext({storageState:state,viewport:{width:1400,height:900}});
  const p=await ctx.newPage();const frames=[];
  p.on('websocket',ws=>ws.on('framereceived',e=>{try{const s=typeof e.payload==='string'?e.payload:Buffer.from(e.payload).toString('utf8');if(/TRXUSDT|minmov|pricescale|pointvalue|lot_size|mincontract|volume_precision/i.test(s))frames.push(s)}catch{}}));
  await p.goto('https://www.tradingview.com/chart/?symbol=BINANCE%3ATRXUSDT.P&interval=5',{waitUntil:'domcontentloaded',timeout:90000});
  await p.waitForTimeout(12000);
  const body=await p.locator('body').innerText().catch(()=>'');if(/\bSign in\b/i.test(body))throw new Error('auth missing');
  fs.writeFileSync('/tmp/trx-resolve-frames.txt',frames.join('\n---FRAME---\n'));
  const candidates=[];
  for(const raw of frames){
    for(const chunk of raw.split(/~m~\d+~m~/).filter(Boolean)){
      try{const o=JSON.parse(chunk);const txt=JSON.stringify(o);if(/TRXUSDT/i.test(txt)&&/minmov|pricescale|pointvalue|volume_precision|lot_size/i.test(txt))candidates.push(o)}catch{}
    }
  }
  fs.writeFileSync('/tmp/trx-resolve-candidates.json',JSON.stringify(candidates,null,2));
  console.log('TRX_RESOLVE_FRAMES='+frames.length);console.log('TRX_RESOLVE_CANDIDATES='+candidates.length);
  if(candidates.length===0)throw new Error('TRX resolve_symbol metadata not captured');
}finally{await browser.close()}
