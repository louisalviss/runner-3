import { chromium } from 'playwright-core';
import fs from 'fs';

const site = JSON.parse(fs.readFileSync('ops/site-factory/runner5-restore-lab-1.json', 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(site.siteUrl || 'https://runner5-restore-lab-1.wasmer.app/').replace(/\/$/, '');
const dashboard = site.dashboardUrl;
const out = '/tmp/runner5-kadence-starter.json';
const shot = '/tmp/runner5-kadence-home.png';
const result = { status:'STARTING', stage:'init', siteUrl:base+'/', theme:'kadence', demo:'Digital Services', source:'Kadence Starter Templates official UI', noindex:false, plugins:{}, ui:[], pages:[], posts:[], mediaCount:0, qa:null, detail:null, updatedAt:new Date().toISOString() };
const save=()=>{result.updatedAt=new Date().toISOString();fs.writeFileSync(out,JSON.stringify(result,null,2));};
const stage=s=>{result.stage=s;save();console.log('STAGE',s);};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const onWasmerLogin=p=>/\/login(?:[/?#]|$)/i.test(p.url());

async function loginWasmer(p){
  stage('wasmer_login');
  await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{}); await p.waitForTimeout(600);
  if(!onWasmerLogin(p)) return;
  const user=p.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();
  await user.fill(account.username||account.email); await user.press('Enter');
  const pass=p.locator('input[type=password]').first(); await pass.waitFor({state:'visible',timeout:20000}); await pass.fill(account.password); await pass.press('Enter');
  const end=Date.now()+20000; while(Date.now()<end){if(!onWasmerLogin(p))return;await p.waitForTimeout(350);} throw new Error('wasmer_login_failed');
}
async function pollWpAdmin(ctx,ms=22000){const end=Date.now()+ms;while(Date.now()<end){for(const p of ctx.pages())if(p.url().startsWith(base)&&/\/wp-admin(?:\/|\?|$)/i.test(p.url())&&!/wp-login\.php/i.test(p.url()))return p;await sleep(400);}return null;}
async function enterWpAdmin(ctx,p){
  stage('wordpress_admin');
  for(let attempt=0;attempt<3;attempt++){
    await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{});await p.waitForTimeout(800);
    let admin=p.getByText(/WordPress Admin/i).first();
    if(!await admin.isVisible().catch(()=>false)){
      const settings=p.getByText(/^Settings$/i).first(); if(await settings.isVisible().catch(()=>false)){await settings.click().catch(()=>{});await p.waitForTimeout(450);const wp=p.getByText(/^WordPress$/i).first();if(await wp.isVisible().catch(()=>false)){await wp.click().catch(()=>{});await p.waitForTimeout(450);}admin=p.getByText(/WordPress Admin/i).first();}
    }
    if(await admin.isVisible().catch(()=>false)){
      const href=await admin.getAttribute('href').catch(()=>null); if(href){const wp=await ctx.newPage();await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{});const found=await pollWpAdmin(ctx,18000);if(found)return found;}
      await admin.click({noWaitAfter:true}).catch(()=>{});const found=await pollWpAdmin(ctx,20000);if(found)return found;
    }
  }
  throw new Error('magic_admin_failed');
}
async function getNonce(wp){
  await wp.goto(`${base}/wp-admin/`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(500);
  let n=await wp.evaluate(()=>globalThis.wpApiSettings?.nonce||globalThis.wp?.apiSettings?.nonce||null).catch(()=>null);
  if(!n){const h=await wp.content();const m=h.match(/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i);if(m)n=m[1];}
  if(!n)throw new Error('wp_rest_nonce_missing');return n;
}
async function api(ctx,nonce,path,{method='GET',json=null,soft=false,timeout=180000}={}){
  const headers={'X-WP-Nonce':nonce,Accept:'application/json'};let data;if(json!==null){headers['Content-Type']='application/json';data=JSON.stringify(json);}
  const r=await ctx.request.fetch(`${base}/wp-json${path}`,{method,headers,data,timeout,failOnStatusCode:false});const text=await r.text();let body;try{body=JSON.parse(text)}catch{body=text}
  if(!r.ok()){if(soft)return{ok:false,status:r.status(),data:body};throw new Error(`api_${method}_${path}:${r.status()}:${String(text).slice(0,500)}`);}return soft?{ok:true,status:r.status(),data:body}:body;
}
async function ensurePlugin(ctx,nonce,slug,prefix=`${slug}/`){
  const ps=await api(ctx,nonce,'/wp/v2/plugins?context=edit');let p=Array.isArray(ps)?ps.find(x=>String(x.plugin||'').startsWith(prefix)):null;
  if(!p)p=await api(ctx,nonce,'/wp/v2/plugins',{method:'POST',json:{slug,status:'active'},timeout:180000});else if(p.status!=='active')p=await api(ctx,nonce,`/wp/v2/plugins/${encodeURIComponent(p.plugin)}`,{method:'POST',json:{status:'active'},timeout:120000});
  result.plugins[slug]=p?.status||'active';save();return p;
}
async function activateKadence(wp){
  stage('kadence_theme');
  await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(900);
  let card=wp.locator('.theme[data-slug="kadence"]').first();
  if(!await card.count()){
    await wp.goto(`${base}/wp-admin/theme-install.php?search=kadence`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1500);card=wp.locator('.theme[data-slug="kadence"]').first();await card.waitFor({state:'visible',timeout:20000});
    const install=card.getByRole('button',{name:/Install/i}).first();const installLink=card.getByRole('link',{name:/Install/i}).first();
    if(await install.isVisible().catch(()=>false))await install.click();else if(await installLink.isVisible().catch(()=>false))await installLink.click();else throw new Error('kadence_install_control_missing');
    const end=Date.now()+90000;while(Date.now()<end){const a=card.getByRole('button',{name:/Activate/i}).first();const l=card.getByRole('link',{name:/Activate/i}).first();if(await a.isVisible().catch(()=>false)){await a.click();break;}if(await l.isVisible().catch(()=>false)){await l.click();break;}await wp.waitForTimeout(1000);}
  }else if(!/active/i.test(await card.getAttribute('class')||'')){
    const a=card.getByRole('link',{name:/Activate/i}).first();if(await a.isVisible().catch(()=>false))await a.click();
  }
  await wp.waitForTimeout(1800);await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000});if(!await wp.locator('.theme.active[data-slug="kadence"]').count())throw new Error('kadence_activation_failed');
}
async function setNoindex(wp){
  await wp.goto(`${base}/wp-admin/options-reading.php`,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{});await wp.waitForTimeout(500);
  const target=wp.locator('input[name="blog_public"][value="0"],input#blog-norobots,input#blog_public,input[name="blog_public"]').first();
  if(await target.count()){if(!await target.isChecked().catch(()=>false))await target.check().catch(()=>target.click({force:true}).catch(()=>{}));const submit=wp.locator('#submit,input[type=submit],button[type=submit]').first();if(await submit.count()){await submit.click().catch(()=>{});await wp.waitForLoadState('domcontentloaded').catch(()=>{});}}
  const probe=await wp.evaluate(async()=>{try{const r=await fetch('/?kadence-noindex='+Date.now(),{cache:'no-store'});return{html:await r.text(),xr:r.headers.get('x-robots-tag')||''}}catch{return{html:'',xr:''}}}).catch(()=>({html:'',xr:''}));
  result.noindex=/noindex/i.test(String(probe.xr))||/<meta[^>]+name=["']robots["'][^>]+noindex/i.test(String(probe.html))||/noindex[^>]+nofollow/i.test(String(probe.html));save();
}
async function uiSnapshot(p,label){
  const x=await p.evaluate(()=>({url:location.href,title:document.title,text:(document.body?.innerText||'').replace(/\s+/g,' ').slice(0,9000),buttons:[...document.querySelectorAll('button,[role=button],input[type=button],input[type=submit]')].map(e=>(e.innerText||e.value||e.getAttribute('aria-label')||'').trim()).filter(Boolean).slice(0,120),links:[...document.querySelectorAll('a')].map(e=>(e.innerText||e.getAttribute('aria-label')||'').trim()).filter(Boolean).slice(0,120),inputs:[...document.querySelectorAll('input')].map(e=>({type:e.type,placeholder:e.placeholder||'',value:e.value||''})).slice(0,80)}));result.ui.push({label,...x});save();return x;
}
async function clickText(p,patterns){for(const re of patterns){for(const loc of [p.getByRole('button',{name:re}).first(),p.getByRole('link',{name:re}).first(),p.getByText(re,{exact:false}).first()]){if(await loc.count().catch(()=>0)&&await loc.isVisible().catch(()=>false)){await loc.click().catch(()=>{});await p.waitForTimeout(1800);return true;}}}return false;}
async function importKadence(wp){
  stage('starter_library');
  let opened=false;
  for(const url of [`${base}/wp-admin/themes.php?page=kadence-starter-templates`,`${base}/wp-admin/admin.php?page=kadence-starter-templates`]){
    await wp.goto(url,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{});await wp.waitForTimeout(4500);const s=await uiSnapshot(wp,'landing');if(/Starter Templates|Pre-Designed|Classic Starter/i.test(s.text)){opened=true;break;}
  }
  if(!opened)throw new Error('kadence_starter_page_unavailable');
  await clickText(wp,[/Use a Classic Starter Template/i,/Pre-Designed Starter Templates/i,/Pre-Designed Templates/i,/Classic Starter/i]);await wp.waitForTimeout(4500);await uiSnapshot(wp,'library');
  const search=wp.locator('input[type=search],input[placeholder*="Search" i]').first();if(await search.count()&&await search.isVisible().catch(()=>false)){await search.fill('Digital Services');await wp.waitForTimeout(1800);}
  let selected=await clickText(wp,[/^Digital Services$/i]);
  if(!selected){for(const fallback of [/^Agency$/i,/^Recipe Blog$/i,/^SAAS$/i,/^Cornerstone$/i]){if(await clickText(wp,[fallback])){selected=true;result.demo=String(fallback);break;}}}
  if(!selected){await uiSnapshot(wp,'template_missing');throw new Error('kadence_free_template_not_found');}
  await wp.waitForTimeout(3500);await uiSnapshot(wp,'template_detail');
  if(!await clickText(wp,[/Full Site/i,/Import Full Site/i,/Full Website/i])){await uiSnapshot(wp,'full_site_missing');throw new Error('kadence_full_site_control_missing');}
  await wp.waitForTimeout(3000);await uiSnapshot(wp,'style_setup');
  for(let step=0;step<8;step++){
    const text=(await wp.locator('body').innerText().catch(()=>''));
    if(/Importing|Installing|Creating|Processing/i.test(text)){await wp.waitForTimeout(5000);continue;}
    if(/Finish and Launch|View Your Site|See Your Site|Visit Site/i.test(text))break;
    const clicked=await clickText(wp,[/Start Importing/i,/Import Site/i,/Begin Import/i,/Finish and Launch/i,/Next/i,/Continue/i]);
    if(!clicked)break;
    await wp.waitForTimeout(2500);
  }
  const end=Date.now()+300000;let last='';while(Date.now()<end){last=(await wp.locator('body').innerText().catch(()=>''));if(/Finish and Launch|View Your Site|See Your Site|Congratulations|site.*ready/i.test(last))break;if(/Import Failed|Import Error|Something went wrong/i.test(last))throw new Error('kadence_import_ui_failed:'+last.replace(/\s+/g,' ').slice(0,800));await wp.waitForTimeout(5000);}
  await uiSnapshot(wp,'import_end');
}
async function snapshotContent(ctx,nonce){
  const [pages,posts,media]=await Promise.all([api(ctx,nonce,'/wp/v2/pages?context=edit&per_page=100&_fields=id,slug,title,status'),api(ctx,nonce,'/wp/v2/posts?context=edit&per_page=100&_fields=id,slug,title,status'),api(ctx,nonce,'/wp/v2/media?context=edit&per_page=100&_fields=id,source_url')]);
  result.pages=(pages||[]).map(x=>({id:x.id,slug:x.slug,title:x.title?.rendered||'',status:x.status}));result.posts=(posts||[]).map(x=>({id:x.id,slug:x.slug,title:x.title?.rendered||'',status:x.status}));result.mediaCount=Array.isArray(media)?media.length:0;save();
}
async function qa(browser){
  stage('direct_origin_qa');const ctx=await browser.newContext({viewport:{width:1440,height:1000}});const p=await ctx.newPage();const failed=[];const errors=[];
  p.on('response',r=>{if(r.status()>=400&&['stylesheet','script','image','font'].includes(r.request().resourceType()))failed.push({status:r.status(),type:r.request().resourceType(),url:r.url()});});p.on('requestfailed',r=>failed.push({status:null,type:r.resourceType(),url:r.url(),error:r.failure()?.errorText||''}));p.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
  const response=await p.goto(`${base}/?kadence-origin-qa=${Date.now()}`,{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(2500);const total=await p.evaluate(()=>document.documentElement.scrollHeight);for(let y=0;y<total;y+=700){await p.evaluate(v=>window.scrollTo(0,v),y);await p.waitForTimeout(80);}await p.evaluate(()=>scrollTo(0,0));await p.waitForTimeout(600);
  const m=await p.evaluate(()=>{const imgs=[...document.images];return{title:document.title,bodyClass:document.body.className,themeKadence:/wp-theme-kadence|theme-kadence/.test(document.body.className),kadenceBlocks:document.querySelectorAll('[class*="wp-block-kadence"],[class*="kt-"]').length,imageCount:imgs.length,loadedImages:imgs.filter(i=>i.complete&&i.naturalWidth>0).length,stylesheetCount:document.querySelectorAll('link[rel~="stylesheet"]').length,scrollWidth:Math.max(document.documentElement.scrollWidth,document.body.scrollWidth),viewportWidth:document.documentElement.clientWidth,htmlBytes:new Blob([document.documentElement.outerHTML]).size,text:(document.body?.innerText||'').replace(/\s+/g,' ').slice(0,1200)}});await p.screenshot({path:shot,fullPage:true});
  result.qa={http:response?.status()??null,failed:failed.slice(0,80),consoleErrors:errors.slice(0,40),...m};save();await ctx.close();
  const localFails=failed.filter(x=>x.url.startsWith(base));return m.themeKadence&&response?.status()===200&&m.stylesheetCount>=3&&m.kadenceBlocks>=3&&m.loadedImages>=Math.min(6,m.imageCount)&&localFails.length===0&&m.scrollWidth-m.viewportWidth<=2;
}

const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({viewport:{width:1440,height:1100}});const gate=await ctx.newPage();
try{
  await loginWasmer(gate);const wp=await enterWpAdmin(ctx,gate);let nonce=await getNonce(wp);
  stage('clean_oceanwp_demo');await api(ctx,nonce,'/oceanwp/v1/onboarding/reset-site',{method:'POST',json:{resetOptions:['pages','posts','media','menus','customizer-settings']},soft:true,timeout:180000}).catch(()=>null);
  await activateKadence(wp);nonce=await getNonce(wp);await ensurePlugin(ctx,nonce,'kadence-blocks','kadence-blocks/');await ensurePlugin(ctx,nonce,'kadence-starter-templates','kadence-starter-templates/');await setNoindex(wp);
  await importKadence(wp);nonce=await getNonce(wp);await setNoindex(wp);nonce=await getNonce(wp);await snapshotContent(ctx,nonce);
  const good=await qa(browser);if(!good)throw new Error(`kadence_visual_qa_failed:${JSON.stringify(result.qa).slice(0,1800)}`);
  if(result.pages.length<3)throw new Error(`kadence_pages_too_few:${result.pages.length}`);if(result.mediaCount<5)throw new Error(`kadence_media_too_few:${result.mediaCount}`);
  result.status='READY';result.stage='done';result.detail=null;save();
}catch(e){result.status='FAILED';result.detail=String(e?.stack||e);save();console.error(result.detail);process.exitCode=1;}finally{await ctx.close().catch(()=>{});await browser.close();}
console.log(JSON.stringify(result,null,2));
