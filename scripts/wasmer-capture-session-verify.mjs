import { chromium } from 'playwright-core';
import fs from 'fs';
const state=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const out={status:'starting',attempts:0,login:false,dashboard:false,verificationOpened:false,verificationText:null,verificationControls:[],detail:null,updatedAt:new Date().toISOString()};
function save(){out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-session-verify.json',JSON.stringify(out,null,2));}
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function tryLogin(browser){
 const ctx=await browser.newContext();const p=await ctx.newPage();
 try{
  await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(900);
  const u=p.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  if(!(await u.waitFor({state:'visible',timeout:10000}).then(()=>true).catch(()=>false))){await ctx.close();return null;}
  await u.fill(state.username||state.email);await u.press('Enter');
  const pw=p.locator('input[type=password]').first();
  if(!(await pw.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false))){await ctx.close();return null;}
  await pw.fill(state.password);
  const sub=p.locator('input[type=submit]').first();
  if(await sub.count()&&await sub.isVisible().catch(()=>false))await sub.click();else await pw.press('Enter');
  await p.waitForTimeout(4500);
  const t=await body(p);
  if(/\/login(?:[/?#]|$)/i.test(p.url())||/incorrect|invalid password|wrong password|authentication failed/i.test(t)){await ctx.close();return null;}
  return {ctx,p};
 }catch{await ctx.close().catch(()=>{});return null;}
}
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});let sess=null;
try{
 for(let i=1;i<=3;i++){out.attempts=i;save();sess=await tryLogin(browser);if(sess)break;if(i<3)await new Promise(r=>setTimeout(r,15000));}
 if(!sess){out.status='login_unavailable';out.detail='Could not establish Wasmer session after controlled retries';save();process.exit(0);}
 const {ctx,p}=sess;out.login=true;await ctx.storageState({path:'/tmp/wasmer-browser-state.json'});save();
 const dash=`https://wasmer.io/apps/${encodeURIComponent(state.username)}/${encodeURIComponent(state.appName)}`;
 await p.goto(dash,{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(1600);
 const t=await body(p);if(/page requested does not exist|\b404\b/i.test(t)||/\/login(?:[/?#]|$)/i.test(p.url())){out.status='dashboard_failed';out.detail=t.slice(0,700);save();await ctx.close();process.exit(0);}out.dashboard=true;
 const verify=p.locator('button,a').filter({hasText:/Verify your account/i}).first();
 if(!(await verify.count())||!(await verify.isVisible().catch(()=>false))){out.status='verification_control_missing';out.detail=t.slice(0,900);save();await ctx.close();process.exit(0);}
 await verify.click();await p.waitForTimeout(1000);out.verificationOpened=true;
 const d=p.locator('[role=dialog]').last();const root=(await d.count()&&await d.isVisible().catch(()=>false))?d:p;
 out.verificationText=(await root.innerText().catch(()=>'' )).replace(/\s+/g,' ').replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'EMAIL_REDACTED').slice(0,1500);
 out.verificationControls=await root.locator('input,button,a').evaluateAll(xs=>xs.map(x=>{const type=x.getAttribute('type');const raw=(x.innerText||x.textContent||x.getAttribute('value')||'').replace(/\s+/g,' ').trim();return {tag:x.tagName.toLowerCase(),type,name:x.getAttribute('name'),placeholder:x.getAttribute('placeholder'),text:type==='email'?'EMAIL_REDACTED':raw.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'EMAIL_REDACTED')};}).filter(x=>x.text||x.placeholder||x.name).slice(0,40)).catch(()=>[]);
 out.status='verification_inspected';save();await ctx.close();
}catch(e){out.status='error';out.detail=String(e).slice(0,900);save();}finally{await browser.close();}
