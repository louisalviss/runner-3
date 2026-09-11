import crypto from 'node:crypto';
import { webkit } from 'playwright';

const token=String(process.env.RUNNER3_CORE_TOKEN||'').trim();
if(!token) throw new Error('RUNNER3_CORE_TOKEN_MISSING');
const core=String(process.env.RUNNER3_CORE_URL||'https://runner3-core.ducduy2411.workers.dev').replace(/\/$/,'');
const bookKey=String(process.env.EBOOK_WEBKIT_BOOK_KEY||'core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub');
const cookieValue=crypto.createHash('sha256').update('runner3-artifact-library-v1:'+token).digest('hex');
const url=core+'/artifact-library/read?key='+encodeURIComponent(bookKey);
const host=new URL(core).hostname;

const browser=await webkit.launch({headless:true});
const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
await context.addCookies([{name:'r3_artifact_library',value:cookieValue,domain:host,path:'/artifact-library',httpOnly:true,secure:true,sameSite:'Lax'}]);
const page=await context.newPage();
const consoleErrors=[];
const failedRequests=[];
const badResponses=[];
const redactUrl=value=>{try{const u=new URL(String(value));return u.hostname+u.pathname}catch{return String(value||'').split('?')[0]}};
page.on('pageerror',error=>consoleErrors.push(String(error?.stack||error)));
page.on('console',msg=>{if(msg.type()==='error')consoleErrors.push(msg.text())});
page.on('requestfailed',request=>failedRequests.push({url:redactUrl(request.url()),error:String(request.failure()?.errorText||'failed')}));
page.on('response',response=>{if(response.status()>=400)badResponses.push({status:response.status(),url:redactUrl(response.url())})});

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

  await page.waitForSelector('#viewer iframe',{timeout:30000});
  await page.waitForFunction(()=>Boolean(window.r3ReaderBridge),null,{timeout:30000});
  try{
    await page.waitForFunction(()=>{
      const frame=document.querySelector('#viewer iframe');
      try{return String(frame?.contentDocument?.body?.innerText||'').trim().length>80}catch{return false}
    },null,{timeout:30000});
  }catch(error){
    const diagnostic=await page.evaluate(()=>{
      const safeFrameSrc=value=>{
        const raw=String(value||'');
        if(!raw)return '';
        if(raw.startsWith('blob:'))return 'blob:';
        try{const u=new URL(raw,location.href);return u.protocol+'//'+u.host+u.pathname}catch{return raw.split('?')[0].slice(0,240)}
      };
      const frames=[...document.querySelectorAll('#viewer iframe')].map(frame=>{
        try{
          const doc=frame.contentDocument;
          return {src:safeFrameSrc(frame.getAttribute('src')||frame.src),contentDocument:Boolean(doc),readyState:doc?.readyState||'',body:Boolean(doc?.body),textLength:String(doc?.body?.innerText||'').trim().length,htmlLength:String(doc?.body?.innerHTML||'').length,title:String(doc?.title||'').slice(0,120)};
        }catch(frameError){return {src:safeFrameSrc(frame.getAttribute('src')||frame.src),accessError:String(frameError?.message||frameError).slice(0,180)}}
      });
      let current=null;
      try{const loc=window.r3ReaderBridge?.current?.();current={cfi:String(loc?.start?.cfi||''),href:String(loc?.start?.href||'').split('?')[0].slice(0,240)}}catch{}
      return {
        href:location.pathname,
        title:String(document.title||'').slice(0,180),
        loading:{text:String(document.getElementById('loading')?.textContent||'').slice(0,300),className:String(document.getElementById('loading')?.className||'')},
        epubType:typeof window.ePub,
        bridge:Boolean(window.r3ReaderBridge),
        current,
        baseBoot:window.__r3BaseReaderBootV47||null,
        basePending:Boolean(window.__R3_BASE_READER_BOOT_PENDING),
        baseDone:Boolean(window.__R3_BASE_READER_BOOT_DONE),
        restorePending:Boolean(window.__R3_READER_RESTORE_PENDING),
        stableRuntime:window.__r3StableRuntimeV82?{restoreTarget:String(window.__r3StableRuntimeV82.restoreTarget||''),restoreAfter:String(window.__r3StableRuntimeV82.restoreAfter||''),restoreOk:Boolean(window.__r3StableRuntimeV82.restoreOk),restoreReleasedBy:String(window.__r3StableRuntimeV82.restoreReleasedBy||''),restoreError:String(window.__r3StableRuntimeV82.restoreError||''),navMoves:Number(window.__r3StableRuntimeV82.navMoves||0)}:null,
        frames,
      };
    }).catch(diagError=>({diagnosticError:String(diagError?.message||diagError).slice(0,240)}));
    console.error('WEBKIT_BOOT_DIAGNOSTIC='+safe({diagnostic,consoleErrors:consoleErrors.slice(0,8),failedRequests:failedRequests.slice(0,12),badResponses:badResponses.slice(0,12)}));
    throw error;
  }
  await page.waitForTimeout(1200);

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
  await page.evaluate(()=>{
    const doc=document.querySelector('#viewer iframe')?.contentDocument;
    const win=doc?.defaultView;
    if(!doc||!win?.PointerEvent) throw new Error('EPUB_POINTER_EVENT_UNAVAILABLE');
    const target=doc.elementFromPoint(300,300)||doc.body;
    const fire=(type,x,y)=>target.dispatchEvent(new win.PointerEvent(type,{bubbles:true,cancelable:true,pointerId:77,pointerType:'touch',clientX:x,clientY:y,button:0}));
    fire('pointerdown',300,300); fire('pointermove',180,302); fire('pointerup',70,303);
  });
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
