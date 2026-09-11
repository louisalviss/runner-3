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
await context.addCookies([{name:'r3_artifact_library',value:cookieValue,domain:host,path:'/artifact-library',httpOnly:true,secure:true,sameSite:'Lax'}]);
const page=await context.newPage();
const consoleErrors=[];
page.on('pageerror',error=>consoleErrors.push(String(error?.stack||error)));
page.on('console',msg=>{if(msg.type()==='error')consoleErrors.push(msg.text())});

function safe(obj){return JSON.stringify(obj);}

try{
  let response=null;
  for(let attempt=1;attempt<=20;attempt++){
    response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:60000});
    const owner=response?.headers()?.['x-r3-reader-interaction-owner']||'';
    if(response?.status()===200&&owner==='single-v92') break;
    if(attempt===20) throw new Error(`LIVE_V92_NOT_READY status=${response?.status()} owner=${owner}`);
    await page.waitForTimeout(1000);
  }

  const csp=String(response?.headers()?.['content-security-policy']||'');
  if(!/connect-src[^;]*\bblob:/.test(csp)) throw new Error('WEBKIT_CSP_BLOB_CONNECT_MISSING '+csp);
  await page.waitForSelector('#viewer iframe',{timeout:30000});
  await page.waitForFunction(()=>Boolean(window.r3ReaderBridge),null,{timeout:30000});
  await page.waitForFunction(()=>window.__R3_BASE_READER_BOOT_DONE===true,null,{timeout:30000});
  // Some EPUBs legitimately open on a cover/title page with no text. Advance through
  // a few spine positions until a readable page is rendered, then test interactions.
  let readable=false;
  for(let step=0;step<12;step++){
    readable=await page.evaluate(()=>{
      const frame=document.querySelector('#viewer iframe');
      try{return String(frame?.contentDocument?.body?.innerText||'').trim().length>80}catch{return false}
    });
    if(readable)break;
    const moved=await page.evaluate(async()=>{
      const bridge=window.r3ReaderBridge;
      if(!bridge||typeof bridge.next!=='function')return false;
      try{await bridge.next();return true}catch{return false}
    });
    if(!moved)break;
    await page.waitForTimeout(350);
  }
  if(!readable){
    const state=await page.evaluate(()=>({
      boot:window.__r3BaseReaderBootV47||null,
      runtime:window.__r3StableRuntimeV82||null,
      frameText:String(document.querySelector('#viewer iframe')?.contentDocument?.body?.innerText||'').trim().length,
      current:String(window.r3ReaderBridge?.current?.()?.start?.cfi||''),
    }));
    throw new Error('WEBKIT_NO_READABLE_SPINE '+safe(state));
  }
  await page.evaluate(()=>{ try{window.__r3BindReaderFramesV91?.();}catch{} });
  await page.waitForFunction(()=>{
    const doc=document.querySelector('#viewer iframe')?.contentDocument;
    return doc?.documentElement?.dataset?.r3GestureOwnerV94==='1';
  },null,{timeout:5000});
  await page.waitForTimeout(400);

  const before=await page.evaluate(()=>{
    const style=id=>{const el=document.getElementById(id);return el?{display:getComputedStyle(el).display,pointerEvents:getComputedStyle(el).pointerEvents}:null};
    return {
      owner:String(window.__R3_INTERACTION_OWNER_V92||''),
      v2:window.__r3LegacyGestureV2Suppressed===true,
      v3:window.__r3LegacyGestureV3Suppressed===true,
      v4:window.__r3LegacyHitZonesV4Suppressed===true,
      oldGesture:style('r3GestureLayer'),
      v82Gesture:style('r3V82GestureLayer'),
      hitLeft:style('r3HitLeft'),
      backdrop:style('r3SettingsBackdrop'),
      moves:Number(window.__r3StableRuntimeV82?.navMoves||0),
      cfi:String(window.r3ReaderBridge?.current?.()?.start?.cfi||''),
      frameText:String(document.querySelector('#viewer iframe')?.contentDocument?.body?.innerText||'').trim().length,
    };
  });

  if(before.owner!=='single-owner-v92') throw new Error('V92_RUNTIME_OWNER_MISSING '+safe(before));
  if(!before.v2||!before.v4) throw new Error('LEGACY_GESTURES_NOT_SUPPRESSED '+safe({v2:before.v2,v3:before.v3,v4:before.v4}));
  for(const [name,state] of [['oldGesture',before.oldGesture],['hitLeft',before.hitLeft],['backdrop',before.backdrop]]){
    if(state&&state.display!=='none') throw new Error(`LEGACY_LAYER_ACTIVE ${name} ${safe(state)}`);
  }
  if(before.v82Gesture&&before.v82Gesture.pointerEvents!=='none') throw new Error('V82_OVERLAY_INTERCEPTS_POINTERS '+safe(before.v82Gesture));

  const expand=page.locator('#r3AudioExpand');
  await expand.waitFor({state:'visible',timeout:15000});
  await expand.click({timeout:10000});
  await page.waitForFunction(()=>document.getElementById('r3AudioDock')?.classList.contains('r3-expanded'),null,{timeout:5000});

  const speed=page.locator('#r3AudioSpeed');
  const speedBefore=String(await speed.textContent()||'');
  await speed.click({timeout:10000});
  await page.waitForFunction(old=>String(document.getElementById('r3AudioSpeed')?.textContent||'')!==old,speedBefore,{timeout:5000});
  const speedAfter=String(await speed.textContent()||'');

  const moveBefore=await page.evaluate(()=>Number(window.__r3StableRuntimeV82?.navMoves||0));
  const cfiBefore=await page.evaluate(()=>String(window.r3ReaderBridge?.current?.()?.start?.cfi||''));
  const swipePoint=await page.evaluate(()=>{
    const frame=document.querySelector('#viewer iframe');
    const doc=frame?.contentDocument;
    const win=doc?.defaultView;
    if(!frame||!doc||!win)throw new Error('EPUB_FRAME_UNAVAILABLE');
    const target=[...doc.querySelectorAll('p,div,span')].find(el=>{
      try{
        if(el.closest('a,button,input,select,textarea,label,[contenteditable=\"true\"]'))return false;
        const r=el.getBoundingClientRect();
        return String(el.textContent||'').trim().length>30&&r.width>80&&r.height>10;
      }catch{return false}
    })||doc.body;
    const r=target.getBoundingClientRect();
    return {
      x0:Math.max(260,Math.min((win.innerWidth||390)-24,r.right-20)),
      x1:Math.max(30,Math.max(260,Math.min((win.innerWidth||390)-24,r.right-20))-230),
      y:Math.max(20,Math.min((win.innerHeight||600)-20,r.top+Math.min(24,Math.max(8,r.height/2)))),
      target:String(target.tagName||''),
      owner:String(doc.documentElement?.dataset?.r3GestureOwnerV94||''),
    };
  });
  const frameBox=await page.locator('#viewer iframe').boundingBox();
  if(!frameBox)throw new Error('EPUB_FRAME_BOX_MISSING');
  await page.mouse.move(frameBox.x+swipePoint.x0,frameBox.y+swipePoint.y);
  await page.mouse.down();
  await page.mouse.move(frameBox.x+(swipePoint.x0+swipePoint.x1)/2,frameBox.y+swipePoint.y,{steps:4});
  await page.mouse.move(frameBox.x+swipePoint.x1,frameBox.y+swipePoint.y,{steps:4});
  await page.mouse.up();
  await page.waitForFunction(old=>Number(window.__r3StableRuntimeV82?.navMoves||0)===old+1,moveBefore,{timeout:8000});
  await page.waitForTimeout(500);
  const moveAfter=await page.evaluate(()=>Number(window.__r3StableRuntimeV82?.navMoves||0));
  const cfiAfter=await page.evaluate(()=>String(window.r3ReaderBridge?.current?.()?.start?.cfi||''));
  if(moveAfter!==moveBefore+1) throw new Error(`SWIPE_NOT_SINGLE ${moveBefore}->${moveAfter}`);
  if(!cfiAfter||cfiAfter===cfiBefore) throw new Error('SWIPE_CFI_UNCHANGED');

  const controlsBefore=await page.evaluate(()=>document.body.classList.contains('controls'));
  await page.evaluate(()=>{
    const doc=document.querySelector('#viewer iframe')?.contentDocument;
    const win=doc?.defaultView;
    if(!doc||!win?.PointerEvent) throw new Error('EPUB_POINTER_EVENT_UNAVAILABLE');
    const target=doc.elementFromPoint(195,300)||doc.body;
    const fire=(type)=>target.dispatchEvent(new win.PointerEvent(type,{bubbles:true,cancelable:true,pointerId:78,pointerType:'touch',clientX:195,clientY:300,button:0}));
    fire('pointerdown'); fire('pointerup');
  });
  await page.waitForTimeout(250);
  const controlsAfter=await page.evaluate(()=>document.body.classList.contains('controls'));
  const moveAfterCenter=await page.evaluate(()=>Number(window.__r3StableRuntimeV82?.navMoves||0));
  if(controlsAfter===controlsBefore) throw new Error('CENTER_TAP_DID_NOT_TOGGLE_CONTROLS');
  if(moveAfterCenter!==moveAfter) throw new Error('CENTER_TAP_NAVIGATED');

  if(!controlsAfter){
    await page.evaluate(()=>document.body.classList.add('controls'));
  }
  const settings=page.locator('#settingsButton');
  await settings.click({timeout:10000});
  await page.waitForFunction(()=>document.body.classList.contains('settings'),null,{timeout:5000});
  const closeSettings=page.locator('#closeSettings');
  await closeSettings.click({timeout:10000});
  await page.waitForFunction(()=>!document.body.classList.contains('settings'),null,{timeout:5000});

  if(consoleErrors.length) throw new Error('WEBKIT_CONSOLE_ERRORS '+consoleErrors.slice(0,6).join(' | '));
  console.log(safe({
    ok:true,
    engine:'webkit',
    header:'single-v92',
    legacy:{v2Suppressed:before.v2,v3PresentInChain:before.v3,v4Suppressed:before.v4},
    layers:{oldGesture:before.oldGesture,hitLeft:before.hitLeft,backdrop:before.backdrop,v82Gesture:before.v82Gesture},
    audio:{expand:true,speedBefore,speedAfter},
    navigation:{singleSwipe:true,movesDelta:moveAfter-moveBefore,cfiChanged:cfiAfter!==cfiBefore,centerTapControls:true},
    settings:{openClose:true},
    frameText:before.frameText,
  }));
} finally {
  await browser.close();
}
