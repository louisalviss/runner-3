import { chromium } from 'playwright-core';
import fs from 'fs';

const account=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const storage=JSON.parse(fs.readFileSync('/tmp/wasmer-browser-state.json','utf8'));
const base=(account.siteUrl||'').replace(/\/$/,'');
const baseHost=(()=>{try{return new URL(base).host}catch{return ''}})();
const out={status:'starting',dashboard:false,wordpressAdmin:false,themeInstalled:false,themeActive:false,frontHttp:null,adminControl:null,pageUrls:[],detail:null,updatedAt:new Date().toISOString()};
function save(){out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-session-theme.json',JSON.stringify(out,null,2));}
function safeUrl(s=''){
  try{const u=new URL(s);for(const k of [...u.searchParams.keys()]){if(/token|magic|key|code|secret|auth|signature/i.test(k))u.searchParams.set(k,'REDACTED');}return u.toString();}
  catch{return String(s).replace(/([?&](?:token|magiclogin|key|code|secret|auth|signature)=)[^&\s"']+/ig,'$1REDACTED').slice(0,500)}
}
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
  if(await a.count()&&await a.isVisible().catch(()=>false)){await a.click();await p.waitForTimeout(1800);out.themeActive=true;return true;}
  return false;
}
async function wpAdminPage(ctx){
  // First inspect any page already handed off by Wasmer.
  for(const p of ctx.pages()){
    try{if(new URL(p.url()).host===baseHost)return p;}catch{}
  }
  // A magic-login request may have set cookies without leaving a page behind.
  const p=await ctx.newPage();
  await p.goto(base+'/wp-admin/',{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>null);
  await p.waitForTimeout(1200);
  if(!/wp-login\.php/i.test(p.url()))return p;
  return null;
}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({storageState:storage,ignoreHTTPSErrors:true});
const dashPage=await ctx.newPage();
try{
  const dashboard=`https://wasmer.io/apps/${encodeURIComponent(account.username)}/${encodeURIComponent(account.appName)}`;
  await dashPage.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000});await dashPage.waitForTimeout(1400);
  const dtext=await text(dashPage);
  if(/\/login(?:[/?#]|$)/i.test(dashPage.url())||/page requested does not exist|\b404\b/i.test(dtext)){out.status='session_expired';out.detail='Stored Wasmer session no longer reaches app dashboard';save();process.exit(0);}
  out.dashboard=true;

  const admin=dashPage.locator('a,button').filter({hasText:/WordPress Admin/i}).first();
  if(!(await admin.count())||!(await admin.isVisible().catch(()=>false))){out.status='admin_control_missing';out.detail=dtext.slice(0,800);save();process.exit(0);}
  const href=await admin.getAttribute('href');
  const tag=await admin.evaluate(el=>el.tagName.toLowerCase()).catch(()=>null);
  const target=await admin.getAttribute('target');
  out.adminControl={tag,href:safeUrl(href||''),target};save();

  // Prefer visiting an anchor href directly: this reliably executes Wasmer's magic-login
  // redirect while preserving cookies in this browser context.
  if(href){
    const handoff=await ctx.newPage();
    await handoff.goto(href,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>null);
    await handoff.waitForTimeout(4000);
  }else{
    const popupPromise=ctx.waitForEvent('page',{timeout:6000}).catch(()=>null);
    await admin.click({noWaitAfter:true}).catch(()=>{});
    const popup=await popupPromise;
    if(popup){await popup.waitForLoadState('domcontentloaded',{timeout:30000}).catch(()=>{});await popup.waitForTimeout(2500);}
    else await dashPage.waitForTimeout(4000);
  }

  out.pageUrls=ctx.pages().map(p=>safeUrl(p.url()));save();
  let wp=await wpAdminPage(ctx);
  if(!wp){
    out.status='magic_admin_failed';
    out.detail='WordPress Admin handoff did not create an authenticated WordPress session';
    save();process.exit(0);
  }

  // Always test /wp-admin explicitly, even when Wasmer landed on the homepage.
  await wp.goto(base+'/wp-admin/',{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1200);
  if(/wp-login\.php/i.test(wp.url())){out.status='wp_session_missing';out.detail='Wasmer handoff reached site but WordPress still requested login';save();process.exit(0);}
  const wpText=await text(wp);
  if(!/dashboard|wordpress|wp-admin/i.test(wp.url()+' '+wpText)){out.status='wp_admin_unconfirmed';out.detail=wpText.slice(0,900);save();process.exit(0);}
  out.wordpressAdmin=true;

  await wp.goto(base+'/wp-admin/themes.php',{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1200);
  if(/wp-login\.php/i.test(wp.url())){out.status='wp_session_missing';out.detail='Authenticated WordPress session was not retained';save();process.exit(0);}
  if(await activateIfPresent(wp)){
    out.status='ready';
  }else{
    await wp.goto(base+'/wp-admin/theme-install.php?upload',{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1000);
    const toggle=wp.locator('.upload-view-toggle,button,a').filter({hasText:/Upload Theme/i}).first();
    if(await toggle.count()&&await toggle.isVisible().catch(()=>false)){await toggle.click().catch(()=>{});await wp.waitForTimeout(700);}
    const fi=wp.locator('#themezip,input[type=file]').first();
    if(!(await fi.count())){out.status='upload_input_missing';out.detail=(await text(wp)).slice(0,800);save();process.exit(0);}
    await fi.setInputFiles('/tmp/runner3-starter.zip');
    const install=wp.locator('#install-theme-submit,input[name=install-theme-submit],input[type=submit][value*="Install" i]').first();
    const visible=await install.waitFor({state:'visible',timeout:8000}).then(()=>true).catch(()=>false);
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
}catch(e){out.status='error';out.detail=String(e).replace(/([?&](?:token|magiclogin|key|code|secret|auth|signature)=)[^&\s"']+/ig,'$1REDACTED').slice(0,900);save();}
finally{await browser.close();}
