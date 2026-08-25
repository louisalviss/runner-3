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
await page.goto(`${target}/?rest_route=/wasmer/v1/magiclogin&magiclogin=${encodeURIComponent(token)}`,{waitUntil:'domcontentloaded',timeout:90000});
const out={};
for(const [key,url] of Object.entries({visibility:`${target}/wp-admin/admin.php?page=wc-settings&tab=site-visibility`,products:`${target}/wp-admin/admin.php?page=wc-settings&tab=products`})){
  await page.goto(url,{waitUntil:'domcontentloaded',timeout:120000});
  await page.waitForTimeout(1500);
  out[key]={
    url:page.url(),
    inputs:await page.locator('input,select,button').evaluateAll(xs=>xs.map(x=>({tag:x.tagName,type:x.type||'',name:x.name||'',id:x.id||'',value:x.value||'',checked:!!x.checked,text:(x.textContent||'').trim(),aria:x.getAttribute('aria-label')})).filter(x=>x.name||x.id||x.text)),
    body:(await page.locator('body').innerText().catch(()=>'')).slice(0,10000)
  };
}
console.log('SITE2_WOO_SETTINGS_FIELDS',JSON.stringify(out,null,2));
await browser.close();
