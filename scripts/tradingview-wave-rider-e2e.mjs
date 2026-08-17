import fs from 'node:fs';
import crypto from 'node:crypto';
import { chromium } from 'playwright-core';

const src=fs.readFileSync('/tmp/wr2513.pine','utf8');
const state=JSON.parse(fs.readFileSync('/tmp/tv-state.json','utf8'));
const want=process.env.EXPECTED_SHA256;
const R=[]; const log=(k,v)=>{const s=`${k}=${v}`;console.log(s);R.push(s)};
const exes=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium-browser','/usr/bin/chromium'];
const executablePath=exes.find(fs.existsSync);
if(!executablePath) throw new Error('Chrome missing');
const browser=await chromium.launch({executablePath,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});

try{
  const ctx=await browser.newContext({storageState:state,viewport:{width:1920,height:1080},permissions:['clipboard-read','clipboard-write'],acceptDownloads:true});
  const p=await ctx.newPage(); p.setDefaultTimeout(20000);
  const net=[]; p.on('response',r=>{/pine-facade/i.test(r.url())&&net.push({status:r.status(),url:r.url().slice(0,500)})});
  await p.exposeFunction('__tvPine',()=>src);
  await p.exposeFunction('__tvSaveCsvB64',(name,b64)=>{
    const buf=Buffer.from(b64,'base64');
    fs.writeFileSync('/tmp/wr2513-trades-export.csv',buf);
    log('TV_E2E_BLOB_CAPTURE_NAME',String(name||'').slice(0,120));
    log('TV_E2E_BLOB_CAPTURE_BYTES',buf.length);
  });

  await p.goto('https://www.tradingview.com/chart/?symbol=BINANCE%3ABNBUSDT.P&interval=5',{waitUntil:'domcontentloaded',timeout:90000});
  await p.waitForTimeout(10000);
  let body=await p.locator('body').innerText().catch(()=>'');
  log('TV_E2E_AUTH',/\bSign in\b/i.test(body)?'FAIL':'PASS');
  log('TV_E2E_BNB',/BNBUSDT|BNB\/USDT|BNBUSDT\.P/i.test(body)?'PASS':'FAIL');

  const pine=p.locator('[data-name="pine-dialog-button"]').first(); await pine.click();
  const dlg=p.locator('[data-name="pine-dialog"]').first(); await dlg.waitFor({state:'visible'}); await p.waitForTimeout(2500);
  const ta=dlg.locator('.monaco-editor textarea.inputarea, .monaco-editor textarea').first(); await ta.waitFor({state:'attached'});
  let editable=false; for(let i=0;i<30;i++){editable=await ta.isEditable().catch(()=>false);if(editable)break;await p.waitForTimeout(500)}
  log('TV_E2E_EDITOR_EDITABLE',editable?'YES':'NO'); if(!editable)throw new Error('Editor not editable');

  await ta.evaluate(e=>e.focus()); await p.keyboard.press('Control+A');
  await p.evaluate(async()=>navigator.clipboard.writeText(await window.__tvPine()));
  await p.keyboard.press('Control+V'); await p.waitForTimeout(5000);
  await p.evaluate(async()=>navigator.clipboard.writeText('sentinel')); await ta.evaluate(e=>e.focus());
  await p.keyboard.press('Control+A'); await p.keyboard.press('Control+C'); await p.waitForTimeout(1200);
  const rt=await p.evaluate(async()=>navigator.clipboard.readText());
  const hash=crypto.createHash('sha256').update(rt,'utf8').digest('hex');
  log('TV_E2E_EDITOR_LEN',rt.length); log('TV_E2E_EDITOR_SHA256',hash); log('TV_E2E_EDITOR_EXACT_HASH',hash===want?'PASS':'FAIL');
  if(hash!==want)throw new Error('Editor hash mismatch');

  net.length=0; const add=dlg.getByRole('button',{name:'Add to chart',exact:true}).first();
  log('TV_E2E_ADD_VISIBLE',await add.isVisible().catch(()=>false)?'YES':'NO'); await add.click();
  let upd=false,tr=false; for(let i=0;i<90;i++){await p.waitForTimeout(1000);upd=await dlg.locator('[title="Update on chart"]').count()>0;tr=net.some(x=>x.status===200&&/pine-facade\/translate\/USER%3B/i.test(x.url));if(upd&&tr)break}
  const dtext=await dlg.innerText().catch(()=>''); const cerr=/compilation error|cannot compile|script could not be translated|error on bar|failed to add/i.test(dtext);
  log('TV_E2E_UPDATE_ON_CHART',upd?'PRESENT':'ABSENT');log('TV_E2E_USER_TRANSLATE_200',tr?'PASS':'FAIL');log('TV_E2E_COMPILE_ERROR',cerr?'PRESENT':'ABSENT');
  if(!upd||!tr||cerr)throw new Error('Compile/add failed');

  if(await dlg.isVisible().catch(()=>false)){await pine.click().catch(()=>{});await p.waitForTimeout(2500)}
  body=await p.locator('body').innerText().catch(()=>''); log('TV_E2E_WR_OUTSIDE_EDITOR',body.includes('WR 2.5.13 WIN')?'PRESENT':'ABSENT');
  let trades=p.locator('[title="Trades"]').first(); for(let i=0;i<20&&await trades.count()===0;i++){await p.waitForTimeout(500);trades=p.locator('[title="Trades"]').first()}
  log('TV_E2E_TRADES_BUTTON',await trades.count()>0?'PRESENT':'ABSENT'); if(await trades.count()===0)throw new Error('Trades button missing');
  await trades.click({force:true}); await p.waitForTimeout(6000);

  body=await p.locator('body').innerText().catch(()=>'');
  fs.writeFileSync('/tmp/wr2513-trades-body.txt',body.split('\n').map(x=>x.trim()).filter(x=>/trade|entry|exit|profit|pnl|long|short|date|time|qty|contracts|download|export|upgrade/i.test(x)).slice(0,500).join('\n')+'\n');
  log('TV_E2E_TRADES_HAS_ENTRY',/\bEntry\b/i.test(body)?'YES':'NO');log('TV_E2E_TRADES_HAS_EXIT',/\bExit\b/i.test(body)?'YES':'NO');log('TV_E2E_REPORT_UPGRADE_GATE',/Upgrade to get full access to Strategy report data/i.test(body)?'PRESENT':'ABSENT');
  const controls=await p.locator('button,[role="button"],[aria-label],[title],[data-name]').evaluateAll(es=>es.map(e=>({text:(e.innerText||e.textContent||'').trim().replace(/\s+/g,' ').slice(0,180),aria:e.getAttribute('aria-label')||'',title:e.getAttribute('title')||'',dataName:e.getAttribute('data-name')||'',disabled:e.disabled||e.getAttribute('aria-disabled')||''})).filter(x=>/trade|download|export|csv|report|upgrade|entry|exit/i.test([x.text,x.aria,x.title,x.dataName].join(' '))).slice(0,250));
  fs.writeFileSync('/tmp/wr2513-trades-controls.json',JSON.stringify(controls,null,2));

  const csv=p.locator('[title="Download .csv"]').first(); const visible=await csv.count()>0&&await csv.isVisible().catch(()=>false); log('TV_E2E_DOWNLOAD_CONTROL',visible?'PRESENT':'ABSENT');
  if(visible){
    const info=await csv.evaluate(e=>({tag:e.tagName,disabled:e.disabled||false,cls:String(e.className||'').slice(0,300),html:e.outerHTML.slice(0,1200)}));
    fs.writeFileSync('/tmp/wr2513-download-control.json',JSON.stringify(info,null,2));
    await p.evaluate(()=>{
      window.__tvDownloadTrace=[];
      const old=URL.createObjectURL.bind(URL);
      URL.createObjectURL=function(obj){
        let url=old(obj);
        try{
          window.__tvDownloadTrace.push({kind:'objectURL',type:obj?.type||'',size:obj?.size||0});
          if(obj instanceof Blob){obj.arrayBuffer().then(buf=>{
            const a=new Uint8Array(buf);let s='';const step=0x8000;
            for(let i=0;i<a.length;i+=step)s+=String.fromCharCode(...a.subarray(i,i+step));
            window.__tvSaveCsvB64('blob:'+String(obj.type||''),btoa(s));
          }).catch(()=>{});}
        }catch{}
        return url;
      };
      const oldClick=HTMLAnchorElement.prototype.click;
      HTMLAnchorElement.prototype.click=function(){try{window.__tvDownloadTrace.push({kind:'anchor',download:this.download||'',href:String(this.href||'').slice(0,240)})}catch{};return oldClick.call(this)};
      const oldDispatch=HTMLAnchorElement.prototype.dispatchEvent;
      HTMLAnchorElement.prototype.dispatchEvent=function(ev){try{if(ev?.type==='click')window.__tvDownloadTrace.push({kind:'anchor-dispatch',download:this.download||'',href:String(this.href||'').slice(0,240)})}catch{};return oldDispatch.call(this,ev)};
    });
    await csv.click({force:true}); await p.waitForTimeout(6000);
    const trace=await p.evaluate(()=>window.__tvDownloadTrace||[]).catch(()=>[]);
    fs.writeFileSync('/tmp/wr2513-download-events.json',JSON.stringify(trace,null,2));
    log('TV_E2E_DOWNLOAD_TRACE_EVENTS',trace.length);
  }
  const downloaded=fs.existsSync('/tmp/wr2513-trades-export.csv'); log('TV_E2E_CSV_DOWNLOADED',downloaded?'YES':'NO');
  if(downloaded){const n=fs.statSync('/tmp/wr2513-trades-export.csv').size;log('TV_E2E_CSV_BYTES',n);const head=fs.readFileSync('/tmp/wr2513-trades-export.csv','utf8').split(/\r?\n/).slice(0,4).join('\n');fs.writeFileSync('/tmp/wr2513-trades-export-head.txt',head+'\n')}
  fs.writeFileSync('/tmp/wr2513-e2e-report.txt',R.join('\n')+'\n'); await p.screenshot({path:'/tmp/wr2513-trades-panel.png',fullPage:true}).catch(()=>{});
}catch(e){console.error('TV_E2E_ERROR='+e.message);R.push('TV_E2E_ERROR='+e.message);fs.writeFileSync('/tmp/wr2513-e2e-report.txt',R.join('\n')+'\n');process.exitCode=8}
finally{await browser.close()}
