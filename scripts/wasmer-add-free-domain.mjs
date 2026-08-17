import { chromium } from 'playwright-core';
import fs from 'fs';

const account=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const targetDomain='runner3wp.is-a-good.dev';
const out={status:'starting',domain:targetDomain,added:false,verified:false,cnameTarget:null,aTarget:null,detail:null,updatedAt:new Date().toISOString()};
const save=()=>{out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-domain.json',JSON.stringify(out,null,2));};
const clean=s=>String(s||'').replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'EMAIL_REDACTED').slice(0,2400);
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({storageState:'/tmp/wasmer-browser-state.json'});
const p=await ctx.newPage();
try{
  save();
  const url=`https://wasmer.io/apps/${encodeURIComponent(account.username)}/${encodeURIComponent(account.appName)}/settings/domains`;
  await p.goto(url,{waitUntil:'domcontentloaded',timeout:60000});
  await p.waitForTimeout(1500);
  let t=await body(p);
  if(/\/login(?:[/?#]|$)/i.test(p.url())){out.status='session_expired';out.detail=clean(t);save();process.exit(0);}

  // If already present, skip straight to parsing DNS instructions/status.
  if(!t.toLowerCase().includes(targetDomain.toLowerCase())){
    let add=p.locator('button').filter({hasText:/Add Domain|Add domain/i}).first();
    if(!(await add.count())) add=p.getByText(/Add Domain|Add domain/i).first();
    if(!(await add.count())){out.status='add_control_missing';out.detail=clean(t);save();process.exit(0);}
    await add.click();
    await p.waitForTimeout(700);
    const input=p.locator('input[type=text],input[name*=domain i],input[placeholder*=domain i]').filter({visible:true}).last();
    const visible=await input.waitFor({state:'visible',timeout:8000}).then(()=>true).catch(()=>false);
    if(!visible){out.status='domain_input_missing';out.detail=clean(await body(p));save();process.exit(0);}
    await input.fill(targetDomain);
    let submit=p.locator('button').filter({hasText:/Add|Continue|Save/i}).last();
    if(!(await submit.count())){out.status='domain_submit_missing';out.detail=clean(await body(p));save();process.exit(0);}
    await submit.click();
    await p.waitForTimeout(2200);
  }

  t=await body(p);
  out.added=t.toLowerCase().includes(targetDomain.toLowerCase());
  out.verified=/verified|active|ready/i.test(t) && !/pending|waiting|not verified|unverified/i.test(t);

  // Extract likely DNS targets from visible text and input/code fields.
  const vals=await p.locator('input,code,pre').evaluateAll(xs=>xs.map(x=>('value' in x&&x.value?x.value:x.textContent||'').trim()).filter(Boolean)).catch(()=>[]);
  const all=[t,...vals].join('\n');
  const hosts=[...all.matchAll(/(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:wasmer\.app|edge\.wasmer\.io|wasmer\.io)/ig)].map(m=>m[0]);
  const unique=[...new Set(hosts.map(x=>x.toLowerCase()))];
  out.cnameTarget=unique.find(x=>x!==targetDomain.toLowerCase())||null;
  const ips=[...all.matchAll(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g)].map(m=>m[0]);
  out.aTarget=[...new Set(ips)][0]||null;
  out.status=out.added?'domain_added':'domain_add_unconfirmed';
  out.detail=clean(t);
  save();
}catch(e){out.status='error';out.detail=clean(String(e));save();}
finally{await browser.close();}
