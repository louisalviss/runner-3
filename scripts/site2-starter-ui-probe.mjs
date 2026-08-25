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
const pagesResp=await page.request.get(`${target}/?rest_route=/wp/v2/pages&per_page=100&context=edit&_fields=id,slug,link,title,status,parent&orderby=id&order=asc`);
const pages=await pagesResp.json();
const out={pages:Array.isArray(pages)?pages.map(p=>({id:p.id,slug:p.slug,link:p.link,title:p.title?.rendered,status:p.status,parent:p.parent})):pages};
for(const [key,url] of Object.entries({products:`${target}/wp-admin/admin.php?page=wc-settings&tab=products`,advanced:`${target}/wp-admin/admin.php?page=wc-settings&tab=advanced`,visibility:`${target}/wp-admin/admin.php?page=wc-settings&tab=site-visibility`})){
 await page.goto(url,{waitUntil:'domcontentloaded',timeout:120000}); await page.waitForTimeout(1200);
 out[key]=await page.locator('input,select').evaluateAll(xs=>xs.map(x=>({name:x.name||'',id:x.id||'',type:x.type||'',value:x.value||'',checked:!!x.checked})).filter(x=>/^woocommerce_(shop|cart|checkout|myaccount|terms|coming_soon|store_pages_only)/.test(x.name||x.id)));
}
await page.goto(`${target}/`,{waitUntil:'domcontentloaded',timeout:120000});
out.nav=await page.locator('header a, nav a').evaluateAll(xs=>xs.map(a=>({text:(a.textContent||'').trim(),href:a.href})).filter(x=>/Everything|Groceries|Juice|Cart|Account|Shop/i.test(x.text)));
console.log('SITE2_CORE_PAGE_MAP',JSON.stringify(out,null,2));
await browser.close();
