import { chromium } from 'playwright-core';
import fs from 'fs';

const account=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const storage=JSON.parse(fs.readFileSync('/tmp/wasmer-browser-state.json','utf8'));
const base=(account.siteUrl||'').replace(/\/$/,'');
const out={status:'starting',dashboard:false,wordpressAdmin:false,themeInstalled:false,themeActive:false,frontHttp:null,detail:null,updatedAt:new Date().toISOString()};
function save(){out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-session-theme.json',JSON.stringify(out,null,2));}
async function text(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function runnerCard(p){
  const cards=p.locator('.theme');
  for(let i=0;i<await cards.count();i++){
    const c=cards.nth(i);const t=await c.innerText().catch(()=> '');
    if(/runner3 starter/i.test(t)) return c;
  }
  return null;
}
async function activateIfPresent(p){
  const card=await runnerCard(p);if(!card)return false;
  out.themeInstalled=true;
  const t=await card.innerText().catch(()=> '');
  if(/active:/i.test(t)||/customize/i.test(t)){out.themeActive=true;return true;}
  const a=card.locator('a,button').filter({hasText:/Activate/i}).first();
  if(await a.count()&&await a.isVisible().catch(()=>false)){await a.click();await p.waitForTimeout(1700);out.themeActive=true;return true;}
  return false;
}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({storageState:storage,ignoreHTTPSErrors:true});
const dashPage=await ctx.newPage();
try{
  const dashboard=`https://wasmer.io/apps/${encodeURIComponent(account.username)}/${encodeURIComponent(account.appName)}`;
  await dashPage.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000});await dashPage.waitForTimeout(1600);
  const dtext=await text(dashPage);
  if(/\/login(?:[/?#]|$)/i.test(dashPage.url())||/page requested does not exist|\b404\b/i.test(dtext)){out.status='session_expired';out.detail='Stored Wasmer session no longer reaches app dashboard';save();process.exit(0);}
  out.dashboard=true;

  const admin=dashPage.locator('a,button').filter({hasText:/WordPress Admin/i}).first();
  if(!(await admin.count())||!(await admin.isVisible().catch(()=>false))){out.status='admin_control_missing';out.detail=dtext.slice(0,800);save();process.exit(0);}
  const oldPages=ctx.pages().length;
  await admin.click();await dashPage.waitForTimeout(3500);
  let wp=ctx.pages().find(x=>x.url().startsWith(base)&&/wp-admin/i.test(x.url()));
  if(!wp&&dashPage.url().startsWith(base)&&/wp-admin/i.test(dashPage.url()))wp=dashPage;
  if(!wp){out.status='magic_admin_failed';out.detail='WordPress Admin control did not establish wp-admin session';save();process.exit(0);}
  out.wordpressAdmin=true;

  await wp.goto(base+'/wp-admin/themes.php',{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1200);
  if(/wp-login\.php/i.test(wp.url())){out.status='wp_session_missing';out.detail='Wasmer magic admin session was not retained';save();process.exit(0);}
  if(await activateIfPresent(wp)){
    out.status='ready';
  }else{
    await wp.goto(base+'/wp-admin/theme-install.php?upload',{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1000);
    const toggle=wp.locator('.upload-view-toggle,button').filter({hasText:/Upload Theme/i}).first();
    if(await toggle.count()&&await toggle.isVisible().catch(()=>false)){await toggle.click();await wp.waitForTimeout(700);}
    const fi=wp.locator('#themezip,input[type=file]').first();
    if(!(await fi.count())){out.status='upload_input_missing';out.detail=(await text(wp)).slice(0,800);save();process.exit(0);}
    await fi.setInputFiles('/tmp/runner3-starter.zip');
    const install=wp.locator('#install-theme-submit,input[name=install-theme-submit]').first();
    const visible=await install.waitFor({state:'visible',timeout:7000}).then(()=>true).catch(()=>false);
    if(!visible){out.status='install_button_hidden';out.detail=(await text(wp)).slice(0,800);save();process.exit(0);}
    await install.click();await wp.waitForTimeout(5500);
    const installText=await text(wp);
    if(/successfully|theme installed|runner3 starter/i.test(installText))out.themeInstalled=true;

    await wp.goto(base+'/wp-admin/themes.php',{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1200);
    await activateIfPresent(wp);
    out.status=out.themeInstalled&&out.themeActive?'ready':'theme_partial';
    if(out.status!=='ready')out.detail=(await text(wp)).slice(0,900);
  }

  const r=await ctx.request.get(base+'/',{timeout:30000,failOnStatusCode:false}).catch(()=>null);out.frontHttp=r?.status()||null;
  save();
}catch(e){out.status='error';out.detail=String(e).slice(0,900);save();}
finally{await browser.close();}
