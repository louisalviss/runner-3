import { chromium } from 'playwright-core';
import fs from 'fs';

const slug='runner5-restore-lab-1';
const site=JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`,'utf8'));
const prior=JSON.parse(fs.readFileSync(`ops/restore-lab/${slug}.restore.json`,'utf8'));
const account=JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const base=String(site.siteUrl||`https://${slug}.wasmer.app/`).replace(/\/$/,'');
const dashboard=site.dashboardUrl||`https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName||slug)}`;
const out='/tmp/runner5-restore-lab-restore.json';
const baseline=prior.baseline||{title:'Runner5 Restore Lab Demo',postSlug:'restore-lab-article-1',pageSlug:'restore-lab-case-study'};
const jobId=String(prior?.recovery?.importJobId||'').trim();
if(!jobId) throw new Error('existing_import_job_missing');
const safe={...prior,status:'watching',stage:'init',detail:null,updatedAt:new Date().toISOString()};
safe.recovery={...(prior.recovery||{}),importJobId:jobId,verified:false};
const save=()=>{safe.updatedAt=new Date().toISOString();fs.writeFileSync(out,JSON.stringify(safe,null,2));};
const stage=s=>{safe.stage=s;console.log('STAGE',s);save();};
const summary=v=>{try{return JSON.stringify(v).slice(0,700);}catch{return String(v).slice(0,700);}};

async function publicJson(path,timeout=45000){
  const ctrl=new AbortController();const timer=setTimeout(()=>ctrl.abort(),timeout);
  try{const r=await fetch(`${base}${path}`,{headers:{Accept:'application/json','Cache-Control':'no-cache'},redirect:'follow',signal:ctrl.signal});const t=await r.text();let d;try{d=JSON.parse(t);}catch{d=t;}return{ok:r.ok,status:r.status,data:d};}catch(e){return{ok:false,status:0,data:String(e.message||e)};}finally{clearTimeout(timer);}
}
async function publicState(){
  const [root,post,page]=await Promise.all([
    publicJson('/wp-json/'),
    publicJson(`/wp-json/wp/v2/posts?slug=${encodeURIComponent(baseline.postSlug)}&_=${Date.now()}`),
    publicJson(`/wp-json/wp/v2/pages?slug=${encodeURIComponent(baseline.pageSlug)}&_=${Date.now()}`)
  ]);
  return{rootStatus:root.status,title:root.data?.name||null,postCount:Array.isArray(post.data)?post.data.length:null,pageCount:Array.isArray(page.data)?page.data.length:null};
}
const restored=s=>s.rootStatus===200&&s.title===baseline.title&&s.postCount>=1&&s.pageCount>=1;
const onLogin=p=>/\/login(?:[/?#]|$)/i.test(p.url());
async function loginWasmer(p){
  stage('wasmer_login');
  for(let attempt=1;attempt<=3;attempt++){
    await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null);await p.waitForTimeout(900);
    if(!onLogin(p))return;
    const ident=p.locator('input[name=username],input[placeholder*=Username i],input[autocomplete=username],input[type=email],input[type=text]').first();
    if(!(await ident.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false)))continue;
    await ident.fill(account.username||account.email);
    const next=p.locator('button,input[type=submit]').filter({hasText:/continue|next|log in|sign in/i}).first();
    if(await next.count()&&await next.isVisible().catch(()=>false))await next.click({noWaitAfter:true}).catch(()=>{});else await ident.press('Enter').catch(()=>{});
    let pass=null;const pe=Date.now()+30000;while(Date.now()<pe){if(!onLogin(p))return;const x=p.locator('input[type=password]').first();if(await x.count()&&await x.isVisible().catch(()=>false)){pass=x;break;}await p.waitForTimeout(500);}if(!pass)continue;
    await pass.fill(account.password);const submit=p.locator('button,input[type=submit]').filter({hasText:/continue|log in|sign in/i}).first();
    if(await submit.count()&&await submit.isVisible().catch(()=>false))await submit.click({noWaitAfter:true}).catch(()=>{});else await pass.press('Enter').catch(()=>{});
    const end=Date.now()+20000;while(Date.now()<end){if(!onLogin(p))return;await p.waitForTimeout(500);}
  }
  throw new Error('wasmer_login_failed');
}
async function pollAdmin(ctx,ms=26000){const end=Date.now()+ms;while(Date.now()<end){for(const p of ctx.pages()){const u=p.url();if(u.startsWith(base)&&/\/wp-admin(?:\/|\?|$)/i.test(u)&&!/wp-login\.php/i.test(u))return p;}await new Promise(r=>setTimeout(r,500));}return null;}
async function adminControl(p){const t=p.getByText(/WordPress Admin/i).first();if(!(await t.count())||!(await t.isVisible().catch(()=>false)))return null;const a=t.locator('xpath=ancestor-or-self::a[@href] | ancestor-or-self::button').first();return await a.count()?a:t;}
async function enterAdmin(ctx,p){
  stage('wordpress_admin');
  for(let k=0;k<3;k++){
    await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null);await p.waitForTimeout(1400);let c=await adminControl(p);
    if(!c){const st=p.getByText(/^Settings$/i).first();if(await st.count()&&await st.isVisible().catch(()=>false)){await st.click({noWaitAfter:true}).catch(()=>{});await p.waitForTimeout(700);const w=p.getByText(/^WordPress$/i).first();if(await w.count()&&await w.isVisible().catch(()=>false)){await w.click({noWaitAfter:true}).catch(()=>{});await p.waitForTimeout(900);}c=await adminControl(p);}}
    if(c){const href=await c.getAttribute('href').catch(()=>null);if(href){const wp=await ctx.newPage();await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null);const f=await pollAdmin(ctx,18000);if(f)return f;await wp.close().catch(()=>{});}await c.click({noWaitAfter:true}).catch(()=>{});const f=await pollAdmin(ctx,22000);if(f)return f;}
  }
  throw new Error('magic_admin_failed');
}
async function nonce(wp){stage('rest_nonce');await wp.goto(`${base}/wp-admin/`,{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(800);let n=await wp.evaluate(()=>globalThis.wpApiSettings?.nonce||globalThis.wp?.apiSettings?.nonce||null).catch(()=>null);if(!n){const h=await wp.content();for(const re of [/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i,/["']nonce["']\s*:\s*["']([A-Fa-f0-9]{10,})["']/i]){const m=h.match(re);if(m){n=m[1];break;}}}if(!n)throw new Error('wp_rest_nonce_missing');safe.restNonce=true;save();return n;}
async function jobState(ctx,n){const r=await ctx.request.get(`${base}/wp-json/ai1wm/v1/imports/${encodeURIComponent(jobId)}`,{headers:{'X-WP-Nonce':n,Accept:'application/json'},timeout:45000,failOnStatusCode:false});const t=await r.text();let d;try{d=JSON.parse(t);}catch{d=t;}return{status:r.status(),data:d,text:t};}

const initial=await publicState();
if(restored(initial)){safe.status='RESTORE_VERIFIED';safe.stage='complete';safe.recovery.verified=true;safe.recovery.elapsedSeconds=0;save();console.log(`ALREADY_RESTORED ${summary(initial)}`);process.exit(0);}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});const ctx=await browser.newContext({ignoreHTTPSErrors:true});const p=await ctx.newPage();
try{
  save();await loginWasmer(p);const wp=await enterAdmin(ctx,p);const n=await nonce(wp);stage('watch_existing_import');
  const started=Date.now(),end=started+35*60*1000;let last=initial,lastJob=null,lastLog=0;
  while(Date.now()<end){
    last=await publicState();
    if(restored(last)){safe.status='RESTORE_VERIFIED';safe.stage='complete';safe.recovery.verified=true;safe.recovery.elapsedSeconds=Math.round((Date.now()-started)/1000);save();console.log(`RESTORE_VERIFIED seconds=${safe.recovery.elapsedSeconds} ${summary(last)}`);break;}
    try{lastJob=await jobState(ctx,n);const s=summary(lastJob.data);if(/fail|error|cancel/i.test(s))throw new Error(`import_job_failed:${s}`);}catch(e){if(/import_job_failed/.test(String(e.message||e)))throw e;lastJob={status:0,data:String(e.message||e)};}
    safe.recovery.lastObservedJob=lastJob?.data||null;safe.recovery.lastPublicState=last;save();
    if(Date.now()-lastLog>30000){console.log(`IMPORT_WATCH public=${summary(last)} job=${summary(lastJob)}`);lastLog=Date.now();}
    await new Promise(r=>setTimeout(r,10000));
  }
  if(!safe.recovery.verified)throw new Error(`existing_import_timeout:public=${summary(last)}:job=${summary(lastJob)}`);
}catch(e){safe.status='FAILED';safe.detail=String(e?.message||e);save();console.error(e);process.exitCode=1;}finally{await browser.close().catch(()=>{});}
