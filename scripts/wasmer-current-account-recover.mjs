import { chromium } from 'playwright-core';
import fs from 'fs';
const state=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const base=state.siteUrl.replace(/\/$/,'');
const safe={status:'starting',loginAttempts:0,wasmerLogin:false,dashboard:false,wordpressAdmin:false,themeInstalled:false,themeActive:false,verificationOpened:false,verificationControls:[],verificationText:null,detail:null,updatedAt:new Date().toISOString()};
function save(){safe.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-current-recover.json',JSON.stringify(safe,null,2));}
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function oneLogin(browser){
 const ctx=await browser.newContext({ignoreHTTPSErrors:true});const p=await ctx.newPage();
 try{
  await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(900);
  const u=p.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();if(!(await u.waitFor({state:'visible',timeout:10000}).then(()=>true).catch(()=>false))){await ctx.close();return null;}
  await u.fill(state.username||state.email);const f1=p.locator('form').first();await u.press('Enter').catch(()=>{});
  const pw=p.locator('input[type=password]').first();if(!(await pw.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false))){await ctx.close();return null;}
  await pw.fill(state.password);const submit=p.locator('input[type=submit]').first();if(await submit.count()&&await submit.isVisible().catch(()=>false))await submit.click();else await pw.press('Enter').catch(()=>{});
  await p.waitForTimeout(6500);const t=await body(p);if(/\/login(?:[/?#]|$)/i.test(p.url())||/incorrect|invalid password|wrong password|authentication failed/i.test(t)){await ctx.close();return null;}
  return {ctx,p};
 }catch{await ctx.close().catch(()=>{});return null;}
}
async function installTheme(ctx,p){
 const dashboard=`https://wasmer.io/apps/${encodeURIComponent(state.username)}/${encodeURIComponent(state.appName)}`;await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(1800);safe.dashboard=true;
 const admin=p.getByText(/WordPress Admin/i).first();if(!(await admin.count()))return {ok:false,why:'WordPress Admin control missing'};
 const before=ctx.pages().length;await admin.click();await p.waitForTimeout(3800);
 let wp=ctx.pages().find(x=>x.url().startsWith(base)&&/wp-admin/i.test(x.url()));if(!wp&&p.url().startsWith(base)&&/wp-admin/i.test(p.url()))wp=p;
 if(!wp)return {ok:false,why:'Wasmer magic login did not reach wp-admin'};safe.wordpressAdmin=true;
 await wp.goto(base+'/wp-admin/theme-install.php?upload',{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1200);if(/wp-login\.php/i.test(wp.url()))return {ok:false,why:'WP session lost'};
 let fi=wp.locator('input[type=file]').first();if(!(await fi.count())){const up=wp.locator('button,a').filter({hasText:/Upload Theme/i}).first();if(await up.count())await up.click();await wp.waitForTimeout(500);fi=wp.locator('input[type=file]').first();}
 if(!(await fi.count()))return {ok:false,why:'theme upload input missing'};
 await fi.setInputFiles('/tmp/runner3-starter.zip');let ins=wp.locator('input[type=submit]').first();if(await ins.count())await ins.click();else{ins=wp.locator('button').filter({hasText:/Install Now/i}).first();if(await ins.count())await ins.click();}
 await wp.waitForTimeout(5000);safe.themeInstalled=/successfully|installed|runner3/i.test(await body(wp));
 await wp.goto(base+'/wp-admin/themes.php',{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1200);const cards=wp.locator('.theme');
 for(let i=0;i<await cards.count();i++){const c=cards.nth(i);const t=await c.innerText().catch(()=> '');if(!/runner3 starter/i.test(t))continue;safe.themeInstalled=true;if(/active:/i.test(t)||/customize/i.test(t)){safe.themeActive=true;break;}const a=c.locator('a,button').filter({hasText:/Activate/i}).first();if(await a.count()){await a.click();await wp.waitForTimeout(1600);safe.themeActive=true;break;}}
 if(wp!==p)await wp.close().catch(()=>{});
 await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(1500);return {ok:true,why:null};
}
async function inspectVerification(p){
 const verify=p.locator('button,a').filter({hasText:/Verify your account/i}).first();if(!(await verify.count()))return false;await verify.click();await p.waitForTimeout(1000);safe.verificationOpened=true;
 const dialog=p.locator('[role=dialog]').last();const root=(await dialog.count()&&await dialog.isVisible().catch(()=>false))?dialog:p;
 safe.verificationText=(await root.innerText().catch(()=>'' )).replace(/\s+/g,' ').slice(0,1200).replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'EMAIL_REDACTED');
 safe.verificationControls=await root.locator('input,button,a').evaluateAll(xs=>xs.map(x=>({tag:x.tagName.toLowerCase(),type:x.getAttribute('type'),name:x.getAttribute('name'),placeholder:x.getAttribute('placeholder'),text:(x.innerText||x.textContent||x.getAttribute('value')||'').replace(/\s+/g,' ').trim()})).filter(x=>x.text||x.placeholder||x.name).slice(0,30)).catch(()=>[]);
 return true;
}
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});let session=null;
try{
 for(let i=1;i<=3;i++){safe.loginAttempts=i;save();session=await oneLogin(browser);if(session)break;if(i<3)await new Promise(r=>setTimeout(r,12000));}
 if(!session){safe.status='login_unavailable';safe.detail='Current Wasmer account login did not establish a session after controlled retries';save();process.exit(0);}
 safe.wasmerLogin=true;const {ctx,p}=session;save();
 const theme=await installTheme(ctx,p);if(!theme.ok)safe.detail=theme.why;
 await inspectVerification(p);
 safe.status=safe.themeInstalled&&safe.themeActive?'theme_ready_verification_pending':'verification_inspected';save();await ctx.close();
}catch(e){safe.status='error';safe.detail=String(e).slice(0,900);save();}finally{await browser.close();}
