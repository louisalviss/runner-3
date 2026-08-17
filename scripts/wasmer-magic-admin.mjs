import { chromium } from 'playwright-core';
import fs from 'fs';

const state=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const base=(state.siteUrl||'').replace(/\/$/,'');
const safe={status:'starting',siteUrl:state.siteUrl||null,appName:state.appName||null,wasmerLogin:false,appDashboard:false,magicAdmin:false,themeInstalled:false,themeActive:false,detail:null,updatedAt:new Date().toISOString()};
function save(){safe.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-magic-status.json',JSON.stringify(safe,null,2));fs.writeFileSync('/tmp/wasmer-result.json',JSON.stringify(state,null,2));}
async function bt(page){return (await page.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function snapshot(page,label){
  const body=(await bt(page)).slice(0,1000);
  const buttons=await page.locator('button').evaluateAll(bs=>bs.map(b=>(b.innerText||b.textContent||'').replace(/\s+/g,' ').trim()).filter(Boolean).slice(0,40)).catch(()=>[]);
  const links=await page.locator('a').evaluateAll(as=>as.map(a=>({t:(a.innerText||a.textContent||'').replace(/\s+/g,' ').trim(),h:a.href})).filter(x=>x.t||x.h).slice(0,80)).catch(()=>[]);
  const scrub=u=>String(u||'').replace(/([?&](?:magiclogin|token|key|secret|password)=)[^&#]+/ig,'$1REDACTED');
  return `${label} url=${scrub(page.url())} buttons=${JSON.stringify(buttons)} links=${JSON.stringify(links.filter(x=>/wordpress|admin|manage|settings|dashboard|app/i.test(x.t+' '+x.h)).map(x=>({t:x.t.slice(0,90),h:scrub(x.h)})).slice(0,25))} body=${body}`;
}
async function loginWasmer(page){
  await page.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1000);
  const ident=page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  if(!(await ident.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false))) return {ok:false,stage:'username_field_missing'};
  await ident.fill(state.username||state.email);
  const next=page.locator('button').filter({hasText:/continue|next|log in|sign in/i}).first();
  if(await next.count()&&await next.isVisible().catch(()=>false)) await next.click(); else await ident.press('Enter');
  const pass=page.locator('input[type=password]').first();
  if(!(await pass.waitFor({state:'visible',timeout:15000}).then(()=>true).catch(()=>false))) return {ok:false,stage:'password_field_missing'};
  await pass.fill(state.password);
  const submit=page.locator('button').filter({hasText:/log in|sign in|continue/i}).first();
  if(await submit.count()&&await submit.isVisible().catch(()=>false)) await submit.click(); else await pass.press('Enter');
  await Promise.race([
    page.waitForURL(u=>!/\/login(?:[/?#]|$)/i.test(u.toString()),{timeout:15000}).catch(()=>null),
    page.waitForTimeout(5000)
  ]);
  const body=await bt(page);
  const ok=!/\/login(?:[/?#]|$)/i.test(page.url()) && !/incorrect|invalid password|wrong password|authentication failed/i.test(body);
  return {ok,stage:ok?'done':'rejected'};
}
async function findAppDashboard(page){
  const dashboard=`https://wasmer.io/apps/${encodeURIComponent(state.username)}/${encodeURIComponent(state.appName)}`;
  await page.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(2200);
  const body=await bt(page);
  if(/page requested does not exist|\b404\b/i.test(body)) return false;
  if(/\/login(?:[/?#]|$)/i.test(page.url())) return false;
  return body.includes(state.appName)||/settings|deployments|logs|wordpress|domains|databases/i.test(body);
}
async function enterWpAdminViaWasmer(page){
  for(let round=0;round<6;round++){
    const links=await page.locator('a').evaluateAll(as=>as.map(a=>({t:(a.innerText||a.textContent||'').replace(/\s+/g,' ').trim(),h:a.href}))).catch(()=>[]);
    const direct=links.find(x=>/magiclogin=/i.test(x.h)||(/wp-admin/i.test(x.h)&&x.h.startsWith(base))||/wordpress admin|wp admin|open admin|admin dashboard/i.test(x.t));
    if(direct){
      await page.goto(direct.h,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>null);
      await page.waitForTimeout(1800);
      if(page.url().startsWith(base)&&/wp-admin/i.test(page.url())) return true;
    }

    const body=await bt(page);
    const wpSetting=page.locator('button,a').filter({hasText:/wordpress/i}).first();
    if(await wpSetting.count()&&await wpSetting.isVisible().catch(()=>false)){
      await wpSetting.click().catch(()=>{});
      await page.waitForTimeout(1600);
      if(page.url().startsWith(base)&&/wp-admin/i.test(page.url())) return true;
      continue;
    }
    const settings=page.locator('button,a').filter({hasText:/^settings$/i}).first();
    if(await settings.count()&&await settings.isVisible().catch(()=>false) && !/wordpress/i.test(body)){
      await settings.click().catch(()=>{});
      await page.waitForTimeout(1400);
      continue;
    }
    break;
  }
  return false;
}
async function installTheme(page){
  if(!page.url().startsWith(base)||!/wp-admin/i.test(page.url())){
    await page.goto(base+'/wp-admin/',{waitUntil:'domcontentloaded',timeout:60000});
    await page.waitForTimeout(1200);
  }
  if(/wp-login\.php/i.test(page.url())) return {installed:false,active:false,why:'wordpress_session_missing'};
  await page.goto(base+'/wp-admin/theme-install.php?upload',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1200);
  if(/wp-login\.php/i.test(page.url())) return {installed:false,active:false,why:'wordpress_session_lost'};
  let input=page.locator('input[type=file]').first();
  if(!(await input.count())){
    const upload=page.locator('button,a').filter({hasText:/upload theme/i}).first();
    if(await upload.count()) await upload.click().catch(()=>{});
    await page.waitForTimeout(600);
    input=page.locator('input[type=file]').first();
  }
  if(!(await input.count())) return {installed:false,active:false,why:'theme_upload_input_missing'};
  await input.setInputFiles('/tmp/runner3-starter.zip');
  const install=page.locator('input[type=submit],button').filter({hasText:/install now/i}).first();
  if(await install.count()) await install.click(); else await page.locator('input[type=submit]').first().click();
  await page.waitForTimeout(5000);
  let body=await bt(page);
  let installed=/successfully|installed successfully|theme installed|runner3/i.test(body);
  await page.goto(base+'/wp-admin/themes.php',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1200);
  const cards=page.locator('.theme');
  let active=false;
  for(let i=0;i<await cards.count();i++){
    const c=cards.nth(i);const t=await c.innerText().catch(()=> '');
    if(!/runner3 starter/i.test(t)) continue;
    installed=true;
    if(/active:/i.test(t)||/customize/i.test(t)){active=true;break;}
    const a=c.locator('a,button').filter({hasText:/activate/i}).first();
    if(await a.count()){await a.click().catch(()=>{});await page.waitForTimeout(1600);active=true;break;}
  }
  return {installed,active,why:null};
}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({ignoreHTTPSErrors:true});
const page=await ctx.newPage();
try{
  save();
  const l=await loginWasmer(page);
  if(!l.ok){safe.status='blocked_wasmer_login';safe.detail=await snapshot(page,l.stage);save();process.exit(0);}
  safe.wasmerLogin=true;save();
  if(!(await findAppDashboard(page))){safe.status='app_dashboard_not_found';safe.detail=await snapshot(page,'app_not_found');save();process.exit(0);}
  safe.appDashboard=true;save();
  const magic=await enterWpAdminViaWasmer(page);
  if(!magic){safe.status='magic_admin_control_not_found';safe.detail=await snapshot(page,'magic_admin_missing');save();process.exit(0);}
  safe.magicAdmin=true;save();
  const r=await installTheme(page);
  safe.themeInstalled=r.installed;safe.themeActive=r.active;
  if(!r.installed||!r.active){safe.status='theme_partial';safe.detail=r.why||await snapshot(page,'theme_partial');save();process.exit(0);}
  await page.goto(base+'/',{waitUntil:'domcontentloaded',timeout:60000});
  safe.status='ready';safe.detail=(await bt(page)).slice(0,400);save();
}catch(e){safe.status='error';safe.detail=String(e).slice(0,800);save();}
finally{await browser.close();}
