import { chromium } from 'playwright-core';
import fs from 'fs';
import { execFileSync, spawnSync } from 'child_process';

const slug = process.env.WP_SITE_SLUG || 'runner3-speed-site3-realistic';
const state = JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(state.siteUrl || '').replace(/\/$/, '');
const dashboard = state.dashboardUrl;
const out = '/tmp/runner3-speed-site3-inspiro-a.json';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const median = xs => { const a=[...xs].filter(Number.isFinite).sort((x,y)=>x-y); if(!a.length)return null; const m=Math.floor(a.length/2); return a.length%2?a[m]:(a[m-1]+a[m])/2; };
const round = (v,n=1) => Number.isFinite(v) ? Number(v.toFixed(n)) : null;
const routes=['/','/about/','/projects/','/contact/','/blog/','/transforming-historic-buildings-for-modern-use/'];

async function login(page){
  for(let attempt=1;attempt<=3;attempt++){
    try{
      await page.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});
      if(!/\/login(?:[/?#]|$)/i.test(page.url())) return;
      const ident=page.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();
      await ident.waitFor({state:'visible',timeout:15000});
      await ident.fill(account.username||account.email); await ident.press('Enter');
      const pass=page.locator('input[type=password]').first(); await pass.waitFor({state:'visible',timeout:20000}); await pass.fill(account.password); await pass.press('Enter');
      await sleep(2200); if(!/\/login(?:[/?#]|$)/i.test(page.url())) return;
    }catch{}
    await sleep(1000*attempt);
  }
  throw new Error('wasmer_login_failed');
}

async function adminPage(ctx,page){
  await page.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000}); await sleep(900);
  const admin=page.getByText(/WordPress Admin/i).first(); if(!(await admin.count())) throw new Error('wordpress_admin_control_missing');
  const href=await admin.getAttribute('href').catch(()=>null);
  if(href){ const wp=await ctx.newPage(); await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:60000}); await sleep(1200); if(wp.url().startsWith(base)&&/wp-admin/i.test(wp.url())) return wp; }
  const pp=ctx.waitForEvent('page',{timeout:10000}).catch(()=>null); await admin.click().catch(()=>{}); const popup=await pp; await sleep(1600);
  for(const p of [popup,...ctx.pages()].filter(Boolean)) if(p.url().startsWith(base)&&/wp-admin/i.test(p.url())) return p;
  throw new Error('magic_admin_failed');
}

function curlRuns(n=15){
  const rows=[];
  for(let i=0;i<n;i++){
    const raw=execFileSync('curl',['-L','-sS','-D','-','-o','/dev/null','-w','\n__M__ %{http_code} %{time_starttransfer} %{time_total} %{size_download}',base+'/'],{encoding:'utf8'});
    const [head,m='']=raw.split('__M__'); const [code,ttfb,total,size]=m.trim().split(/\s+/);
    rows.push({code:Number(code),ttfbMs:Number(ttfb)*1000,totalMs:Number(total)*1000,size:Number(size),runner3:/^x-runner3-speed:/im.test(head)});
  }
  return {runs:rows,medianTtfbMs:round(median(rows.map(x=>x.ttfbMs))),medianTotalMs:round(median(rows.map(x=>x.totalMs))),medianBytes:round(median(rows.map(x=>x.size)),0)};
}

async function browserRuns(browser,n=7){
  const rows=[];
  for(let i=0;i<n;i++){
    const ctx=await browser.newContext({ignoreHTTPSErrors:true}); const page=await ctx.newPage(); const cdp=await ctx.newCDPSession(page);
    await cdp.send('Network.enable'); await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});
    await page.addInitScript(()=>{ window.__lcp=0;window.__cls=0; new PerformanceObserver(l=>{for(const e of l.getEntries())window.__lcp=Math.max(window.__lcp,e.startTime||0)}).observe({type:'largest-contentful-paint',buffered:true}); new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)window.__cls+=e.value||0}).observe({type:'layout-shift',buffered:true}); });
    const resp=await page.goto(base+'/',{waitUntil:'load',timeout:60000}); await sleep(800);
    const perf=await page.evaluate(()=>{const n=performance.getEntriesByType('navigation')[0],f=performance.getEntriesByName('first-contentful-paint')[0];return{ttfb:n?.responseStart||0,fcp:f?.startTime||0,lcp:window.__lcp||0,cls:window.__cls||0,load:n?.loadEventEnd||0}});
    rows.push({status:resp?.status()||0,...perf}); await ctx.close();
  }
  const pick=(k,d=1)=>round(median(rows.map(x=>Number(x[k]))),d);
  return {runs:rows,medianTtfbMs:pick('ttfb'),medianFcpMs:pick('fcp'),medianLcpMs:pick('lcp'),medianCls:pick('cls',3),medianLoadMs:pick('load')};
}

function lighthouseRuns(n=5){
  const rows=[];
  for(let i=0;i<n;i++){
    const file=`/tmp/lh-inspiro-a-${i}.json`; const p=spawnSync('npx',['lighthouse',base+'/', '--quiet','--chrome-flags=--headless --no-sandbox','--form-factor=mobile','--only-categories=performance','--output=json',`--output-path=${file}`],{encoding:'utf8',timeout:180000});
    if(p.status!==0) throw new Error(`lighthouse_a_${i}_failed:${(p.stderr||p.stdout||'').slice(-400)}`);
    const j=JSON.parse(fs.readFileSync(file,'utf8')),a=j.audits||{}; rows.push({score:Math.round((j.categories?.performance?.score||0)*100),fcp:a['first-contentful-paint']?.numericValue||null,lcp:a['largest-contentful-paint']?.numericValue||null,si:a['speed-index']?.numericValue||null,tbt:a['total-blocking-time']?.numericValue||null,cls:a['cumulative-layout-shift']?.numericValue||null,ttfb:a['server-response-time']?.numericValue||null});
  }
  const pick=(k,d=1)=>round(median(rows.map(x=>Number(x[k]))),d);
  return {runs:rows,medianScore:pick('score',0),medianFcpMs:pick('fcp'),medianLcpMs:pick('lcp'),medianSpeedIndexMs:pick('si'),medianTbtMs:pick('tbt'),medianCls:pick('cls',3),medianServerResponseMs:pick('ttfb')};
}

async function publicSnapshot(browser){
  const [pages,posts,media]=await Promise.all([
    fetch(`${base}/wp-json/wp/v2/pages?per_page=100&_fields=id,slug,title`).then(r=>r.json()),
    fetch(`${base}/wp-json/wp/v2/posts?per_page=100&_fields=id,slug,title,featured_media`).then(r=>r.json()),
    fetch(`${base}/wp-json/wp/v2/media?per_page=100&_fields=id,slug,source_url`).then(r=>r.json())
  ]);
  const routeRows=[];
  for(const route of routes){
    const ctx=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1440,height:1000}}); const page=await ctx.newPage(); const failed=[]; const consoleErrors=[];
    page.on('requestfailed',r=>failed.push({url:r.url(),error:r.failure()?.errorText||'failed'}));
    page.on('console',m=>{if(m.type()==='error') consoleErrors.push(m.text())});
    const resp=await page.goto(base+route,{waitUntil:'networkidle',timeout:90000}); await sleep(700);
    const dom=await page.evaluate(()=>({title:document.title,h1:(document.querySelector('h1')?.textContent||'').trim(),bodyClass:document.body.className,images:document.images.length,links:document.links.length,elementorMarkers:document.querySelectorAll('[class*="elementor-"],.elementor').length,htmlBytes:new TextEncoder().encode(document.documentElement.outerHTML).length}));
    routeRows.push({route,status:resp?.status()||0,...dom,failedRequests:failed.filter(x=>x.url.startsWith(base)).slice(0,20),consoleErrors:consoleErrors.filter(x=>!/favicon|ERR_BLOCKED_BY_CLIENT/i.test(x)).slice(0,20)}); await ctx.close();
  }
  return {pages:pages.map(x=>({id:x.id,slug:x.slug,title:x.title?.rendered||''})).sort((a,b)=>a.slug.localeCompare(b.slug)),posts:posts.map(x=>({id:x.id,slug:x.slug,title:x.title?.rendered||'',featured_media:x.featured_media||0})).sort((a,b)=>a.slug.localeCompare(b.slug)),media:media.map(x=>({id:x.id,slug:x.slug,source_url:x.source_url||''})).sort((a,b)=>a.id-b.id),routes:routeRows};
}

const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
const adminCtx=await browser.newContext({ignoreHTTPSErrors:true}); const page=await adminCtx.newPage();
const report={status:'starting',state:'A_NO_PLUGIN',site:slug,url:base,pluginAbsent:false,themeInspiro:false,elementorActive:false,cloudflare:null,snapshot:null,curl:null,browser:null,lighthouse:null,checkedAt:null};
try{
  await login(page); const wp=await adminPage(adminCtx,page);
  await wp.goto(`${base}/wp-admin/plugins.php`,{waitUntil:'domcontentloaded',timeout:60000}); report.pluginAbsent=(await wp.locator('tr[data-slug="runner3-speed"]').count())===0; report.elementorActive=(await wp.locator('tr.active[data-slug="elementor"]').count())>0;
  if(!report.pluginAbsent) throw new Error('runner3_speed_present_clean_baseline_invalid');
  await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000}); report.themeInspiro=(await wp.locator('.theme.active[data-slug="inspiro"]').count())>0;
  if(!report.themeInspiro||!report.elementorActive) throw new Error('inspiro_or_elementor_not_active');
  const headers=execFileSync('curl',['-sSI',base+'/'],{encoding:'utf8'}); report.cloudflare=/^cf-ray:/im.test(headers); if(report.cloudflare) throw new Error('cloudflare_detected_invalid_direct_host_test');
  report.snapshot=await publicSnapshot(browser);
  if(report.snapshot.pages.length<4||report.snapshot.posts.length<5||report.snapshot.media.length<8) throw new Error('fixture_content_missing');
  for(const r of report.snapshot.routes){ if(r.status!==200) throw new Error(`route_not_200:${r.route}:${r.status}`); if(!/wp-theme-inspiro|theme-inspiro/i.test(r.bodyClass)) throw new Error(`theme_marker_missing:${r.route}`); if(r.failedRequests.length) throw new Error(`route_failed_requests:${r.route}:${JSON.stringify(r.failedRequests)}`); }
  report.curl=curlRuns(15); report.browser=await browserRuns(browser,7); report.lighthouse=lighthouseRuns(5); report.status='ready'; report.checkedAt=new Date().toISOString();
}catch(e){report.status='failed';report.error=String(e?.stack||e);report.checkedAt=new Date().toISOString();process.exitCode=1}
finally{fs.writeFileSync(out,JSON.stringify(report,null,2)+'\n');await adminCtx.close().catch(()=>{});await browser.close().catch(()=>{})}
console.log(JSON.stringify(report,null,2));
