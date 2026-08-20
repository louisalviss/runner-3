import { chromium } from 'playwright-core';
import fs from 'fs';

const site = JSON.parse(fs.readFileSync('ops/site-factory/runner5-restore-lab-1.json','utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const base = String(site.siteUrl || 'https://runner5-restore-lab-1.wasmer.app/').replace(/\/$/,'');
const dashboard = site.dashboardUrl;
const out = '/tmp/runner5-neve-official-demo.json';
const result = {status:'STARTING',siteUrl:base+'/',theme:null,demo:'Photography Studio',source:'Themeisle official starter site',noindex:false,plugins:{},pages:[],posts:[],mediaCount:0,homeImages:0,homeLinks:0,matchedSite:null,stage:'init',detail:null,updatedAt:new Date().toISOString()};
const save=()=>{result.updatedAt=new Date().toISOString();fs.writeFileSync(out,JSON.stringify(result,null,2));};
const stage=s=>{result.stage=s;console.log('STAGE',s);save();};
const onLogin=p=>/\/login(?:[/?#]|$)/i.test(p.url());

async function loginWasmer(p){
  stage('wasmer_login');
  await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{});await p.waitForTimeout(700);
  if(!onLogin(p))return;
  const i=p.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();await i.fill(account.username||account.email);await i.press('Enter');
  const q=p.locator('input[type=password]').first();await q.waitFor({state:'visible',timeout:20000});await q.fill(account.password);await q.press('Enter');
  const e=Date.now()+20000;while(Date.now()<e){if(!onLogin(p))return;await p.waitForTimeout(400);}throw new Error('wasmer_login_failed');
}
async function pollAdmin(ctx,ms=25000){const e=Date.now()+ms;while(Date.now()<e){for(const p of ctx.pages())if(p.url().startsWith(base)&&/\/wp-admin(?:\/|\?|$)/i.test(p.url())&&!/wp-login\.php/i.test(p.url()))return p;await new Promise(r=>setTimeout(r,500));}return null;}
async function enterAdmin(ctx,p){
  stage('wordpress_admin');
  for(let k=0;k<3;k++){
    await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{});await p.waitForTimeout(1000);
    let c=p.getByText(/WordPress Admin/i).first();
    if(!await c.isVisible().catch(()=>false)){const s=p.getByText(/^Settings$/i).first();if(await s.isVisible().catch(()=>false)){await s.click().catch(()=>{});await p.waitForTimeout(500);const w=p.getByText(/^WordPress$/i).first();if(await w.isVisible().catch(()=>false)){await w.click().catch(()=>{});await p.waitForTimeout(500);}c=p.getByText(/WordPress Admin/i).first();}}
    if(await c.isVisible().catch(()=>false)){const href=await c.getAttribute('href').catch(()=>null);if(href){const wp=await ctx.newPage();await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{});const f=await pollAdmin(ctx,18000);if(f)return f;}await c.click({noWaitAfter:true}).catch(()=>{});const f=await pollAdmin(ctx,22000);if(f)return f;}
  }
  throw new Error('magic_admin_failed');
}
async function nonce(wp){await wp.goto(`${base}/wp-admin/`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(700);let n=await wp.evaluate(()=>globalThis.wpApiSettings?.nonce||globalThis.wp?.apiSettings?.nonce||null).catch(()=>null);if(!n){const h=await wp.content();const m=h.match(/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i);if(m)n=m[1];}if(!n)throw new Error('wp_rest_nonce_missing');return n;}
async function api(ctx,n,path,{method='GET',json=null,soft=false,timeout=180000}={}){const headers={'X-WP-Nonce':n,Accept:'application/json'};let data;if(json!==null){headers['Content-Type']='application/json';data=JSON.stringify(json);}const r=await ctx.request.fetch(`${base}/wp-json${path}`,{method,headers,data,timeout,failOnStatusCode:false});const t=await r.text();let d;try{d=JSON.parse(t)}catch{d=t}if(!r.ok()&&!soft)throw new Error(`api_${method}_${path}:${r.status()}:${String(t).slice(0,300)}`);return soft?{ok:r.ok(),status:r.status(),data:d}:d;}
async function ensurePlugin(ctx,n,slug,prefix){const ps=await api(ctx,n,'/wp/v2/plugins?context=edit');let p=Array.isArray(ps)?ps.find(x=>String(x.plugin||'').startsWith(prefix)):null;if(!p)p=await api(ctx,n,'/wp/v2/plugins',{method:'POST',json:{slug,status:'active'}});else if(p.status!=='active')p=await api(ctx,n,`/wp/v2/plugins/${encodeURIComponent(p.plugin)}`,{method:'POST',json:{status:'active'}});return p;}
async function setNoIndex(wp){stage('wordpress_noindex');await wp.goto(`${base}/wp-admin/options-reading.php`,{waitUntil:'domcontentloaded',timeout:60000});const box=wp.locator('input[name="blog_public"]').first();await box.waitFor({state:'attached',timeout:15000});if(!await box.isChecked())await box.check();await wp.locator('#submit,input[type=submit]').first().click();await wp.waitForLoadState('domcontentloaded').catch(()=>{});result.noindex=await wp.locator('input[name="blog_public"]').first().isChecked().catch(()=>false);if(!result.noindex)throw new Error('blog_public_zero_not_confirmed');save();}
async function installActivateTheme(wp,slug,name){
  stage('theme_neve');
  await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000});
  let active=wp.locator(`.theme.active[data-slug="${slug}"],.theme.active`).filter({hasText:new RegExp(`\\b${name}\\b`,'i')}).first();if(await active.count()){result.theme=slug;save();return;}
  let card=wp.locator(`.theme[data-slug="${slug}"],.theme`).filter({hasText:new RegExp(`\\b${name}\\b`,'i')}).first();
  if(!await card.count()){
    await wp.goto(`${base}/wp-admin/theme-install.php?search=${encodeURIComponent(name)}`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1400);
    let link=wp.locator(`a[href*="action=install-theme"][href*="theme=${slug}"],a[href*="theme=${slug}"]`).first();let href=await link.getAttribute('href').catch(()=>null);
    if(!href){const h=await wp.content();const m=h.match(new RegExp(`href=["']([^"']*(?:action=install-theme[^"']*theme=${slug}|theme=${slug}[^"']*action=install-theme)[^"']*)["']`,'i'));if(m)href=m[1].replaceAll('&amp;','&');}
    if(!href)throw new Error(`${slug}_install_url_missing`);await wp.goto(new URL(href,base).href,{waitUntil:'domcontentloaded',timeout:120000});await wp.waitForTimeout(1000);
  }
  await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000});card=wp.locator(`.theme[data-slug="${slug}"],.theme`).filter({hasText:new RegExp(`\\b${name}\\b`,'i')}).first();if(!await card.count())throw new Error(`${slug}_not_installed`);
  active=wp.locator(`.theme.active[data-slug="${slug}"],.theme.active`).filter({hasText:new RegExp(`\\b${name}\\b`,'i')}).first();
  if(!await active.count()){const a=card.locator('a.activate,a[href*="action=activate"]').first();let href=await a.getAttribute('href').catch(()=>null);if(!href){const h=await card.innerHTML();const m=h.match(/href=["']([^"']*action=activate[^"']*)["']/i);if(m)href=m[1].replaceAll('&amp;','&');}if(!href)throw new Error(`${slug}_activate_url_missing`);await wp.goto(new URL(href,base).href,{waitUntil:'domcontentloaded',timeout:60000});}
  result.theme=slug;save();
}
async function removeCustomContent(ctx,n){
  stage('remove_custom_sample');
  for(const type of ['posts','pages']){for(let page=1;page<=10;page++){const r=await api(ctx,n,`/wp/v2/${type}?context=edit&per_page=100&page=${page}`,{soft:true});if(!r.ok||!Array.isArray(r.data)||!r.data.length)break;for(const x of r.data){await api(ctx,n,`/wp/v2/${type}/${x.id}?force=true`,{method:'DELETE',soft:true});}if(r.data.length<100)break;}}
}
function collectObjects(v,out=[]){if(Array.isArray(v)){for(const x of v)collectObjects(x,out);}else if(v&&typeof v==='object'){out.push(v);for(const x of Object.values(v))collectObjects(x,out);}return out;}
function scoreSite(o){const s=JSON.stringify(o).toLowerCase();let score=0;if(/photography studio/.test(s))score+=20;if(/photography/.test(s))score+=8;if(/gutenberg/.test(s))score+=5;if(o.remote_url||o.url)score+=2;return score;}
async function importOfficialDemo(ctx,n){
  stage('themeisle_catalog');
  const cat=await api(ctx,n,'/ti-sites-lib/v1/refresh_sites_data');
  const objs=collectObjects(cat?.data??cat).filter(o=>o&&typeof o==='object');
  const ranked=objs.map(o=>({o,s:scoreSite(o)})).filter(x=>x.s>0).sort((a,b)=>b.s-a.s);
  if(!ranked.length)throw new Error('photography_studio_not_found_in_themeisle_catalog');
  const siteData=ranked[0].o;result.matchedSite={title:siteData.title||siteData.name||siteData.slug||null,slug:siteData.slug||null,url:siteData.remote_url||siteData.url||null};save();
  const fetchAddress=siteData.remote_url||siteData.url;if(!fetchAddress)throw new Error('themeisle_demo_remote_url_missing');
  stage('themeisle_demo_data');
  const demoUrl=new URL('wp-json/ti-demo-data/data',String(fetchAddress).replace(/\/$/,'')+'/');demoUrl.searchParams.set('license','free');demoUrl.searchParams.set('ti_downloads','yes');
  const rr=await fetch(demoUrl,{headers:{Accept:'application/json','User-Agent':'Runner5OfficialNeveImport/1.0'}});if(!rr.ok)throw new Error(`themeisle_demo_data_http_${rr.status}`);const demo=await rr.json();const importData={...demo,...siteData};
  const mandatory={...(demo.mandatory_plugins||{})},optional={...(demo.recommended_plugins||{})},off=demo.default_off_recommended_plugins||[],downloads={...(demo.ti_downloads||{})};const pluginOptions={};for(const k of Object.keys(optional))pluginOptions[k]=!off.includes(k);for(const k of Object.keys(mandatory))pluginOptions[k]=true;for(const k of Object.keys(downloads))pluginOptions[k]=downloads[k]===false?false:true;
  stage('official_plugins');
  const pr=await api(ctx,n,'/ti-sites-lib/v1/install_plugins',{method:'POST',json:pluginOptions});if(pr?.success===false)throw new Error(`official_plugin_import_failed:${JSON.stringify(pr).slice(0,400)}`);result.plugins=pluginOptions;save();
  stage('official_content');
  const cr=await api(ctx,n,'/ti-sites-lib/v1/import_content',{method:'POST',json:{contentFile:importData.content_file,source:'remote',frontPage:importData.front_page,shopPages:importData.shop_pages,paymentForms:importData.payment_forms,masteriyoData:importData.masteriyo_data,demoSlug:importData.slug,editor:'gutenberg'}});if(cr?.success===false)throw new Error(`official_content_import_failed:${JSON.stringify(cr).slice(0,500)}`);
  stage('official_customizer');
  const mr=await api(ctx,n,'/ti-sites-lib/v1/import_theme_mods',{method:'POST',json:{source_url:importData.url,theme_mods:importData.theme_mods,wp_options:importData.wp_options}});if(mr?.success===false)throw new Error(`official_theme_mods_failed:${JSON.stringify(mr).slice(0,500)}`);
  stage('official_widgets');
  const wr=await api(ctx,n,'/ti-sites-lib/v1/import_widgets',{method:'POST',json:importData.widgets||{}});if(wr?.success===false)throw new Error(`official_widgets_failed:${JSON.stringify(wr).slice(0,500)}`);
}
async function verify(ctx,n){
  stage('verify_official_demo');
  const [pages,posts,media]=await Promise.all([api(ctx,n,'/wp/v2/pages?per_page=100&_fields=id,slug,title'),api(ctx,n,'/wp/v2/posts?per_page=100&_fields=id,slug,title'),api(ctx,n,'/wp/v2/media?per_page=100&_fields=id,source_url')]);
  result.pages=Array.isArray(pages)?pages.map(x=>({id:x.id,slug:x.slug,title:x.title?.rendered||''})):[];result.posts=Array.isArray(posts)?posts.map(x=>({id:x.id,slug:x.slug,title:x.title?.rendered||''})):[];result.mediaCount=Array.isArray(media)?media.length:0;
  const r=await fetch(`${base}/?verify=${Date.now()}`,{headers:{'Cache-Control':'no-cache','User-Agent':'Runner5OfficialDemoVerify/1.0'}});const h=await r.text();result.homeImages=(h.match(/<img\b/gi)||[]).length;result.homeLinks=(h.match(/<a\b/gi)||[]).length;const hasNeve=/\bneve\b|nv-(?:header|footer|container)|theme-neve/i.test(h);const hasNoIndex=/<meta[^>]+name=["']robots["'][^>]+noindex/i.test(h)||/noindex[^>]+nofollow/i.test(h);result.noindex=result.noindex&&hasNoIndex;save();
  if(!r.ok)throw new Error(`public_home_http_${r.status}`);if(!hasNeve)throw new Error('neve_public_marker_missing');if(!result.noindex)throw new Error('public_noindex_missing');if(result.pages.length<3)throw new Error(`official_demo_pages_too_few:${result.pages.length}`);if(result.mediaCount<5)throw new Error(`official_demo_media_too_few:${result.mediaCount}`);if(result.homeImages<3)throw new Error(`official_demo_home_images_too_few:${result.homeImages}`);
}

const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});const ctx=await browser.newContext({viewport:{width:1440,height:1100}});const p=await ctx.newPage();
try{await loginWasmer(p);const wp=await enterAdmin(ctx,p);await setNoIndex(wp);await installActivateTheme(wp,'neve','Neve');const n=await nonce(wp);const lib=await ensurePlugin(ctx,n,'templates-patterns-collection','templates-patterns-collection/');result.plugins.library=lib.status||'active';save();await removeCustomContent(ctx,n);await importOfficialDemo(ctx,n);await verify(ctx,n);result.status='READY';result.stage='done';save();}catch(e){result.status='FAILED';result.detail=String(e?.stack||e);save();console.error(result.detail);process.exitCode=1}finally{await browser.close();}
console.log(JSON.stringify(result,null,2));
