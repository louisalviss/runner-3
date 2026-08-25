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
await page.goto(`${target}/wp-admin/plugins.php`,{waitUntil:'domcontentloaded',timeout:90000});
const pluginRow=page.locator('tr[data-slug="astra-sites"]').first();
const pluginInfo={exists:!!(await pluginRow.count()),text:(await pluginRow.innerText().catch(()=>'')),links:await pluginRow.locator('a').evaluateAll(xs=>xs.map(x=>({text:(x.textContent||'').trim(),href:x.href,class:x.className})))};
const menuLinks=await page.locator('#adminmenu a').evaluateAll(xs=>xs.map(x=>({text:(x.textContent||'').trim(),href:x.href})).filter(x=>/starter|astra|template/i.test(x.text+x.href)));
const candidates=[...menuLinks.map(x=>x.href),`${target}/wp-admin/admin.php?page=starter-templates`,`${target}/wp-admin/themes.php?page=starter-templates`,`${target}/wp-admin/admin.php?page=astra-sites`];
const tried=[];
for(const url of [...new Set(candidates)]){
  await page.goto(url,{waitUntil:'domcontentloaded',timeout:90000});
  await page.waitForTimeout(3000);
  tried.push({url:page.url(),title:await page.title(),body:(await page.locator('body').innerText()).slice(0,2500),inputs:await page.locator('input').evaluateAll(xs=>xs.map(x=>({type:x.type,placeholder:x.placeholder,name:x.name,aria:x.getAttribute('aria-label')})))});
}
console.log('STARTER_UI_PROBE',JSON.stringify({pluginInfo,menuLinks,tried},null,2));
await browser.close();
