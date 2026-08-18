import { chromium } from 'playwright-core';
import fs from 'fs';
const email=fs.readFileSync('/tmp/target-email.txt','utf8').trim();
const out={status:'starting',signupUrl:null,captcha:false,payment:false,fields:[],buttons:[],detail:null,updatedAt:new Date().toISOString()};
const save=()=>{out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/cloudns-probe.json',JSON.stringify(out,null,2));};
const clean=s=>String(s||'').replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'EMAIL_REDACTED').slice(0,3000);
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext();const p=await ctx.newPage();
try{
 save();
 await p.goto('https://www.cloudns.net/index/show/signup/',{waitUntil:'domcontentloaded',timeout:60000});
 await p.waitForTimeout(1800);
 out.signupUrl=p.url();
 const body=(await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();
 const html=(await p.content()).toLowerCase();
 out.captcha=/recaptcha|hcaptcha|turnstile|captcha|verify you are human|cf-chl/i.test(html+' '+body);
 out.payment=/credit card|payment method|billing information|card details/i.test(body);
 out.fields=await p.locator('input,select,textarea').evaluateAll(xs=>xs.map(x=>({tag:x.tagName.toLowerCase(),type:x.getAttribute('type'),name:x.getAttribute('name'),id:x.id||null,placeholder:x.getAttribute('placeholder'),required:x.required||x.getAttribute('aria-required')==='true'})).filter(x=>x.type!=='hidden').slice(0,50));
 out.buttons=await p.locator('button,input[type=submit],a').evaluateAll(xs=>xs.map(x=>({tag:x.tagName.toLowerCase(),text:(x.innerText||x.value||x.textContent||'').replace(/\s+/g,' ').trim().slice(0,100),type:x.getAttribute('type')})).filter(x=>/sign|register|create|free|submit|continue|account/i.test(x.text)).slice(0,30));
 out.status=out.captcha?'blocked_captcha':(out.payment?'blocked_payment':'signup_form_available');
 out.detail=clean(body);save();
}catch(e){out.status='error';out.detail=clean(String(e));save();}finally{await browser.close();}
