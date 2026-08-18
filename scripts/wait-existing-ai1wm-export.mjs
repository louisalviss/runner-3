import { chromium } from 'playwright-core';
import fs from 'fs';
import crypto from 'crypto';

const slug='runner5-restore-lab-1';
const site=JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`,'utf8'));
const backup=JSON.parse(fs.readFileSync(`ops/restore-lab/${slug}.backup.json`,'utf8'));
let priorRestore={};
try{priorRestore=JSON.parse(fs.readFileSync(`ops/restore-lab/${slug}.restore.json`,'utf8'));}catch{}
const account=JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const base=String(site.siteUrl||`https://${slug}.wasmer.app/`).replace(/\/$/,'');
const dashboard=site.dashboardUrl||`https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName||slug)}`;
const out='/tmp/runner5-restore-lab-restore.json';
const backupName=String(backup.backupName||'').trim();
if(backup.status!=='BACKUP_READY'||!backupName) throw new Error('verified_backup_missing');

const baseline={
  title:priorRestore?.baseline?.title||'Runner5 Restore Lab Demo',
  postSlug:priorRestore?.baseline?.postSlug||'restore-lab-article-1',
  pageSlug:priorRestore?.baseline?.pageSlug||'restore-lab-case-study'
};
const safe={
  status:'starting',siteSlug:slug,siteUrl:base+'/',backupName,backupSha256:backup.sha256||null,
  stage:'init',authMode:'wp-admin-cookie-nonce',restNonce:false,
  baseline,
  preRecovery:null,
  recovery:{backupDownloaded:false,backupBytes:0,backupSha256:null,importJobId:null,secretKey:false,uploadStatus:null,confirmStatus:null,verified:false,elapsedSeconds:null},
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
  if(!r.ok()){if(soft)return{ok:false,status:r.status(),data:d};throw new Error(`api_${method}_${path}:${r.status()}:${String(t).slice(0,260)}`);}return soft?{ok:true,status:r.status(),data:d}:d;
}
async function publicJson(path,timeout=45000){
  const ctrl=new AbortController();const timer=setTimeout(()=>ctrl.abort(),timeout);
  try{const r=await fetch(`${base}${path}`,{headers:{Accept:'application/json','Cache-Control':'no-cache'},redirect:'follow',signal:ctrl.signal});const t=await r.text();let d;try{d=JSON.parse(t);}catch{d=t;}return{ok:r.ok,status:r.status,data:d};}catch(e){return{ok:false,status:0,data:String(e.message||e)};}finally{clearTimeout(timer);}
}
function stringsDeep(v,out=[]){if(typeof v==='string')out.push(v);else if(Array.isArray(v))for(const x of v)stringsDeep(x,out);else if(v&&typeof v==='object')for(const x of Object.values(v))stringsDeep(x,out);return out;}
function findJobId(v){if(!v||typeof v!=='object')return null;for(const k of ['job_id','jobId','id']){const x=v[k];if(typeof x==='string'&&/^[a-f0-9]{13,40}$/i.test(x))return x;}for(const x of Object.values(v)){const y=findJobId(x);if(y)return y;}return null;}
function findSecret(v){if(!v||typeof v!=='object')return null;for(const k of ['secret_key','secretKey','secret'])if(typeof v[k]==='string'&&v[k])return v[k];for(const x of Object.values(v)){const y=findSecret(x);if(y)return y;}return null;}
function summary(v){try{return JSON.stringify(v).slice(0,700);}catch{return String(v).slice(0,700);}}

async function downloadBackup(ctx,nonce){
  stage('download_verified_backup');
  let r=await ctx.request.get(`${base}/wp-json/ai1wm/v1/backups/${encodeURIComponent(backupName)}/download`,{headers:{'X-WP-Nonce':nonce,Accept:'application/octet-stream'},timeout:180000,failOnStatusCode:false});
  if(!r.ok())throw new Error(`backup_download_http_${r.status()}:${(await r.text()).slice(0,220)}`);
  let buf=await r.body();const ct=(r.headers()['content-type']||'').toLowerCase();
  if(ct.includes('application/json')){let d;try{d=JSON.parse(buf.toString('utf8'));}catch{}const url=d&&stringsDeep(d).find(s=>/^https?:\/\//i.test(s));if(!url)throw new Error('backup_download_json_without_url');r=await ctx.request.get(url,{timeout:180000,failOnStatusCode:false});if(!r.ok())throw new Error(`backup_url_http_${r.status()}`);buf=await r.body();}
  if(buf.length<1024)throw new Error(`backup_too_small:${buf.length}`);
  const sha=crypto.createHash('sha256').update(buf).digest('hex');
  safe.recovery.backupDownloaded=true;safe.recovery.backupBytes=buf.length;safe.recovery.backupSha256=sha;save();
  if(backup.sha256&&sha!==backup.sha256)throw new Error(`backup_sha_mismatch:${sha}`);
  console.log(`BACKUP_DOWNLOADED bytes=${buf.length} sha256=${sha}`);return buf;
}

async function uploadImport(ctx,nonce,jobId,buf){
  stage('upload_import_file');
  const r=await ctx.request.post(`${base}/wp-json/ai1wm/v1/imports/${encodeURIComponent(jobId)}/file?auto_confirm=true`,{
    headers:{'X-WP-Nonce':nonce,Accept:'application/json'},
    multipart:{file:{name:backupName,mimeType:'application/octet-stream',buffer:buf}},
    timeout:10*60*1000,failOnStatusCode:false
  });
  const text=await r.text();safe.recovery.uploadStatus=r.status();save();
  console.log(`IMPORT_UPLOAD status=${r.status()} body=${text.slice(0,500)}`);
  if(!r.ok())throw new Error(`import_upload_http_${r.status()}:${text.slice(0,300)}`);
  let d;try{d=JSON.parse(text);}catch{d=text;}return d;
}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({ignoreHTTPSErrors:true});const p=await ctx.newPage();
try{
  save();await loginWasmer(p);const wp=await enterAdmin(ctx,p);const nonce=await getNonce(wp);

  stage('verify_broken_state');
  const [root0,post0,page0]=await Promise.all([
    publicJson('/wp-json/'),publicJson(`/wp-json/wp/v2/posts?slug=${baseline.postSlug}&_=${Date.now()}`),publicJson(`/wp-json/wp/v2/pages?slug=${baseline.pageSlug}&_=${Date.now()}`)
  ]);
  safe.preRecovery={rootStatus:root0.status,title:root0.data?.name||null,postCount:Array.isArray(post0.data)?post0.data.length:null,pageCount:Array.isArray(page0.data)?page0.data.length:null};save();
  if(root0.ok&&root0.data?.name===baseline.title&&Array.isArray(post0.data)&&post0.data.length>=1&&Array.isArray(page0.data)&&page0.data.length>=1){safe.recovery.verified=true;safe.status='RESTORE_VERIFIED';safe.stage='complete';save();console.log('ALREADY_RESTORED');process.exit(0);}
  console.log(`BROKEN_STATE ${summary(safe.preRecovery)}`);

  const buf=await downloadBackup(ctx,nonce);

  stage('create_import_job');
  const started=await api(ctx,nonce,'/ai1wm/v1/imports',{method:'POST',json:{}});
  const jobId=findJobId(started),secret=findSecret(started);
  if(!jobId)throw new Error(`import_job_id_missing:${summary(started)}`);
  safe.recovery.importJobId=jobId;safe.recovery.secretKey=!!secret;save();
  console.log(`IMPORT_JOB ${jobId} secret=${!!secret}`);

  const uploaded=await uploadImport(ctx,nonce,jobId,buf);
  const uploadSecret=findSecret(uploaded);const pollSecret=secret||uploadSecret;
  if(uploadSecret&&!safe.recovery.secretKey){safe.recovery.secretKey=true;save();}

  stage('confirm_import_if_needed');
  const confirm=await api(ctx,nonce,`/ai1wm/v1/imports/${encodeURIComponent(jobId)}/confirm`,{method:'POST',json:{proceed:true},soft:true,timeout:120000}).catch(e=>({ok:false,status:0,data:String(e.message||e)}));
  safe.recovery.confirmStatus=confirm.status;save();
  console.log(`IMPORT_CONFIRM status=${confirm.status} body=${summary(confirm.data)}`);

  stage('poll_import_and_public_state');
  const startedAt=Date.now(),end=startedAt+22*60*1000;let last={};let lastLog=0;
  while(Date.now()<end){
    const [root,postNow,pageNow]=await Promise.all([
      publicJson('/wp-json/'),publicJson(`/wp-json/wp/v2/posts?slug=${baseline.postSlug}&_=${Date.now()}`),publicJson(`/wp-json/wp/v2/pages?slug=${baseline.pageSlug}&_=${Date.now()}`)
    ]);
    last={rootStatus:root.status,title:root.data?.name||null,postCount:Array.isArray(postNow.data)?postNow.data.length:null,pageCount:Array.isArray(pageNow.data)?pageNow.data.length:null};
    if(root.ok&&root.data?.name===baseline.title&&Array.isArray(postNow.data)&&postNow.data.length>=1&&Array.isArray(pageNow.data)&&pageNow.data.length>=1){safe.recovery.verified=true;safe.recovery.elapsedSeconds=Math.round((Date.now()-startedAt)/1000);safe.status='RESTORE_VERIFIED';safe.stage='complete';save();console.log(`RESTORE_VERIFIED seconds=${safe.recovery.elapsedSeconds}`);break;}
    if(Date.now()-lastLog>30000){let jobState='';if(pollSecret){try{const jr=await fetch(`${base}/wp-json/ai1wm/v1/imports/${encodeURIComponent(jobId)}?secret_key=${encodeURIComponent(pollSecret)}`,{headers:{Accept:'application/json'},redirect:'follow'});jobState=(await jr.text()).slice(0,500);}catch{}}console.log(`IMPORT_WAIT public=${summary(last)} job=${jobState}`);lastLog=Date.now();}
    await new Promise(r=>setTimeout(r,8000));
  }
  if(!safe.recovery.verified)throw new Error(`import_restore_verify_timeout:${summary(last)}`);
}catch(e){safe.status='FAILED';safe.detail=String(e?.message||e);save();console.error(e);process.exitCode=1;}finally{await browser.close().catch(()=>{});}
