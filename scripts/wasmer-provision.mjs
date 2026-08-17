import { chromium } from 'playwright-core';
import fs from 'fs';
import crypto from 'crypto';

const mail=JSON.parse(fs.readFileSync('/tmp/mailtm.json','utf8'));
const username='runner3wp'+crypto.randomBytes(5).toString('hex');
const password=crypto.randomBytes(27).toString('base64url');
const appName='runner3-wp-'+crypto.randomBytes(4).toString('hex');
const result={provider:'wasmer',plan:'hobby',username,email:mail.address,password,appName,status:'started',siteUrl:null,detail:null,createdAt:new Date().toISOString()};
const safe={status:'started',appName,siteUrl:null,detail:null,updatedAt:new Date().toISOString()};

function save(){
  fs.writeFileSync('/tmp/wasmer-result.json',JSON.stringify(result,null,2));
  safe.status=result.status;
  safe.siteUrl=result.siteUrl;
  safe.detail=result.detail;
  safe.updatedAt=new Date().toISOString();
  fs.writeFileSync('/tmp/wasmer-status.json',JSON.stringify(safe,null,2));
}
async function bodyText(page){return (await page.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
function blockedReason(text,html=''){
  const s=(text+' '+html).toLowerCase();
  if(/recaptcha|hcaptcha|turnstile|verify you are human|security verification|captcha/.test(s)) return 'captcha';
  if(/credit card|payment method|add card|billing information|card details/.test(s)) return 'payment';
  return null;
}
async function pollVerificationLink(){
  const headers={Authorization:'Bearer '+mail.token};
  let lastSubject='';
  for(let i=0;i<30;i++){
    await new Promise(r=>setTimeout(r,4000));
    const list=await fetch('https://api.mail.tm/messages',{headers}).then(r=>r.json()).catch(()=>null);
    const msgs=list?.['hydra:member']||list?.member||[];
    for(const m of msgs){
      lastSubject=m.subject||lastSubject;
      const msg=await fetch('https://api.mail.tm/messages/'+m.id,{headers}).then(r=>r.json()).catch(()=>null);
      if(!msg) continue;
      const raw=[msg.text||'',...(Array.isArray(msg.html)?msg.html:[msg.html||''])].join('\n').replace(/&amp;/g,'&');
      const urls=[...raw.matchAll(/https?:\/\/[^\s<>"']+/g)].map(x=>x[0].replace(/[).,]+$/,''));
      const ranked=urls.filter(u=>/wasmer\.io/i.test(u)).sort((a,b)=>{
        const score=u=>/valid|verify|confirm|activate|token|email/i.test(u)?3:/[?&](token|code|key)=/i.test(u)?2:u.length>50?1:0;
        return score(b)-score(a);
      });
      if(ranked[0]) return {url:ranked[0],subject:lastSubject};
    }
  }
  return {url:null,subject:lastSubject};
}
async function loginIfNeeded(page){
  if(!/login/i.test(page.url())) return;
  const ident=page.locator('input[type=email],input[name*=email i],input[name*=user i],input[type=text]').first();
  const pass=page.locator('input[type=password]').first();
  if(await ident.count()) await ident.fill(mail.address);
  if(await pass.count()) await pass.fill(password);
  const btn=page.getByRole('button',{name:/log in|sign in|continue/i}).first();
  if(await btn.count()) await btn.click().catch(()=>{});
  await page.waitForTimeout(2200);
}
async function chooseDefaults(page){
  const selects=page.locator('select');
  for(let i=0;i<await selects.count();i++){
    const s=selects.nth(i);
    const opts=await s.locator('option').evaluateAll(os=>os.map(o=>({v:o.value,t:o.textContent?.trim()||'',d:o.disabled}))).catch(()=>[]);
    const pick=opts.find(o=>!o.d && o.v && !/select|choose/i.test(o.t));
    if(pick) await s.selectOption(pick.v).catch(()=>{});
  }
  const combos=page.getByRole('combobox');
  for(let i=0;i<Math.min(await combos.count(),5);i++){
    const c=combos.nth(i);
    await c.click().catch(()=>{});
    await page.waitForTimeout(250);
    const opts=page.getByRole('option');
    for(let j=0;j<Math.min(await opts.count(),15);j++){
      const o=opts.nth(j);
      if(await o.isVisible().catch(()=>false)){await o.click().catch(()=>{});break;}
    }
  }
}

async function main(){
  save();
  const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
  const ctx=await browser.newContext();
  const page=await ctx.newPage();
  try{
    await page.goto('https://wasmer.io/signup',{waitUntil:'domcontentloaded',timeout:60000});
    await page.waitForTimeout(1600);
    let text=await bodyText(page); let html=(await page.content()).toLowerCase();
    let blocked=blockedReason(text,html);
    if(blocked){result.status='blocked_'+blocked;result.detail='signup_entry';save();return;}

    const personal=page.getByRole('button',{name:/personal/i}).first();
    if(await personal.count()) await personal.click().catch(()=>{});
    const cont=page.getByRole('button',{name:/continue/i}).first();
    if(await cont.count()) await cont.click().catch(()=>{});
    await page.waitForTimeout(1000);

    const user=page.locator('input[name=username],input[placeholder*=Username i]').first();
    const email=page.locator('input[type=email],input[name=email]').first();
    const pass=page.locator('input[type=password],input[name=password]').first();
    if(!(await user.count())||!(await email.count())||!(await pass.count())){result.status='blocked_signup_form';result.detail='required_fields_missing';save();return;}
    await user.fill(username); await email.fill(mail.address); await pass.fill(password);

    const checkbox=page.getByRole('checkbox').first();
    if(await checkbox.count()){
      const checked=await checkbox.isChecked().catch(()=>false);
      if(!checked) await checkbox.click().catch(()=>{});
    }else{
      const aria=page.locator('[role=checkbox]').first();
      if(await aria.count()) await aria.click().catch(()=>{});
      else {
        const falseBtn=page.getByRole('button',{name:/^false$/i}).first();
        if(await falseBtn.count()) await falseBtn.click().catch(()=>{});
      }
    }

    const signup=page.getByRole('button',{name:/sign up/i}).first();
    if(!(await signup.count())){result.status='blocked_signup_form';result.detail='signup_button_missing';save();return;}
    await signup.click();
    await page.waitForTimeout(2600);

    text=await bodyText(page); html=(await page.content()).toLowerCase(); blocked=blockedReason(text,html);
    if(blocked){result.status='blocked_'+blocked;result.detail='after_signup_submit';save();return;}
    if(/already exists|already taken|invalid email|disposable|not allowed/i.test(text)){result.status='blocked_signup_rejected';result.detail=text.slice(0,350);save();return;}

    result.status='account_submitted';save();
    if(/validat|verify|confirm.*email|check.*email/i.test(text)||/terms/i.test(page.url())){
      const verification=await pollVerificationLink();
      if(!verification.url){result.status='blocked_email_verification';result.detail='mail_not_found subject='+verification.subject;save();return;}
      await page.goto(verification.url,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>null);
      await page.waitForTimeout(2200);
    }

    text=await bodyText(page); html=(await page.content()).toLowerCase(); blocked=blockedReason(text,html);
    if(blocked){result.status='blocked_'+blocked;result.detail='after_email_verification';save();return;}
    const accept=page.getByRole('button',{name:/accept|agree/i}).first();
    if(await accept.count()){await accept.click().catch(()=>{});await page.waitForTimeout(1600);}
    await loginIfNeeded(page);

    await page.goto('https://wasmer.io/apps/create?template=wordpress-starter',{waitUntil:'domcontentloaded',timeout:60000});
    await page.waitForTimeout(2000);
    await loginIfNeeded(page);
    if(/login|signup/.test(page.url())){result.status='blocked_login';result.detail='could_not_authenticate_after_signup';save();return;}

    text=await bodyText(page); html=(await page.content()).toLowerCase(); blocked=blockedReason(text,html);
    if(blocked){result.status='blocked_'+blocked;result.detail='wordpress_create_entry';save();return;}

    const named=page.locator('input[name*=name i],input[placeholder*=name i]').first();
    if(await named.count()) await named.fill(appName);
    else {
      const inputs=page.locator('input:not([type=hidden]):not([type=password])');
      if(await inputs.count()) await inputs.first().fill(appName).catch(()=>{});
    }
    await chooseDefaults(page);

    const deploy=page.getByRole('button',{name:/deploy now|deploy/i}).first();
    if(!(await deploy.count())){result.status='blocked_deploy_form';result.detail='deploy_button_missing';save();return;}
    await deploy.click();

    for(let i=0;i<40;i++){
      await page.waitForTimeout(2500);
      text=await bodyText(page); html=(await page.content()).toLowerCase(); blocked=blockedReason(text,html);
      if(blocked){result.status='blocked_'+blocked;result.detail='after_deploy_submit';save();return;}
      const links=await page.locator('a[href*=".wasmer.app"]').evaluateAll(as=>as.map(a=>a.href)).catch(()=>[]);
      if(links.length){result.siteUrl=links[0];result.status='deployed';break;}
      const m=text.match(/https:\/\/[^\s]+\.wasmer\.app\/?/i);
      if(m){result.siteUrl=m[0];result.status='deployed';break;}
      if(/successfully deployed|site.*live|deployment.*complete/i.test(text)) result.status='deployed_pending_url';
    }
    if(!/^deployed/.test(result.status)){result.status='deploy_unconfirmed';result.detail=('url='+page.url()+' '+text.slice(0,300));}
    if(result.siteUrl){const r=await page.request.get(result.siteUrl,{timeout:30000}).catch(()=>null);result.httpStatus=r?.status()||null;}
    save();
  }catch(e){result.status='automation_error';result.detail=String(e).slice(0,600);save();}
  finally{await browser.close();}
}

await main();
