import { chromium } from 'playwright-core';
import fs from 'fs';
const state=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const base=state.siteUrl.replace(/\/$/,'');
const safe={status:'starting',wasmerLogin:false,dashboard:false,wordpressAdmin:false,themeInstalled:false,themeActive:false,detail:null,updatedAt:new Date().toISOString()};
function save(){safe.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-dashboard-theme.json',JSON.stringify(safe,null,2));}
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function login(p){
 await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(800);
 const u=p.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();if(!(await u.waitFor({state:'visible',timeout:10000}).then(()=>true).catch(()=>false))) return false;
 await u.fill(state.username||state.email);const s1=p.locator('input[type=submit]').first();if(await s1.count()&&await s1.isVisible().catch(()=>false))await s1.click();else await u.press('Enter');
 const pw=p.locator('input[type=password]').first();if(!(await pw.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false)))return false;
 await pw.fill(state.password);const s2=p.locator('input[type=submit]').first();if(await s2.count()&&await s2.isVisible().catch(()=>false))await s2.click();else await pw.press('Enter');
 await p.waitForTimeout(5000);return !/\/login(?:[/?#]|$)/i.test(p.url());
}
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});const ctx=await browser.newContext({ignoreHTTPSErrors:true});const p=await ctx.newPage();
try{
 if(!(await login(p))){safe.status='login_failed';safe.detail='url='+p.url()+' body='+(await body(p)).slice(0,500);save();process.exit(0);}safe.wasmerLogin=true;
 const dash=`https://wasmer.io/apps/${encodeURIComponent(state.username)}/${encodeURIComponent(state.appName)}`;await p.goto(dash,{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(1800);safe.dashboard=true;
 let admin=p.getByText(/WordPress Admin/i).first();if(!(await admin.count()))admin=p.locator('a,button').filter({hasText:/WordPress Admin/i}).first();
 if(!(await admin.count())){safe.status='admin_control_missing';safe.detail=(await body(p)).slice(0,900);save();process.exit(0);}
 await admin.click();
 await p.waitForTimeout(3500);
 if(!p.url().startsWith(base)||!/wp-admin/i.test(p.url())){
   // Some dashboard controls open a new tab.
   const pages=ctx.pages();const wp=pages.find(x=>x.url().startsWith(base)&&/wp-admin/i.test(x.url()));if(wp){await wp.bringToFront();}else{safe.status='magic_login_failed';safe.detail='url='+p.url()+' pages='+pages.map(x=>x.url().replace(/([?&]magiclogin=)[^&#]+/i,'$1REDACTED')).join(',');save();process.exit(0);}
 }
 const wp=ctx.pages().find(x=>x.url().startsWith(base)&&/wp-admin/i.test(x.url()))||p;safe.wordpressAdmin=true;
 await wp.goto(base+'/wp-admin/theme-install.php?upload',{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1200);
 let fi=wp.locator('input[type=file]').first();if(!(await fi.count())){const up=wp.locator('button,a').filter({hasText:/Upload Theme/i}).first();if(await up.count())await up.click();await wp.waitForTimeout(500);fi=wp.locator('input[type=file]').first();}
 if(!(await fi.count())){safe.status='upload_missing';safe.detail='url='+wp.url()+' body='+(await body(wp)).slice(0,700);save();process.exit(0);}
 await fi.setInputFiles('/tmp/runner3-starter.zip');let ins=wp.locator('input[type=submit]').first();if(await ins.count())await ins.click();else{ins=wp.locator('button').filter({hasText:/Install Now/i}).first();await ins.click();}
 await wp.waitForTimeout(5000);safe.themeInstalled=/successfully|installed|runner3/i.test(await body(wp));
 await wp.goto(base+'/wp-admin/themes.php',{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1200);const cards=wp.locator('.theme');
 for(let i=0;i<await cards.count();i++){const c=cards.nth(i);const t=await c.innerText().catch(()=> '');if(!/runner3 starter/i.test(t))continue;safe.themeInstalled=true;if(/active:/i.test(t)||/customize/i.test(t)){safe.themeActive=true;break;}const a=c.locator('a,button').filter({hasText:/Activate/i}).first();if(await a.count()){await a.click();await wp.waitForTimeout(1600);safe.themeActive=true;break;}}
 safe.status=safe.themeInstalled&&safe.themeActive?'ready':'theme_partial';safe.detail='front='+base;save();
}catch(e){safe.status='error';safe.detail=String(e).slice(0,800);save();}finally{await browser.close();}
