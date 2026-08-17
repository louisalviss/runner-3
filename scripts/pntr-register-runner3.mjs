import { chromium } from 'playwright-core';
import fs from 'fs';

const name='runner3wp';
const fqdn=`${name}.pntr.dev`;
const cname='lnh8iwtjmk3x.id.wasmer.app';
const out={status:'starting',domain:fqdn,registered:false,cnameConfigured:false,dnsTarget:cname,detail:null,updatedAt:new Date().toISOString()};
const save=()=>{out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/pntr-status.json',JSON.stringify(out,null,2));};
const clean=s=>String(s||'').replace(/[A-Za-z0-9_-]{28,}/g,'REDACTED').slice(0,2800);
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function visible(loc){return !!(await loc.count().catch(()=>0)) && await loc.isVisible().catch(()=>false);}
async function clickText(p,re){
  for(const sel of ['button','a','[role=button]']){
    const l=p.locator(sel).filter({hasText:re}).first();
    if(await visible(l)){await l.click().catch(()=>{});await p.waitForTimeout(800);return true;}
  }
  return false;
}
async function findNameInput(p){
  const candidates=[
    'input[placeholder*="your-project" i]',
    'input[placeholder*="subdomain" i]',
    'input[name*="subdomain" i]',
    'input[name="name"]',
    'input[type=text]'
  ];
  for(const s of candidates){
    const xs=p.locator(s);
    for(let i=0;i<await xs.count();i++) if(await xs.nth(i).isVisible().catch(()=>false)) return xs.nth(i);
  }
  return null;
}
async function dumpControls(p){
  const rows=await p.locator('input,button,a,select,[role=button]').evaluateAll(xs=>xs.map(x=>({tag:x.tagName.toLowerCase(),text:(x.innerText||x.textContent||x.getAttribute('value')||'').replace(/\s+/g,' ').trim().slice(0,100),href:x.getAttribute('href'),type:x.getAttribute('type'),name:x.getAttribute('name'),placeholder:x.getAttribute('placeholder')})).filter(x=>x.text||x.placeholder||x.name).slice(0,80)).catch(()=>[]);
  return clean(JSON.stringify(rows));
}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext();
const p=await ctx.newPage();
try{
  save();
  await p.goto('https://pntr.dev/',{waitUntil:'domcontentloaded',timeout:60000});
  await p.waitForTimeout(1500);
  let t=await body(p);
  if(/captcha|verify you are human|turnstile|hcaptcha|recaptcha/i.test(t)){out.status='blocked_human_verification';out.detail=clean(t);save();process.exit(0);}

  // The landing page itself exposes a name checker. Use it first so the same
  // anonymous browser session becomes the owner when PNTR hands us to dashboard.
  let input=await findNameInput(p);
  if(input){
    await input.fill(name);
    await clickText(p,/check name|check availability|check/i);
    await p.waitForTimeout(900);
  }

  t=await body(p);
  if(/not available|already taken|unavailable/i.test(t) && t.toLowerCase().includes(name)){
    out.status='name_unavailable';out.detail=clean(t);save();process.exit(0);
  }

  // Follow PNTR's own registration/claim CTA if shown.
  await clickText(p,/claim|register|create subdomain|use this name|get subdomain|continue/i);
  await p.waitForTimeout(1200);

  // Open dashboard if we are still on landing page.
  if(!/dashboard/i.test(p.url())){
    const dash=p.locator('a').filter({hasText:/open dashboard|dashboard/i}).first();
    if(await visible(dash)){
      const href=await dash.getAttribute('href');
      if(href) await p.goto(new URL(href,p.url()).toString(),{waitUntil:'domcontentloaded',timeout:60000});
      else await dash.click();
      await p.waitForTimeout(1300);
    }
  }

  t=await body(p);
  // If dashboard has no domain yet, use its visible create controls.
  if(!t.toLowerCase().includes(fqdn)){
    input=await findNameInput(p);
    if(input){
      await input.fill(name);
      await clickText(p,/check|create|register|claim|add/i);
      await p.waitForTimeout(1200);
      t=await body(p);
      if(!t.toLowerCase().includes(fqdn)){
        await clickText(p,/claim|register|create|confirm|continue/i);
        await p.waitForTimeout(1200);
        t=await body(p);
      }
    }
  }

  out.registered=t.toLowerCase().includes(fqdn) || (t.toLowerCase().includes(name) && /dns|record|subdomain/i.test(t));
  if(!out.registered){
    out.status='registration_unconfirmed';
    out.detail=`url=${p.url()} body=${clean(t)} controls=${await dumpControls(p)}`;
    save();process.exit(0);
  }

  // Enter the domain card/detail if necessary.
  const domainLink=p.locator('a,button,[role=button]').filter({hasText:new RegExp(name,'i')}).first();
  if(await visible(domainLink)){
    await domainLink.click().catch(()=>{});
    await p.waitForTimeout(900);
  }

  t=await body(p);
  // Add a CNAME through the dashboard. A CNAME must be the only DNS record.
  // Remove a default A/AAAA record only if PNTR created one automatically.
  if(!t.toLowerCase().includes(cname.toLowerCase())){
    let add=p.locator('button,[role=button]').filter({hasText:/add record|new record|add dns/i}).first();
    if(!await visible(add)) add=p.locator('button,[role=button]').filter({hasText:/^add$/i}).first();
    if(await visible(add)){await add.click();await p.waitForTimeout(600);}

    // Pick CNAME from a native select or combobox.
    const selects=p.locator('select');
    for(let i=0;i<await selects.count();i++){
      const s=selects.nth(i);if(!await s.isVisible().catch(()=>false))continue;
      const opts=await s.locator('option').evaluateAll(os=>os.map(o=>({v:o.value,t:(o.textContent||'').trim()}))).catch(()=>[]);
      const c=opts.find(o=>/cname/i.test(o.t)||/cname/i.test(o.v));
      if(c){await s.selectOption(c.v).catch(()=>{});break;}
    }
    const combo=p.getByRole('combobox').filter({hasText:/a|aaaa|cname|record type/i}).first();
    if(await visible(combo)){
      await combo.click().catch(()=>{});await p.waitForTimeout(300);
      const opt=p.getByRole('option',{name:/CNAME/i}).first();if(await visible(opt))await opt.click().catch(()=>{});
      else await clickText(p,/^CNAME$/i);
    }

    // Fill record value/target. Avoid the subdomain-name field itself.
    const inputs=p.locator('input');
    let targetInput=null;
    for(let i=0;i<await inputs.count();i++){
      const x=inputs.nth(i);if(!await x.isVisible().catch(()=>false))continue;
      const meta=((await x.getAttribute('name'))||'')+' '+((await x.getAttribute('placeholder'))||'')+' '+((await x.getAttribute('aria-label'))||'');
      if(/value|target|points|destination|content/i.test(meta)){targetInput=x;break;}
    }
    if(!targetInput){
      const visibleText=[];
      for(let i=0;i<await inputs.count();i++){const x=inputs.nth(i);if(await x.isVisible().catch(()=>false)){const type=await x.getAttribute('type');if(type!=='hidden'&&type!=='checkbox'&&type!=='radio')visibleText.push(x);}}
      targetInput=visibleText.at(-1)||null;
    }
    if(!targetInput){out.status='dns_target_input_missing';out.detail=`body=${clean(await body(p))} controls=${await dumpControls(p)}`;save();process.exit(0);}
    await targetInput.fill(cname);
    const hostInput=p.locator('input[name*="host" i],input[name*="name" i],input[placeholder*="name" i],input[placeholder*="host" i]').first();
    if(await visible(hostInput)){
      const current=await hostInput.inputValue().catch(()=>'');
      if(!current)await hostInput.fill('@').catch(()=>{});
    }
    const saved=await clickText(p,/save record|add record|create record|save|confirm/i);
    if(!saved){out.status='dns_save_control_missing';out.detail=`body=${clean(await body(p))} controls=${await dumpControls(p)}`;save();process.exit(0);}
    await p.waitForTimeout(1300);
  }

  t=await body(p);
  out.cnameConfigured=t.toLowerCase().includes(cname.toLowerCase()) || (/cname/i.test(t)&&t.toLowerCase().includes('lnh8iwtjmk3x'));
  out.status=out.cnameConfigured?'ready':'dns_unconfirmed';
  if(out.status!=='ready')out.detail=`url=${p.url()} body=${clean(t)} controls=${await dumpControls(p)}`;
  await ctx.storageState({path:'/tmp/pntr-browser-state.json'});
  save();
}catch(e){out.status='error';out.detail=clean(String(e));save();try{await ctx.storageState({path:'/tmp/pntr-browser-state.json'});}catch{}}
finally{await browser.close();}
