import { chromium } from 'playwright-core';
import fs from 'fs';

const APP = 'runner3-factory-smoke-2';
const CUSTOM_ORIGIN = 'https://runner3wp.pntr.dev';
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
if (!account?.username || !account?.password) throw new Error('Wasmer account state incomplete');
const owner = account.username;
const dashboard = `https://wasmer.io/apps/${encodeURIComponent(owner)}/${APP}`;
const nativeOrigin = `https://${APP}.wasmer.app`;

function cleanText(s){ return String(s||'').replace(/\s+/g,' ').trim(); }
async function bodyText(page){ return cleanText(await page.locator('body').innerText().catch(()=>'')); }
async function freshLogin(page){
  await page.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(900);
  const ident=page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  if(!(await ident.count())) return false;
  await ident.fill(account.username || account.email);
  let b=page.locator('button').filter({hasText:/continue|next|log in|sign in/i}).first();
  if(await b.count()) await b.click().catch(()=>{}); else await ident.press('Enter').catch(()=>{});
  const pass=page.locator('input[type=password]').first();
  if(!(await pass.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false))) return false;
  await pass.fill(account.password);
  b=page.locator('button,input[type=submit]').filter({hasText:/log in|sign in|continue/i}).first();
  if(await b.count()) await b.click().catch(()=>{}); else await pass.press('Enter').catch(()=>{});
  await page.waitForTimeout(3500);
  return !/\/login(?:[/?#]|$)/i.test(page.url());
}
async function ensureWasmerSession(page){
  await page.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1300);
  if(/\/login(?:[/?#]|$)/i.test(page.url()) || /log in|sign in/i.test((await bodyText(page)).slice(0,500))){
    if(!(await freshLogin(page))) throw new Error('Wasmer login failed');
    await page.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000});
    await page.waitForTimeout(1300);
  }
}
async function enterWpAdmin(ctx,page){
  await ensureWasmerSession(page);
  const admin=page.getByText(/WordPress Admin/i).first();
  if(!(await admin.count())) throw new Error('WordPress Admin control missing');
  const href=await admin.getAttribute('href').catch(()=>null);
  if(href){
    const p=await ctx.newPage();
    await p.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:60000});
    await p.waitForTimeout(2500);
    if(/\/wp-admin/i.test(p.url())) return p;
    await p.close().catch(()=>{});
  }
  const popPromise=ctx.waitForEvent('page',{timeout:10000}).catch(()=>null);
  await admin.click().catch(()=>{});
  const pop=await popPromise;
  await page.waitForTimeout(3000);
  for(const p of [pop,...ctx.pages()].filter(Boolean)) if(/\/wp-admin/i.test(p.url())) return p;
  throw new Error('WordPress magic admin failed');
}
async function probe(ctx,label,origin){
  const r=await ctx.request.get(`${origin}/pntr-bridge-status`,{failOnStatusCode:false,timeout:30000}).catch(()=>null);
  if(!r){ console.log(`BRIDGE_${label}_REQUEST_FAILED=true`); return false; }
  const t=await r.text().catch(()=> '');
  const ready=r.status()===200 && t.includes('RUNNER3_PNTR_BRIDGE_READY');
  console.log(`BRIDGE_${label}_HTTP=${r.status()} READY=${ready}`);
  return ready;
}

const storageStatePath=fs.existsSync('/tmp/wasmer-browser-state.json')?'/tmp/wasmer-browser-state.json':undefined;
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({storageState:storageStatePath,ignoreHTTPSErrors:true});
const page=await ctx.newPage();
try{
  const wp=await enterWpAdmin(ctx,page);
  const wpOrigin=new URL(wp.url()).origin;
  console.log(`WP_ADMIN_ORIGIN=${wpOrigin}`);
  await wp.goto(`${wpOrigin}/wp-admin/plugins.php`,{waitUntil:'domcontentloaded',timeout:60000});
  await wp.waitForTimeout(1000);
  if(/wp-login\.php/i.test(wp.url())) throw new Error('WordPress session lost');

  const rows=wp.locator('tr');
  let row=null;
  for(let i=0;i<await rows.count();i++){
    const r=rows.nth(i);
    const txt=await r.innerText().catch(()=> '');
    if(/Runner3 PNTR Cookie Bridge/i.test(txt)){ row=r; break; }
  }
  if(!row) throw new Error('Bridge plugin row not found');
  const cls=await row.getAttribute('class').catch(()=> '');
  let txt=await row.innerText().catch(()=> '');
  let active=/(^|\s)active(\s|$)/i.test(cls||'') || /\bDeactivate\b/i.test(txt);
  console.log(`BRIDGE_PLUGIN_ACTIVE_BEFORE=${active}`);
  if(!active){
    let a=row.locator('a').filter({hasText:/^Activate$/i}).first();
    if(!(await a.count())) a=row.locator('a[href*="action=activate"]').first();
    if(!(await a.count())) throw new Error('Activate link not found');
    const href=await a.getAttribute('href').catch(()=>null);
    if(href) await wp.goto(new URL(href,wp.url()).href,{waitUntil:'domcontentloaded',timeout:60000});
    else await a.click();
    await wp.waitForTimeout(1800);
    await wp.goto(`${wpOrigin}/wp-admin/plugins.php`,{waitUntil:'domcontentloaded',timeout:60000});
    await wp.waitForTimeout(700);
    const rows2=wp.locator('tr');
    row=null;
    for(let i=0;i<await rows2.count();i++){
      const r=rows2.nth(i);
      if(/Runner3 PNTR Cookie Bridge/i.test(await r.innerText().catch(()=>''))){ row=r; break; }
    }
    if(!row) throw new Error('Bridge row missing after activate');
    const cls2=await row.getAttribute('class').catch(()=> '');
    txt=await row.innerText().catch(()=> '');
    active=/(^|\s)active(\s|$)/i.test(cls2||'') || /\bDeactivate\b/i.test(txt);
  }
  console.log(`BRIDGE_PLUGIN_ACTIVE_AFTER=${active}`);
  if(!active) throw new Error('Bridge plugin activation unconfirmed');

  const nativeReady=await probe(ctx,'NATIVE',nativeOrigin);
  const customReady=await probe(ctx,'CUSTOM',CUSTOM_ORIGIN);
  if(!nativeReady) throw new Error('Bridge not live on native Wasmer origin');
  if(!customReady) throw new Error('Bridge live natively but not on custom domain');
  console.log('PNTR_COOKIE_BRIDGE_READY=true');
} finally {
  await browser.close().catch(()=>{});
}
