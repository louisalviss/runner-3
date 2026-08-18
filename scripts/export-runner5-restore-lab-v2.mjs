import { chromium } from 'playwright-core';
import fs from 'fs';
import crypto from 'crypto';

const slug='runner5-restore-lab-1';
const site=JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`,'utf8'));
const account=JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const base=String(site.siteUrl||`https://${slug}.wasmer.app/`).replace(/\/$/,'');
const dashboard=site.dashboardUrl||`https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName||slug)}`;
const statusPath='/tmp/runner5-restore-lab-backup.json';
const backupPath='/tmp/runner5-restore-lab-before.wpress';
const safe={status:'starting',siteSlug:slug,siteUrl:base+'/',stage:'init',exportPage:false,exportStarted:false,downloadFound:false,backupBytes:0,sha256:null,artifactName:'runner5-restore-lab-before-wpress',detail:null,updatedAt:new Date().toISOString()};
const save=()=>{safe.updatedAt=new Date().toISOString();fs.writeFileSync(statusPath,JSON.stringify(safe,null,2));};
const stage=s=>{safe.stage=s;console.log('STAGE',s);save();};
const body=async p=>(await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();

async function loginWasmer(p){
  stage('wasmer_login');
  await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:45000});
  const i=p.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  await i.waitFor({state:'visible',timeout:12000}); await i.fill(account.username||account.email);
  const n=p.locator('button').filter({hasText:/continue|next|log in|sign in/i}).first();
  if(await n.count()&&await n.isVisible().catch(()=>false)) await n.click({noWaitAfter:true}); else await i.press('Enter');
  const pw=p.locator('input[type=password]').first(); await pw.waitFor({state:'visible',timeout:12000}); await pw.fill(account.password);
  const s=p.locator('button,input[type=submit]').filter({hasText:/continue|log in|sign in/i}).first();
  if(await s.count()&&await s.isVisible().catch(()=>false)) await s.click({noWaitAfter:true}); else await pw.press('Enter');
  await p.waitForTimeout(3500); if(/\/login(?:[/?#]|$)/i.test(p.url())) throw new Error('wasmer_login_failed');
}
async function pollAdmin(ctx,ms=22000){const end=Date.now()+ms;while(Date.now()<end){for(const p of ctx.pages()){const u=p.url();if(u.startsWith(base)&&/\/wp-admin(?:\/|\?|$)/i.test(u)&&!/wp-login\.php/i.test(u))return p;}await new Promise(r=>setTimeout(r,500));}return null;}
async function adminControl(p){const t=p.getByText(/WordPress Admin/i).first();if(!(await t.count())||!(await t.isVisible().catch(()=>false)))return null;const a=t.locator('xpath=ancestor-or-self::a[@href] | ancestor-or-self::button').first();return await a.count()?a:t;}
async function enterAdmin(ctx,p){
  stage('wordpress_admin');
  for(let k=0;k<2;k++){
    await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:45000});await p.waitForTimeout(1300);let c=await adminControl(p);
    if(!c){const st=p.getByText(/^Settings$/i).first();if(await st.count()&&await st.isVisible().catch(()=>false)){await st.click({noWaitAfter:true}).catch(()=>{});await p.waitForTimeout(700);const w=p.getByText(/^WordPress$/i).first();if(await w.count()&&await w.isVisible().catch(()=>false)){await w.click({noWaitAfter:true}).catch(()=>{});await p.waitForTimeout(900);}c=await adminControl(p);}}
    if(c){const href=await c.getAttribute('href').catch(()=>null);if(href){const wp=await ctx.newPage();await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null);const f=await pollAdmin(ctx,15000);if(f)return f;await wp.close().catch(()=>{});}await c.click({noWaitAfter:true}).catch(()=>{});const f=await pollAdmin(ctx,18000);if(f)return f;}
  }
  throw new Error('magic_admin_failed');
}
async function findVisible(page,re){const q=page.locator('button:visible,a:visible,input[type=submit]:visible,[role=button]:visible');for(let i=0;i<await q.count();i++){const el=q.nth(i);const t=((await el.innerText().catch(()=>''))||(await el.getAttribute('value').catch(()=>''))||'').replace(/\s+/g,' ').trim();if(re.test(t))return el;}return null;}
async function downloadHref(page){const links=page.locator('a[href]');for(let i=0;i<await links.count();i++){const a=links.nth(i);const href=await a.getAttribute('href').catch(()=>null);const t=(await a.innerText().catch(()=> '')).trim();if(!href||href==='#'||/^javascript:/i.test(href))continue;if(/\.wpress(?:\?|$)/i.test(href)||/Download/i.test(t)||/ai1wm.*(?:backup|download)|(?:backup|download).*ai1wm/i.test(href))return new URL(href,base).href;}return null;}
function finalizeBuffer(buf){if(buf.length<1024)throw new Error(`backup_too_small:${buf.length}`);fs.writeFileSync(backupPath,buf,{mode:0o600});safe.backupBytes=buf.length;safe.sha256=crypto.createHash('sha256').update(buf).digest('hex');safe.status='BACKUP_READY';safe.stage='complete';safe.downloadFound=true;save();console.log(`BACKUP_READY bytes=${buf.length} sha256=${safe.sha256}`);}
async function fetchBackup(href){stage('download_backup');console.log('backup href detected; URL intentionally not persisted');const r=await ctx.request.get(href,{timeout:120000,failOnStatusCode:false});if(!r.ok())throw new Error(`backup_download_http_${r.status()}`);finalizeBuffer(await r.body());}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({ignoreHTTPSErrors:true,acceptDownloads:true});const p=await ctx.newPage();
try{
  save();await loginWasmer(p);const wp=await enterAdmin(ctx,p);
  stage('open_export');await wp.goto(`${base}/wp-admin/admin.php?page=ai1wm_export`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1800);
  const t=await body(wp);console.log('EXPORT PAGE',t.slice(0,1600));
  if(/not allowed|do not have access|insufficient permissions/i.test(t))throw new Error('export_page_permission_denied');
  if(!/EXPORT SITE TO/i.test(t))throw new Error(`export_site_to_missing:${t.slice(0,700)}`);
  safe.exportPage=true;save();
  stage('start_export');
  let file=await findVisible(wp,/^FILE$/i);
  if(!file){const exact=wp.getByText(/^FILE$/i).first();if(await exact.count()&&await exact.isVisible().catch(()=>false))file=exact;}
  if(!file)throw new Error(`file_export_control_missing:${(await body(wp)).slice(0,1000)}`);
  await file.click({force:true,noWaitAfter:true});safe.exportStarted=true;save();

  // First allow the export UI to expose a direct link, but do not wait forever.
  stage('wait_export');let href=null;const directEnd=Date.now()+75*1000;
  while(Date.now()<directEnd){href=await downloadHref(wp);if(href)break;const bt=await body(wp);if(/unable to export|export failed|out of disk|not enough space|permission denied|critical error/i.test(bt))throw new Error(`export_failed:${bt.slice(-900)}`);await wp.waitForTimeout(1800);}
  if(href){await fetchBackup(href);}
  else {
    // AI1WM can finish FILE export without leaving a usable link on the export screen.
    // Poll its Backups page and retrieve the newest generated archive there.
    stage('backups_fallback');
    const end=Date.now()+4*60*1000;
    let got=false;
    while(Date.now()<end&&!got){
      await wp.goto(`${base}/wp-admin/admin.php?page=ai1wm_backups`,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>null);
      await wp.waitForTimeout(1400);
      const bt=await body(wp);console.log('BACKUPS PAGE',bt.slice(0,1200));
      href=await downloadHref(wp);
      if(href){await fetchBackup(href);got=true;break;}
      const dl=await findVisible(wp,/Download/i);
      if(dl){
        const dp=wp.waitForEvent('download',{timeout:15000}).catch(()=>null);
        await dl.click({force:true,noWaitAfter:true}).catch(()=>{});
        const d=await dp;
        if(d){await d.saveAs(backupPath);const buf=fs.readFileSync(backupPath);finalizeBuffer(buf);got=true;break;}
      }
      if(/no backups|no backup/i.test(bt))await wp.waitForTimeout(2500);else await wp.waitForTimeout(1800);
    }
    if(!got)throw new Error(`backup_not_found_on_backups_page:${(await body(wp)).slice(-1400)}`);
  }
}catch(e){safe.status='FAILED';safe.detail=String(e?.message||e);save();console.error(e);process.exitCode=1;}finally{await browser.close().catch(()=>{});}
