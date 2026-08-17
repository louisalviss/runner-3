import { chromium } from 'playwright-core';
import fs from 'fs';
const state=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const safe={status:'starting',username:state.username,firstStage:false,passwordStage:false,submitControl:null,loginSuccess:false,dashboardSuccess:false,detail:null,updatedAt:new Date().toISOString()};
function save(){safe.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-login-probe.json',JSON.stringify(safe,null,2));}
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function controls(p){return await p.locator('input,button').evaluateAll(xs=>xs.map(x=>({tag:x.tagName.toLowerCase(),type:x.getAttribute('type'),name:x.getAttribute('name'),placeholder:x.getAttribute('placeholder'),value:(x.getAttribute('type')==='password'||x.getAttribute('name')==='username')?'REDACTED':x.getAttribute('value'),text:(x.innerText||x.textContent||'').trim()})).slice(0,30)).catch(()=>[]);}
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext();const p=await ctx.newPage();
try{
  await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(900);
  const ident=p.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  if(!(await ident.waitFor({state:'visible',timeout:10000}).then(()=>true).catch(()=>false))){safe.status='username_missing';safe.detail=JSON.stringify(await controls(p));save();process.exit(0);}
  await ident.fill(state.username||state.email);safe.firstStage=true;
  const c1=p.locator('input[type=submit]').first();
  if(await c1.count()&&await c1.isVisible().catch(()=>false)) await c1.click(); else await ident.press('Enter');
  const pass=p.locator('input[type=password]').first();
  if(!(await pass.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false))){safe.status='password_missing';safe.detail='url='+p.url()+' controls='+JSON.stringify(await controls(p))+' body='+(await body(p)).slice(0,600);save();process.exit(0);}
  safe.passwordStage=true;await pass.fill(state.password);
  const all=await controls(p);
  const submit=all.find(x=>x.type==='submit');safe.submitControl=submit?{tag:submit.tag,type:submit.type,name:submit.name,value:submit.value,text:submit.text}:null;
  const s=p.locator('input[type=submit]').first();
  if(await s.count()&&await s.isVisible().catch(()=>false)) await s.click();
  else {
    const b=p.locator('button').filter({hasText:/log in|sign in|continue/i}).first();
    if(await b.count()&&await b.isVisible().catch(()=>false)) await b.click(); else await pass.press('Enter');
  }
  await p.waitForTimeout(4000);
  const after=await body(p);
  safe.loginSuccess=!/\/login(?:[/?#]|$)/i.test(p.url())&&!/incorrect|invalid password|wrong password|authentication failed/i.test(after);
  if(!safe.loginSuccess){safe.status='login_rejected';safe.detail='url='+p.url()+' controls='+JSON.stringify(await controls(p))+' body='+after.slice(0,700);save();process.exit(0);}
  const dash=`https://wasmer.io/apps/${encodeURIComponent(state.username)}/${encodeURIComponent(state.appName)}`;
  await p.goto(dash,{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(1800);
  const db=await body(p);safe.dashboardSuccess=!/page requested does not exist|\b404\b/i.test(db)&&!/\/login(?:[/?#]|$)/i.test(p.url());
  safe.status=safe.dashboardSuccess?'dashboard_ready':'dashboard_failed';safe.detail='url='+p.url()+' body='+db.slice(0,800);save();
}catch(e){safe.status='error';safe.detail=String(e).slice(0,800);save();}finally{await browser.close();}
