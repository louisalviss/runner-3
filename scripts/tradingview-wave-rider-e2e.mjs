import fs from 'node:fs';
import crypto from 'node:crypto';
import { chromium } from 'playwright-core';

const source = fs.readFileSync('/tmp/wr2513.pine','utf8');
const expectedHash = process.env.EXPECTED_SHA256;
const state = JSON.parse(fs.readFileSync('/tmp/tv-state.json','utf8'));
const report = [];
const log = (k,v) => { const s = `${k}=${v}`; console.log(s); report.push(s); };

const exes=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium-browser','/usr/bin/chromium'];
const executablePath=exes.find(p=>fs.existsSync(p));
if(!executablePath) throw new Error('Chrome/Chromium missing');

const browser=await chromium.launch({executablePath,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
try {
  const context=await browser.newContext({
    storageState: state,
    viewport:{width:1920,height:1080},
    permissions:['clipboard-read','clipboard-write'],
    acceptDownloads:true,
  });
  const page=await context.newPage();
  page.setDefaultTimeout(20000);
  const pineNet=[];
  page.on('response',r=>{const u=r.url(); if(/pine-facade/i.test(u)) pineNet.push({status:r.status(),url:u.slice(0,500)});});
  await page.exposeFunction('__tvCanonicalPine',()=>source);

  await page.goto('https://www.tradingview.com/chart/?symbol=BINANCE%3ABNBUSDT.P&interval=5',{waitUntil:'domcontentloaded',timeout:90000});
  await page.waitForTimeout(10000);
  let body=await page.locator('body').innerText().catch(()=>'');
  log('TV_E2E_AUTH',/\bSign in\b/i.test(body)?'FAIL':'PASS');
  log('TV_E2E_BNB',/BNBUSDT|BNB\/USDT|BNBUSDT\.P/i.test(body)?'PASS':'FAIL');

  const pine=page.locator('[data-name="pine-dialog-button"]').first();
  await pine.click();
  const dialog=page.locator('[data-name="pine-dialog"]').first();
  await dialog.waitFor({state:'visible',timeout:15000});
  await page.waitForTimeout(2500);
  const ta=dialog.locator('.monaco-editor textarea.inputarea, .monaco-editor textarea').first();
  await ta.waitFor({state:'attached'});
  let editable=false;
  for(let i=0;i<30;i++){
    editable=await ta.isEditable().catch(()=>false);
    if(editable) break;
    await page.waitForTimeout(500);
  }
  log('TV_E2E_EDITOR_EDITABLE',editable?'YES':'NO');
  if(!editable) throw new Error('Pine editor never became editable');

  await ta.evaluate(el=>el.focus());
  await page.keyboard.press('Control+A');
  await page.evaluate(async()=>{await navigator.clipboard.writeText(await window.__tvCanonicalPine())});
  await page.keyboard.press('Control+V');
  await page.waitForTimeout(5000);

  await page.evaluate(async()=>{await navigator.clipboard.writeText('TV_CLIPBOARD_SENTINEL')});
  await ta.evaluate(el=>el.focus());
  await page.keyboard.press('Control+A');
  await page.keyboard.press('Control+C');
  await page.waitForTimeout(1200);
  const roundtrip=await page.evaluate(async()=>await navigator.clipboard.readText());
  const roundHash=crypto.createHash('sha256').update(roundtrip,'utf8').digest('hex');
  log('TV_E2E_EDITOR_LEN',roundtrip.length);
  log('TV_E2E_EDITOR_SHA256',roundHash);
  log('TV_E2E_EDITOR_EXACT_HASH',roundHash===expectedHash?'PASS':'FAIL');
  if(roundHash!==expectedHash) throw new Error('Canonical Pine editor hash mismatch');

  pineNet.length=0;
  const add=dialog.getByRole('button',{name:'Add to chart',exact:true}).first();
  log('TV_E2E_ADD_VISIBLE',await add.isVisible().catch(()=>false)?'YES':'NO');
  await add.click();
  let updateOnChart=false;
  let translateUser=false;
  for(let i=0;i<90;i++){
    await page.waitForTimeout(1000);
    updateOnChart=(await dialog.locator('[title="Update on chart"]').first().count()>0);
    translateUser=pineNet.some(x=>x.status===200 && /pine-facade\/translate\/USER%3B/i.test(x.url));
    if(updateOnChart&&translateUser) break;
  }
  log('TV_E2E_UPDATE_ON_CHART',updateOnChart?'PRESENT':'ABSENT');
  log('TV_E2E_USER_TRANSLATE_200',translateUser?'PASS':'FAIL');
  const dialogText=await dialog.innerText().catch(()=>'');
  const compileError=/compilation error|cannot compile|script could not be translated|error on bar|failed to add/i.test(dialogText);
  log('TV_E2E_COMPILE_ERROR',compileError?'PRESENT':'ABSENT');
  if(!updateOnChart||!translateUser||compileError) throw new Error('Canonical strategy did not compile/add cleanly');

  if(await dialog.isVisible().catch(()=>false)) {
    await pine.click().catch(()=>{});
    await page.waitForTimeout(2500);
  }
  body=await page.locator('body').innerText().catch(()=>'');
  log('TV_E2E_STRATEGY_TESTER',/Strategy Tester/i.test(body)?'PRESENT':'ABSENT');
  log('TV_E2E_WR_OUTSIDE_EDITOR',body.includes('WR 2.5.13 WIN')?'PRESENT':'ABSENT');

  let tradesButton=page.locator('[title="Trades"]').first();
  for(let i=0;i<20 && await tradesButton.count()===0;i++) {
    await page.waitForTimeout(500);
    tradesButton=page.locator('[title="Trades"]').first();
  }
  const tradesPresent=await tradesButton.count()>0;
  log('TV_E2E_TRADES_BUTTON',tradesPresent?'PRESENT':'ABSENT');
  if(!tradesPresent) throw new Error('Strategy report Trades button not found');
  await tradesButton.click({force:true});
  await page.waitForTimeout(6000);

  body=await page.locator('body').innerText().catch(()=>'');
  const bodyLines=body.split('\n').map(x=>x.trim()).filter(Boolean);
  const tradeLines=bodyLines.filter(x=>/trade|entry|exit|profit|pnl|long|short|date|time|qty|contracts|download|export|upgrade/i.test(x)).slice(0,400);
  fs.writeFileSync('/tmp/wr2513-trades-body.txt',tradeLines.join('\n')+'\n');
  log('TV_E2E_TRADES_HAS_ENTRY',/\bEntry\b/i.test(body)?'YES':'NO');
  log('TV_E2E_TRADES_HAS_EXIT',/\bExit\b/i.test(body)?'YES':'NO');
  log('TV_E2E_TRADES_HAS_LONGSHORT',/\bLong\b|\bShort\b/i.test(body)?'YES':'NO');
  log('TV_E2E_REPORT_UPGRADE_GATE',/Upgrade to get full access to Strategy report data/i.test(body)?'PRESENT':'ABSENT');

  const controls=await page.locator('button,[role="button"],[aria-label],[title],[data-name]').evaluateAll(els=>els.map(e=>({
    text:(e.innerText||e.textContent||'').trim().replace(/\s+/g,' ').slice(0,180),
    aria:e.getAttribute('aria-label')||'',
    title:e.getAttribute('title')||'',
    dataName:e.getAttribute('data-name')||'',
    disabled:e.disabled||e.getAttribute('aria-disabled')||''
  })).filter(x=>/trade|download|export|csv|report|upgrade|entry|exit/i.test([x.text,x.aria,x.title,x.dataName].join(' '))).slice(0,250));
  fs.writeFileSync('/tmp/wr2513-trades-controls.json',JSON.stringify(controls,null,2));
  log('TV_E2E_TRADES_CONTROLS',controls.length);

  const csvControl=page.locator('[title="Download .csv"]').first();
  const csvVisible=await csvControl.count()>0 && await csvControl.isVisible().catch(()=>false);
  log('TV_E2E_DOWNLOAD_CONTROL',csvVisible?'PRESENT':'ABSENT');
  if(csvVisible){
    const info=await csvControl.evaluate(e=>{
      const a=e.closest('a');
      const b=e.closest('button');
      return {tag:e.tagName,href:a?.getAttribute('href')||'',role:e.getAttribute('role')||'',parentTag:e.parentElement?.tagName||'',buttonTag:b?.tagName||''};
    }).catch(()=>({}));
    fs.writeFileSync('/tmp/wr2513-download-control.json',JSON.stringify(info,null,2));
  }

  let downloaded=false;
  if(csvVisible){
    fs.mkdirSync('/tmp/tv-downloads',{recursive:true});
    const cdp=await context.newCDPSession(page);
    let willBegin=null;
    let completed=null;
    cdp.on('Browser.downloadWillBegin',e=>{willBegin={guid:e.guid,suggestedFilename:e.suggestedFilename,url:String(e.url).slice(0,500)};});
    cdp.on('Browser.downloadProgress',e=>{if(e.state==='completed') completed={guid:e.guid,receivedBytes:e.receivedBytes,totalBytes:e.totalBytes};});
    await cdp.send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:'/tmp/tv-downloads',eventsEnabled:true});
    await csvControl.click({force:true});
    for(let i=0;i<30;i++){
      await page.waitForTimeout(500);
      const files=fs.readdirSync('/tmp/tv-downloads');
      if((completed||files.some(x=>!x.endsWith('.crdownload'))) && files.length) break;
    }
    const files=fs.readdirSync('/tmp/tv-downloads');
    log('TV_E2E_CDP_DOWNLOAD_WILL_BEGIN',willBegin?'YES':'NO');
    log('TV_E2E_CDP_DOWNLOAD_COMPLETED',completed?'YES':'NO');
    log('TV_E2E_DOWNLOAD_FILES',files.length);
    fs.writeFileSync('/tmp/wr2513-download-events.json',JSON.stringify({willBegin,completed,files},null,2));
    const completedFile=files.find(x=>!x.endsWith('.crdownload'));
    if(completedFile){
      fs.copyFileSync('/tmp/tv-downloads/'+completedFile,'/tmp/wr2513-trades-export.csv');
      downloaded=true;
    }
  }
  log('TV_E2E_CSV_DOWNLOADED',downloaded?'YES':'NO');
  if(downloaded){
    const st=fs.statSync('/tmp/wr2513-trades-export.csv');
    log('TV_E2E_CSV_BYTES',st.size);
    const head=fs.readFileSync('/tmp/wr2513-trades-export.csv','utf8').split(/\r?\n/).slice(0,4).join('\n');
    fs.writeFileSync('/tmp/wr2513-trades-export-head.txt',head+'\n');
  }

  fs.writeFileSync('/tmp/wr2513-e2e-report.txt',report.join('\n')+'\n');
  await page.screenshot({path:'/tmp/wr2513-trades-panel.png',fullPage:true}).catch(()=>{});
} catch (e) {
  console.error('TV_E2E_ERROR='+e.message);
  report.push('TV_E2E_ERROR='+e.message);
  fs.writeFileSync('/tmp/wr2513-e2e-report.txt',report.join('\n')+'\n');
  process.exitCode=8;
} finally {
  await browser.close();
}
