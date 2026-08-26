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
  const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,isMobile:true,hasTouch:true});
  const page=await context.newPage();
  const response=await page.goto(`${target}?__visual=${Date.now()}`,{waitUntil:'domcontentloaded',timeout:120000});
  if(!response||response.status()>=400) throw new Error(`homepage returned ${response?.status()}`);
  await page.waitForLoadState('networkidle',{timeout:60000}).catch(()=>{});
  await page.waitForTimeout(1500);

  const bodyText=(await page.locator('body').innerText()).replace(/\s+/g,' ');
  if(!bodyText.includes('Best Quality Products')||!bodyText.includes('Join The Organic Movement!')) {
    throw new Error('official Organic Store homepage identity missing');
  }
  const heading=page.getByRole('heading',{name:/Best Quality Products/i}).first();
  const headingRect=await heading.boundingBox();
  if(!headingRect||headingRect.width<100||headingRect.height<20) throw new Error(`hero heading geometry invalid: ${JSON.stringify(headingRect)}`);
  const homeProductCards=await page.locator('li.product, .wc-block-product, .products .product').count();
  if(homeProductCards<8) throw new Error(`homepage product regression: ${homeProductCards}`);

  await page.screenshot({path:screenshotOut,fullPage:false,animations:'disabled'});
  const result={status:'ready',target,checkedAt:new Date().toISOString(),viewport:{width:390,height:844},headingRect,headline:'Best Quality Products',homeProductCards,screenshotOut};
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
