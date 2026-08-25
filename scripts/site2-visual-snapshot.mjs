#!/usr/bin/env node

import fs from 'node:fs';
import { chromium } from 'playwright-core';

const target=(process.env.SITE2_URL||'https://runner3-wp-a94b8fd2.wasmer.app/').replace(/\/$/,'/');
const screenshotOut=process.env.VISUAL_SCREENSHOT_OUT||'/tmp/site2-visual.png';
const jsonOut=process.env.VISUAL_JSON_OUT||'/tmp/site2-visual.json';

let browser;
try {
  const executablePath=[process.env.CHROME_PATH,'/usr/bin/google-chrome-stable','/usr/bin/google-chrome','/usr/bin/chromium']
    .filter(Boolean).find((p)=>fs.existsSync(p));
  if(!executablePath) throw new Error('Chrome executable not found');
  browser=await chromium.launch({headless:true,executablePath,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
  const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1});
  const page=await context.newPage();
  const response=await page.goto(`${target}?__visual=${Date.now()}`,{waitUntil:'domcontentloaded',timeout:120000});
  if(!response||response.status()>=400) throw new Error(`homepage returned ${response?.status()}`);
  await page.waitForLoadState('networkidle',{timeout:60000}).catch(()=>{});
  await page.waitForTimeout(1500);
  const hero=page.locator('.runner3-fixture-home section').first();
  const rect=await hero.boundingBox();
  const headline=(await hero.locator('h1').first().textContent().catch(()=>''))?.trim()||'';
  if(!rect||rect.width<250||rect.height<450) throw new Error(`hero geometry invalid: ${JSON.stringify(rect)}`);
  if(!headline.includes('Everyday goods')) throw new Error('hero headline missing');
  await page.screenshot({path:screenshotOut,fullPage:false,animations:'disabled'});
  const result={status:'ready',target,checkedAt:new Date().toISOString(),viewport:{width:390,height:844},heroRect:rect,headline,screenshotOut};
  fs.writeFileSync(jsonOut,`${JSON.stringify(result,null,2)}\n`);
  console.log(JSON.stringify(result,null,2));
}catch(error){
  const result={status:'failed',target,error:String(error?.stack||error)};
  fs.writeFileSync(jsonOut,`${JSON.stringify(result,null,2)}\n`);
  console.error(JSON.stringify(result,null,2));
  process.exitCode=1;
}finally{
  if(browser) await browser.close().catch(()=>{});
}
