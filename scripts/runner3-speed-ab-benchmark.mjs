import { chromium } from 'playwright-core';
import fs from 'fs';
import { execFileSync, spawnSync } from 'child_process';

const slug = process.env.WP_SITE_SLUG || 'runner5-restore-lab-1';
const zip = process.env.RUNNER3_PLUGIN_ZIP || '/tmp/runner3-speed.zip';
const state = JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const pluginSource = fs.readFileSync('wordpress/runner3-speed/runner3-speed.php', 'utf8');
const expectedVersion = (pluginSource.match(/\* Version:\s*([^\r\n]+)/i)?.[1] || '').trim();
const base = String(state.siteUrl || '').replace(/\/$/, '');
const dashboard = state.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(state.owner)}/${encodeURIComponent(state.appName)}`;
const out = '/tmp/runner3-speed-ab.json';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const median = values => { const a=[...values].filter(Number.isFinite).sort((x,y)=>x-y); if(!a.length)return null; const m=Math.floor(a.length/2); return a.length%2?a[m]:(a[m-1]+a[m])/2; };
const round = (v,n=1) => Number.isFinite(v) ? Number(v.toFixed(n)) : null;

async function login(page) {
  await page.goto('https://wasmer.io/login', { waitUntil:'domcontentloaded', timeout:60000 });
  const ident = page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  await ident.waitFor({ state:'visible', timeout:15000 });
  await ident.fill(account.username || account.email);
  const next = page.locator('button').filter({ hasText:/continue|next|log in|sign in/i }).first();
  if (await next.count() && await next.isVisible().catch(()=>false)) await next.click(); else await ident.press('Enter');
  const pass = page.locator('input[type=password]').first();
  await pass.waitFor({ state:'visible', timeout:15000 }); await pass.fill(account.password);
  const submit = page.locator('input[type=submit],button').filter({ hasText:/log in|sign in|continue/i }).first();
  if (await submit.count() && await submit.isVisible().catch(()=>false)) await submit.click(); else await pass.press('Enter');
  await sleep(2200); if (/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('wasmer_login_failed');
}

async function adminPage(ctx,page) {
  await page.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000}); await sleep(1000);
  const admin=page.getByText(/WordPress Admin/i).first(); if(!(await admin.count())) throw new Error('wordpress_admin_control_missing');
  const href=await admin.getAttribute('href').catch(()=>null);
  if(href){ const wp=await ctx.newPage(); await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:60000}); await sleep(1200); if(wp.url().startsWith(base)&&/wp-admin/i.test(wp.url()))return wp; await wp.close().catch(()=>{}); }
  const popupP=ctx.waitForEvent('page',{timeout:10000}).catch(()=>null); await admin.click(); const popup=await popupP; await sleep(1800);
  for(const p of [popup,...ctx.pages()].filter(Boolean)) if(p.url().startsWith(base)&&/wp-admin/i.test(p.url())) return p;
  throw new Error('magic_admin_failed');
}

async function row(wp){ await wp.goto(`${base}/wp-admin/plugins.php`,{waitUntil:'domcontentloaded',timeout:60000}); return wp.locator('tr[data-slug="runner3-speed"]').first(); }
async function install(wp){
  await row(wp);
  await wp.goto(`${base}/wp-admin/plugin-install.php?tab=upload`,{waitUntil:'domcontentloaded',timeout:60000});
  const input=wp.locator('input[type=file][name=pluginzip],input[type=file]').first(); await input.waitFor({state:'attached',timeout:15000}); await input.setInputFiles(zip);
  const btn=wp.locator('#install-plugin-submit').first(); if(!(await btn.count()))throw new Error('plugin_upload_submit_missing'); await btn.click({force:true}); await wp.waitForLoadState('domcontentloaded').catch(()=>{}); await sleep(1800);
  const replace=wp.locator('a,button,input[type=submit]').filter({hasText:/replace current with uploaded|replace current|overwrite/i}).first();
  if(await replace.count()){
    const href=await replace.getAttribute('href').catch(()=>null);
    if(href) await wp.goto(new URL(href,`${base}/wp-admin/`).href,{waitUntil:'domcontentloaded',timeout:60000});
    else { await replace.click({force:true}); await wp.waitForLoadState('domcontentloaded').catch(()=>{}); }
    await sleep(1800);
  }
  const r=await row(wp); if(!(await r.count()))throw new Error('runner3_speed_install_missing');
  if(expectedVersion){const text=await r.innerText();if(!text.includes(`Version ${expectedVersion}`))throw new Error(`plugin_version_mismatch:expected_${expectedVersion}`);}
}
async function activate(wp){let r=await row(wp);if(!/\bactive\b/.test(await r.getAttribute('class')||'')){const a=r.locator('a').filter({hasText:/^Activate$/i}).first();const href=await a.getAttribute('href');if(!href)throw new Error('activate_missing');await wp.goto(new URL(href,`${base}/wp-admin/`).href,{waitUntil:'domcontentloaded',timeout:60000});await sleep(800);r=await row(wp);}if(!/\bactive\b/.test(await r.getAttribute('class')||''))throw new Error('activate_failed');}
async function toggle(wp,want){
  await wp.goto(`${base}/wp-admin/options-general.php?page=runner3-speed`,{waitUntil:'domcontentloaded',timeout:60000}); const text=await wp.locator('body').innerText(); const on=/Performance\s*ON/i.test(text); if(on===want)return;
  const form=wp.locator('form').filter({has:wp.locator('input[name="action"][value="runner3_speed_toggle"]')}).first(); if(!(await form.count()))throw new Error('toggle_missing');
  await Promise.all([wp.waitForNavigation({waitUntil:'domcontentloaded',timeout:60000}).catch(()=>null),form.evaluate(el=>HTMLFormElement.prototype.submit.call(el))]); await sleep(900);
  const after=await wp.locator('body').innerText(); if(want&&!/Performance\s*ON/i.test(after))throw new Error(`turn_on_failed:${after.slice(0,300)}`); if(!want&&!/Performance\s*OFF/i.test(after))throw new Error('turn_off_failed');
}

function curlRuns(n=15){
  const rows=[];
  for(let i=0;i<n;i++){
    const raw=execFileSync('curl',['-L','-sS','-o','/dev/null','-w','%{http_code} %{time_starttransfer} %{time_total} %{size_download}',base+'/'],{encoding:'utf8'}).trim();
    const [code,ttfb,total,size]=raw.split(/\s+/); rows.push({code:Number(code),ttfbMs:Number(ttfb)*1000,totalMs:Number(total)*1000,size:Number(size)});
  }
  return {runs:rows,medianTtfbMs:round(median(rows.map(x=>x.ttfbMs))),medianTotalMs:round(median(rows.map(x=>x.totalMs))),medianBytes:round(median(rows.map(x=>x.size)),0)};
}

async function browserRuns(browser,n=7){
  const rows=[];
  for(let i=0;i<n;i++){
    const ctx=await browser.newContext({ignoreHTTPSErrors:true}); const page=await ctx.newPage();
    const cdp=await ctx.newCDPSession(page); await cdp.send('Network.enable'); await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});
    await page.addInitScript(()=>{window.__runner3Lcp=0;window.__runner3Cls=0;new PerformanceObserver(list=>{for(const e of list.getEntries())window.__runner3Lcp=Math.max(window.__runner3Lcp,e.startTime||0);}).observe({type:'largest-contentful-paint',buffered:true});new PerformanceObserver(list=>{for(const e of list.getEntries())if(!e.hadRecentInput)window.__runner3Cls+=e.value||0;}).observe({type:'layout-shift',buffered:true});});
    const started=Date.now(); const resp=await page.goto(base+'/',{waitUntil:'load',timeout:60000}); await sleep(600);
    const perf=await page.evaluate(()=>{const nav=performance.getEntriesByType('navigation')[0];const fcp=performance.getEntriesByName('first-contentful-paint')[0];return{ttfb:nav?.responseStart||0,domContentLoaded:nav?.domContentLoadedEventEnd||0,load:nav?.loadEventEnd||0,fcp:fcp?.startTime||0,lcp:window.__runner3Lcp||0,cls:window.__runner3Cls||0};});
    rows.push({status:resp?.status()||0,wallMs:Date.now()-started,...perf}); await ctx.close();
  }
  const pick=k=>round(median(rows.map(x=>Number(x[k]))),k==='cls'?3:1);
  return {runs:rows,medianTtfbMs:pick('ttfb'),medianFcpMs:pick('fcp'),medianLcpMs:pick('lcp'),medianCls:pick('cls'),medianDclMs:pick('domContentLoaded'),medianLoadMs:pick('load'),medianWallMs:pick('wallMs')};
}

function lighthouseRuns(label,n=3){
  const rows=[];
  for(let i=0;i<n;i++){
    const file=`/tmp/lh-${label}-${i}.json`;
    const p=spawnSync('npx',['lighthouse',base+'/', '--quiet','--chrome-flags=--headless --no-sandbox','--form-factor=mobile','--only-categories=performance','--output=json',`--output-path=${file}`],{encoding:'utf8',timeout:180000});
    if(p.status!==0) throw new Error(`lighthouse_${label}_${i}_failed:${(p.stderr||p.stdout||'').slice(-500)}`);
    const j=JSON.parse(fs.readFileSync(file,'utf8')); const a=j.audits||{};
    rows.push({score:Math.round((j.categories?.performance?.score||0)*100),fcp:a['first-contentful-paint']?.numericValue||null,lcp:a['largest-contentful-paint']?.numericValue||null,si:a['speed-index']?.numericValue||null,tbt:a['total-blocking-time']?.numericValue||null,cls:a['cumulative-layout-shift']?.numericValue||null,ttfb:a['server-response-time']?.numericValue||null});
  }
  const pick=k=>round(median(rows.map(x=>Number(x[k]))),k==='score'?0:k==='cls'?3:1);
  return {runs:rows,medianScore:pick('score'),medianFcpMs:pick('fcp'),medianLcpMs:pick('lcp'),medianSpeedIndexMs:pick('si'),medianTbtMs:pick('tbt'),medianCls:pick('cls'),medianServerResponseMs:pick('ttfb')};
}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']}); const adminCtx=await browser.newContext({ignoreHTTPSErrors:true}); const page=await adminCtx.newPage(); let wp;
const report={status:'starting',site:slug,url:base,pluginVersion:expectedVersion,cloudflare:false,baseline:null,optimized:null,delta:null,checkedAt:null};
try{
  await login(page); wp=await adminPage(adminCtx,page); await install(wp); await activate(wp); await toggle(wp,false); await sleep(1500);
  const headers=execFileSync('curl',['-sSI',base+'/'],{encoding:'utf8'}); report.cloudflare=/^cf-ray:/im.test(headers); report.responseHeaders=headers.split(/\r?\n/).filter(x=>/^(server|cf-ray|x-runner3-speed|via|x-powered-by):/i.test(x));
  report.baseline={curl:curlRuns(15),browser:await browserRuns(browser,7),lighthouse:lighthouseRuns('off',3)};
  await toggle(wp,true); await fetch(base+'/'); await fetch(base+'/'); await sleep(800); const warm=await fetch(base+'/'); if(warm.headers.get('x-runner3-speed')!=='HIT')throw new Error('optimized_cache_not_hit');
  report.optimized={curl:curlRuns(15),browser:await browserRuns(browser,7),lighthouse:lighthouseRuns('on',3)};
  const b=report.baseline,o=report.optimized;
  report.delta={curlTtfbMs:round(o.curl.medianTtfbMs-b.curl.medianTtfbMs),curlTtfbPct:round((o.curl.medianTtfbMs/b.curl.medianTtfbMs-1)*100),browserTtfbMs:round(o.browser.medianTtfbMs-b.browser.medianTtfbMs),browserTtfbPct:round((o.browser.medianTtfbMs/b.browser.medianTtfbMs-1)*100),browserFcpMs:round(o.browser.medianFcpMs-b.browser.medianFcpMs),browserLcpMs:round(o.browser.medianLcpMs-b.browser.medianLcpMs),browserCls:round(o.browser.medianCls-b.browser.medianCls,3),browserLoadMs:round(o.browser.medianLoadMs-b.browser.medianLoadMs),lighthouseScore:round(o.lighthouse.medianScore-b.lighthouse.medianScore,0),lighthouseFcpMs:round(o.lighthouse.medianFcpMs-b.lighthouse.medianFcpMs),lighthouseLcpMs:round(o.lighthouse.medianLcpMs-b.lighthouse.medianLcpMs),lighthouseCls:round(o.lighthouse.medianCls-b.lighthouse.medianCls,3),lighthouseServerResponseMs:round(o.lighthouse.medianServerResponseMs-b.lighthouse.medianServerResponseMs)};
  report.status='ready'; report.checkedAt=new Date().toISOString(); fs.writeFileSync(out,JSON.stringify(report,null,2)+'\n'); console.log('RUNNER3_SPEED_AB_RESULT'); console.log(JSON.stringify(report,null,2));
}catch(e){report.status='failed';report.error=String(e?.message||e);report.checkedAt=new Date().toISOString();fs.writeFileSync(out,JSON.stringify(report,null,2)+'\n');console.error(JSON.stringify(report,null,2));process.exitCode=1;}finally{if(wp)await toggle(wp,false).catch(()=>{});await adminCtx.close().catch(()=>{});await browser.close().catch(()=>{});}
