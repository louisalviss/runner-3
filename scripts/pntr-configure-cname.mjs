import { chromium } from 'playwright-core';
import fs from 'fs';

const fqdn='runner3wp.pntr.dev';
const cname='lnh8iwtjmk3x.id.wasmer.app';
const out={status:'starting',domain:fqdn,registered:false,cnameConfigured:false,dnsTarget:cname,detail:null,updatedAt:new Date().toISOString()};
const save=()=>{out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/pntr-status.json',JSON.stringify(out,null,2));};
const clean=s=>String(s||'').replace(/[A-Za-z0-9_-]{28,}/g,'REDACTED').slice(0,4200);
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function visible(l){return !!(await l.count().catch(()=>0))&&await l.isVisible().catch(()=>false);}
async function controls(p){
  return clean(JSON.stringify(await p.locator('input,button,a,select,[role=button],[role=option]').evaluateAll(xs=>xs.map(x=>({tag:x.tagName.toLowerCase(),text:(x.innerText||x.textContent||x.getAttribute('value')||'').replace(/\s+/g,' ').trim().slice(0,120),type:x.getAttribute('type'),name:x.getAttribute('name'),placeholder:x.getAttribute('placeholder'),aria:x.getAttribute('aria-label'),value:x.tagName==='INPUT'?x.value:null})).filter(x=>x.text||x.placeholder||x.name||x.aria).slice(0,120)).catch(()=>[])));
}
async function clickAny(p,re){
  for(const sel of ['button','[role=button]','a']){
    const xs=p.locator(sel).filter({hasText:re});
    for(let i=0;i<await xs.count();i++){const x=xs.nth(i);if(await visible(x)){await x.click();await p.waitForTimeout(700);return true;}}
  }
  return false;
}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const storage=JSON.parse(fs.readFileSync('/tmp/pntr-browser-state.json','utf8'));
const ctx=await browser.newContext({storageState:storage});
const p=await ctx.newPage();
try{
  save();
  await p.goto('https://pntr.dev/dashboard',{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(1300);
  let t=await body(p);
  if(/no subdomains yet/i.test(t)||!t.toLowerCase().includes(fqdn)){
    out.status='stored_session_missing_domain';out.detail=`body=${clean(t)} controls=${await controls(p)}`;save();process.exitCode=0;
  }else{
    out.registered=true;
    const card=p.locator('[role=button]').filter({hasText:new RegExp(fqdn.replaceAll('.','\\.'),'i')}).first();
    if(await visible(card)){await card.click();await p.waitForTimeout(900);}
    t=await body(p);

    if(t.toLowerCase().includes(cname.toLowerCase())&&/cname/i.test(t)){
      out.cnameConfigured=true;out.status='ready';save();
    }else{
      let add=p.locator('button,[role=button]').filter({hasText:/add (dns )?record|new record|create record/i}).first();
      if(!await visible(add)){
        out.status='dns_add_control_missing';out.detail=`body=${clean(t)} controls=${await controls(p)}`;save();
      }else{
        await add.click();await p.waitForTimeout(600);
        // Type selector.
        let selected=false;
        const sels=p.locator('select');
        for(let i=0;i<await sels.count();i++){
          const s=sels.nth(i);if(!await visible(s))continue;
          const opts=await s.locator('option').evaluateAll(os=>os.map(o=>({v:o.value,t:(o.textContent||'').trim()}))).catch(()=>[]);
          const c=opts.find(o=>/cname/i.test(o.t)||/cname/i.test(o.v));
          if(c){await s.selectOption(c.v);selected=true;break;}
        }
        if(!selected){
          const combos=p.getByRole('combobox');
          for(let i=0;i<await combos.count();i++){
            const c=combos.nth(i);if(!await visible(c))continue;
            await c.click().catch(()=>{});await p.waitForTimeout(200);
            const opt=p.getByRole('option',{name:/CNAME/i}).first();
            if(await visible(opt)){await opt.click();selected=true;break;}
          }
        }
        if(!selected){
          out.status='dns_type_control_missing';out.detail=`body=${clean(await body(p))} controls=${await controls(p)}`;save();
        }else{
          await p.waitForTimeout(300);
          // PNTR record form exposes record_value/value/target. Fill only target field.
          let value=null;
          const inputs=p.locator('input');
          for(let i=0;i<await inputs.count();i++){
            const x=inputs.nth(i);if(!await visible(x))continue;
            const meta=[await x.getAttribute('name'),await x.getAttribute('placeholder'),await x.getAttribute('aria-label')].filter(Boolean).join(' ');
            if(/record.?value|value|target|points|destination|content/i.test(meta)){value=x;break;}
          }
          if(!value){
            out.status='dns_value_control_missing';out.detail=`body=${clean(await body(p))} controls=${await controls(p)}`;save();
          }else{
            await value.fill(cname);
            // For the apex of runner3wp.pntr.dev, leave host/name blank if PNTR provides it.
            const host=p.locator('input[name="record_name"],input[name="host"],input[placeholder*="host" i]').first();
            if(await visible(host))await host.fill('').catch(()=>{});
            const didSave=await clickAny(p,/^Add Record$|^Save Record$|^Create Record$|^Save$|^Add$/i);
            if(!didSave){
              out.status='dns_save_control_missing';out.detail=`body=${clean(await body(p))} controls=${await controls(p)}`;save();
            }else{
              await p.waitForTimeout(1400);t=await body(p);
              out.cnameConfigured=t.toLowerCase().includes(cname.toLowerCase())&&/cname/i.test(t);
              out.status=out.cnameConfigured?'ready':'dns_unconfirmed';
              if(!out.cnameConfigured)out.detail=`body=${clean(t)} controls=${await controls(p)}`;
              save();
            }
          }
        }
      }
    }
  }
}catch(e){out.status='error';out.detail=clean(String(e));save();}
finally{
  try{await ctx.storageState({path:'/tmp/pntr-browser-state.json'});}catch{}
  save();await browser.close();
}
