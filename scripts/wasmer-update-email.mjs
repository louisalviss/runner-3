import { chromium } from 'playwright-core';
import fs from 'fs';

const targetEmail = fs.readFileSync('/tmp/target-email.txt', 'utf8').trim();
const out = {status:'starting',profile:false,emailUpdated:false,resendClicked:false,confirmationDetected:false,detail:null,updatedAt:new Date().toISOString()};
function save(){out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-email-update.json',JSON.stringify(out,null,2));}
function redact(s=''){return String(s).replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'EMAIL_REDACTED').slice(0,1800);}
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({storageState:'/tmp/wasmer-browser-state.json'});
const page=await ctx.newPage();
try{
  save();
  await page.goto('https://wasmer.io/settings/profile',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1200);
  let t=await body(page);
  if(/\/login(?:[/?#]|$)/i.test(page.url())){out.status='stored_session_expired';out.detail=redact(t);save();process.exit(0);}
  out.profile=true;save();

  const email=page.locator('input[name=email],input[type=email],input[placeholder*="email" i]').first();
  if(!(await email.waitFor({state:'visible',timeout:10000}).then(()=>true).catch(()=>false))){out.status='email_input_missing';out.detail=redact(t);save();process.exit(0);}
  await email.fill(targetEmail);

  const update=page.locator('button').filter({hasText:/Update email/i}).first();
  if(!(await update.waitFor({state:'visible',timeout:5000}).then(()=>true).catch(()=>false))){out.status='update_button_missing';out.detail=redact(t);save();process.exit(0);}
  await update.click();
  await page.waitForTimeout(2200);
  const current=await email.inputValue().catch(()=> '');
  out.emailUpdated=current.trim().toLowerCase()===targetEmail.toLowerCase();

  const resend=page.locator('button').filter({hasText:/Resend verification email/i}).first();
  if(await resend.count()&&await resend.isVisible().catch(()=>false)){
    await resend.click();
    out.resendClicked=true;
    await page.waitForTimeout(1800);
  }
  t=await body(page);
  const safe=redact(t);
  out.confirmationDetected=out.emailUpdated && (/verifying|verification|verify|resend verification email/i.test(t));
  out.status=out.confirmationDetected?'verification_email_requested':(out.emailUpdated?'email_updated_unconfirmed':'email_update_failed');
  out.detail=safe;save();
}catch(e){out.status='error';out.detail=redact(String(e));save();}finally{await browser.close();}
