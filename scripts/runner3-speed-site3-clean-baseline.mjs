import { chromium } from 'playwright-core';
import fs from 'fs';

const slug=process.env.WP_SITE_SLUG||'runner3-speed-site3-realistic';
const state=JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`,'utf8'));
const account=JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const base=String(state.siteUrl||'').replace(/\/$/,'');
const dashboard=state.dashboardUrl;
const out='/tmp/runner3-speed-site3-clean-baseline.json';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

async function login(page){
  for(let a=1;a<=3;a++){
    try{
      await page.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});
      if(!/\/login(?:[/?#]|$)/i.test(page.url())) return;
      const i=page.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();
      await i.waitFor({state:'visible',timeout:15000}); await i.fill(account.username||account.email); await i.press('Enter');
      const p=page.locator('input[type=password]').first(); await p.waitFor({state:'visible',timeout:20000}); await p.fill(account.password); await p.press('Enter');
      await sleep(2200); if(!/\/login(?:[/?#]|$)/i.test(page.url())) return;
    }catch{}
    await sleep(1000*a);
  }
  throw new Error('wasmer_login_failed');
}

async function adminPage(ctx,page){
  await page.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000}); await sleep(900);
  const c=page.getByText(/WordPress Admin/i).first(); if(!(await c.count())) throw new Error('wordpress_admin_control_missing');
  const href=await c.getAttribute('href').catch(()=>null);
  if(href){const wp=await ctx.newPage();await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:60000});await sleep(1200);if(wp.url().startsWith(base)&&/wp-admin/i.test(wp.url()))return wp;}
  const pp=ctx.waitForEvent('page',{timeout:10000}).catch(()=>null); await c.click().catch(()=>{}); const pop=await pp; await sleep(1600);
  for(const p of [pop,...ctx.pages()].filter(Boolean)) if(p.url().startsWith(base)&&/wp-admin/i.test(p.url())) return p;
  throw new Error('magic_admin_failed');
}

async function nonce(wp){
  await wp.goto(`${base}/wp-admin/`,{waitUntil:'domcontentloaded',timeout:60000}); await sleep(500);
  let n=await wp.evaluate(()=>globalThis.wpApiSettings?.nonce||globalThis.wp?.apiSettings?.nonce||null).catch(()=>null);
  if(!n){const html=await wp.content();const m=html.match(/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i);if(m)n=m[1];}
  if(!n) throw new Error('wp_rest_nonce_missing'); return n;
}

async function api(ctx,n,endpoint,{method='GET',json=null}={}){
  const headers={'X-WP-Nonce':n,Accept:'application/json'};let data;
  if(json!==null){headers['Content-Type']='application/json';data=JSON.stringify(json);}
  const r=await ctx.request.fetch(`${base}/wp-json${endpoint}`,{method,headers,data,timeout:120000,failOnStatusCode:false});
  const text=await r.text();let body;try{body=JSON.parse(text)}catch{body=text}
  if(!r.ok())throw new Error(`api_${method}_${endpoint}:${r.status()}:${String(text).slice(0,300)}`);return body;
}

const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({ignoreHTTPSErrors:true});const page=await ctx.newPage();
const report={status:'starting',found:false,deactivated:false,deleted:false,pluginAbsent:false,front200:false,noRunner3Header:false,checkedAt:null};
try{
  await login(page);const wp=await adminPage(ctx,page);const n=await nonce(wp);
  let plugins=await api(ctx,n,'/wp/v2/plugins?context=edit');
  let p=Array.isArray(plugins)?plugins.find(x=>String(x.plugin||'').startsWith('runner3-speed/')):null;
  report.found=!!p;
  if(p){const path=p.plugin.split('/').map(encodeURIComponent).join('/');if(p.status==='active'){await api(ctx,n,`/wp/v2/plugins/${path}`,{method:'POST',json:{status:'inactive'}});report.deactivated=true;}await api(ctx,n,`/wp/v2/plugins/${path}`,{method:'DELETE'});report.deleted=true;}
  plugins=await api(ctx,n,'/wp/v2/plugins?context=edit');report.pluginAbsent=!Array.isArray(plugins)||!plugins.some(x=>String(x.plugin||'').startsWith('runner3-speed/'));
  if(!report.pluginAbsent)throw new Error('runner3_speed_still_present_after_delete');
  const r=await fetch(base+'/',{redirect:'follow',headers:{'Cache-Control':'no-cache'}});report.front200=r.status===200;report.noRunner3Header=!r.headers.get('x-runner3-speed');
  if(!report.front200||!report.noRunner3Header)throw new Error(`clean_front_invalid:${r.status}:${r.headers.get('x-runner3-speed')||'none'}`);
  report.status='ready';report.checkedAt=new Date().toISOString();
}catch(e){report.status='failed';report.error=String(e?.stack||e);report.checkedAt=new Date().toISOString();process.exitCode=1}
finally{fs.writeFileSync(out,JSON.stringify(report,null,2)+'\n');await ctx.close().catch(()=>{});await browser.close().catch(()=>{})}
console.log(JSON.stringify(report,null,2));
