import { chromium } from 'playwright-core';
import fs from 'fs';

const account=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const targetDomain='runner3wp.pntr.dev';
const out={status:'starting',domain:targetDomain,added:false,verified:false,cnameTarget:null,aTarget:null,detail:null,updatedAt:new Date().toISOString()};
const save=()=>{out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-domain.json',JSON.stringify(out,null,2));};
const clean=s=>String(s||'').replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'EMAIL_REDACTED').slice(0,3600);
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function firstVisible(locator){const n=await locator.count();for(let i=0;i<n;i++){const el=locator.nth(i);if(await el.isVisible().catch(()=>false))return el;}return null;}
async function snapshot(p,label){
  const controls=await p.locator('button,input,a,[role=dialog]').evaluateAll(xs=>xs.map(x=>({tag:x.tagName.toLowerCase(),text:(x.innerText||x.textContent||'').replace(/\s+/g,' ').trim().slice(0,140),type:x.getAttribute('type'),name:x.getAttribute('name'),placeholder:x.getAttribute('placeholder'),value:(x.tagName==='INPUT'&&x.getAttribute('type')!=='password')?x.value:null})).filter(x=>x.text||x.placeholder||x.name).slice(0,70)).catch(()=>[]);
  return clean(`${label} url=${p.url()} body=${await body(p)} controls=${JSON.stringify(controls)}`);
}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({storageState:'/tmp/wasmer-browser-state.json'});
const p=await ctx.newPage();
try{
  save();
  const url=`https://wasmer.io/apps/${encodeURIComponent(account.username)}/${encodeURIComponent(account.appName)}/settings/domains`;
  await p.goto(url,{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(1500);
  let t=await body(p);
  if(/\/login(?:[/?#]|$)/i.test(p.url())){out.status='session_expired';out.detail=clean(t);save();process.exit(0);}

  if(!t.toLowerCase().includes(targetDomain.toLowerCase())){
    let add=await firstVisible(p.locator('button').filter({hasText:/^\s*Add\s*$/i}));
    if(!add)add=await firstVisible(p.locator('button').filter({hasText:/Add Domain/i}));
    if(!add){out.status='add_control_missing';out.detail=await snapshot(p,'add_missing');save();process.exit(0);}
    await add.click();await p.waitForTimeout(650);
    const input=await firstVisible(p.locator('input[type=text],input[name*=domain i],input[placeholder*=domain i],input[type=url]'));
    if(!input){out.status='domain_input_missing';out.detail=await snapshot(p,'input_missing');save();process.exit(0);}
    await input.fill(targetDomain);await p.waitForTimeout(250);
    const dialog=p.locator('[role=dialog]').last();let submit=null;
    if(await dialog.count()&&await dialog.isVisible().catch(()=>false))submit=await firstVisible(dialog.locator('button').filter({hasText:/^\s*(Add|Save|Continue)\s*$/i}));
    if(!submit){const all=p.locator('button').filter({hasText:/^\s*(Add|Save|Continue)\s*$/i});for(let i=(await all.count())-1;i>=0;i--){const el=all.nth(i);if(await el.isVisible().catch(()=>false)){submit=el;break;}}}
    if(!submit){out.status='domain_submit_missing';out.detail=await snapshot(p,'submit_missing');save();process.exit(0);}
    await submit.click();await p.waitForTimeout(3500);
  }

  t=await body(p);
  out.added=t.toLowerCase().includes(targetDomain.toLowerCase());
  // Look at the text near the target domain rather than treating another domain's
  // "Valid configuration" as proof for this one.
  const idx=t.toLowerCase().indexOf(targetDomain.toLowerCase());
  const nearby=idx>=0?t.slice(Math.max(0,idx-180),idx+900):'';
  out.verified=/valid configuration|verified|active|ready/i.test(nearby)&&!/pending|waiting|not verified|unverified|invalid configuration/i.test(nearby);

  const vals=await p.locator('input,code,pre').evaluateAll(xs=>xs.map(x=>('value'in x&&x.value?x.value:x.textContent||'').trim()).filter(Boolean)).catch(()=>[]);
  const all=[nearby,...vals].join('\n');
  const hosts=[...all.matchAll(/(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:wasmer\.app|edge\.wasmer\.io|wasmer\.io)/ig)].map(m=>m[0]);
  out.cnameTarget=[...new Set(hosts.map(x=>x.toLowerCase()))].find(x=>x!==targetDomain.toLowerCase())||null;
  const ips=[...all.matchAll(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g)].map(m=>m[0]);out.aTarget=[...new Set(ips)][0]||null;
  out.status=out.added?(out.verified?'domain_valid':'domain_added_pending_dns'):'domain_add_unconfirmed';
  out.detail=await snapshot(p,'final');save();
}catch(e){out.status='error';out.detail=clean(String(e));save();}
finally{await browser.close();}
