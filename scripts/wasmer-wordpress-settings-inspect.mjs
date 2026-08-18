import { chromium } from 'playwright-core';
import fs from 'fs';
// This inspection step also acts as the stable trigger for the live edge-speed workflow.
const state=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const out={status:'starting',dashboard:false,adminControl:null,wordpressSettings:false,controls:[],detail:null,updatedAt:new Date().toISOString()};
const redact=s=>String(s||'')
  .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'EMAIL_REDACTED')
  .replace(/([?&](?:token|magiclogin|key|code|secret|auth|signature)=)[^&\s"']+/ig,'$1REDACTED')
  .slice(0,3000);
const save=()=>{out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-wp-settings-inspect.json',JSON.stringify(out,null,2));};
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function controls(p){
 return await p.locator('a,button,input').evaluateAll(xs=>xs.map(x=>({
   tag:x.tagName.toLowerCase(),
   text:(x.innerText||x.textContent||x.getAttribute('value')||'').replace(/\s+/g,' ').trim().slice(0,140),
   href:x.href||'',type:x.getAttribute('type'),name:x.getAttribute('name'),placeholder:x.getAttribute('placeholder')||''
 })).filter(x=>/wordpress|admin|password|user|email|reset|login|credential|magic|settings/i.test([x.text,x.href,x.name,x.placeholder].join(' '))).slice(0,80));
}
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({storageState:'/tmp/wasmer-browser-state.json'});const p=await ctx.newPage();
try{
 const dash=`https://wasmer.io/apps/${encodeURIComponent(state.username)}/${encodeURIComponent(state.appName)}`;
 await p.goto(dash,{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(1200);
 let t=await body(p);if(/\/login(?:[/?#]|$)/i.test(p.url())){out.status='session_expired';out.detail=redact(t);save();process.exit(0);}out.dashboard=true;
 const admin=p.locator('a,button').filter({hasText:/WordPress Admin/i}).first();
 if(await admin.count()){
   out.adminControl={tag:await admin.evaluate(el=>el.tagName.toLowerCase()).catch(()=>null),href:redact(await admin.getAttribute('href')),target:await admin.getAttribute('target'),text:redact(await admin.innerText().catch(()=>''))};
 }
 const wpSettings=`${dash}/settings/wordpress`;
 const r=await p.goto(wpSettings,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>null);await p.waitForTimeout(1400);
 t=await body(p);out.wordpressSettings=!!r && !/page requested does not exist|\b404\b/i.test(t) && !/\/login(?:[/?#]|$)/i.test(p.url());
 out.controls=(await controls(p)).map(x=>({...x,text:redact(x.text),href:redact(x.href),placeholder:redact(x.placeholder)}));
 out.detail=redact(t);out.status=out.wordpressSettings?'inspected':'settings_unavailable';save();
}catch(e){out.status='error';out.detail=redact(String(e));save();}finally{await browser.close();}
