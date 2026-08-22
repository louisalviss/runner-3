import { chromium } from 'playwright-core';
import fs from 'fs';

const site = JSON.parse(fs.readFileSync('ops/site-factory/runner5-restore-lab-1.json','utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const base = String(site.siteUrl || 'https://runner5-restore-lab-1.wasmer.app/').replace(/\/$/,'');
const dashboard = site.dashboardUrl;
const out = '/tmp/runner5-astra-elementor-baseline.json';
const result = {
  status:'STARTING', baseline:'PRE', siteUrl:`${base}/`, theme:'astra', builder:'elementor',
  starter:{name:'Digital Agency', slug:'agency-02', source:'Astra Starter Templates', imported:false},
  plugins:{}, cleanup:{pages:0,posts:0,media:0,deactivated:[]},
  content:{pages:[],posts:[],mediaCount:0},
  verify:{http:0,restHttp:0,admin:true,astraMarker:false,oceanwpMarker:false,elementorMarker:false,noindex:false,homepageBytes:0,coreLinks:[]},
  stage:'init', detail:null, updatedAt:new Date().toISOString()
};
const save=()=>{result.updatedAt=new Date().toISOString();fs.writeFileSync(out,JSON.stringify(result,null,2));};
const stage=s=>{result.stage=s;console.log('STAGE',s);save();};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const onLogin=p=>/\/login(?:[/?#]|$)/i.test(p.url());

async function loginWasmer(p){
  stage('wasmer_login');
  await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{});
  await p.waitForTimeout(700);
  if(!onLogin(p)) return;
  const ident=p.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();
  await ident.fill(account.username||account.email); await ident.press('Enter');
  const pass=p.locator('input[type=password]').first(); await pass.waitFor({state:'visible',timeout:20000});
  await pass.fill(account.password); await pass.press('Enter');
  const end=Date.now()+20000; while(Date.now()<end){if(!onLogin(p)) return; await p.waitForTimeout(400);} throw new Error('wasmer_login_failed');
}
async function pollAdmin(ctx,ms=25000){const end=Date.now()+ms;while(Date.now()<end){for(const p of ctx.pages())if(p.url().startsWith(base)&&/\/wp-admin(?:\/|\?|$)/i.test(p.url())&&!/wp-login\.php/i.test(p.url()))return p;await sleep(500);}return null;}
async function enterAdmin(ctx,p){
  stage('wordpress_admin');
  for(let k=0;k<3;k++){
    await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{}); await p.waitForTimeout(1000);
    let c=p.getByText(/WordPress Admin/i).first();
    if(!await c.isVisible().catch(()=>false)){
      const s=p.getByText(/^Settings$/i).first(); if(await s.isVisible().catch(()=>false)){await s.click().catch(()=>{});await p.waitForTimeout(500);const w=p.getByText(/^WordPress$/i).first();if(await w.isVisible().catch(()=>false)){await w.click().catch(()=>{});await p.waitForTimeout(600);}c=p.getByText(/WordPress Admin/i).first();}
    }
    if(await c.isVisible().catch(()=>false)){
      const href=await c.getAttribute('href').catch(()=>null);
      if(href){const wp=await ctx.newPage();await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{});const f=await pollAdmin(ctx,18000);if(f)return f;}
      await c.click({noWaitAfter:true}).catch(()=>{});const f=await pollAdmin(ctx,22000);if(f)return f;
    }
  }
  throw new Error('magic_admin_failed');
}
async function getNonce(wp){
  await wp.goto(`${base}/wp-admin/`,{waitUntil:'domcontentloaded',timeout:60000}); await wp.waitForTimeout(600);
  let n=await wp.evaluate(()=>globalThis.wpApiSettings?.nonce||globalThis.wp?.apiSettings?.nonce||null).catch(()=>null);
  if(!n){const h=await wp.content();const m=h.match(/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i);if(m)n=m[1];}
  if(!n)throw new Error('wp_rest_nonce_missing'); return n;
}
async function api(ctx,nonce,path,{method='GET',json=null,soft=false,timeout=180000}={}){
  const headers={'X-WP-Nonce':nonce,Accept:'application/json'};let data;
  if(json!==null){headers['Content-Type']='application/json';data=JSON.stringify(json);}
  const r=await ctx.request.fetch(`${base}/wp-json${path}`,{method,headers,data,timeout,failOnStatusCode:false});
  const t=await r.text();let d;try{d=JSON.parse(t)}catch{d=t}
  if(!r.ok()){if(soft)return{ok:false,status:r.status(),data:d};throw new Error(`api_${method}_${path}:${r.status()}:${String(t).slice(0,260)}`)}
  return soft?{ok:true,status:r.status(),data:d}:d;
}
async function ensurePlugin(ctx,nonce,slug,prefix=`${slug}/`){
  const ps=await api(ctx,nonce,'/wp/v2/plugins?context=edit');let p=Array.isArray(ps)?ps.find(x=>String(x.plugin||'').startsWith(prefix)):null;
  if(!p)p=await api(ctx,nonce,'/wp/v2/plugins',{method:'POST',json:{slug,status:'active'}});
  else if(p.status!=='active')p=await api(ctx,nonce,`/wp/v2/plugins/${encodeURIComponent(p.plugin)}`,{method:'POST',json:{status:'active'}});
  result.plugins[slug]=p?.status||'active';save();return p;
}
async function deactivateOldPlugins(ctx,nonce){
  stage('deactivate_old_plugins');
  const ps=await api(ctx,nonce,'/wp/v2/plugins?context=edit');
  const old=['ocean-extra/','ocean-social-sharing/','ocean-custom-sidebar/','ultimate-addons-for-gutenberg/','sureforms/'];
  for(const p of Array.isArray(ps)?ps:[]){if(p.status==='active'&&old.some(x=>String(p.plugin||'').startsWith(x))){const r=await api(ctx,nonce,`/wp/v2/plugins/${encodeURIComponent(p.plugin)}`,{method:'POST',json:{status:'inactive'},soft:true});if(r.ok)result.cleanup.deactivated.push(p.plugin);}}
  save();
}
async function ensureAstra(wp){
  stage('astra_theme');
  await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(900);
  let astra=wp.locator('.theme[data-slug="astra"],.theme').filter({hasText:/\bAstra\b/i}).first();
  if(!await astra.count()){
    await wp.goto(`${base}/wp-admin/theme-install.php?search=astra`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1200);
    const card=wp.locator('.theme[data-slug="astra"],.theme').filter({hasText:/\bAstra\b/i}).first();if(!await card.count())throw new Error('astra_theme_card_missing');
    const install=card.locator('a.install-now,button.install-now').first();if(!await install.count())throw new Error('astra_install_control_missing');
    const href=await install.getAttribute('href').catch(()=>null);if(href)await wp.goto(new URL(href,base).href,{waitUntil:'domcontentloaded',timeout:120000});else{await install.click();await wp.waitForTimeout(7000);}
    await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000});astra=wp.locator('.theme[data-slug="astra"],.theme').filter({hasText:/\bAstra\b/i}).first();
  }
  if(!await astra.count())throw new Error('astra_not_installed');
  if(!await astra.evaluate(el=>el.classList.contains('active')).catch(()=>false)){
    const activate=astra.locator('a.activate').first();if(!await activate.count())throw new Error('astra_activate_control_missing');const href=await activate.getAttribute('href');if(!href)throw new Error('astra_activate_href_missing');await wp.goto(new URL(href,base).href,{waitUntil:'domcontentloaded',timeout:60000});
  }
  await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000});
  const active=wp.locator('.theme.active[data-slug="astra"],.theme.active').filter({hasText:/\bAstra\b/i}).first();if(!await active.count())throw new Error('astra_activation_failed');
}
async function clickOne(page,res,timeout=850){for(const re of res){for(const l of [page.getByRole('button',{name:re}).first(),page.getByRole('link',{name:re}).first(),page.getByText(re,{exact:false}).first()])if(await l.isVisible({timeout}).catch(()=>false)){await l.click().catch(()=>{});await page.waitForTimeout(650);return true;}}return false;}
async function locateDigitalAgency(wp){
  stage('locate_digital_agency');
  await wp.goto(`${base}/wp-admin/themes.php?page=starter-templates`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(2500);
  await clickOne(wp,[/Build with Templates/i,/Classic Starter Templates/i,/Get Started/i,/Start Building/i]);await wp.waitForTimeout(1200);
  await clickOne(wp,[/^Elementor$/i,/Elementor/i],700);
  const search=wp.locator('input[type=search],input[placeholder*="Search" i]').first();if(await search.isVisible().catch(()=>false)){await search.fill('Digital Agency');await wp.waitForTimeout(1800);}
  let card=wp.getByText(/^Digital Agency$/i).first();if(!await card.isVisible({timeout:12000}).catch(()=>false))card=wp.getByText(/Digital Agency/i).first();
  if(!await card.isVisible().catch(()=>false))throw new Error('digital_agency_template_not_found');
  await card.click();await wp.waitForTimeout(1500);await clickOne(wp,[/^Elementor$/i,/Elementor/i],500);
}
async function clearContent(ctx,nonce){
  stage('clean_old_content');
  for(const [type,key] of [['pages','pages'],['posts','posts']]){
    const xs=await api(ctx,nonce,`/wp/v2/${type}?per_page=100&context=edit`);for(const x of Array.isArray(xs)?xs:[]){const r=await api(ctx,nonce,`/wp/v2/${type}/${x.id}?force=true`,{method:'DELETE',soft:true});if(r.ok)result.cleanup[key]++;}
  }
  const media=await api(ctx,nonce,'/wp/v2/media?per_page=100&context=edit');for(const x of Array.isArray(media)?media:[]){const r=await api(ctx,nonce,`/wp/v2/media/${x.id}?force=true`,{method:'DELETE',soft:true});if(r.ok)result.cleanup.media++;}
  save();
}
async function importTemplate(wp){
  stage('import_digital_agency');
  let started=false;
  for(let i=0;i<22;i++){
    if(await clickOne(wp,[/Submit & Build My Website/i,/Import Complete Site/i,/Import Site/i,/Build My Website/i,/Start Import/i],650)){started=true;break;}
    if(await clickOne(wp,[/Skip & Continue/i,/Skip this step/i,/Continue/i,/Next/i],650))continue;
    await wp.waitForTimeout(500);
  }
  if(!started)throw new Error('starter_import_button_not_reached');
  const end=Date.now()+9*60*1000;
  while(Date.now()<end){const t=await wp.locator('body').innerText().catch(()=>'');if(/View Your Website|Your Website is Ready|Congratulations|Website Ready|Hurray/i.test(t)){result.starter.imported=true;save();return;}if(/import failed|failed to import|something went wrong/i.test(t))throw new Error(`starter_import_failed:${t.slice(-450)}`);await wp.waitForTimeout(2500);}
  throw new Error('starter_import_timeout');
}
async function upsertPage(ctx,n,title,slug){const xs=await api(ctx,n,`/wp/v2/pages?slug=${encodeURIComponent(slug)}&context=edit`);if(Array.isArray(xs)&&xs[0])return xs[0];return api(ctx,n,'/wp/v2/pages',{method:'POST',json:{title,slug,status:'publish',content:`<!-- wp:group {"layout":{"type":"constrained"}} --><div class="wp-block-group"><!-- wp:heading {"level":1} --><h1 class="wp-block-heading">${title}</h1><!-- /wp:heading --><!-- wp:paragraph --><p>Insights, practical guidance and updates from our team.</p><!-- /wp:paragraph --></div><!-- /wp:group -->`}});}
async function ensureRealBlog(ctx,n,wp){
  stage('ensure_realistic_blog');
  const blog=await upsertPage(ctx,n,'Blog','blog');
  const titles=['How to Build a Website That Converts','A Practical Guide to Better Landing Pages','What Makes a Strong Small-Business Brand','Five SEO Basics Every Website Needs','How to Plan Content Without Wasting Time','When It Is Time to Redesign Your Website'];
  let media=await api(ctx,n,'/wp/v2/media?per_page=20&context=edit').catch(()=>[]); if(!Array.isArray(media))media=[];
  for(let i=0;i<titles.length;i++){
    const title=titles[i],slug=`agency-guide-${i+1}`;const xs=await api(ctx,n,`/wp/v2/posts?slug=${slug}&context=edit`);if(Array.isArray(xs)&&xs[0])continue;
    const content=`<!-- wp:paragraph --><p>A good website should make the next step obvious. This guide covers the decisions that matter most for a growing business.</p><!-- /wp:paragraph --><!-- wp:heading --><h2 class="wp-block-heading">Start with the user</h2><!-- /wp:heading --><!-- wp:paragraph --><p>Clear structure, useful information and credible proof usually matter more than visual novelty. Focus each page on one primary job and remove anything that distracts from it.</p><!-- /wp:paragraph --><!-- wp:heading --><h2 class="wp-block-heading">Measure what changes</h2><!-- /wp:heading --><!-- wp:paragraph --><p>Track leads, engagement and performance before and after meaningful changes so improvements are based on evidence rather than preference.</p><!-- /wp:paragraph -->`;
    const body={title,slug,status:'publish',content,excerpt:'Practical website and digital marketing guidance for growing businesses.'};if(media[i]?.id)body.featured_media=media[i].id;await api(ctx,n,'/wp/v2/posts',{method:'POST',json:body});
  }
  await wp.goto(`${base}/wp-admin/options-reading.php`,{waitUntil:'domcontentloaded',timeout:60000});
  const postsSel=wp.locator('select[name="page_for_posts"]').first();if(await postsSel.count())await postsSel.selectOption(String(blog.id));
  const submit=wp.locator('#submit,input[type=submit]').first();if(await submit.count())await submit.click();await wp.waitForLoadState('domcontentloaded').catch(()=>{});
}
async function setNoindex(wp){
  stage('noindex');await wp.goto(`${base}/wp-admin/options-reading.php`,{waitUntil:'domcontentloaded',timeout:60000});
  const box=wp.locator('input[name="blog_public"]').first();if(await box.count()&&!await box.isChecked())await box.check();
  const submit=wp.locator('#submit,input[type=submit]').first();if(await submit.count())await submit.click();await wp.waitForLoadState('domcontentloaded').catch(()=>{});
}
async function verify(ctx,n){
  stage('verify');
  const hr=await fetch(`${base}/?baseline=${Date.now()}`,{headers:{'Cache-Control':'no-cache'}});const html=await hr.text();result.verify.http=hr.status;result.verify.homepageBytes=Buffer.byteLength(html);
  const rr=await fetch(`${base}/wp-json/`,{headers:{'Cache-Control':'no-cache'}});result.verify.restHttp=rr.status;
  result.verify.astraMarker=/\bast-(?:desktop|header|container|primary|site|plain-container)/i.test(html)||/astra/i.test(html);
  result.verify.oceanwpMarker=/oceanwp|oceanwp-style|oceanwp-theme/i.test(html);
  result.verify.elementorMarker=/elementor/i.test(html);
  result.verify.noindex=/<meta[^>]+name=["']robots["'][^>]+noindex/i.test(html)||/noindex[^>]+nofollow/i.test(html);
  const pages=await api(ctx,n,'/wp/v2/pages?per_page=100&_fields=id,slug,title,status');const posts=await api(ctx,n,'/wp/v2/posts?per_page=100&_fields=id,slug,title,status,featured_media');const media=await api(ctx,n,'/wp/v2/media?per_page=100&_fields=id');
  result.content.pages=(Array.isArray(pages)?pages:[]).map(x=>({id:x.id,slug:x.slug,title:x.title?.rendered||'',status:x.status}));
  result.content.posts=(Array.isArray(posts)?posts:[]).map(x=>({id:x.id,slug:x.slug,title:x.title?.rendered||'',status:x.status,featured_media:x.featured_media||0}));
  result.content.mediaCount=Array.isArray(media)?media.length:0;
  const lower=result.content.pages.map(x=>`${x.slug} ${x.title}`).join(' ').toLowerCase();for(const k of ['home','about','service','blog','contact'])if(lower.includes(k))result.verify.coreLinks.push(k);
  save();
  const errs=[];if(hr.status!==200)errs.push(`home_${hr.status}`);if(rr.status!==200)errs.push(`rest_${rr.status}`);if(!result.verify.astraMarker)errs.push('astra_marker_missing');if(result.verify.oceanwpMarker)errs.push('oceanwp_marker_present');if(!result.verify.elementorMarker)errs.push('elementor_marker_missing');if(!result.verify.noindex)errs.push('noindex_missing');if(result.verify.coreLinks.length<5)errs.push(`core_pages_${result.verify.coreLinks.join(',')}`);if(result.content.posts.length<6)errs.push(`posts_${result.content.posts.length}`);if(result.content.mediaCount<6)errs.push(`media_${result.content.mediaCount}`);if(errs.length)throw new Error(`baseline_verify_failed:${errs.join('|')}`);
}

save();
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({viewport:{width:1440,height:1100}});const p=await ctx.newPage();
try{
  await loginWasmer(p);const wp=await enterAdmin(ctx,p);await ensureAstra(wp);let n=await getNonce(wp);
  await ensurePlugin(ctx,n,'astra-sites','astra-sites/');await ensurePlugin(ctx,n,'elementor','elementor/');await ensurePlugin(ctx,n,'wpforms-lite','wpforms-lite/');await deactivateOldPlugins(ctx,n);
  await locateDigitalAgency(wp);n=await getNonce(wp);await clearContent(ctx,n);await importTemplate(wp);n=await getNonce(wp);await ensureRealBlog(ctx,n,wp);await setNoindex(wp);n=await getNonce(wp);await verify(ctx,n);
  result.status='PRE_BASELINE_READY';result.stage='done';save();
}catch(e){result.status='FAILED';result.detail=String(e?.stack||e);save();console.error(result.detail);process.exitCode=1;}finally{await browser.close();}
console.log(JSON.stringify(result,null,2));
