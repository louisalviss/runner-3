import { chromium } from 'playwright-core';
import fs from 'fs';

const site=JSON.parse(fs.readFileSync('ops/site-factory/runner5-restore-lab-1.json','utf8'));
const account=JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const base=String(site.siteUrl||'https://runner5-restore-lab-1.wasmer.app/').replace(/\/$/,'');
const dashboard=site.dashboardUrl;
const out='/tmp/runner5-neve-official-demo.json';
const result={status:'STARTING',siteUrl:base+'/',theme:'neve',demo:'Photography Studio',source:'Neve > Starter Sites official UI',noindex:true,plugins:{library:'active'},pages:[],posts:[],mediaCount:0,homeImages:0,homeLinks:0,stage:'init',detail:null,uiTail:null,updatedAt:new Date().toISOString()};
const save=()=>{result.updatedAt=new Date().toISOString();fs.writeFileSync(out,JSON.stringify(result,null,2));};
const stage=s=>{result.stage=s;console.log('STAGE',s);save();};
const onLogin=p=>/\/login(?:[/?#]|$)/i.test(p.url());
async function login(p){stage('wasmer_login');await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{});await p.waitForTimeout(700);if(!onLogin(p))return;const i=p.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();await i.fill(account.username||account.email);await i.press('Enter');const q=p.locator('input[type=password]').first();await q.waitFor({state:'visible',timeout:20000});await q.fill(account.password);await q.press('Enter');const e=Date.now()+20000;while(Date.now()<e){if(!onLogin(p))return;await p.waitForTimeout(400);}throw new Error('wasmer_login_failed');}
async function pollAdmin(ctx,ms=25000){const e=Date.now()+ms;while(Date.now()<e){for(const p of ctx.pages())if(p.url().startsWith(base)&&/\/wp-admin(?:\/|\?|$)/i.test(p.url())&&!/wp-login\.php/i.test(p.url()))return p;await new Promise(r=>setTimeout(r,500));}return null;}
async function admin(ctx,p){stage('wordpress_admin');for(let k=0;k<3;k++){await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{});await p.waitForTimeout(900);let c=p.getByText(/WordPress Admin/i).first();if(!await c.isVisible().catch(()=>false)){const s=p.getByText(/^Settings$/i).first();if(await s.isVisible().catch(()=>false)){await s.click().catch(()=>{});await p.waitForTimeout(500);const w=p.getByText(/^WordPress$/i).first();if(await w.isVisible().catch(()=>false)){await w.click().catch(()=>{});await p.waitForTimeout(500);}c=p.getByText(/WordPress Admin/i).first();}}if(await c.isVisible().catch(()=>false)){const href=await c.getAttribute('href').catch(()=>null);if(href){const wp=await ctx.newPage();await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{});const f=await pollAdmin(ctx,18000);if(f)return f;}await c.click({noWaitAfter:true}).catch(()=>{});const f=await pollAdmin(ctx,22000);if(f)return f;}}throw new Error('magic_admin_failed');}
async function getNonce(wp){await wp.goto(`${base}/wp-admin/`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(600);let n=await wp.evaluate(()=>globalThis.wpApiSettings?.nonce||globalThis.wp?.apiSettings?.nonce||null).catch(()=>null);if(!n){const h=await wp.content();const m=h.match(/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i);if(m)n=m[1];}if(!n)throw new Error('nonce_missing');return n;}
async function api(ctx,n,path){const r=await ctx.request.fetch(`${base}/wp-json${path}`,{headers:{'X-WP-Nonce':n,Accept:'application/json'},timeout:90000,failOnStatusCode:false});const t=await r.text();let d;try{d=JSON.parse(t)}catch{d=t}if(!r.ok())throw new Error(`api_${path}:${r.status()}:${String(t).slice(0,180)}`);return d;}
async function bodyText(wp){return (await wp.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function clickAny(wp,patterns,{timeout=600,exact=false}={}){for(const re of patterns){for(const loc of [wp.getByRole('button',{name:re,exact}).first(),wp.getByRole('link',{name:re,exact}).first(),wp.getByText(re,{exact}).first()]){if(await loc.isVisible({timeout}).catch(()=>false)){console.log('CLICK',String(re));await loc.click().catch(()=>{});await wp.waitForTimeout(800);return true;}}}return false;}
async function preserveNoindex(wp){stage('confirm_noindex');await wp.goto(`${base}/wp-admin/options-reading.php`,{waitUntil:'domcontentloaded',timeout:60000});const b=wp.locator('input[name="blog_public"]').first();await b.waitFor({state:'attached',timeout:15000});if(!await b.isChecked())await b.check();await wp.locator('#submit,input[type=submit]').first().click();await wp.waitForLoadState('domcontentloaded').catch(()=>{});result.noindex=await wp.locator('input[name="blog_public"]').first().isChecked().catch(()=>false);if(!result.noindex)throw new Error('noindex_not_set');save();}
async function runOfficialUI(wp){
  stage('starter_sites_ui');
  await wp.goto(`${base}/wp-admin/admin.php?page=tiob-starter-sites`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(4000);
  let text=await bodyText(wp);console.log('UI_START',text.slice(0,1800));
  if(/error|critical error/i.test(text)&&!/no error/i.test(text))throw new Error('starter_ui_error:'+text.slice(0,500));
  // Close welcome/onboarding preliminaries but never synthesize site content.
  await clickAny(wp,[/Get Started/i,/Start Building/i,/Explore Starter Sites/i,/Browse Starter Sites/i],{timeout:800});
  await wp.waitForTimeout(1500);
  // Force Gutenberg/Block Editor so the official Otter-based version is selected.
  await clickAny(wp,[/^Gutenberg$/i,/Block Editor/i,/WordPress Editor/i],{timeout:700});
  await wp.waitForTimeout(1200);
  // Search current official library.
  const searches=[wp.locator('input[type="search"]').first(),wp.locator('input[placeholder*="Search" i]').first(),wp.locator('input[placeholder*="website" i]').first()];
  let search=null;for(const s of searches){if(await s.isVisible({timeout:700}).catch(()=>false)){search=s;break;}}
  if(search){await search.fill('Photography Studio');await wp.waitForTimeout(2500);}
  text=await bodyText(wp);console.log('UI_AFTER_SEARCH',text.slice(0,2400));
  let card=wp.getByText(/^Photography Studio$/i).first();if(!await card.isVisible({timeout:6000}).catch(()=>false))card=wp.getByText(/Photography Studio/i).first();
  if(!await card.isVisible({timeout:3000}).catch(()=>false))throw new Error('official_photography_studio_card_missing:'+text.slice(0,900));
  await card.click();await wp.waitForTimeout(2200);
  // Some versions show a preview first, then an Import Website action.
  for(let i=0;i<12;i++){
    text=await bodyText(wp);console.log('UI_STEP',i,text.slice(0,1800));
    if(/Import Website|Import Site|Import Complete Site|Start Import/i.test(text)){
      if(await clickAny(wp,[/Import Website/i,/Import Site/i,/Import Complete Site/i,/Start Import/i],{timeout:800}))continue;
    }
    // Builder choice may appear after choosing a site.
    if(/Gutenberg|Block Editor|WordPress Editor/i.test(text)&&!/Importing/i.test(text)){if(await clickAny(wp,[/^Gutenberg$/i,/Block Editor/i,/WordPress Editor/i],{timeout:500}))continue;}
    // Plugin confirmation / logo customization / optional subscription screens.
    if(await clickAny(wp,[/Continue/i,/Next/i,/Skip & Continue/i,/Skip/i],{timeout:400}))continue;
    break;
  }
  // Wait for the official importer to complete. Keep clicking only explicit import/continue actions if exposed.
  const end=Date.now()+9*60*1000;
  while(Date.now()<end){
    text=await bodyText(wp);result.uiTail=text.slice(-1800);save();
    if(/Website Imported|Import Complete|Website is Ready|Your Site is Ready|View Website|View Site|Congratulations/i.test(text)){console.log('IMPORT_UI_READY');return;}
    if(/Import Failed|Failed to Import|Something went wrong|Import Error/i.test(text))throw new Error('official_ui_import_failed:'+text.slice(-900));
    if(/Import Website|Import Site|Start Import/i.test(text)&&!/Importing|Please wait/i.test(text)){await clickAny(wp,[/Import Website/i,/Import Site/i,/Start Import/i],{timeout:300});}
    if(/Subscribe|Skip.*view|Skip.*website/i.test(text)){await clickAny(wp,[/Skip/i,/View Website/i,/View Site/i],{timeout:300});}
    await wp.waitForTimeout(2500);
  }
  throw new Error('official_ui_import_timeout:'+text.slice(-1000));
}
async function verify(ctx,wp){stage('verify_official_demo');const n=await getNonce(wp);const [pages,posts,media]=await Promise.all([api(ctx,n,'/wp/v2/pages?context=edit&per_page=100&_fields=id,slug,title,status'),api(ctx,n,'/wp/v2/posts?context=edit&per_page=100&_fields=id,slug,title,status'),api(ctx,n,'/wp/v2/media?context=edit&per_page=100&_fields=id,source_url')]);result.pages=Array.isArray(pages)?pages.map(x=>({id:x.id,slug:x.slug,title:x.title?.rendered||'',status:x.status})):[];result.posts=Array.isArray(posts)?posts.map(x=>({id:x.id,slug:x.slug,title:x.title?.rendered||'',status:x.status})):[];result.mediaCount=Array.isArray(media)?media.length:0;const r=await fetch(`${base}/?official=${Date.now()}`,{headers:{'Cache-Control':'no-cache','User-Agent':'Runner5OfficialUIVerify/1.0'}});const h=await r.text();result.homeImages=(h.match(/<img\b/gi)||[]).length;result.homeLinks=(h.match(/<a\b/gi)||[]).length;const noidx=/<meta[^>]+name=["']robots["'][^>]+noindex/i.test(h)||/noindex[^>]+nofollow/i.test(h);result.noindex=result.noindex&&noidx;save();if(!r.ok)throw new Error(`home_http_${r.status}`);if(result.pages.length<3)throw new Error(`official_pages_too_few:${result.pages.length}`);if(result.mediaCount<5)throw new Error(`official_media_too_few:${result.mediaCount}`);if(result.homeImages<3)throw new Error(`official_home_images_too_few:${result.homeImages}`);if(!result.noindex)throw new Error('noindex_lost');}

const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});const ctx=await browser.newContext({viewport:{width:1440,height:1100}});const p=await ctx.newPage();
try{await login(p);const wp=await admin(ctx,p);await preserveNoindex(wp);await runOfficialUI(wp);await preserveNoindex(wp);await verify(ctx,wp);result.status='READY';result.stage='done';result.detail=null;save();}catch(e){result.status='FAILED';result.detail=String(e?.stack||e);try{result.uiTail=await bodyText(ctx.pages().at(-1)).then(x=>x.slice(-2200));}catch{}save();console.error(result.detail);process.exitCode=1}finally{await browser.close();}console.log(JSON.stringify(result,null,2));
