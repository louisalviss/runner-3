import { chromium } from 'playwright-core';
import fs from 'fs';

const fqdn='runner3wp.pntr.dev';
const cname='lnh8iwtjmk3x.id.wasmer.app';
const out={status:'starting',domain:fqdn,registered:false,cnameConfigured:false,dnsTarget:cname,detail:null,updatedAt:new Date().toISOString()};
const save=()=>{out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/pntr-status.json',JSON.stringify(out,null,2));};
const clean=s=>String(s||'').replace(/[A-Za-z0-9_-]{28,}/g,'REDACTED').slice(0,4200);
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function visible(l){return !!(await l.count().catch(()=>0))&&await l.isVisible().catch(()=>false);}
async function controls(p){return clean(JSON.stringify(await p.locator('input,button,a,[role=button]').evaluateAll(xs=>xs.map(x=>({tag:x.tagName.toLowerCase(),text:(x.innerText||x.textContent||x.getAttribute('value')||'').replace(/\s+/g,' ').trim().slice(0,120),type:x.getAttribute('type'),name:x.getAttribute('name'),placeholder:x.getAttribute('placeholder'),aria:x.getAttribute('aria-label'),value:x.tagName==='INPUT'?x.value:null})).filter(x=>x.text||x.placeholder||x.name||x.aria).slice(0,120)).catch(()=>[])))}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const storage=JSON.parse(fs.readFileSync('/tmp/pntr-browser-state.json','utf8'));
const ctx=await browser.newContext({storageState:storage});
const p=await ctx.newPage();
try{
  save();
  await p.goto('https://pntr.dev/dashboard',{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(1200);
  let t=await body(p);
  if(/no subdomains yet/i.test(t)||!t.toLowerCase().includes(fqdn)){
    out.status='stored_session_missing_domain';out.detail=`body=${clean(t)} controls=${await controls(p)}`;
  }else{
    out.registered=true;
    const card=p.locator('[role=button]').filter({hasText:new RegExp(fqdn.replaceAll('.','\\.'),'i')}).first();
    if(await visible(card)){await card.click();await p.waitForTimeout(650);}
    t=await body(p);
    if(t.toLowerCase().includes(cname.toLowerCase())&&/cname/i.test(t)){
      out.cnameConfigured=true;out.status='ready';
    }else{
      // Open PNTR's inline record form.
      const openAdd=p.locator('button').filter({hasText:/^Add Record$/i}).first();
      if(await visible(openAdd)){await openAdd.click();await p.waitForTimeout(450);}

      // Then choose CNAME from the explicit type buttons.
      const cnameBtn=p.locator('button').filter({hasText:/^CNAME$/i}).first();
      if(!await visible(cnameBtn)){
        out.status='cname_button_missing';out.detail=`body=${clean(await body(p))} controls=${await controls(p)}`;
      }else{
        await cnameBtn.click();await p.waitForTimeout(350);
        const textInputs=p.locator('input[type=text]');
        let valueInput=null;
        for(let i=0;i<await textInputs.count();i++){
          const x=textInputs.nth(i);if(await visible(x)){valueInput=x;break;}
        }
        if(!valueInput){
          out.status='dns_value_control_missing';out.detail=`body=${clean(await body(p))} controls=${await controls(p)}`;
        }else{
          await valueInput.fill(cname);
          // After the form is open, the submit control is also labelled Add Record.
          const submits=p.locator('button[type=submit]').filter({hasText:/^Add Record$/i});
          let submit=null;
          for(let i=0;i<await submits.count();i++){const x=submits.nth(i);if(await visible(x)){submit=x;break;}}
          if(!submit){
            out.status='dns_save_control_missing';out.detail=`body=${clean(await body(p))} controls=${await controls(p)}`;
          }else{
            await submit.click();await p.waitForTimeout(1500);
            t=await body(p);
            out.cnameConfigured=t.toLowerCase().includes(cname.toLowerCase())&&/cname/i.test(t);
            out.status=out.cnameConfigured?'ready':'dns_unconfirmed';
            if(!out.cnameConfigured)out.detail=`body=${clean(t)} controls=${await controls(p)}`;
          }
        }
      }
    }
  }
}catch(e){out.status='error';out.detail=clean(String(e));}
finally{
  try{await ctx.storageState({path:'/tmp/pntr-browser-state.json'});}catch{}
  save();await browser.close();
}
