import crypto from 'node:crypto';
import { webkit } from 'playwright';

const token=String(process.env.RUNNER3_CORE_TOKEN||'').trim();
if(!token) throw new Error('RUNNER3_CORE_TOKEN_MISSING');
const core=String(process.env.RUNNER3_CORE_URL||'https://runner3-core.ducduy2411.workers.dev').replace(/\/$/,'');
const bookKey=String(process.env.EBOOK_WEBKIT_BOOK_KEY||'core/ebook/tha-nu-phu-thuy-kia-ra-nhi-muc-1lwhn39/final/Thả Nữ Phù Thủy Kia Ra - Nhị Mục.epub');
const cookieValue=crypto.createHash('sha256').update('runner3-artifact-library-v1:'+token).digest('hex');
const url=core+'/artifact-library/read?key='+encodeURIComponent(bookKey);
const host=new URL(core).hostname;
const browser=await webkit.launch({headless:true});
const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
await context.addInitScript(()=>{
  try{Object.defineProperty(navigator,'standalone',{configurable:true,get:()=>true});}catch{}
});
await context.addCookies([{name:'r3_artifact_library',value:cookieValue,domain:host,path:'/artifact-library',httpOnly:true,secure:true,sameSite:'Lax'}]);
await context.route('**/artifact-library/api/progress**',async route=>{
  if(route.request().method()==='POST') return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true,smoke:true})});
  return route.continue();
});
await context.route('**/artifact-library/audio**',async route=>{
  if(route.request().method()==='POST') return route.fulfill({status:202,contentType:'application/json',body:JSON.stringify({ok:true,id:'ebook-00000000000000000000000000000000',status:'pending',smoke:true})});
  return route.continue();
});
const page=await context.newPage();
const errors=[];
page.on('pageerror',e=>errors.push(String(e?.stack||e)));
page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
const safe=x=>JSON.stringify(x);

try{
  const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:60000});
  const headers=response?.headers()||{};
  if(response?.status()!==200) throw new Error('STANDALONE_HTTP_'+response?.status());
  if(headers['x-r3-reader-webkit-runtime']!=='compat-v93') throw new Error('STANDALONE_WEBKIT_V93_MISSING');
  if(headers['x-r3-reader-frame-bind']!=='relocated-v94') throw new Error('STANDALONE_FRAME_V94_MISSING');
  if(headers['x-r3-reader-touch-owner']!=='hybrid-v96') throw new Error('STANDALONE_TOUCH_V96_MISSING');
  const csp=String(headers['content-security-policy']||'');
  if(!/connect-src[^;]*\bblob:/.test(csp)) throw new Error('STANDALONE_CSP_BLOB_MISSING');

  await page.waitForSelector('#viewer iframe',{timeout:30000});
  await page.waitForFunction(()=>Boolean(window.r3ReaderBridge),null,{timeout:30000});
  await page.waitForFunction(()=>window.__R3_BASE_READER_BOOT_DONE===true,null,{timeout:30000});
  await page.waitForFunction(()=>{
    const f=document.querySelector('#viewer iframe');
    try{return String(f?.contentDocument?.body?.innerText||'').trim().length>80}catch{return false}
  },null,{timeout:30000});
  await page.evaluate(()=>{try{window.__r3BindReaderFramesV91?.();}catch{}});
  await page.waitForFunction(()=>{
    const d=document.querySelector('#viewer iframe')?.contentDocument;
    return d?.documentElement?.dataset?.r3GestureOwnerV94==='1'&&d?.documentElement?.dataset?.r3TouchOwnerV96==='hybrid';
  },null,{timeout:5000});

  const state=await page.evaluate(()=>({
    standalone:navigator.standalone===true,
    home:document.documentElement.classList.contains('r3-v90-home'),
    browser:document.documentElement.classList.contains('r3-v90-browser'),
    frameText:String(document.querySelector('#viewer iframe')?.contentDocument?.body?.innerText||'').trim().length,
    current:String(window.r3ReaderBridge?.current?.()?.start?.cfi||''),
    owner:String(window.__R3_INTERACTION_OWNER_V92||''),
    touchOwner:String(window.__R3_TOUCH_OWNER_V96||''),
  }));
  if(!state.standalone||!state.home||state.browser) throw new Error('STANDALONE_MODE_CLASS_BAD '+safe(state));
  if(state.frameText<80||!state.current) throw new Error('STANDALONE_BOOK_NOT_RENDERED '+safe(state));
  if(state.owner!=='single-owner-v92'||state.touchOwner!=='hybrid-v96') throw new Error('STANDALONE_OWNER_BAD '+safe(state));

  const expand=page.locator('#r3AudioExpand');
  await expand.waitFor({state:'visible',timeout:10000});
  await expand.click({timeout:10000});
  await page.waitForFunction(()=>document.getElementById('r3AudioDock')?.classList.contains('r3-expanded'),null,{timeout:5000});
  const speed=page.locator('#r3AudioSpeed');
  const before=String(await speed.textContent()||'');
  await speed.click({timeout:10000});
  await page.waitForFunction(old=>String(document.getElementById('r3AudioSpeed')?.textContent||'')!==old,before,{timeout:5000});
  await page.evaluate(()=>document.body.classList.add('controls'));
  const settings=page.locator('#settingsButton');
  await settings.click({timeout:10000});
  await page.waitForFunction(()=>document.body.classList.contains('settings'),null,{timeout:5000});
  await page.locator('#closeSettings').click({timeout:10000});
  await page.waitForFunction(()=>!document.body.classList.contains('settings'),null,{timeout:5000});

  if(errors.length) throw new Error('STANDALONE_WEBKIT_ERRORS '+errors.slice(0,6).join(' | '));
  console.log(safe({ok:true,mode:'standalone',book:'affected-1498',frameText:state.frameText,owners:{interaction:state.owner,touch:state.touchOwner},controls:{expand:true,speed:true,settings:true}}));
} finally {
  await browser.close();
}
