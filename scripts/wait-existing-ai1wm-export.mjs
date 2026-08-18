import { chromium } from 'playwright-core';
import fs from 'fs';

const slug='runner5-restore-lab-1';
const site=JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`,'utf8'));
const backup=JSON.parse(fs.readFileSync(`ops/restore-lab/${slug}.backup.json`,'utf8'));
const account=JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const base=String(site.siteUrl||`https://${slug}.wasmer.app/`).replace(/\/$/,'');
const dashboard=site.dashboardUrl||`https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName||slug)}`;
const out='/tmp/runner5-restore-lab-restore.json';
const backupName=String(backup.backupName||'').trim();
if(backup.status!=='BACKUP_READY'||!backupName) throw new Error('verified_backup_missing');

const safe={
  status:'starting',siteSlug:slug,siteUrl:base+'/',backupName,backupSha256:backup.sha256||null,
  stage:'init',authMode:'wp-admin-cookie-nonce',restNonce:false,
  baseline:{title:null,postSlug:'restore-lab-article-1',pageSlug:'restore-lab-case-study',postId:null,pageId:null},
  mutation:{title:null,titleChanged:false,postDeleted:false,pageDeleted:false,verified:false},
  restore:{requestStatus:null,responseSummary:null,verified:false,elapsedSeconds:null},
  detail:null,updatedAt:new Date().toISOString()
};
const save=()=>{safe.updatedAt=new Date().toISOString();fs.writeFileSync(out,JSON.stringify(safe,null,2));};
const stage=s=>{safe.stage=s;console.log('STAGE',s);save();};
const onLogin=p=>/\/login(?:[/?#]|$)/i.test(p.url());

async function loginWasmer(p){
  stage('wasmer_login');
  for(let attempt=1;attempt<=3;attempt++){
    await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null);
    await p.waitForTimeout(900);
    if(!onLogin(p)) return;
    const ident=p.locator('input[name=username],input[placeholder*=Username i],input[autocomplete=username],input[type=email],input[type=text]').first();
    if(!(await ident.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false))) continue;
    await ident.fill(account.username||account.email);
    const next=p.locator('button,input[type=submit]').filter({hasText:/continue|next|log in|sign in/i}).first();
    if(await next.count()&&await next.isVisible().catch(()=>false)) await next.click({noWaitAfter:true}).catch(()=>{}); else await ident.press('Enter').catch(()=>{});
    const passEnd=Date.now()+30000;let pass=null;
    while(Date.now()<passEnd){if(!onLogin(p))return;const x=p.locator('input[type=password]').first();if(await x.count()&&await x.isVisible().catch(()=>false)){pass=x;break;}await p.waitForTimeout(500);}
    if(!pass) continue;
    await pass.fill(account.password);
    const submit=p.locator('button,input[type=submit]').filter({hasText:/continue|log in|sign in/i}).first();
    if(await submit.count()&&await submit.isVisible().catch(()=>false)) await submit.click({noWaitAfter:true}).catch(()=>{}); else await pass.press('Enter').catch(()=>{});
    const end=Date.now()+20000;while(Date.now()<end){if(!onLogin(p))return;await p.waitForTimeout(500);}
  }
  throw new Error('wasmer_login_failed');
}
async function pollAdmin(ctx,ms=26000){const end=Date.now()+ms;while(Date.now()<end){for(const p of ctx.pages()){const u=p.url();if(u.startsWith(base)&&/\/wp-admin(?:\/|\?|$)/i.test(u)&&!/wp-login\.php/i.test(u))return p;}await new Promise(r=>setTimeout(r,500));}return null;}
async function adminControl(p){const t=p.getByText(/WordPress Admin/i).first();if(!(await t.count())||!(await t.isVisible().catch(()=>false)))return null;const a=t.locator('xpath=ancestor-or-self::a[@href] | ancestor-or-self::button').first();return await a.count()?a:t;}
async function enterAdmin(ctx,p){
  stage('wordpress_admin');
  for(let k=0;k<3;k++){
    await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null);await p.waitForTimeout(1400);
    let c=await adminControl(p);
    if(!c){const st=p.getByText(/^Settings$/i).first();if(await st.count()&&await st.isVisible().catch(()=>false)){await st.click({noWaitAfter:true}).catch(()=>{});await p.waitForTimeout(700);const w=p.getByText(/^WordPress$/i).first();if(await w.count()&&await w.isVisible().catch(()=>false)){await w.click({noWaitAfter:true}).catch(()=>{});await p.waitForTimeout(900);}c=await adminControl(p);}}
    if(c){const href=await c.getAttribute('href').catch(()=>null);if(href){const wp=await ctx.newPage();await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null);const f=await pollAdmin(ctx,18000);if(f)return f;await wp.close().catch(()=>{});}await c.click({noWaitAfter:true}).catch(()=>{});const f=await pollAdmin(ctx,22000);if(f)return f;}
  }
  throw new Error('magic_admin_failed');
}
async function getNonce(wp){
  stage('rest_nonce');await wp.goto(`${base}/wp-admin/`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1000);
  let nonce=await wp.evaluate(()=>globalThis.wpApiSettings?.nonce||globalThis.wp?.apiSettings?.nonce||null).catch(()=>null);
  if(!nonce){const html=await wp.content();for(const re of [/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i,/["']nonce["']\s*:\s*["']([A-Fa-f0-9]{10,})["']/i]){const m=html.match(re);if(m){nonce=m[1];break;}}}
  if(!nonce)throw new Error('wp_rest_nonce_missing');safe.restNonce=true;save();return nonce;
}
async function api(ctx,nonce,path,{method='GET',json=null,soft=false,timeout=60000}={}){
  const headers={'X-WP-Nonce':nonce,Accept:'application/json'};let data;if(json!==null){headers['Content-Type']='application/json';data=JSON.stringify(json);}
  const r=await ctx.request.fetch(`${base}/wp-json${path}`,{method,headers,data,timeout,failOnStatusCode:false});
  const t=await r.text();let d;try{d=JSON.parse(t);}catch{d=t;}
  if(!r.ok()){if(soft)return{ok:false,status:r.status(),data:d};throw new Error(`api_${method}_${path}:${r.status()}:${String(t).slice(0,240)}`);}return soft?{ok:true,status:r.status(),data:d}:d;
}
async function publicJson(path,timeout=45000){
  const ctrl=new AbortController();const timer=setTimeout(()=>ctrl.abort(),timeout);
  try{const r=await fetch(`${base}${path}`,{headers:{Accept:'application/json','Cache-Control':'no-cache'},redirect:'follow',signal:ctrl.signal});const t=await r.text();let d;try{d=JSON.parse(t);}catch{d=t;}return{ok:r.ok,status:r.status,data:d};}catch(e){return{ok:false,status:0,data:String(e.message||e)};}finally{clearTimeout(timer);}
}
function arrFirst(v){return Array.isArray(v)&&v.length?v[0]:null;}
function summary(v){try{return JSON.stringify(v).slice(0,500);}catch{return String(v).slice(0,500);}}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({ignoreHTTPSErrors:true});const p=await ctx.newPage();
try{
  save();await loginWasmer(p);const wp=await enterAdmin(ctx,p);const nonce=await getNonce(wp);

  stage('capture_baseline');
  const settings=await api(ctx,nonce,'/wp/v2/settings');
  const posts=await api(ctx,nonce,`/wp/v2/posts?slug=${encodeURIComponent(safe.baseline.postSlug)}&status=any&context=edit`);
  const pages=await api(ctx,nonce,`/wp/v2/pages?slug=${encodeURIComponent(safe.baseline.pageSlug)}&status=any&context=edit`);
  const post=arrFirst(posts),page=arrFirst(pages);
  if(!post||!page)throw new Error(`baseline_marker_missing:post=${!!post}:page=${!!page}`);
  safe.baseline.title=settings.title;safe.baseline.postId=post.id;safe.baseline.pageId=page.id;save();
  console.log(`BASELINE title=${safe.baseline.title} postId=${post.id} pageId=${page.id}`);

  stage('destructive_mutation');
  const broken=`BROKEN Restore Lab ${Date.now()}`;safe.mutation.title=broken;
  await api(ctx,nonce,'/wp/v2/settings',{method:'POST',json:{title:broken}});safe.mutation.titleChanged=true;save();
  await api(ctx,nonce,`/wp/v2/posts/${post.id}?force=true`,{method:'DELETE'});safe.mutation.postDeleted=true;save();
  await api(ctx,nonce,`/wp/v2/pages/${page.id}?force=true`,{method:'DELETE'});safe.mutation.pageDeleted=true;save();

  stage('verify_mutation');
  const [rootBroken,postBroken,pageBroken]=await Promise.all([
    publicJson('/wp-json/'),publicJson(`/wp-json/wp/v2/posts?slug=${safe.baseline.postSlug}&_=${Date.now()}`),publicJson(`/wp-json/wp/v2/pages?slug=${safe.baseline.pageSlug}&_=${Date.now()}`)
  ]);
  const mutationOk=rootBroken.ok&&rootBroken.data?.name===broken&&Array.isArray(postBroken.data)&&postBroken.data.length===0&&Array.isArray(pageBroken.data)&&pageBroken.data.length===0;
  safe.mutation.verified=mutationOk;save();
  if(!mutationOk)throw new Error(`mutation_verify_failed:${summary({root:rootBroken.data,post:postBroken.data,page:pageBroken.data})}`);
  console.log('MUTATION_VERIFIED');

  stage('restore_request');
  const restore=await api(ctx,nonce,`/ai1wm/v1/backups/${encodeURIComponent(backupName)}/restore`,{method:'POST',soft:true,timeout:120000});
  safe.restore.requestStatus=restore.status;safe.restore.responseSummary=summary(restore.data);save();
  console.log(`RESTORE_REQUEST status=${restore.status} body=${safe.restore.responseSummary}`);

  stage('poll_restored_public_state');
  const started=Date.now();const end=started+20*60*1000;let last={};
  while(Date.now()<end){
    const [root,postNow,pageNow]=await Promise.all([
      publicJson('/wp-json/'),publicJson(`/wp-json/wp/v2/posts?slug=${safe.baseline.postSlug}&_=${Date.now()}`),publicJson(`/wp-json/wp/v2/pages?slug=${safe.baseline.pageSlug}&_=${Date.now()}`)
    ]);
    last={rootStatus:root.status,title:root.data?.name||null,postCount:Array.isArray(postNow.data)?postNow.data.length:null,pageCount:Array.isArray(pageNow.data)?pageNow.data.length:null};
    if(root.ok&&root.data?.name===safe.baseline.title&&Array.isArray(postNow.data)&&postNow.data.length>=1&&Array.isArray(pageNow.data)&&pageNow.data.length>=1){safe.restore.verified=true;safe.restore.elapsedSeconds=Math.round((Date.now()-started)/1000);safe.status='RESTORE_VERIFIED';safe.stage='complete';save();console.log(`RESTORE_VERIFIED seconds=${safe.restore.elapsedSeconds}`);break;}
    console.log(`RESTORE_WAIT ${summary(last)}`);await new Promise(r=>setTimeout(r,10000));
  }
  if(!safe.restore.verified)throw new Error(`restore_verify_timeout:${summary(last)}`);
}catch(e){safe.status='FAILED';safe.detail=String(e?.message||e);save();console.error(e);process.exitCode=1;}finally{await browser.close().catch(()=>{});}
