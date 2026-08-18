import { chromium } from 'playwright-core';
import fs from 'fs';
const state=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const out={status:'starting',dashboard:false,hasExpiryBanner:null,hasVerifyControl:null,relevant:[],settingsProbes:[],detail:null,updatedAt:new Date().toISOString()};
const redact=s=>String(s||'').replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'EMAIL_REDACTED').slice(0,2200);
const save=()=>{out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-account-inspect.json',JSON.stringify(out,null,2));};
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function controls(p){
 const rows=await p.locator('a,button,input').evaluateAll(xs=>xs.map(x=>({tag:x.tagName.toLowerCase(),text:(x.innerText||x.textContent||x.getAttribute('value')||'').replace(/\s+/g,' ').trim().slice(0,120),href:x.href||null,type:x.getAttribute('type'),name:x.getAttribute('name'),placeholder:x.getAttribute('placeholder')})).filter(x=>/verify|account|profile|setting|email|logout|log out/i.test([x.text,x.href,x.name,x.placeholder].join(' '))).slice(0,60)).catch(()=>[]);
 return rows.map(x=>({...x,text:redact(x.text),href:redact(x.href),placeholder:redact(x.placeholder)}));
}
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({storageState:'/tmp/wasmer-browser-state.json'});const p=await ctx.newPage();
try{
 const dash=`https://wasmer.io/apps/${encodeURIComponent(state.username)}/${encodeURIComponent(state.appName)}`;
 await p.goto(dash,{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(1600);
 let t=await body(p);if(/\/login(?:[/?#]|$)/i.test(p.url())){out.status='session_expired';out.detail=redact(t);save();process.exit(0);}out.dashboard=true;out.hasExpiryBanner=/expire/i.test(t);out.hasVerifyControl=/verify your account/i.test(t);out.relevant=await controls(p);out.detail=redact(t);
 const userCtl=p.locator('button,a').filter({hasText:new RegExp(state.username.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'i')}).first();
 if(await userCtl.count()&&await userCtl.isVisible().catch(()=>false)){await userCtl.click().catch(()=>{});await p.waitForTimeout(500);out.relevant.push(...await controls(p));}
 for(const url of ['https://wasmer.io/settings','https://wasmer.io/account','https://wasmer.io/profile']){
   const r=await p.goto(url,{waitUntil:'domcontentloaded',timeout:30000}).catch(()=>null);await p.waitForTimeout(700);const b=await body(p);out.settingsProbes.push({url:p.url(),http:r?.status?.()??null,notFound:/page requested does not exist|\b404\b/i.test(b),login:/\/login(?:[/?#]|$)/i.test(p.url()),body:redact(b),controls:await controls(p)});
 }
 out.status='inspected';save();
}catch(e){out.status='error';out.detail=redact(String(e));save();}finally{await browser.close();}
