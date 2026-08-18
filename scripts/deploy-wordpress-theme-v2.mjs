import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const statusFile = `ops/site-factory/${slug}.json`;
if (!fs.existsSync(statusFile)) throw new Error(`site factory state missing: ${statusFile}`);
if (!fs.existsSync('/tmp/wasmer-account.json')) throw new Error('decrypted Wasmer account state missing');
if (!fs.existsSync('/tmp/runner3-starter.zip')) throw new Error('theme zip missing');

const site = JSON.parse(fs.readFileSync(statusFile, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(site.siteUrl || '').replace(/\/$/, '');
const dashboard = site.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName)}`;
const safeOut = `/tmp/wp-theme-deploy-${slug}.json`;
const safe = { status:'starting', siteSlug:slug, siteUrl:base+'/', adminEntered:false, uploadStarted:false, replacedExisting:false, themeActive:false, homepageVerified:false, articleVerified:false, detail:null, updatedAt:new Date().toISOString() };
function save(){ safe.updatedAt=new Date().toISOString(); fs.writeFileSync(safeOut, JSON.stringify(safe,null,2)); }
async function txt(p){ return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim(); }
async function firstVisible(locator){ for(let i=0;i<await locator.count();i++) if(await locator.nth(i).isVisible().catch(()=>false)) return locator.nth(i); return null; }

async function loginWasmer(page){
  await page.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(800);
  const ident=page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  await ident.waitFor({state:'visible',timeout:12000});
  await ident.fill(account.username || account.email);
  let next=await firstVisible(page.locator('button').filter({hasText:/continue|next|log in|sign in/i}));
  if(next) await next.click(); else await ident.press('Enter');
  const pass=page.locator('input[type=password]').first();
  await pass.waitFor({state:'visible',timeout:12000});
  await pass.fill(account.password);
  let submit=await firstVisible(page.locator('input[type=submit],button').filter({hasText:/log in|sign in|continue/i}));
  if(submit) await submit.click(); else await pass.press('Enter');
  await page.waitForTimeout(4000);
  if(/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('wasmer_login_failed');
}

async function enterAdmin(ctx,page){
  const locations=[dashboard, `${dashboard}/settings/wordpress`];
  let admin=null;
  for(const url of locations){
    await page.goto(url,{waitUntil:'domcontentloaded',timeout:60000});
    await page.waitForTimeout(1200);
    admin=await firstVisible(page.locator('a,button').filter({hasText:/WordPress Admin/i}));
    if(admin) break;
  }
  if(!admin) throw new Error('wordpress_admin_control_missing');
  const href=await admin.getAttribute('href').catch(()=>null);
  if(href){
    const wp=await ctx.newPage();
    await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:60000});
    await wp.waitForTimeout(2500);
    if(wp.url().startsWith(base) && /wp-admin/i.test(wp.url())) return wp;
    await wp.close().catch(()=>{});
  }
  const before=new Set(ctx.pages());
  const popupPromise=ctx.waitForEvent('page',{timeout:10000}).catch(()=>null);
  await admin.click().catch(()=>{});
  const popup=await popupPromise;
  await page.waitForTimeout(3000);
  const candidates=[...ctx.pages().filter(p=>!before.has(p)),popup,page].filter(Boolean);
  for(const p of candidates) if(p.url().startsWith(base) && /wp-admin/i.test(p.url())) return p;
  throw new Error('magic_admin_failed');
}

async function deployZip(wp){
  await wp.goto(`${base}/wp-admin/theme-install.php`,{waitUntil:'domcontentloaded',timeout:60000});
  await wp.waitForTimeout(1000);
  if(/wp-login\.php/i.test(wp.url())) throw new Error('wp_session_lost');
  const uploadToggle=await firstVisible(wp.locator('button,a').filter({hasText:/Upload Theme/i}));
  if(uploadToggle){ await uploadToggle.click(); await wp.waitForTimeout(500); }
  const file=await firstVisible(wp.locator('input[type=file]'));
  if(!file) throw new Error('visible_theme_upload_input_missing');
  await file.setInputFiles('/tmp/runner3-starter.zip');
  const install=await firstVisible(wp.locator('#install-theme-submit,input[type=submit],button').filter({hasText:/Install Now/i}));
  if(!install) throw new Error('visible_install_theme_button_missing');
  safe.uploadStarted=true; save();
  await install.click();
  await wp.waitForTimeout(3500);
  let body=await txt(wp);
  if(/already installed|destination folder already exists|newer than the currently installed|same as the currently installed/i.test(body)){
    const overwriteLinks = wp.locator('a.update-from-upload-overwrite,a[href*="overwrite"],a[href*="update-theme"]');
    let href = null;
    for(let i=0;i<await overwriteLinks.count();i++){ href = await overwriteLinks.nth(i).getAttribute('href').catch(()=>null); if(href) break; }
    if(href){ await wp.goto(new URL(href, `${base}/wp-admin/`).href,{waitUntil:'domcontentloaded',timeout:60000}); }
    else {
      const replace=await firstVisible(wp.locator('button,input[type=submit]').filter({hasText:/Replace installed with uploaded|Replace current with uploaded|Replace current|Overwrite|Update Theme/i}));
      if(!replace) throw new Error('theme_exists_but_replace_target_missing');
      await replace.click();
    }
    safe.replacedExisting=true; save();
    await wp.waitForTimeout(4500);
    body=await txt(wp);
  }
  if(/theme installed successfully|theme updated successfully|successfully updated|updated successfully/i.test(body)){
    const activate=await firstVisible(wp.locator('a,button').filter({hasText:/^Activate$/i}));
    if(activate){ await activate.click(); await wp.waitForTimeout(1800); }
  }
  await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000});
  await wp.waitForTimeout(900);
  const cards=wp.locator('.theme');
  for(let i=0;i<await cards.count();i++){
    const c=cards.nth(i); const t=await c.innerText().catch(()=> '');
    if(/runner3 editorial|runner3 starter/i.test(t) && (/active:/i.test(t) || /customize/i.test(t))){ safe.themeActive=true; save(); return; }
  }
  throw new Error('theme_activation_unconfirmed');
}

async function publicVerify(ctx){
  const home=await ctx.request.get(base+'/',{timeout:15000,failOnStatusCode:false});
  const hb=await home.text();
  safe.homepageVerified=home.status()===200 && /OFFSET/i.test(hb) && /signal-stage/i.test(hb) && /what moves/i.test(hb) && /underneath/i.test(hb);
  const articleUrl=`${base}/2026/08/17/the-quiet-machines-running-the-city/`;
  const article=await ctx.request.get(articleUrl,{timeout:15000,failOnStatusCode:false});
  const ab=await article.text();
  safe.articleVerified=article.status()===200 && /The Quiet Machines Running the City/i.test(ab) && /article-shell/i.test(ab);
  save();
  if(!safe.homepageVerified) throw new Error(`homepage_verify_failed:${home.status()}`);
  if(!safe.articleVerified) throw new Error(`article_verify_failed:${article.status()}`);
}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({ignoreHTTPSErrors:true});
const page=await ctx.newPage();
try{
  save();
  await loginWasmer(page);
  const wp=await enterAdmin(ctx,page); safe.adminEntered=true; save();
  await deployZip(wp);
  await publicVerify(ctx);
  safe.status='live'; safe.detail=null; save();
  console.log(`WP_THEME_DEPLOY_OK site=${slug}`);
}catch(e){ safe.status='failed'; safe.detail=String(e?.message||e); save(); console.error(`WP_THEME_DEPLOY_FAILED ${safe.detail}`); process.exitCode=1; }
finally{ await browser.close().catch(()=>{}); }
