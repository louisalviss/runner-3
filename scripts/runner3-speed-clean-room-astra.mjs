import { chromium } from 'playwright-core';
import fs from 'fs';

const slug=process.env.WP_SITE_SLUG||'runner3-speed-clean-lab-1';
const site=JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`,'utf8'));
const account=JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const base=String(site.siteUrl).replace(/\/$/,'');
const dashboard=site.dashboardUrl;
const out='/tmp/runner3-speed-clean-room-astra.json';
const result={status:'STARTING',siteUrl:`${base}/`,theme:null,detail:null,updatedAt:new Date().toISOString()};
const save=()=>{result.updatedAt=new Date().toISOString();fs.writeFileSync(out,JSON.stringify(result,null,2));};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const onLogin=p=>/\/login(?:[/?#]|$)/i.test(p.url());

async function login(p){
  for(let attempt=1;attempt<=3;attempt++){
    try{
      await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});await sleep(600);
      if(!onLogin(p))return;
      const i=p.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();
      await i.waitFor({state:'visible',timeout:15000});await i.fill(account.username||account.email);await i.press('Enter');
      const q=p.locator('input[type=password]').first();await q.waitFor({state:'visible',timeout:20000});await q.fill(account.password);await q.press('Enter');await sleep(1800);
      if(!onLogin(p))return;
    }catch{}
    await sleep(800*attempt);
  }
  throw new Error('wasmer_login_failed');
}
async function pollAdmin(ctx,ms=25000){const end=Date.now()+ms;while(Date.now()<end){for(const p of ctx.pages())if(p.url().startsWith(base)&&/\/wp-admin(?:\/|\?|$)/i.test(p.url())&&!/wp-login\.php/i.test(p.url()))return p;await sleep(400);}return null;}
async function admin(ctx,p){
  for(let k=0;k<3;k++){
    await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{});await sleep(900);
    let c=p.getByText(/WordPress Admin/i).first();
    if(!await c.isVisible().catch(()=>false)){const s=p.getByText(/^Settings$/i).first();if(await s.isVisible().catch(()=>false)){await s.click().catch(()=>{});await sleep(400);const w=p.getByText(/^WordPress$/i).first();if(await w.isVisible().catch(()=>false)){await w.click().catch(()=>{});await sleep(400);}c=p.getByText(/WordPress Admin/i).first();}}
    if(await c.isVisible().catch(()=>false)){
      const href=await c.getAttribute('href').catch(()=>null);
      if(href){const wp=await ctx.newPage();await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{});const f=await pollAdmin(ctx,18000);if(f)return f;}
      await c.click({noWaitAfter:true}).catch(()=>{});const f=await pollAdmin(ctx,22000);if(f)return f;
    }
  }
  throw new Error('magic_admin_failed');
}
async function ensureAstra(wp){
  await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000});await sleep(700);
  let active=wp.locator('.theme.active[data-slug="astra"],.theme.active').filter({hasText:/\bAstra\b/i}).first();
  if(await active.count())return;
  let card=wp.locator('.theme[data-slug="astra"],.theme').filter({hasText:/\bAstra\b/i}).first();
  if(!await card.count()){
    await wp.goto(`${base}/wp-admin/theme-install.php?search=astra`,{waitUntil:'domcontentloaded',timeout:60000});await sleep(1200);
    let link=wp.locator('a[href*="action=install-theme"][href*="theme=astra"],a.theme-install[href*="astra"],a[href*="theme=astra"]').first();
    let href=await link.getAttribute('href').catch(()=>null);
    if(!href){const html=await wp.content();const m=html.match(/href=["']([^"']*(?:action=install-theme[^"']*theme=astra|theme=astra[^"']*action=install-theme)[^"']*)["']/i);if(m)href=m[1].replaceAll('&amp;','&');}
    if(!href)throw new Error('astra_install_url_missing');
    await wp.goto(new URL(href,base).href,{waitUntil:'domcontentloaded',timeout:120000});await sleep(1200);
  }
  await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000});await sleep(600);
  card=wp.locator('.theme[data-slug="astra"],.theme').filter({hasText:/\bAstra\b/i}).first();
  if(!await card.count())throw new Error('astra_not_installed');
  active=wp.locator('.theme.active[data-slug="astra"],.theme.active').filter({hasText:/\bAstra\b/i}).first();
  if(!await active.count()){
    const a=card.locator('a.activate,a[href*="action=activate"]').first();let href=await a.getAttribute('href').catch(()=>null);
    if(!href){const html=await card.innerHTML();const m=html.match(/href=["']([^"']*action=activate[^"']*)["']/i);if(m)href=m[1].replaceAll('&amp;','&');}
    if(!href)throw new Error('astra_activate_url_missing');
    await wp.goto(new URL(href,base).href,{waitUntil:'domcontentloaded',timeout:60000});await sleep(900);
  }
  await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000});await sleep(500);
  active=wp.locator('.theme.active[data-slug="astra"],.theme.active').filter({hasText:/\bAstra\b/i}).first();
  if(!await active.count())throw new Error('astra_activation_failed');
}

const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext();const p=await ctx.newPage();
try{save();await login(p);const wp=await admin(ctx,p);await ensureAstra(wp);const html=await fetch(`${base}/?astra_check=${Date.now()}`,{headers:{'Cache-Control':'no-cache'}}).then(r=>r.text());if(!(/\bast-(?:desktop|header|container|primary|site|plain-container)/i.test(html)||/astra/i.test(html)))throw new Error('astra_public_marker_missing');result.status='READY';result.theme='astra';save();}
catch(e){result.status='FAILED';result.detail=String(e?.stack||e);save();console.error(result.detail);process.exitCode=1;}
finally{await browser.close();}
console.log(JSON.stringify(result,null,2));