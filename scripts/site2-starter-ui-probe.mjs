#!/usr/bin/env node
import fs from 'node:fs';
import { chromium } from 'playwright-core';
const target=(process.env.SITE2_URL||'https://runner3-wp-a94b8fd2.wasmer.app').replace(/\/$/,'');
let token=String(process.env.WASMER_TOKEN||'').replace(/[\r\n]/g,'').trim();
if(!token) throw new Error('WASMER_TOKEN required');
if(!token.startsWith('wap_')) token=`wap_${token}`;
const chrome=[process.env.CHROME_PATH,'/usr/bin/google-chrome-stable','/usr/bin/google-chrome','/usr/bin/chromium'].filter(Boolean).find(fs.existsSync);
const browser=await chromium.launch({headless:true,executablePath:chrome,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
const page=await browser.newPage({viewport:{width:1440,height:1100}});
const events=[];
page.on('console',m=>events.push({type:'console',level:m.type(),text:m.text().slice(0,500)}));
page.on('response',r=>{const u=r.url(); if(/starter|astra|template|zipwp|wp-json|admin-ajax/i.test(u)) events.push({type:'response',status:r.status(),url:u.slice(0,500)});});
page.on('requestfailed',r=>events.push({type:'requestfailed',url:r.url().slice(0,500),error:r.failure()?.errorText||''}));
await page.goto(`${target}/?rest_route=/wasmer/v1/magiclogin&magiclogin=${encodeURIComponent(token)}`,{waitUntil:'domcontentloaded',timeout:90000});
await page.goto(`${target}/wp-admin/themes.php?page=starter-templates`,{waitUntil:'domcontentloaded',timeout:120000});
await page.waitForTimeout(5000);
async function forceText(re){
  const loc=page.getByText(re).first();
  if(await loc.count()){await loc.evaluate(el=>el.click()); return true;}
  return false;
}
await forceText(/Build with Templates/i);
await page.waitForTimeout(4000);
const beforeBuilder={url:page.url(),body:(await page.locator('body').innerText()).slice(0,5000)};
await forceText(/^Block Editor$/i);
await page.waitForTimeout(12000);
const body=(await page.locator('body').innerText()).slice(0,15000);
const inputs=await page.locator('input').evaluateAll(xs=>xs.map(x=>({type:x.type,placeholder:x.placeholder,name:x.name,aria:x.getAttribute('aria-label'),value:x.value})));
const buttons=await page.getByRole('button').allTextContents();
const links=await page.getByRole('link').evaluateAll(xs=>xs.slice(0,120).map(x=>({text:(x.textContent||'').trim(),href:x.href})));
const texts=await page.locator('body *').evaluateAll(xs=>xs.map(x=>(x.textContent||'').trim()).filter(x=>/ecommerce|commerce|shop|store/i.test(x)&&x.length<160).slice(0,200));
console.log('STARTER_LIBRARY_PROBE',JSON.stringify({beforeBuilder,after:{url:page.url(),title:await page.title(),body,inputs,buttons,links,texts},events:events.slice(-250)},null,2));
await browser.close();
