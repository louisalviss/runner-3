const fs=require('fs'); const {chromium}=require('playwright-core');
const base=fs.readFileSync('/tmp/wr2515.pine','utf8');
const W1S='1785862800000', W1E='1786294800000';
const W2S='1786294800000', W2E='1786813200000';
function windowed(src,s,e){return src.replace(`startTime=input.time(${W1S},"Start (VN)"`,`startTime=input.time(${s},"Start (VN)"`).replace(`endTime=input.time(${W1E},"End (VN, exclusive)"`,`endTime=input.time(${e},"End (VN, exclusive)"`)}
function cap(src,n){return src.replace('maxNotionalMultiple=input.float(3.0,','maxNotionalMultiple=input.float('+n.toFixed(1)+',')}
function proof(src,tag){return src+`\n// TEMP SYNC PROOF — not part of canonical source\nvar label syncProof_${tag}=na\nif barstate.islastconfirmedhistory\n    if not na(syncProof_${tag})\n        label.delete(syncProof_${tag})\n    syncProof_${tag}:=label.new(bar_index,high,"${tag} | T="+str.tostring(windowTrades)+" | R="+str.tostring(windowTotalR,"#.######")+" | CAPSKIP="+str.tostring(notionalCapSkips)+" | ANCHOR="+str.tostring(stateAnchorSeen),style=label.style_label_down,textcolor=color.white,color=color.black,size=size.large)\n`}
(async()=>{
  const exe=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium'].find(fs.existsSync);
  const state=JSON.parse(fs.readFileSync('/tmp/tv-state.json','utf8'));
  const browser=await chromium.launch({executablePath:exe,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
  const context=await browser.newContext({storageState:state,viewport:{width:1920,height:1080},permissions:['clipboard-read','clipboard-write']});
  const page=await context.newPage(); const pineSel='[data-name="pine-dialog-button"],button[aria-label="Pine"]';
  async function openSymbol(sym){
    await page.goto(`https://www.tradingview.com/chart/?symbol=BINANCE%3A${sym}&interval=5`,{waitUntil:'domcontentloaded',timeout:90000}); await page.waitForTimeout(9000);
    const body=await page.locator('body').innerText().catch(()=> ''); if(/\bSign in\b/i.test(body)) throw new Error('AUTH_FAIL');
    const pine=page.locator(pineSel); if(!(await pine.count())) throw new Error('PINE_BUTTON_MISSING'); await pine.first().click({force:true}); await page.waitForTimeout(4500);
  }
  async function pasteCompile(src){
    const ta=page.locator('.monaco-editor textarea').last(); if(!(await ta.count())) throw new Error('MONACO_MISSING');
    await page.evaluate(s=>navigator.clipboard.writeText(s),src); await ta.click({force:true}); await page.keyboard.press('Control+A'); await page.keyboard.press('Control+V'); await page.waitForTimeout(1000);
    const add=page.getByRole('button',{name:/Add to chart/i}); if(await add.count()) await add.first().click({force:true}); else {await ta.click({force:true});await page.keyboard.press('Control+Enter');}
    await page.waitForTimeout(16000); const body=await page.locator('body').innerText().catch(()=> ''); if(/Compilation error|Syntax error|Error at/i.test(body)) throw new Error('COMPILE_FAIL'); return ta;
  }
  async function closePine(){const pine=page.locator(pineSel); if(await pine.count()) await pine.first().click({force:true}).catch(()=>{}); await page.waitForTimeout(2500);}
  async function shot(sym,tag,src){await openSymbol(sym); await pasteCompile(proof(src,tag.replace(/[^A-Za-z0-9]/g,''))); await closePine(); await page.waitForTimeout(2500); await page.screenshot({path:`/tmp/${tag}-${sym}.png`,fullPage:false}); console.log(`${tag}_${sym}=PROOF_SHOT_PASS`);}
  const w1=windowed(base,W1S,W1E), w2=windowed(base,W2S,W2E);
  await shot('BNBUSDT.P','W1-CAP3',w1); await shot('TRXUSDT.P','W1-CAP3',w1);
  await shot('BNBUSDT.P','W1-CAP100',cap(w1,100)); await shot('TRXUSDT.P','W1-CAP100',cap(w1,100));
  await shot('BNBUSDT.P','W2-CAP100',cap(w2,100)); await shot('TRXUSDT.P','W2-CAP100',cap(w2,100));
  await openSymbol('BNBUSDT.P'); const ta=await pasteCompile(base); await ta.click({force:true}); await page.keyboard.press('Control+S'); await page.waitForTimeout(2500);
  const dialogs=page.getByRole('dialog'); let dlg=null; for(let i=0;i<await dialogs.count();i++){if(await dialogs.nth(i).isVisible().catch(()=>false)){dlg=dialogs.nth(i);break;}}
  if(dlg){const boxes=dlg.getByRole('textbox'); if(await boxes.count()) await boxes.first().fill('Wave Rider Strategy v2.5.15 WINDOW DETERMINISTIC'); const sv=dlg.getByRole('button',{name:/save/i}); if(await sv.count()) await sv.last().click({force:true}); else throw new Error('SAVE_BUTTON_MISSING'); await page.waitForTimeout(5000);} else {console.log('SAVE_DIALOG=NONE_AFTER_CTRL_S');}
  const body=await page.locator('body').innerText().catch(()=> ''); console.log('HAS_V2515_NAME='+/Wave Rider Strategy v2\.5\.15 WINDOW DETERMINISTIC/.test(body)); await page.screenshot({path:'/tmp/v2515-saved.png',fullPage:false});
  await browser.close();
})().catch(e=>{console.error('TV2515_ERROR='+e.stack);process.exit(7)});
