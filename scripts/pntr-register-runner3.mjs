import { chromium } from 'playwright-core';
import fs from 'fs';

const name='runner3wp';
const fqdn=`${name}.pntr.dev`;
const cname='lnh8iwtjmk3x.id.wasmer.app';
const out={status:'starting',domain:fqdn,registered:false,cnameConfigured:false,dnsTarget:cname,detail:null,updatedAt:new Date().toISOString()};
const save=()=>{out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/pntr-status.json',JSON.stringify(out,null,2));};
const clean=s=>String(s||'').replace(/[A-Za-z0-9_-]{28,}/g,'REDACTED').slice(0,3200);
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function visible(loc){return !!(await loc.count().catch(()=>0)) && await loc.isVisible().catch(()=>false);}
async function dumpControls(p){
  const rows=await p.locator('input,button,a,select,[role=button]').evaluateAll(xs=>xs.map(x=>({tag:x.tagName.toLowerCase(),text:(x.innerText||x.textContent||x.getAttribute('value')||'').replace(/\s+/g,' ').trim().slice(0,100),href:x.getAttribute('href'),type:x.getAttribute('type'),name:x.getAttribute('name'),placeholder:x.getAttribute('placeholder'),value:x.tagName==='INPUT'?x.value:null})).filter(x=>x.text||x.placeholder||x.name).slice(0,100)).catch(()=>[]);
  return clean(JSON.stringify(rows));
}
async function clickVisible(p,selector,re){
  const xs=p.locator(selector).filter({hasText:re});
  for(let i=0;i<await xs.count();i++){const x=xs.nth(i);if(await visible(x)){await x.click();await p.waitForTimeout(900);return true;}}
  return false;
}

async function main(){
  const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
  const ctx=await browser.newContext();
  const p=await ctx.newPage();
  try{
    save();
    await p.goto('https://pntr.dev/dashboard',{waitUntil:'domcontentloaded',timeout:60000});
    await p.waitForTimeout(1300);
    let t=await body(p);
    if(/captcha|verify you are human|turnstile|hcaptcha|recaptcha/i.test(t)){
      out.status='blocked_human_verification';out.detail=clean(t);return;
    }

    // Open the official Add Subdomain dialog and create the domain.
    await clickVisible(p,'button,[role=button]',/^Add subdomain$/i);
    let nameInput=p.locator('input[name="name"],input[placeholder="my-project"]').first();
    if(!await visible(nameInput)){
      out.status='create_form_missing';out.detail=`body=${clean(await body(p))} controls=${await dumpControls(p)}`;return;
    }
    await nameInput.fill(name);
    await p.waitForTimeout(900);
    t=await body(p);
    if(/already taken|unavailable|not available/i.test(t)){
      out.status='name_unavailable';out.detail=clean(t);return;
    }
    const create=p.locator('button[type=submit],button').filter({hasText:/^Create Subdomain$/i}).first();
    if(!await visible(create)){
      out.status='create_button_missing';out.detail=`body=${clean(t)} controls=${await dumpControls(p)}`;return;
    }
    await create.click();
    await p.waitForTimeout(1800);
    t=await body(p);
    out.registered=t.toLowerCase().includes(fqdn.toLowerCase()) && !/your domain will be/i.test(t);
    if(!out.registered){
      out.status='creation_unconfirmed';out.detail=`url=${p.url()} body=${clean(t)} controls=${await dumpControls(p)}`;return;
    }

    // Open the newly-created subdomain detail/card.
    let domainCtl=p.locator('a,button,[role=button]').filter({hasText:new RegExp(fqdn.replaceAll('.','\\.'),'i')}).first();
    if(!await visible(domainCtl)) domainCtl=p.locator('a,button,[role=button]').filter({hasText:new RegExp(name,'i')}).first();
    if(await visible(domainCtl)){await domainCtl.click();await p.waitForTimeout(1000);}
    t=await body(p);

    // If the DNS controls are not on the current view, preserve the created session
    // and report the exact DOM for a deterministic continuation run.
    let add=p.locator('button,[role=button]').filter({hasText:/add (dns )?record|new record/i}).first();
    if(!await visible(add)){
      out.status='created_need_dns_inspect';
      out.detail=`url=${p.url()} body=${clean(t)} controls=${await dumpControls(p)}`;
      return;
    }

    await add.click();await p.waitForTimeout(600);
    // Native PNTR form uses select/input controls; choose CNAME explicitly.
    const selects=p.locator('select');
    let typeChosen=false;
    for(let i=0;i<await selects.count();i++){
      const s=selects.nth(i);if(!await visible(s))continue;
      const opts=await s.locator('option').evaluateAll(os=>os.map(o=>({v:o.value,t:(o.textContent||'').trim()}))).catch(()=>[]);
      const c=opts.find(o=>/cname/i.test(o.t)||/^CNAME$/i.test(o.v));
      if(c){await s.selectOption(c.v);typeChosen=true;break;}
    }
    if(!typeChosen){
      const combo=p.getByRole('combobox').first();
      if(await visible(combo)){await combo.click();await p.waitForTimeout(250);const opt=p.getByRole('option',{name:/CNAME/i}).first();if(await visible(opt)){await opt.click();typeChosen=true;}}
    }
    if(!typeChosen){out.status='record_type_control_missing';out.detail=`body=${clean(await body(p))} controls=${await dumpControls(p)}`;return;}

    const inputs=p.locator('input');
    let valueInput=null;
    for(let i=0;i<await inputs.count();i++){
      const x=inputs.nth(i);if(!await visible(x))continue;
      const meta=[await x.getAttribute('name'),await x.getAttribute('placeholder'),await x.getAttribute('aria-label')].filter(Boolean).join(' ');
      if(/value|target|points|destination|content/i.test(meta)){valueInput=x;break;}
    }
    if(!valueInput){
      const vis=[];for(let i=0;i<await inputs.count();i++){const x=inputs.nth(i);if(await visible(x)&&!['hidden','checkbox','radio'].includes((await x.getAttribute('type'))||''))vis.push(x);}valueInput=vis.at(-1)||null;
    }
    if(!valueInput){out.status='dns_target_input_missing';out.detail=`body=${clean(await body(p))} controls=${await dumpControls(p)}`;return;}
    await valueInput.fill(cname);

    let saveBtn=p.locator('button[type=submit],button').filter({hasText:/add record|save record|create record|^save$/i}).first();
    if(!await visible(saveBtn)){out.status='dns_save_control_missing';out.detail=`body=${clean(await body(p))} controls=${await dumpControls(p)}`;return;}
    await saveBtn.click();await p.waitForTimeout(1500);
    t=await body(p);
    out.cnameConfigured=t.toLowerCase().includes(cname.toLowerCase()) && /cname/i.test(t);
    out.status=out.cnameConfigured?'ready':'dns_unconfirmed';
    if(!out.cnameConfigured)out.detail=`url=${p.url()} body=${clean(t)} controls=${await dumpControls(p)}`;
  }catch(e){out.status='error';out.detail=clean(String(e));}
  finally{
    try{await ctx.storageState({path:'/tmp/pntr-browser-state.json'});}catch{}
    save();
    await browser.close();
  }
}

await main();
