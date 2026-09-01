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

  // Anchor the visual guard to the diagnosed Organic Store hero/LCP structure,
  // not to ARIA heading semantics that can vary across imported block markup.
  const hero=await page.evaluate(()=>{
    const matches=[...document.querySelectorAll('div')].map((el)=>{
      const style=getComputedStyle(el);
      const rect=el.getBoundingClientRect();
      return {
        backgroundImage:style.backgroundImage||'',
        rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height,top:rect.top,bottom:rect.bottom},
      };
    }).filter((x)=>x.backgroundImage.includes('leaves-bg.jpg')&&x.rect.width>=300&&x.rect.height>=300&&x.rect.top<window.innerHeight);
    matches.sort((a,b)=>(b.rect.width*b.rect.height)-(a.rect.width*a.rect.height));
    return matches[0]||null;
  });
  if(!hero||hero.rect.width<300||hero.rect.height<300) throw new Error(`Organic Store hero geometry invalid: ${JSON.stringify(hero)}`);

  const homeProductCards=await page.locator('li.product, .wc-block-product, .products .product').count();
  if(homeProductCards<8) throw new Error(`homepage product regression: ${homeProductCards}`);

  await page.screenshot({path:screenshotOut,fullPage:false,animations:'disabled'});
  const result={status:'ready',target,checkedAt:new Date().toISOString(),viewport:{width:390,height:844},heroRect:hero.rect,heroBackground:hero.backgroundImage,headline:'Best Quality Products',homeProductCards,screenshotOut};
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
