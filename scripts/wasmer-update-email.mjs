import { chromium } from 'playwright-core';
import fs from 'fs';

const targetEmail = fs.readFileSync('/tmp/target-email.txt','utf8').trim();
const out={status:'starting',profile:false,emailUpdated:false,resendClicked:false,confirmationDetected:false,detail:null,updatedAt:new Date().toISOString()};
function save(){out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-email-update.json',JSON.stringify(out,null,2));}
function redact(s=''){return String(s).replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'EMAIL_REDACTED').slice(0,1800);}
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({storageState:'/tmp/wasmer-browser-state.json'});const page=await ctx.newPage();
try{
 save();await page.goto('https://wasmer.io/settings/profile',{waitUntil:'domcontentloaded',timeout:60000});await page.waitForTimeout(1200);
 let t=await body(page);if(/\/login(?:[/?#]|$)/i.test(page.url())){out.status='stored_session_expired';out.detail=redact(t);save();process.exit(0);}out.profile=true;
 const email=page.locator('input[name=email],input[type=email],input[placeholder*="email" i]').first();
 if(!(await email.waitFor({state:'visible',timeout:10000}).then(()=>true).catch(()=>false))){out.status='email_input_missing';out.detail=redact(t);save();process.exit(0);}
 let current=(await email.inputValue().catch(()=>'' )).trim();
 if(current.toLowerCase()!==targetEmail.toLowerCase()){
   await email.fill(targetEmail);
   const update=page.locator('button').filter({hasText:/Update email/i}).first();
   if(!(await update.waitFor({state:'visible',timeout:5000}).then(()=>true).catch(()=>false))){out.status='update_button_missing';out.detail=redact(t);save();process.exit(0);}
   await update.click();await page.waitForTimeout(1800);
   current=(await email.inputValue().catch(()=>'' )).trim();
   const dialog=page.locator('[role=dialog]').last();
   if(await dialog.count()&&await dialog.isVisible().catch(()=>false)){
     const dt=await dialog.innerText().catch(()=> '');
     if(/verification|verify|email/i.test(dt)){out.confirmationDetected=true;out.detail=redact(dt);}
     const close=dialog.locator('button').filter({hasText:/close|done|ok|got it/i}).first();
     if(await close.count()&&await close.isVisible().catch(()=>false)) await close.click().catch(()=>{});
     else await page.keyboard.press('Escape').catch(()=>{});
     await page.waitForTimeout(600);
   }
 }
 out.emailUpdated=current.toLowerCase()===targetEmail.toLowerCase();save();
 if(!out.emailUpdated){out.status='email_update_failed';out.detail=redact(await body(page));save();process.exit(0);}
 const resend=page.locator('button').filter({hasText:/Resend verification email/i}).first();
 if(await resend.waitFor({state:'visible',timeout:7000}).then(()=>true).catch(()=>false)){
   await resend.click();out.resendClicked=true;await page.waitForTimeout(1600);
   const dialog=page.locator('[role=dialog]').last();
   if(await dialog.count()&&await dialog.isVisible().catch(()=>false)){const dt=await dialog.innerText().catch(()=> '');out.detail=redact(dt);out.confirmationDetected=/verification|verify|email|sent|inbox/i.test(dt)||out.confirmationDetected;}
 }
 t=await body(page);out.confirmationDetected=out.confirmationDetected||(/verifying|verification/i.test(t)&&out.resendClicked);
 out.status=out.resendClicked?'verification_email_requested':'email_updated_resend_missing';if(!out.detail)out.detail=redact(t);save();
}catch(e){out.status='error';out.detail=redact(String(e));save();}finally{await browser.close();}
