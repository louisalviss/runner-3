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
await page.goto(`${target}/wp-admin/themes.php?page=starter-templates`,{waitUntil:'domcontentloaded',timeout:120000});
await page.waitForTimeout(6000);
const build=page.getByRole('button',{name:/Build with Templates/i}).first();
if(await build.count() && await build.isVisible().catch(()=>false)){await build.click();await page.waitForTimeout(6000);}
const classicText=page.getByText(/Classic Starter Templates/i).first();
if(await classicText.count() && await classicText.isVisible().catch(()=>false)){await classicText.click();await page.waitForTimeout(8000);}
const info={url:page.url(),title:await page.title(),body:(await page.locator('body').innerText()).slice(0,12000),inputs:await page.locator('input').evaluateAll(xs=>xs.map(x=>({type:x.type,placeholder:x.placeholder,name:x.name,aria:x.getAttribute('aria-label')}))),buttons:await page.getByRole('button').allTextContents(),links:(await page.getByRole('link').allTextContents()).slice(0,100),frames:page.frames().map(f=>f.url())};
console.log('STARTER_UI_PROBE',JSON.stringify(info,null,2));
await browser.close();
