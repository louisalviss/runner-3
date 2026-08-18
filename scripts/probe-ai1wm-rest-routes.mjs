import { chromium } from 'playwright-core';
import fs from 'fs';

const slug='runner5-restore-lab-1';
const site=JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`,'utf8'));
const account=JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
const base=String(site.siteUrl||`https://${slug}.wasmer.app/`).replace(/\/$/,'');
const dashboard=site.dashboardUrl||`https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName||slug)}`;
const out='/tmp/runner5-restore-lab-backup.json';
const safe={status:'starting',siteSlug:slug,siteUrl:base+'/',stage:'init',routes:[],detail:null,updatedAt:new Date().toISOString()};
const save=()=>{safe.updatedAt=new Date().toISOString();fs.writeFileSync(out,JSON.stringify(safe,null,2));};
const stage=s=>{safe.stage=s;console.log('STAGE',s);save();};
const text=async p=>(await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();
const onLogin=p=>/\/login(?:[/?#]|$)/i.test(p.url());

async function loginWasmer(p){
  stage('wasmer_login');
  let last='unknown';
  for(let attempt=1;attempt<=2;attempt++){
    console.log(`WASMER_LOGIN_ATTEMPT ${attempt}`);
    await p.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:45000}).catch(e=>{last=`goto:${e.message}`;});
    await p.waitForTimeout(1200);
    if(!onLogin(p)){console.log(`WASMER_ALREADY_AUTHENTICATED ${p.url()}`);return;}

    const ident=p.locator('input[name=username],input[placeholder*=Username i],input[autocomplete=username],input[type=email],input[type=text]').first();
    const identReady=await ident.waitFor({state:'visible',timeout:10000}).then(()=>true).catch(()=>false);
    if(!identReady){
      if(!onLogin(p)) return;
      last=`identifier_missing:${(await text(p)).slice(0,240)}`;
      await p.waitForTimeout(1200);
      continue;
    }

    await ident.fill(account.username||account.email);
    let next=p.locator('button,input[type=submit]').filter({hasText:/continue|next|log in|sign in/i}).first();
    if(await next.count()&&await next.isVisible().catch(()=>false)) await next.click({noWaitAfter:true}).catch(()=>{});
    else await ident.press('Enter').catch(()=>{});

    let pass=null;
    const passDeadline=Date.now()+30000;
    while(Date.now()<passDeadline){
      if(!onLogin(p)){console.log(`WASMER_AUTHENTICATED_AFTER_IDENTIFIER ${p.url()}`);return;}
      const candidate=p.locator('input[type=password]').first();
      if(await candidate.count()&&await candidate.isVisible().catch(()=>false)){pass=candidate;break;}
      const body=await text(p);
      if(/incorrect|invalid|unknown user|authentication failed|too many attempts/i.test(body)){last=`identifier_rejected:${body.slice(0,260)}`;break;}
      await p.waitForTimeout(500);
    }
    if(!pass){last=last==='unknown'?'password_field_timeout':last;continue;}

    await pass.fill(account.password);
    let submit=p.locator('button,input[type=submit]').filter({hasText:/continue|log in|sign in/i}).first();
    if(await submit.count()&&await submit.isVisible().catch(()=>false)) await submit.click({noWaitAfter:true}).catch(()=>{});
    else await pass.press('Enter').catch(()=>{});

    const authDeadline=Date.now()+20000;
    while(Date.now()<authDeadline){
      if(!onLogin(p)){console.log(`WASMER_AUTHENTICATED ${p.url()}`);return;}
      const body=await text(p);
      if(/incorrect|invalid password|wrong password|authentication failed|too many attempts/i.test(body)){last=`password_rejected:${body.slice(0,260)}`;break;}
      await p.waitForTimeout(500);
    }
    if(onLogin(p)&&last==='unknown') last='post_password_redirect_timeout';
  }
  throw new Error(`wasmer_login_failed:${last}`);
}

async function pollAdmin(ctx,ms=22000){
  const end=Date.now()+ms;
  while(Date.now()<end){
    for(const p of ctx.pages()){
      const u=p.url();
      if(u.startsWith(base)&&/\/wp-admin(?:\/|\?|$)/i.test(u)&&!/wp-login\.php/i.test(u))return p;
    }
    await new Promise(r=>setTimeout(r,500));
  }
  return null;
}

async function adminControl(p){
  const t=p.getByText(/WordPress Admin/i).first();
  if(!(await t.count())||!(await t.isVisible().catch(()=>false)))return null;
  const a=t.locator('xpath=ancestor-or-self::a[@href] | ancestor-or-self::button').first();
  return await a.count()?a:t;
}

async function enterAdmin(ctx,p){
  stage('wordpress_admin');
  for(let k=0;k<3;k++){
    await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null);
    await p.waitForTimeout(1500);
    let c=await adminControl(p);
    if(!c){
      const st=p.getByText(/^Settings$/i).first();
      if(await st.count()&&await st.isVisible().catch(()=>false)){
        await st.click({noWaitAfter:true}).catch(()=>{});
        await p.waitForTimeout(800);
        const w=p.getByText(/^WordPress$/i).first();
        if(await w.count()&&await w.isVisible().catch(()=>false)){
          await w.click({noWaitAfter:true}).catch(()=>{});
          await p.waitForTimeout(1000);
        }
        c=await adminControl(p);
      }
    }
    if(c){
      const href=await c.getAttribute('href').catch(()=>null);
      if(href){
        const wp=await ctx.newPage();
        await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null);
        const f=await pollAdmin(ctx,18000);
        if(f)return f;
        await wp.close().catch(()=>{});
      }
      await c.click({noWaitAfter:true}).catch(()=>{});
      const f=await pollAdmin(ctx,22000);
      if(f)return f;
    }
  }
  throw new Error('magic_admin_failed');
}

async function appPassword(wp){
  stage('application_password');
  const u=new URL(`${base}/wp-admin/authorize-application.php`);
  u.searchParams.set('app_name','Runner5 AI1WM REST Probe');
  u.searchParams.set('success_url',`${base}/?runner5-ai1wm-rest=authorized`);
  await wp.goto(u.href,{waitUntil:'domcontentloaded',timeout:45000});
  await wp.waitForTimeout(700);
  let a=wp.locator('input[type=submit][name=approve],button[name=approve],#approve').first();
  if(!(await a.count()))a=wp.locator('button,input[type=submit]').filter({hasText:/approve|authorize/i}).first();
  if(!(await a.count()))throw new Error(`app_password_approve_missing:${(await text(wp)).slice(0,300)}`);
  await a.click({noWaitAfter:true});
  const end=Date.now()+20000;
  while(Date.now()<end){
    const q=new URL(wp.url());
    const user=q.searchParams.get('user_login'),pass=q.searchParams.get('password');
    if(user&&pass)return{username:user,password:pass.replace(/\s+/g,'')};
    await wp.waitForTimeout(400);
  }
  throw new Error('app_password_callback_missing');
}

const auth=c=>'Basic '+Buffer.from(`${c.username}:${c.password}`).toString('base64');
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({ignoreHTTPSErrors:true});
const p=await ctx.newPage();

try{
  save();
  await loginWasmer(p);
  const wp=await enterAdmin(ctx,p);
  const cred=await appPassword(wp);
  stage('fetch_rest_index');
  const r=await fetch(`${base}/wp-json/`,{headers:{Authorization:auth(cred),Accept:'application/json'}});
  if(!r.ok)throw new Error(`rest_index_http_${r.status}`);
  const idx=await r.json();
  const entries=[];
  for(const [route,def] of Object.entries(idx.routes||{})){
    if(!/ai1wm|migration/i.test(route+' '+JSON.stringify(def?.namespace||'')))continue;
    const endpoints=(def.endpoints||[]).map(e=>({
      methods:e.methods,
      args:Object.fromEntries(Object.entries(e.args||{}).map(([k,v])=>[k,{required:!!v.required,type:v.type||null,default:v.default??null,description:v.description||null}]))
    }));
    entries.push({route,namespace:def.namespace||null,methods:def.methods||null,endpoints});
  }
  safe.routes=entries;
  safe.status=entries.length?'REST_ROUTES_FOUND':'NO_AI1WM_REST_ROUTES';
  safe.stage='complete';
  save();
  console.log('AI1WM REST ROUTES',JSON.stringify(entries,null,2));
  if(!entries.length)process.exitCode=2;
}catch(e){
  safe.status='FAILED';safe.detail=String(e?.message||e);save();console.error(e);process.exitCode=1;
}finally{
  await browser.close().catch(()=>{});
}
