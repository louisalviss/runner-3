import { chromium } from 'playwright-core';
import fs from 'fs';
import crypto from 'crypto';

const state=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
if(!state.siteUrl) throw new Error('siteUrl missing from encrypted Wasmer state');
state.wordpress=state.wordpress||{};
const base=state.siteUrl.replace(/\/$/,'');
const safe={status:'starting',siteUrl:state.siteUrl,frontHttp:null,adminHttp:null,coreInstalled:null,adminLogin:null,themeInstalled:null,themeActive:null,detail:null,updatedAt:new Date().toISOString()};
function save(){safe.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wp-finalize-status.json',JSON.stringify(safe,null,2));fs.writeFileSync('/tmp/wasmer-result.json',JSON.stringify(state,null,2));}
async function bodyText(page){return (await page.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function code(request,url){const r=await request.get(url,{timeout:30000,failOnStatusCode:false}).catch(()=>null);return r?.status()||null;}
async function clickVisible(page,re){const b=page.locator('button,a,input[type=submit]').filter({hasText:re}).first();if(await b.count()&&await b.isVisible().catch(()=>false)){await b.click().catch(()=>{});return true;}return false;}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({ignoreHTTPSErrors:true});
const page=await ctx.newPage();
try{
  safe.frontHttp=await code(ctx.request,base+'/');
  safe.adminHttp=await code(ctx.request,base+'/wp-admin/');
  await page.goto(base+'/',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1200);
  let text=await bodyText(page);

  const installLike=/wp-admin\/install\.php/i.test(page.url()) || /information needed|five-minute wordpress installation|install wordpress/i.test(text);
  if(installLike){
    state.wordpress.adminUser=state.wordpress.adminUser||('runner3admin'+crypto.randomBytes(3).toString('hex'));
    state.wordpress.adminPassword=state.wordpress.adminPassword||crypto.randomBytes(30).toString('base64url');
    state.wordpress.adminEmail=state.wordpress.adminEmail||state.email;
    state.wordpress.siteTitle=state.wordpress.siteTitle||'Runner3 Site';

    const title=page.locator('input[name=weblog_title],input#weblog_title').first();
    const user=page.locator('input[name=user_name],input#user_login').first();
    const pass=page.locator('input[name=admin_password],input#pass1,input[type=password]').first();
    const email=page.locator('input[name=admin_email],input[type=email]').first();
    await title.waitFor({state:'visible',timeout:12000}).catch(()=>{});
    if(await title.count()) await title.fill(state.wordpress.siteTitle);
    if(await user.count()) await user.fill(state.wordpress.adminUser);
    if(await pass.count()) await pass.fill(state.wordpress.adminPassword);
    if(await email.count()) await email.fill(state.wordpress.adminEmail);
    const weak=page.locator('input[name=pw_weak]').first();
    if(await weak.count() && !(await weak.isChecked().catch(()=>false))) await weak.check().catch(()=>{});
    const submit=page.locator('input[type=submit],button').filter({hasText:/install wordpress/i}).first();
    if(await submit.count()) await submit.click(); else await page.locator('input[type=submit]').first().click();
    await page.waitForTimeout(3500);
    text=await bodyText(page);
    if(/success|wordpress has been installed|log in/i.test(text) || /wp-login\.php/i.test(page.url())) safe.coreInstalled=true;
    else {safe.coreInstalled=false;safe.detail='install_submit_unconfirmed url='+page.url()+' body='+text.slice(0,500);save();process.exit(0);}
  } else {
    safe.coreInstalled=true;
  }

  if(!state.wordpress.adminUser || !state.wordpress.adminPassword){
    safe.adminLogin=false;
    safe.detail='WordPress already installed but admin credentials are not present in encrypted state';
    save();
    process.exit(0);
  }

  await page.goto(base+'/wp-login.php',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(800);
  const loginUser=page.locator('input#user_login,input[name=log]').first();
  const loginPass=page.locator('input#user_pass,input[name=pwd],input[type=password]').first();
  if(!(await loginUser.count())||!(await loginPass.count())){
    if(/wp-admin/i.test(page.url())) safe.adminLogin=true;
    else {safe.adminLogin=false;safe.detail='wp-login form missing url='+page.url();save();process.exit(0);}
  } else {
    await loginUser.fill(state.wordpress.adminUser);
    await loginPass.fill(state.wordpress.adminPassword);
    const submit=page.locator('input#wp-submit,input[type=submit],button').first();
    await submit.click();
    await page.waitForTimeout(2200);
    safe.adminLogin=/wp-admin/i.test(page.url()) && !/wp-login/i.test(page.url());
    if(!safe.adminLogin){safe.detail='admin login failed url='+page.url()+' body='+(await bodyText(page)).slice(0,500);save();process.exit(0);}
  }

  await page.goto(base+'/wp-admin/theme-install.php?upload',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1200);
  let fileInput=page.locator('input[type=file]').first();
  if(!(await fileInput.count())){
    await clickVisible(page,/upload theme/i);
    await page.waitForTimeout(500);
    fileInput=page.locator('input[type=file]').first();
  }
  if(await fileInput.count()){
    await fileInput.setInputFiles('/tmp/runner3-starter.zip');
    const install=page.locator('input[type=submit],button').filter({hasText:/install now/i}).first();
    if(await install.count()) await install.click();
    else await page.locator('input[type=submit]').first().click();
    await page.waitForTimeout(5000);
    text=await bodyText(page);
    safe.themeInstalled=/successfully|installed successfully|theme installed/i.test(text) || /activate/i.test(text);
  } else {
    safe.themeInstalled=false;
  }

  await page.goto(base+'/wp-admin/themes.php',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1200);
  text=await bodyText(page);
  if(/runner3 starter/i.test(text)){
    const cards=page.locator('.theme');
    let activated=false;
    for(let i=0;i<await cards.count();i++){
      const c=cards.nth(i);
      const t=(await c.innerText().catch(()=>''));
      if(!/runner3 starter/i.test(t)) continue;
      if(/active:/i.test(t)||/customize/i.test(t)){activated=true;break;}
      const a=c.locator('a,button').filter({hasText:/activate/i}).first();
      if(await a.count()){await a.click().catch(()=>{});await page.waitForTimeout(1800);activated=true;break;}
    }
    safe.themeActive=activated;
    safe.themeInstalled=true;
  } else {
    safe.themeActive=false;
  }

  await page.goto(base+'/',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1000);
  text=await bodyText(page);
  safe.frontHttp=await code(ctx.request,base+'/');
  safe.status=(safe.coreInstalled&&safe.adminLogin&&safe.themeInstalled&&safe.themeActive&&safe.frontHttp&&safe.frontHttp<400)?'ready':'partial';
  if(safe.status==='partial'&&!safe.detail) safe.detail='front='+safe.frontHttp+' core='+safe.coreInstalled+' admin='+safe.adminLogin+' themeInstalled='+safe.themeInstalled+' themeActive='+safe.themeActive+' body='+text.slice(0,350);
  save();
}catch(e){safe.status='error';safe.detail=String(e).slice(0,900);save();}
finally{await browser.close();}
