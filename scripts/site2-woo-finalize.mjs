#!/usr/bin/env node
import fs from 'node:fs';
import { chromium } from 'playwright-core';

const target=(process.env.SITE2_URL||'https://runner3-wp-a94b8fd2.wasmer.app').replace(/\/$/,'');
let token=String(process.env.WASMER_TOKEN||'').replace(/[\r\n]/g,'').trim();
if(!token) throw new Error('WASMER_TOKEN required');
if(!token.startsWith('wap_')) token=`wap_${token}`;
const chrome=[process.env.CHROME_PATH,'/usr/bin/google-chrome-stable','/usr/bin/google-chrome','/usr/bin/chromium'].filter(Boolean).find(fs.existsSync);
if(!chrome) throw new Error('Chrome not found');
const browser=await chromium.launch({headless:true,executablePath:chrome,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
const admin=await browser.newPage({viewport:{width:1440,height:1100}});
await admin.goto(`${target}/?rest_route=/wasmer/v1/magiclogin&magiclogin=${encodeURIComponent(token)}`,{waitUntil:'domcontentloaded',timeout:90000});

await admin.goto(`${target}/wp-admin/admin.php?page=wc-settings&tab=site-visibility`,{waitUntil:'domcontentloaded',timeout:120000});
await admin.waitForTimeout(1500);
const form=admin.locator('form#mainform').first();
if(!(await form.count())) throw new Error('WooCommerce settings form missing');
const coming=admin.locator('input[name="woocommerce_coming_soon"]').first();
if(!(await coming.count())) throw new Error('woocommerce_coming_soon field missing');
const before=await coming.inputValue();
if(before!=='no'){
  await coming.evaluate(el=>{el.value='no'; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true}));});
  const save=admin.locator('button[name="save"], input[name="save"]').first();
  if(!(await save.count())) throw new Error('WooCommerce Save changes missing');
  await save.click({force:true});
  await admin.waitForLoadState('domcontentloaded',{timeout:120000}).catch(()=>{});
  await admin.waitForTimeout(2000);
}
await admin.goto(`${target}/wp-admin/admin.php?page=wc-settings&tab=site-visibility`,{waitUntil:'domcontentloaded',timeout:120000});
const after=await admin.locator('input[name="woocommerce_coming_soon"]').first().inputValue();
if(after!=='no') throw new Error(`Store did not switch to Live; woocommerce_coming_soon=${after}`);

await admin.goto(`${target}/wp-admin/admin.php?page=wc-settings&tab=products`,{waitUntil:'domcontentloaded',timeout:120000});
const shopPageId=await admin.locator('#woocommerce_shop_page_id').inputValue();
if(!shopPageId) throw new Error('WooCommerce Shop page is not assigned');

const context=await browser.newContext({viewport:{width:390,height:844}});
const visitor=await context.newPage();
const checks={visibility:{before,after},shop_page_id:shopPageId};
async function visitAbsolute(url,label){
  const u=new URL(url,target); u.searchParams.set('__public_verify',Date.now());
  const r=await visitor.goto(u.href,{waitUntil:'domcontentloaded',timeout:120000});
  const text=(await visitor.locator('body').innerText().catch(()=>''))||'';
  if(!r||r.status()>=400) throw new Error(`Public ${label} HTTP ${r?.status()}`);
  if(/coming soon/i.test(text.slice(0,1200)) && text.length<2500) throw new Error(`Public ${label} is still behind Coming Soon`);
  return {status:r.status(),url:visitor.url(),title:await visitor.title(),body_chars:text.length,product_cards:await visitor.locator('li.product, .wc-block-product, .products .product').count(),images:await visitor.locator('main img, #content img, .site-content img').count(),purchase_actions:await visitor.locator('button[name="add-to-cart"], .single_add_to_cart_button, a.add_to_cart_button').count(),text:text.slice(0,1200)};
}
async function visit(path){return visitAbsolute(`${target}${path}`,path);}

checks.home=await visit('/');
if(checks.home.body_chars<800||checks.home.product_cards<4) throw new Error(`Homepage incomplete: ${JSON.stringify(checks.home)}`);

// Resolve the WooCommerce-assigned shop page canonically; this survives duplicate slugs created by imports.
const catalogResponse=await visitor.goto(`${target}/?page_id=${encodeURIComponent(shopPageId)}&__public_verify=${Date.now()}`,{waitUntil:'domcontentloaded',timeout:120000});
if(!catalogResponse||catalogResponse.status()>=400) throw new Error(`Assigned Shop page HTTP ${catalogResponse?.status()}`);
const catalogUrl=visitor.url();
checks.catalog_path=new URL(catalogUrl).pathname;
checks.catalog=await visitAbsolute(catalogUrl,'assigned-shop');
if(checks.catalog.product_cards<4) throw new Error(`Catalog incomplete: ${JSON.stringify(checks.catalog)}`);

const api=await visitor.request.get(`${target}/?rest_route=/wc/store/v1/products&per_page=100&_=${Date.now()}`);
const products=await api.json();
if(!Array.isArray(products)||products.length<20) throw new Error(`Woo Store API product count too small: ${Array.isArray(products)?products.length:'non-array'}`);
checks.store_api_products=products.length;
checks.product=await visitAbsolute(products[0].permalink,'first-product');
if(checks.product.purchase_actions<1) throw new Error(`Public product page lacks purchase action: ${JSON.stringify(checks.product)}`);

for(const path of ['/product-category/groceries/','/cart/','/checkout/','/about/','/contact/']) checks[path]=await visit(path);
if(checks['/product-category/groceries/'].product_cards<2) throw new Error('Groceries category is incomplete');

console.log('SITE2_WOO_FINAL_READY',JSON.stringify(checks,null,2));
await context.close();
await browser.close();
