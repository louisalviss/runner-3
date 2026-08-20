import { chromium } from 'playwright-core';
import fs from 'fs';

const SITE_STATE = 'ops/site-factory/runner5-restore-lab-1.json';
const site = JSON.parse(fs.readFileSync(SITE_STATE, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(site.siteUrl || 'https://runner5-restore-lab-1.wasmer.app/').replace(/\/$/, '');
const dashboard = site.dashboardUrl;
const out = '/tmp/runner5-wordpress-retheme.json';
const result = {
  status: 'STARTING', siteUrl: `${base}/`, noindex: false, theme: null,
  plugins: {}, starter: { name: 'Nutritionist', builder: 'Block Editor/Spectra', imported: false },
  verify: { pageTitles: [], noindexMeta: false, astraMarker: false }, stage: 'init', detail: null,
  updatedAt: new Date().toISOString(),
};
const save = () => { result.updatedAt = new Date().toISOString(); fs.writeFileSync(out, JSON.stringify(result, null, 2)); };
const stage = s => { result.stage = s; console.log('STAGE', s); save(); };

const onLogin = p => /\/login(?:[/?#]|$)/i.test(p.url());
async function loginWasmer(p) {
  stage('wasmer_login');
  for (let attempt = 0; attempt < 3; attempt++) {
    await p.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => null);
    await p.waitForTimeout(700);
    if (!onLogin(p)) return;
    const ident = p.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();
    if (!await ident.isVisible().catch(() => false)) continue;
    await ident.fill(account.username || account.email);
    await ident.press('Enter').catch(() => {});
    const pass = p.locator('input[type=password]').first();
    if (!await pass.waitFor({ state: 'visible', timeout: 20000 }).then(() => true).catch(() => false)) continue;
    await pass.fill(account.password);
    await pass.press('Enter').catch(() => {});
    const end = Date.now() + 20000;
    while (Date.now() < end) { if (!onLogin(p)) return; await p.waitForTimeout(400); }
  }
  throw new Error('wasmer_login_failed');
}
async function pollAdmin(ctx, ms=25000) {
  const end=Date.now()+ms;
  while(Date.now()<end){
    for(const p of ctx.pages()){ if(p.url().startsWith(base) && /\/wp-admin(?:\/|\?|$)/i.test(p.url()) && !/wp-login\.php/i.test(p.url())) return p; }
    await new Promise(r=>setTimeout(r,500));
  }
  return null;
}
async function enterAdmin(ctx,p){
  stage('wordpress_admin');
  for(let k=0;k<3;k++){
    await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null); await p.waitForTimeout(1200);
    let c=p.getByText(/WordPress Admin/i).first();
    if(!await c.isVisible().catch(()=>false)){
      const settings=p.getByText(/^Settings$/i).first();
      if(await settings.isVisible().catch(()=>false)){ await settings.click().catch(()=>{}); await p.waitForTimeout(700); const w=p.getByText(/^WordPress$/i).first(); if(await w.isVisible().catch(()=>false)){await w.click().catch(()=>{}); await p.waitForTimeout(700);} c=p.getByText(/WordPress Admin/i).first(); }
    }
    if(await c.isVisible().catch(()=>false)){
      const href=await c.getAttribute('href').catch(()=>null);
      if(href){ const wp=await ctx.newPage(); await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null); const found=await pollAdmin(ctx,18000); if(found)return found; }
      await c.click({noWaitAfter:true}).catch(()=>{}); const found=await pollAdmin(ctx,22000); if(found)return found;
    }
  }
  throw new Error('magic_admin_failed');
}
async function getNonce(wp){
  await wp.goto(`${base}/wp-admin/`,{waitUntil:'domcontentloaded',timeout:60000}); await wp.waitForTimeout(700);
  let n=await wp.evaluate(()=>globalThis.wpApiSettings?.nonce||globalThis.wp?.apiSettings?.nonce||null).catch(()=>null);
  if(!n){ const h=await wp.content(); const m=h.match(/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i); if(m)n=m[1]; }
  if(!n) throw new Error('wp_rest_nonce_missing'); return n;
}
async function api(ctx,nonce,path,{method='GET',json=null,soft=false,timeout=90000}={}){
  const headers={'X-WP-Nonce':nonce,Accept:'application/json'}; let data;
  if(json!==null){headers['Content-Type']='application/json';data=JSON.stringify(json);}
  const r=await ctx.request.fetch(`${base}/wp-json${path}`,{method,headers,data,timeout,failOnStatusCode:false}); const t=await r.text(); let d; try{d=JSON.parse(t)}catch{d=t}
  if(!r.ok()){if(soft)return{ok:false,status:r.status(),data:d}; throw new Error(`api_${method}_${path}:${r.status()}:${String(t).slice(0,250)}`)}
  return soft?{ok:true,status:r.status(),data:d}:d;
}
async function ensurePlugin(ctx,nonce,slug,startsWith){
  const plugins=await api(ctx,nonce,'/wp/v2/plugins?context=edit');
  let p=Array.isArray(plugins)?plugins.find(x=>String(x.plugin||'').startsWith(startsWith)):null;
  if(!p) p=await api(ctx,nonce,'/wp/v2/plugins',{method:'POST',json:{slug,status:'active'}});
  else if(p.status!=='active') p=await api(ctx,nonce,`/wp/v2/plugins/${encodeURIComponent(p.plugin)}`,{method:'POST',json:{status:'active'}});
  return p;
}
async function setNoIndex(wp){
  stage('wordpress_noindex');
  await wp.goto(`${base}/wp-admin/options-reading.php`,{waitUntil:'domcontentloaded',timeout:60000});
  const box=wp.locator('input[name="blog_public"]').first();
  await box.waitFor({state:'attached',timeout:20000});
  if(!await box.isChecked()) await box.check();
  await wp.locator('#submit,input[type=submit]').first().click();
  await wp.waitForLoadState('domcontentloaded').catch(()=>{});
  result.noindex=await wp.locator('input[name="blog_public"]').first().isChecked().catch(()=>false); save();
  if(!result.noindex) throw new Error('blog_public_zero_not_confirmed');
}
async function activateAstra(wp){
  stage('astra_theme');
  await wp.goto(`${base}/wp-admin/theme-install.php?search=astra`,{waitUntil:'domcontentloaded',timeout:60000}); await wp.waitForTimeout(1500);
  let card=wp.locator('.theme').filter({hasText:/\bAstra\b/i}).first();
  if(!await card.count()) throw new Error('astra_theme_card_missing');
  let install=card.getByRole('button',{name:/install/i}).first();
  if(!await install.count()) install=card.locator('a.install-now').first();
  if(await install.isVisible().catch(()=>false)){ await install.click(); await wp.waitForTimeout(1500); }
  const end=Date.now()+60000; let activated=false;
  while(Date.now()<end){
    const activate=card.getByRole('button',{name:/activate/i}).first();
    const activateLink=card.locator('a.activate').first();
    if(await activate.isVisible().catch(()=>false)){await activate.click();activated=true;break;}
    if(await activateLink.isVisible().catch(()=>false)){await activateLink.click();activated=true;break;}
    if(/active/i.test(await card.innerText().catch(()=>''))){activated=true;break;}
    await wp.waitForTimeout(1000);
  }
  if(!activated){
    await wp.goto(`${base}/wp-admin/themes.php`,{waitUntil:'domcontentloaded',timeout:60000});
    const active=wp.locator('.theme.active').filter({hasText:/\bAstra\b/i}).first();
    if(!await active.count()) throw new Error('astra_activation_failed');
  }
  result.theme='astra'; save();
}
async function clickVisible(page,names,timeout=1500){
  for(const name of names){
    const re=name instanceof RegExp?name:new RegExp(name,'i');
    for(const loc of [page.getByRole('button',{name:re}).first(),page.getByRole('link',{name:re}).first(),page.getByText(re,{exact:false}).first()]){
      if(await loc.isVisible({timeout}).catch(()=>false)){await loc.click().catch(()=>{}); await page.waitForTimeout(700); return true;}
    }
  }
  return false;
}
async function importStarter(wp){
  stage('starter_templates');
  await wp.goto(`${base}/wp-admin/themes.php?page=starter-templates`,{waitUntil:'domcontentloaded',timeout:60000}); await wp.waitForTimeout(2500);
  await clickVisible(wp,[/Build with Templates/i,/Get Started/i,/Start Building/i],1000);
  await wp.waitForTimeout(1800);
  // Prefer native blocks/Spectra whenever the builder chooser is shown.
  await clickVisible(wp,[/Block Editor/i,/Spectra/i,/Gutenberg/i],700);
  const search=wp.locator('input[type=search],input[placeholder*="Search" i]').first();
  if(await search.isVisible().catch(()=>false)){await search.fill('Nutritionist'); await wp.waitForTimeout(1800);}
  let nutrition=wp.getByText(/^Nutritionist$/i).first();
  if(!await nutrition.isVisible({timeout:12000}).catch(()=>false)) nutrition=wp.getByText(/Nutritionist/i).first();
  if(!await nutrition.isVisible().catch(()=>false)) throw new Error('nutritionist_template_not_found');
  await nutrition.click(); await wp.waitForTimeout(1800);
  await clickVisible(wp,[/Block Editor/i,/Spectra/i,/Gutenberg/i],700);
  // Walk through the classic import wizard, skipping optional branding/AI steps.
  for(let i=0;i<12;i++){
    if(await clickVisible(wp,[/Submit & Build My Website/i,/Import Complete Site/i,/Import Site/i,/Build My Website/i],600)) break;
    if(await clickVisible(wp,[/Skip & Continue/i,/Continue/i,/Next/i],600)) continue;
    break;
  }
  const deadline=Date.now()+8*60*1000;
  while(Date.now()<deadline){
    const text=(await wp.locator('body').innerText().catch(()=>''));
    if(/View Your Website|Your Website is Ready|Congratulations|Website Ready/i.test(text)){result.starter.imported=true;save();return;}
    if(/import failed|something went wrong|failed to import/i.test(text)) throw new Error(`starter_import_failed:${text.slice(-400)}`);
    // Some versions expose the final import button only after plugin installation finishes.
    await clickVisible(wp,[/Submit & Build My Website/i,/Import Complete Site/i,/Import Site/i],400);
    await wp.waitForTimeout(3000);
  }
  // UI completion copy changes frequently; public verification below is authoritative.
}
async function verifyPublic(){
  stage('verify_public');
  const [home,pages]=await Promise.all([
    fetch(`${base}/`,{headers:{'Cache-Control':'no-cache'}}).then(r=>r.text()),
    fetch(`${base}/wp-json/wp/v2/pages?per_page=100&_fields=title,slug&context=view&_=${Date.now()}`).then(r=>r.json()).catch(()=>[]),
  ]);
  result.verify.pageTitles=Array.isArray(pages)?pages.map(x=>x?.title?.rendered||x?.slug).filter(Boolean):[];
  result.verify.noindexMeta=/<meta[^>]+name=["']robots["'][^>]+noindex/i.test(home)||/noindex[^>]+nofollow/i.test(home);
  result.verify.astraMarker=/\bast-(?:desktop|header|container|primary|site|plain-container)/i.test(home)||/astra/i.test(home);
  const wanted=['about','program','success','blog','contact'];
  const joined=result.verify.pageTitles.join(' ').toLowerCase();
  const rich=wanted.filter(x=>joined.includes(x)).length>=4 && result.verify.pageTitles.length>=6;
  result.starter.imported=Boolean(result.starter.imported||rich);
  save();
  if(!result.verify.noindexMeta) throw new Error('public_noindex_meta_missing');
  if(!result.verify.astraMarker) throw new Error('public_astra_marker_missing');
  if(!result.starter.imported) throw new Error(`starter_content_not_verified:${result.verify.pageTitles.join('|')}`);
}

const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({viewport:{width:1440,height:1100}}); const p=await ctx.newPage();
try{
  await loginWasmer(p); const wp=await enterAdmin(ctx,p);
  await setNoIndex(wp);
  await activateAstra(wp);
  const nonce=await getNonce(wp);
  const st=await ensurePlugin(ctx,nonce,'astra-sites','astra-sites/'); result.plugins.starterTemplates=st.status||'active';
  const sp=await ensurePlugin(ctx,nonce,'ultimate-addons-for-gutenberg','ultimate-addons-for-gutenberg/'); result.plugins.spectra=sp.status||'active'; save();
  await importStarter(wp);
  await verifyPublic();
  result.status='READY'; result.stage='done'; save();
}catch(e){result.status='FAILED';result.detail=String(e?.stack||e);save();console.error(result.detail);process.exitCode=1}
finally{await browser.close();}
console.log(JSON.stringify(result,null,2));
