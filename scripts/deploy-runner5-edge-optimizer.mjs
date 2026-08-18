import { chromium } from 'playwright-core';
import fs from 'node:fs';

const dashboard='https://wasmer.io/apps/runner3wp0b90f6b4ab/runner5-restore-lab-1';
const base='https://runner5-restore-lab-1.wasmer.app';
const zip='/tmp/runner5-edge-optimizer.zip';
const out='/tmp/runner5-optimizer-deploy.json';
const result={status:'FAILED',stage:'start',dashboard,base,detail:null,updatedAt:new Date().toISOString()};
function save(){result.updatedAt=new Date().toISOString();fs.writeFileSync(out,JSON.stringify(result,null,2)+'\n');}
function safe(v){return String(v??'').replace(/https?:\/\/[^\s]*?(?:token|magiclogin|secret|auth|signature)=[^\s&]+/ig,'[redacted-url]').slice(-5000);}
if(!fs.existsSync('/tmp/wasmer-browser-state.json')) throw new Error('browser state missing');
if(!fs.existsSync(zip)) throw new Error('plugin zip missing');

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
try{
  const ctx=await browser.newContext({storageState:'/tmp/wasmer-browser-state.json',ignoreHTTPSErrors:true});
  const page=await ctx.newPage();
  result.stage='dashboard'; save();
  await page.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000}); await page.waitForTimeout(1500);
  if(/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('stored_wasmer_session_expired');
  const admin=page.getByText(/WordPress Admin/i).first();
  if(!(await admin.count())) throw new Error('wordpress_admin_control_missing');
  result.stage='wp-admin'; save();
  let wp=null;
  const href=await admin.getAttribute('href').catch(()=>null);
  if(href){
    const p=await ctx.newPage();
    await p.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:60000}); await p.waitForTimeout(1800);
    if(p.url().startsWith(base) && /wp-admin/i.test(p.url())) wp=p; else await p.close().catch(()=>{});
  }
  if(!wp){
    const popupP=ctx.waitForEvent('page',{timeout:12000}).catch(()=>null); await admin.click();
    const popup=await popupP; await page.waitForTimeout(2200);
    for(const p of [popup,...ctx.pages()].filter(Boolean)){if(p.url().startsWith(base) && /wp-admin/i.test(p.url())){wp=p;break;}}
  }
  if(!wp) throw new Error('magic_admin_failed');
  result.wpAdminUrl=wp.url(); result.stage='upload'; save();
  await wp.goto(`${base}/wp-admin/plugin-install.php?tab=upload`,{waitUntil:'domcontentloaded',timeout:60000}); await wp.waitForTimeout(1000);
  let file=wp.locator('input[type=file][name=pluginzip],input[type=file]').first();
  if(!(await file.count())){
    const toggle=wp.getByRole('button',{name:/upload plugin/i}).first();
    if(await toggle.count()){await toggle.click();await wp.waitForTimeout(500);file=wp.locator('input[type=file][name=pluginzip],input[type=file]').first();}
  }
  if(!(await file.count())){
    result.pageText=(await wp.locator('body').innerText().catch(()=>'' )).slice(0,4000);
    throw new Error('plugin_upload_input_missing');
  }
  await file.setInputFiles(zip);
  const submit=wp.locator('input[type=submit][value*="Install" i],button:has-text("Install Now")').first();
  if(!(await submit.count())) throw new Error('plugin_install_submit_missing');
  await submit.click(); await wp.waitForLoadState('domcontentloaded').catch(()=>{}); await wp.waitForTimeout(1800);
  const replace=wp.locator('a').filter({hasText:/replace (current|installed).*uploaded/i}).first();
  if(await replace.count()){
    const rh=await replace.getAttribute('href'); if(rh){await wp.goto(new URL(rh,base).href,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1500);}
  }
  result.stage='activate'; save();
  await wp.goto(`${base}/wp-admin/plugins.php`,{waitUntil:'domcontentloaded',timeout:60000}); await wp.waitForTimeout(800);
  let row=wp.locator('tr[data-slug="runner5-edge-optimizer"]').first();
  if(!(await row.count())) throw new Error('plugin_row_missing_after_upload');
  let cls=await row.getAttribute('class')||'';
  if(!/\bactive\b/.test(cls)){
    const activate=row.locator('a').filter({hasText:/^activate$/i}).first();
    if(!(await activate.count())) throw new Error('plugin_activate_link_missing');
    const ah=await activate.getAttribute('href'); if(!ah) throw new Error('plugin_activate_href_missing');
    await wp.goto(new URL(ah,`${base}/wp-admin/`).href,{waitUntil:'domcontentloaded',timeout:60000}); await wp.waitForTimeout(1000);
    await wp.goto(`${base}/wp-admin/plugins.php`,{waitUntil:'domcontentloaded',timeout:60000}); row=wp.locator('tr[data-slug="runner5-edge-optimizer"]').first(); cls=await row.getAttribute('class')||'';
  }
  if(!/\bactive\b/.test(cls)) throw new Error('plugin_not_active');
  result.status='READY';result.stage='complete';result.active=true;result.detail=null;save();
  console.log(JSON.stringify(result,null,2));
}catch(e){result.detail=safe(e?.stack||e);save();console.error(JSON.stringify(result,null,2));process.exitCode=1;}finally{await browser.close().catch(()=>{});}
