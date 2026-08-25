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
await page.goto(`${target}/wp-admin/edit.php?post_type=product`,{waitUntil:'domcontentloaded',timeout:120000});
out.admin={
  url:page.url(),
  title:await page.title(),
  productRows:await page.locator('table.wp-list-table tbody tr').count(),
  publishedText:(await page.locator('.subsubsub').innerText().catch(()=>'')),
  body:(await page.locator('body').innerText().catch(()=>'')).slice(0,5000)
};

const api=await page.request.get(`${target}/?rest_route=/wc/store/v1/products&per_page=100&_=${Date.now()}`);
let apiBody=''; try{apiBody=await api.text();}catch{}
let apiJson=null; try{apiJson=JSON.parse(apiBody);}catch{}
out.storeApi={status:api.status(),count:Array.isArray(apiJson)?apiJson.length:null,body:apiBody.slice(0,3000)};

for(const path of ['/','/shop/']){
  const r=await page.goto(`${target}${path}?__woo_probe=${Date.now()}`,{waitUntil:'domcontentloaded',timeout:120000});
  const body=await page.locator('body').innerText().catch(()=>'');
  out[path]={
    status:r?.status()??null,
    url:page.url(),
    title:await page.title(),
    bodyClass:await page.locator('body').getAttribute('class'),
    productCards:await page.locator('li.product, .wc-block-product, .products .product').count(),
    addToCart:await page.getByText(/Add to cart/i).count(),
    text:body.slice(0,6000)
  };
}

await page.goto(`${target}/wp-admin/admin.php?page=wc-settings`,{waitUntil:'domcontentloaded',timeout:120000});
out.settings={url:page.url(),body:(await page.locator('body').innerText().catch(()=>'')).slice(0,7000)};
console.log('SITE2_WOO_PROBE',JSON.stringify(out,null,2));
await browser.close();
