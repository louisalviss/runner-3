import { chromium } from 'playwright-core';
import fs from 'fs';

const slug='runner5-restore-lab-1';
const statePath=`ops/site-factory/${slug}.json`;
if(!fs.existsSync(statePath)) throw new Error(`missing ${statePath}`);
if(!fs.existsSync('/tmp/wasmer-account.json')) throw new Error('missing decrypted Wasmer account');
const site=JSON.parse(fs.readFileSync(statePath,'utf8'));
const account=JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const base=String(site.siteUrl||`https://${slug}.wasmer.app/`).replace(/\/$/,'');
const dashboard=site.dashboardUrl||`https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName||slug)}`;
const out='/tmp/runner5-restore-lab-seed.json';
const safe={status:'starting',siteSlug:slug,siteUrl:base+'/',mode:'rest-api-seed',applicationPassword:false,backupPlugin:null,activeTheme:null,pages:0,posts:0,media:0,categories:0,homepageHttp:null,steps:[],detail:null,updatedAt:new Date().toISOString()};
const save=()=>{safe.updatedAt=new Date().toISOString();fs.writeFileSync(out,JSON.stringify(safe,null,2));};
const step=s=>{safe.steps.push(s);console.log('STEP',s);save();};
const body=async p=>(await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();

async function loginWasmer(page){
  step('wasmer_login');
  await page.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:45000});
  const ident=page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  await ident.waitFor({state:'visible',timeout:12000});
  await ident.fill(account.username||account.email);
  const next=page.locator('button').filter({hasText:/continue|next|log in|sign in/i}).first();
  if(await next.count()&&await next.isVisible().catch(()=>false)) await next.click({noWaitAfter:true}); else await ident.press('Enter');
  const pass=page.locator('input[type=password]').first();
  await pass.waitFor({state:'visible',timeout:12000});
  await pass.fill(account.password);
  const submit=page.locator('button,input[type=submit]').filter({hasText:/continue|log in|sign in/i}).first();
  if(await submit.count()&&await submit.isVisible().catch(()=>false)) await submit.click({noWaitAfter:true}); else await pass.press('Enter');
  await page.waitForTimeout(3500);
  if(/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('wasmer_login_failed');
}
async function findAdminControl(page){
  const t=page.getByText(/WordPress Admin/i).first();
  if(!(await t.count())||!(await t.isVisible().catch(()=>false))) return null;
  const a=t.locator('xpath=ancestor-or-self::a[@href] | ancestor-or-self::button').first();
  return await a.count()?a:t;
}
async function pollAdmin(ctx,timeout=25000){
  const end=Date.now()+timeout;
  while(Date.now()<end){for(const p of ctx.pages()){const u=p.url();if(u.startsWith(base)&&/\/wp-admin(?:\/|\?|$)/i.test(u)&&!/wp-login\.php/i.test(u)) return p;}await new Promise(r=>setTimeout(r,500));}return null;
}
async function enterAdmin(ctx,page){
  step('wordpress_admin');
  for(let n=1;n<=2;n++){
    await page.goto(dashboard,{waitUntil:'domcontentloaded',timeout:45000});await page.waitForTimeout(1300);
    let control=await findAdminControl(page);
    if(!control){const settings=page.getByText(/^Settings$/i).first();if(await settings.count()&&await settings.isVisible().catch(()=>false)){await settings.click({noWaitAfter:true}).catch(()=>{});await page.waitForTimeout(700);const w=page.getByText(/^WordPress$/i).first();if(await w.count()&&await w.isVisible().catch(()=>false)){await w.click({noWaitAfter:true}).catch(()=>{});await page.waitForTimeout(900);}control=await findAdminControl(page);}}
    if(control){
      const href=await control.getAttribute('href').catch(()=>null);
      if(href){const wp=await ctx.newPage();await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null);const found=await pollAdmin(ctx,15000);if(found)return found;await wp.close().catch(()=>{});}
      await control.click({noWaitAfter:true}).catch(()=>{});const found=await pollAdmin(ctx,18000);if(found)return found;
    }
  }
  throw new Error('magic_admin_failed');
}
async function createApplicationPassword(wp){
  step('application_password');
  const success=`${base}/?runner5-rest-seed=authorized`;
  const u=new URL(`${base}/wp-admin/authorize-application.php`);
  u.searchParams.set('app_name','Runner5 Restore Lab Seed');
  u.searchParams.set('success_url',success);
  await wp.goto(u.href,{waitUntil:'domcontentloaded',timeout:45000});await wp.waitForTimeout(700);
  const txt=await body(wp);
  if(/application passwords.*not available|requires https|not currently compatible/i.test(txt)) throw new Error('application_passwords_unavailable');
  let approve=wp.locator('input[type=submit][name=approve],button[name=approve],#approve').first();
  if(!(await approve.count())) approve=wp.locator('button,input[type=submit]').filter({hasText:/approve|authorize/i}).first();
  if(!(await approve.count())) throw new Error(`application_password_approve_missing:${txt.slice(0,400)}`);
  await approve.click({noWaitAfter:true});
  const end=Date.now()+20000;
  while(Date.now()<end){
    const cur=new URL(wp.url());
    const username=cur.searchParams.get('user_login');const password=cur.searchParams.get('password');
    if(username&&password){safe.applicationPassword=true;save();return{username,password:password.replace(/\s+/g,'')};}
    await wp.waitForTimeout(400);
  }
  throw new Error(`application_password_callback_missing:${wp.url()}`);
}
function authHeader(cred){return 'Basic '+Buffer.from(`${cred.username}:${cred.password}`).toString('base64');}
async function api(cred,path,{method='GET',json=null,headers={},raw=null}={}){
  const h={Authorization:authHeader(cred),Accept:'application/json',...headers};
  let bodyData;
  if(json!==null){h['Content-Type']='application/json';bodyData=JSON.stringify(json);} else if(raw!==null) bodyData=raw;
  const r=await fetch(`${base}/wp-json${path}`,{method,headers:h,body:bodyData});
  const text=await r.text();let data;try{data=JSON.parse(text);}catch{data=text;}
  if(!r.ok) throw new Error(`api_${method}_${path}:${r.status}:${String(text).slice(0,350)}`);
  return{data,headers:r.headers,status:r.status};
}
async function ensurePlugin(cred,slugName){
  step(`plugin_${slugName}`);
  const list=await api(cred,'/wp/v2/plugins?context=edit');
  let p=Array.isArray(list.data)?list.data.find(x=>String(x.plugin||'').startsWith(slugName+'/')||x.textdomain===slugName):null;
  if(!p){p=(await api(cred,'/wp/v2/plugins',{method:'POST',json:{slug:slugName,status:'active'}})).data;}
  else if(p.status!=='active'){const enc=encodeURIComponent(p.plugin);p=(await api(cred,`/wp/v2/plugins/${enc}`,{method:'POST',json:{status:'active'}})).data;}
  return p;
}
async function upsertTerm(cred,name,slugVal){
  const found=await api(cred,`/wp/v2/categories?slug=${encodeURIComponent(slugVal)}&per_page=1`);
  if(Array.isArray(found.data)&&found.data[0])return found.data[0];
  return (await api(cred,'/wp/v2/categories',{method:'POST',json:{name,slug:slugVal}})).data;
}
async function upsertPost(cred,type,{title,slug:slugVal,content,status='publish',categories=[],featured_media=0}){
  const found=await api(cred,`/wp/v2/${type}?slug=${encodeURIComponent(slugVal)}&status=any&per_page=1&context=edit`);
  const payload={title,slug:slugVal,content,status};if(categories.length)payload.categories=categories;if(featured_media)payload.featured_media=featured_media;
  if(Array.isArray(found.data)&&found.data[0]) return (await api(cred,`/wp/v2/${type}/${found.data[0].id}`,{method:'POST',json:payload})).data;
  return (await api(cred,`/wp/v2/${type}`,{method:'POST',json:payload})).data;
}
async function ensureMedia(cred,index){
  const filename=`restore-lab-${index}.png`;
  const search=await api(cred,`/wp/v2/media?search=${encodeURIComponent('Restore Lab Image '+index)}&per_page=1&context=edit`);
  if(Array.isArray(search.data)&&search.data[0])return search.data[0];
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nH0AAAAASUVORK5CYII=','base64');
  const r=await api(cred,'/wp/v2/media',{method:'POST',headers:{'Content-Type':'image/png','Content-Disposition':`attachment; filename="${filename}"`},raw:png});
  const m=r.data;await api(cred,`/wp/v2/media/${m.id}`,{method:'POST',json:{title:`Restore Lab Image ${index}`,alt_text:`Restore Lab test image ${index}`,caption:`Restore Lab media ${index}`}});return m;
}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({ignoreHTTPSErrors:true});const page=await ctx.newPage();
try{
  save();await loginWasmer(page);const wp=await enterAdmin(ctx,page);const cred=await createApplicationPassword(wp);
  step('verify_api');const me=(await api(cred,'/wp/v2/users/me?context=edit')).data;console.log('API user',me.id,me.slug);
  const backup=await ensurePlugin(cred,'all-in-one-wp-migration');safe.backupPlugin={plugin:backup.plugin,status:backup.status,version:backup.version||null};save();
  step('theme_snapshot');const themes=(await api(cred,'/wp/v2/themes?status=active')).data;safe.activeTheme=Array.isArray(themes)&&themes[0]?{stylesheet:themes[0].stylesheet,name:themes[0].name?.rendered||themes[0].name,version:themes[0].version}:null;save();
  step('site_settings');await api(cred,'/wp/v2/settings',{method:'POST',json:{title:'Runner5 Restore Lab Demo',description:'Controlled backup and restore verification site',posts_per_page:10}});
  step('categories');const cats=[];for(const [name,s] of [['Restore Lab','restore-lab'],['Performance','performance'],['Migration','migration']])cats.push(await upsertTerm(cred,name,s));safe.categories=cats.length;save();
  step('media');const media=[];for(let i=1;i<=3;i++)media.push(await ensureMedia(cred,i));safe.media=media.length;save();
  step('pages');const pages=[
    ['Home','restore-lab-home','<!-- wp:heading {"level":1} --><h1 class="wp-block-heading">Restore Lab Demo</h1><!-- /wp:heading --><!-- wp:paragraph --><p>This site exists to verify full WordPress backup and restore integrity.</p><!-- /wp:paragraph -->'],
    ['About','restore-lab-about','<!-- wp:heading --><h2 class="wp-block-heading">About this test</h2><!-- /wp:heading --><!-- wp:paragraph --><p>Pages, posts, media, plugins, settings and theme state are intentionally included.</p><!-- /wp:paragraph -->'],
    ['Services','restore-lab-services','<!-- wp:columns --><div class="wp-block-columns"><!-- wp:column --><div class="wp-block-column"><!-- wp:heading {"level":3} --><h3 class="wp-block-heading">Migration</h3><!-- /wp:heading --></div><!-- /wp:column --><!-- wp:column --><div class="wp-block-column"><!-- wp:heading {"level":3} --><h3 class="wp-block-heading">Optimization</h3><!-- /wp:heading --></div><!-- /wp:column --></div><!-- /wp:columns -->'],
    ['Contact','restore-lab-contact','<!-- wp:heading --><h2 class="wp-block-heading">Contact</h2><!-- /wp:heading --><!-- wp:paragraph --><p>restore-lab@example.invalid</p><!-- /wp:paragraph -->'],
    ['Case Study','restore-lab-case-study','<!-- wp:heading --><h2 class="wp-block-heading">Migration Case Study</h2><!-- /wp:heading --><!-- wp:list --><ul class="wp-block-list"><li>Database</li><li>Media</li><li>Plugins</li><li>Theme state</li></ul><!-- /wp:list -->']
  ];
  for(const [title,s,c] of pages)await upsertPost(cred,'pages',{title,slug:s,content:c});safe.pages=pages.length;save();
  step('posts');for(let i=1;i<=12;i++){const cat=cats[(i-1)%cats.length];const img=media[(i-1)%media.length];await upsertPost(cred,'posts',{title:`Restore Lab Article ${i}`,slug:`restore-lab-article-${i}`,content:`<!-- wp:heading --><h2 class="wp-block-heading">Restore verification article ${i}</h2><!-- /wp:heading --><!-- wp:paragraph --><p>Controlled content row ${i}. This text should survive backup, destructive mutation and restore.</p><!-- /wp:paragraph -->`,categories:[cat.id],featured_media:img.id});}safe.posts=12;save();
  step('verify_seed');const [pg,po,md,home]=await Promise.all([api(cred,'/wp/v2/pages?search=Restore%20Lab&per_page=100'),api(cred,'/wp/v2/posts?search=Restore%20Lab&per_page=100'),api(cred,'/wp/v2/media?search=Restore%20Lab&per_page=100'),fetch(base+'/',{redirect:'follow'})]);safe.pages=Array.isArray(pg.data)?pg.data.length:0;safe.posts=Array.isArray(po.data)?po.data.length:0;safe.media=Array.isArray(md.data)?md.data.length:0;safe.homepageHttp=home.status;safe.status=(safe.pages>=5&&safe.posts>=12&&safe.media>=3&&safe.backupPlugin?.status==='active'&&home.status===200)?'SEEDED':'PARTIAL';save();
}catch(e){safe.status='FAILED';safe.detail=String(e?.message||e);save();console.error(e);process.exitCode=1;}finally{await browser.close().catch(()=>{});}
