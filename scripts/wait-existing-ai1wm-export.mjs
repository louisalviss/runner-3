import { chromium } from 'playwright-core';
import fs from 'fs';
import crypto from 'crypto';

const slug='runner5-restore-lab-1';
const site=JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`,'utf8'));
const account=JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const prior=JSON.parse(fs.readFileSync(`ops/restore-lab/${slug}.backup.json`,'utf8'));
const jobId=String(prior.exportJobId||'').trim();
if(!jobId) throw new Error('existing_export_job_id_missing');
const base=String(site.siteUrl||`https://${slug}.wasmer.app/`).replace(/\/$/,'');
const dashboard=site.dashboardUrl||`https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName||slug)}`;
const out='/tmp/runner5-restore-lab-backup.json';
const backupPath='/tmp/runner5-restore-lab-before.wpress';
const safe={status:'starting',siteSlug:slug,siteUrl:base+'/',stage:'init',applicationPassword:false,exportJobId:jobId,backupName:null,backupBytes:0,sha256:null,artifactName:'runner5-restore-lab-before-wpress',lastState:null,detail:null,updatedAt:new Date().toISOString()};
const save=()=>{safe.updatedAt=new Date().toISOString();fs.writeFileSync(out,JSON.stringify(safe,null,2));};
const stage=s=>{safe.stage=s;console.log('STAGE',s);save();};
const bodyText=async p=>(await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();
const onLogin=p=>/\/login(?:[/?#]|$)/i.test(p.url());

async function loginWasmer(p){
  stage('wasmer_login');
  let last='unknown';
  for(let attempt=1;attempt<=2;attempt++){
    await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:45000}).catch(e=>{last=`goto:${e.message}`;});
    await p.waitForTimeout(1000);
    if(!onLogin(p)) return;
    const ident=p.locator('input[name=username],input[placeholder*=Username i],input[autocomplete=username],input[type=email],input[type=text]').first();
    if(!(await ident.waitFor({state:'visible',timeout:10000}).then(()=>true).catch(()=>false))){last='identifier_missing';continue;}
    await ident.fill(account.username||account.email);
    const next=p.locator('button,input[type=submit]').filter({hasText:/continue|next|log in|sign in/i}).first();
    if(await next.count()&&await next.isVisible().catch(()=>false))await next.click({noWaitAfter:true}).catch(()=>{});else await ident.press('Enter').catch(()=>{});
    let pass=null;const passEnd=Date.now()+30000;
    while(Date.now()<passEnd){if(!onLogin(p))return;const x=p.locator('input[type=password]').first();if(await x.count()&&await x.isVisible().catch(()=>false)){pass=x;break;}await p.waitForTimeout(500);}
    if(!pass){last='password_field_timeout';continue;}
    await pass.fill(account.password);
    const submit=p.locator('button,input[type=submit]').filter({hasText:/continue|log in|sign in/i}).first();
    if(await submit.count()&&await submit.isVisible().catch(()=>false))await submit.click({noWaitAfter:true}).catch(()=>{});else await pass.press('Enter').catch(()=>{});
    const end=Date.now()+20000;while(Date.now()<end){if(!onLogin(p))return;await p.waitForTimeout(500);}last='post_password_redirect_timeout';
  }
  throw new Error(`wasmer_login_failed:${last}`);
}
async function pollAdmin(ctx,ms=24000){const end=Date.now()+ms;while(Date.now()<end){for(const p of ctx.pages()){const u=p.url();if(u.startsWith(base)&&/\/wp-admin(?:\/|\?|$)/i.test(u)&&!/wp-login\.php/i.test(u))return p;}await new Promise(r=>setTimeout(r,500));}return null;}
async function adminControl(p){const t=p.getByText(/WordPress Admin/i).first();if(!(await t.count())||!(await t.isVisible().catch(()=>false)))return null;const a=t.locator('xpath=ancestor-or-self::a[@href] | ancestor-or-self::button').first();return await a.count()?a:t;}
async function enterAdmin(ctx,p){stage('wordpress_admin');for(let k=0;k<3;k++){await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null);await p.waitForTimeout(1400);let c=await adminControl(p);if(!c){const st=p.getByText(/^Settings$/i).first();if(await st.count()&&await st.isVisible().catch(()=>false)){await st.click({noWaitAfter:true}).catch(()=>{});await p.waitForTimeout(700);const w=p.getByText(/^WordPress$/i).first();if(await w.count()&&await w.isVisible().catch(()=>false)){await w.click({noWaitAfter:true}).catch(()=>{});await p.waitForTimeout(900);}c=await adminControl(p);}}if(c){const href=await c.getAttribute('href').catch(()=>null);if(href){const wp=await ctx.newPage();await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null);const found=await pollAdmin(ctx,18000);if(found)return found;await wp.close().catch(()=>{});}await c.click({noWaitAfter:true}).catch(()=>{});const found=await pollAdmin(ctx,22000);if(found)return found;}}throw new Error('magic_admin_failed');}
async function appPassword(wp){stage('application_password');const u=new URL(`${base}/wp-admin/authorize-application.php`);u.searchParams.set('app_name','Runner5 Existing Export Watch');u.searchParams.set('success_url',`${base}/?runner5-export-watch=authorized`);await wp.goto(u.href,{waitUntil:'domcontentloaded',timeout:45000});await wp.waitForTimeout(700);let a=wp.locator('input[type=submit][name=approve],button[name=approve],#approve').first();if(!(await a.count()))a=wp.locator('button,input[type=submit]').filter({hasText:/approve|authorize/i}).first();if(!(await a.count()))throw new Error(`app_password_approve_missing:${(await bodyText(wp)).slice(0,300)}`);await a.click({noWaitAfter:true});const end=Date.now()+20000;while(Date.now()<end){const q=new URL(wp.url());const user=q.searchParams.get('user_login'),pass=q.searchParams.get('password');if(user&&pass){safe.applicationPassword=true;save();return{username:user,password:pass.replace(/\s+/g,'')};}await wp.waitForTimeout(400);}throw new Error('app_password_callback_missing');}
const auth=c=>'Basic '+Buffer.from(`${c.username}:${c.password}`).toString('base64');
async function api(c,path,{method='GET',json=null,soft=false}={}){const headers={Authorization:auth(c),Accept:'application/json'};let payload;if(json!==null){headers['Content-Type']='application/json';payload=JSON.stringify(json);}const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),45000);try{const r=await fetch(`${base}/wp-json${path}`,{method,headers,body:payload,redirect:'follow',signal:controller.signal});const t=await r.text();let d;try{d=JSON.parse(t);}catch{d=t;}if(!r.ok){if(soft)return{ok:false,status:r.status,data:d};throw new Error(`api_${method}_${path}:${r.status}:${String(t).slice(0,220)}`);}return soft?{ok:true,status:r.status,data:d}:d;}finally{clearTimeout(timer);}}
function stringsDeep(v,out=[]){if(typeof v==='string')out.push(v);else if(Array.isArray(v))for(const x of v)stringsDeep(x,out);else if(v&&typeof v==='object')for(const x of Object.values(v))stringsDeep(x,out);return out;}
function backupNames(v){return [...new Set(stringsDeep(v).map(s=>{const m=s.match(/([A-Za-z0-9._-]{1,247}\.wpress)(?:\b|$)/i);return m?.[1]||null;}).filter(Boolean))];}
function stateSummary(v){return stringsDeep(v).filter(s=>/complete|done|success|finish|fail|error|progress|running|archiv|export/i.test(s)).slice(0,8).join('|').replace(/<br\s*\/?>/gi,' ').slice(0,350);}
async function finalize(c,name){stage('download_backup');const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),120000);try{let r=await fetch(`${base}/wp-json/ai1wm/v1/backups/${encodeURIComponent(name)}/download`,{headers:{Authorization:auth(c),Accept:'application/octet-stream'},redirect:'follow',signal:controller.signal});if(!r.ok)throw new Error(`backup_download_http_${r.status}`);let buf=Buffer.from(await r.arrayBuffer());const ct=(r.headers.get('content-type')||'').toLowerCase();if(ct.includes('application/json')){let d;try{d=JSON.parse(buf.toString('utf8'));}catch{}const url=d&&stringsDeep(d).find(s=>/^https?:\/\//i.test(s));if(!url)throw new Error('backup_download_json_without_url');r=await fetch(url,{headers:{Authorization:auth(c)},redirect:'follow'});if(!r.ok)throw new Error(`backup_url_http_${r.status}`);buf=Buffer.from(await r.arrayBuffer());}if(buf.length<1024)throw new Error(`backup_too_small:${buf.length}`);const head=buf.subarray(0,100).toString('utf8').toLowerCase();if(head.includes('<html')||head.includes('<!doctype'))throw new Error('backup_download_returned_html');fs.writeFileSync(backupPath,buf,{mode:0o600});safe.backupName=name;safe.backupBytes=buf.length;safe.sha256=crypto.createHash('sha256').update(buf).digest('hex');safe.status='BACKUP_READY';safe.stage='complete';save();console.log(`BACKUP_READY name=${name} bytes=${buf.length} sha256=${safe.sha256}`);}finally{clearTimeout(timer);}}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});const ctx=await browser.newContext({ignoreHTTPSErrors:true});const p=await ctx.newPage();
try{
  save();await loginWasmer(p);const wp=await enterAdmin(ctx,p);const c=await appPassword(wp);
  stage('watch_existing_export');
  const end=Date.now()+18*60*1000;
  let lastLog=0;
  while(Date.now()<end){
    const backups=await api(c,'/ai1wm/v1/backups');const names=backupNames(backups);if(names.length){console.log(`BACKUP_APPEARED ${names[0]}`);await finalize(c,names[0]);break;}
    const job=await api(c,`/ai1wm/v1/exports/${encodeURIComponent(jobId)}`,{soft:true});
    if(job.ok){safe.lastState=stateSummary(job.data)||`http_${job.status}`;if(stringsDeep(job.data).some(s=>/fail|error|cancel/i.test(s)))throw new Error(`existing_export_failed:${safe.lastState}`);}else{safe.lastState=`job_status_http_${job.status}`;}
    if(Date.now()-lastLog>30000){console.log(`EXPORT_WATCH job=${jobId} state=${safe.lastState||'unknown'} backups=0`);lastLog=Date.now();save();}
    await new Promise(r=>setTimeout(r,5000));
  }
  if(safe.status!=='BACKUP_READY')throw new Error(`existing_export_timeout:${safe.lastState||'no_state'}`);
}catch(e){safe.status='FAILED';safe.detail=String(e?.message||e);save();console.error(e);process.exitCode=1;}finally{await browser.close().catch(()=>{});}
