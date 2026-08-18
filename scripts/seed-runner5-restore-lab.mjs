import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = 'runner5-restore-lab-1';
const statePath = `ops/site-factory/${slug}.json`;
if (!fs.existsSync(statePath)) throw new Error(`missing ${statePath}`);
if (!fs.existsSync('/tmp/wasmer-account.json')) throw new Error('missing decrypted Wasmer account');
const site = JSON.parse(fs.readFileSync(statePath, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const base = String(site.siteUrl || `https://${slug}.wasmer.app/`).replace(/\/$/,'');
const dashboard = site.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName || slug)}`;
const out = '/tmp/runner5-restore-lab-seed.json';
const safe = {status:'starting',siteSlug:slug,siteUrl:base+'/',theme:'Inspiro',starterPlugin:'Inspiro Starter Sites',themeActive:false,starterPluginActive:false,importAttempted:false,importComplete:false,pages:0,posts:0,media:0,homepageHttp:null,steps:[],detail:null,updatedAt:new Date().toISOString()};
const save=()=>{safe.updatedAt=new Date().toISOString();fs.writeFileSync(out,JSON.stringify(safe,null,2));};
const step=(s)=>{safe.steps.push(s);console.log('STEP',s);save();};
const body=async p=>(await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();

async function loginWasmer(page){
  step('wasmer_login');
  await page.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});
  const ident=page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  await ident.waitFor({state:'visible',timeout:15000});
  await ident.fill(account.username||account.email);
  const next=page.locator('button').filter({hasText:/continue|next|log in|sign in/i}).first();
  if(await next.count()&&await next.isVisible().catch(()=>false)) await next.click(); else await ident.press('Enter');
  const pass=page.locator('input[type=password]').first();
  await pass.waitFor({state:'visible',timeout:15000});
  await pass.fill(account.password);
  const submit=page.locator('button,input[type=submit]').filter({hasText:/continue|log in|sign in/i}).first();
  if(await submit.count()&&await submit.isVisible().catch(()=>false)) await submit.click(); else await pass.press('Enter');
  await page.waitForTimeout(4000);
  if(/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('wasmer_login_failed');
}

async function findAdminControl(page){
  const textNode=page.getByText(/WordPress Admin/i).first();
  if(await textNode.count() && await textNode.isVisible().catch(()=>false)){
    const ancestor=textNode.locator('xpath=ancestor-or-self::a[@href] | ancestor-or-self::button').first();
    if(await ancestor.count()) return ancestor;
    return textNode;
  }
  return null;
}

async function pollWpAdmin(ctx, preferred=null, timeoutMs=30000){
  const deadline=Date.now()+timeoutMs;
  while(Date.now()<deadline){
    const pages=[preferred,...ctx.pages()].filter(Boolean);
    for(const p of pages){
      const u=p.url();
      if(u.startsWith(base) && /\/wp-admin(?:\/|\?|$)/i.test(u)) return p;
    }
    await new Promise(r=>setTimeout(r,600));
  }
  return null;
}

async function tryAdminFromCurrent(ctx,page){
  const admin=await findAdminControl(page);
  if(!admin) return null;
  const href=await admin.getAttribute('href').catch(()=>null);
  if(href){
    const magic=new URL(href,'https://wasmer.io').href;
    const wp=await ctx.newPage();
    await wp.goto(magic,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>null);
    const found=await pollWpAdmin(ctx,wp,20000);
    if(found) return found;
    await wp.close().catch(()=>{});
  }
  const before=new Set(ctx.pages());
  const popupPromise=ctx.waitForEvent('page',{timeout:12000}).catch(()=>null);
  await admin.click().catch(()=>{});
  const popup=await popupPromise;
  const candidate=await pollWpAdmin(ctx,popup||page,25000);
  if(candidate) return candidate;
  for(const p of ctx.pages().filter(p=>!before.has(p))) await p.close().catch(()=>{});
  return null;
}

async function enterAdmin(ctx,page){
  step('wordpress_admin');
  for(let attempt=1;attempt<=3;attempt++){
    console.log(`admin attempt ${attempt}`);
    await page.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000});
    await page.waitForTimeout(1600);
    let found=await tryAdminFromCurrent(ctx,page);
    if(found) return found;

    // Wasmer may expose the control under Settings -> WordPress instead of Overview.
    const settings=page.getByText(/^Settings$/i).first();
    if(await settings.count() && await settings.isVisible().catch(()=>false)){
      await settings.click().catch(()=>{});
      await page.waitForTimeout(1200);
      const wordpress=page.getByText(/^WordPress$/i).first();
      if(await wordpress.count() && await wordpress.isVisible().catch(()=>false)){
        await wordpress.click().catch(()=>{});
        await page.waitForTimeout(1400);
      }
      found=await tryAdminFromCurrent(ctx,page);
      if(found) return found;
    }

    // A magic-login click can set auth cookies even when navigation is slow; verify directly.
    const direct=await ctx.newPage();
    await direct.goto(`${base}/wp-admin/`,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>null);
    if(direct.url().startsWith(base) && /\/wp-admin(?:\/|\?|$)/i.test(direct.url()) && !/wp-login\.php/i.test(direct.url())) return direct;
    await direct.close().catch(()=>{});
    await page.waitForTimeout(1200);
  }
  const excerpt=(await body(page)).slice(0,700);
  console.log('dashboard excerpt',excerpt);
  throw new Error('magic_admin_failed');
}

async function uploadTheme(wp){
  step('install_inspiro_theme');
  await wp.goto(`${base}/wp-admin/theme-install.php?upload`,{waitUntil:'domcontentloaded',timeout:60000});
  await wp.waitForTimeout(800);
  if(/wp-login\.php/i.test(wp.url())) throw new Error('wp_session_lost_theme');
  let file=wp.locator('input[type=file]').first();
  if(!(await file.count())){const b=wp.getByText(/Upload Theme/i).first();if(await b.count())await b.click();await wp.waitForTimeout(400);file=wp.locator('input[type=file]').first();}
  if(!(await file.count())) throw new Error('theme_upload_input_missing');
  await file.setInputFiles('/tmp/inspiro.zip');
  let install=wp.locator('#install-theme-submit').first();
  if(!(await install.count())) install=wp.locator('input[type=submit],button').filter({hasText:/Install Now/i}).first();
  if(!(await install.count())) throw new Error('theme_install_button_missing');
  await install.click(); await wp.waitForTimeout(6000);
  let t=await body(wp);
  if(!/Theme installed successfully|already installed|destination folder already exists/i.test(t)) console.log('theme install body',t.slice(0,500));
  await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000}); await wp.waitForTimeout(1000);
  const cards=wp.locator('.theme'); let target=null;
  for(let i=0;i<await cards.count();i++){const c=cards.nth(i);if(/\bInspiro\b/i.test(await c.innerText().catch(()=>''))){target=c;break;}}
  if(!target) throw new Error('inspiro_theme_not_found');
  let txt=await target.innerText().catch(()=> '');
  if(!/Active:/i.test(txt)){const a=target.locator('a,button').filter({hasText:/^Activate$/i}).first();if(!(await a.count())) throw new Error('inspiro_activate_missing');await a.click();await wp.waitForTimeout(2500);}
  await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(700);
  safe.themeActive=/Inspiro/i.test(await wp.locator('.theme.active').first().innerText().catch(()=>''));save();
  if(!safe.themeActive) throw new Error('inspiro_activation_unconfirmed');
}

async function uploadPlugin(wp,zip,needle){
  step(`install_plugin_${needle}`);
  await wp.goto(`${base}/wp-admin/plugin-install.php?tab=upload`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(700);
  let file=wp.locator('input[type=file]').first(); if(!(await file.count())) throw new Error(`plugin_upload_missing:${needle}`);
  await file.setInputFiles(zip);
  let install=wp.locator('#install-plugin-submit').first();if(!(await install.count()))install=wp.locator('input[type=submit],button').filter({hasText:/Install Now/i}).first();
  if(!(await install.count())) throw new Error(`plugin_install_missing:${needle}`);
  await install.click();await wp.waitForTimeout(6000);
  let txt=await body(wp);
  if(/Activate Plugin/i.test(txt)){const a=wp.locator('a,button').filter({hasText:/Activate Plugin/i}).first();if(await a.count()){await a.click();await wp.waitForTimeout(2500);}}
  await wp.goto(`${base}/wp-admin/plugins.php`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(700);
  const rows=wp.locator('tr.active');let found=false;
  for(let i=0;i<await rows.count();i++){if(new RegExp(needle,'i').test(await rows.nth(i).innerText().catch(()=>''))){found=true;break;}}
  return found;
}

async function importDemo(wp){
  step('open_demo_importer');
  safe.importAttempted=true;save();
  await wp.goto(`${base}/wp-admin/admin.php?page=inspiro-demo`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(2500);
  let txt=await body(wp);
  if(/Default Starter Content Detected/i.test(txt)){
    const remove=wp.locator('button,a').filter({hasText:/Remove|Delete.*Starter Content/i}).first();
    if(await remove.count()&&await remove.isVisible().catch(()=>false)){await remove.click().catch(()=>{});await wp.waitForTimeout(1200);}
  }
  let card=wp.locator('[class*=demo],[class*=import],[class*=theme]').filter({hasText:/Business\s*\/\s*Portfolio/i}).first();
  if(!(await card.count())) card=wp.getByText(/Business\s*\/\s*Portfolio/i).first();
  if(!(await card.count())) throw new Error(`business_portfolio_demo_missing:${(await body(wp)).slice(0,600)}`);
  const within=card.locator('button,a').filter({hasText:/Select|Import Demo|Import|Choose/i}).first();
  if(await within.count()&&await within.isVisible().catch(()=>false)) await within.click(); else await card.click();
  await wp.waitForTimeout(1500);

  for(let round=0;round<50;round++){
    txt=await body(wp);
    if(/Demo Imported|Import Complete|Successfully Imported|Your site is ready|import has finished/i.test(txt)){safe.importComplete=true;save();break;}
    const candidates=[
      /Block Editor|Gutenberg/i,
      /Install\s*&\s*Activate|Install and Activate/i,
      /Continue|Next/i,
      /Import Demo Content/i,
      /Start Importing|Start Import/i,
      /^Import Demo$/i,
      /^Import$/i,
    ];
    let clicked=false;
    for(const re of candidates){
      const b=wp.locator('button,a,input[type=submit]').filter({hasText:re}).first();
      if(await b.count()&&await b.isVisible().catch(()=>false)&&await b.isEnabled().catch(()=>true)){
        console.log('click',re.toString(),(await b.innerText().catch(()=>'' )).slice(0,100));
        await b.click().catch(()=>{});clicked=true;await wp.waitForTimeout(/Start Import|Import Demo Content|^\/\^Import/.test(re.toString())?3500:1600);break;
      }
    }
    if(!clicked) await wp.waitForTimeout(1800);
  }
  txt=await body(wp);
  if(!safe.importComplete && /Demo Imported|Import Complete|Successfully Imported|Your site is ready/i.test(txt)) safe.importComplete=true;
  save();
}

async function restCount(path){const r=await fetch(`${base}${path}`,{headers:{Accept:'application/json'}});if(!r.ok)return {count:0,status:r.status};const j=await r.json();return {count:Array.isArray(j)?j.length:0,status:r.status};}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({ignoreHTTPSErrors:true});const page=await ctx.newPage();
try{
  save();await loginWasmer(page);const wp=await enterAdmin(ctx,page);await uploadTheme(wp);
  safe.starterPluginActive=await uploadPlugin(wp,'/tmp/inspiro-starter-sites.zip','Inspiro Starter Sites');save();
  if(!safe.starterPluginActive) throw new Error('starter_plugin_activation_unconfirmed');
  await importDemo(wp);
  step('verify_seed');
  const [pages,posts,media,home]=await Promise.all([restCount('/wp-json/wp/v2/pages?per_page=100&_fields=id'),restCount('/wp-json/wp/v2/posts?per_page=100&_fields=id'),restCount('/wp-json/wp/v2/media?per_page=100&_fields=id'),fetch(base+'/',{redirect:'follow'})]);
  safe.pages=pages.count;safe.posts=posts.count;safe.media=media.count;safe.homepageHttp=home.status;
  safe.status=(safe.themeActive&&safe.starterPluginActive&&safe.homepageHttp===200&&safe.pages>=2)?'SEEDED':'PARTIAL';
  if(!safe.importComplete && safe.pages>=2) safe.detail='demo_content_present_but_success_banner_not_detected';
  save();
}catch(e){safe.status='FAILED';safe.detail=String(e?.message||e);save();console.error(e);process.exitCode=1;}finally{await browser.close().catch(()=>{});}
