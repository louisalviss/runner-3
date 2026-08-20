import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner5-restore-lab-1';
const state = JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`, 'utf8'));
const base = String(state.siteUrl || '').replace(/\/$/, '');
const browser = await chromium.launch({ headless:true, executablePath:'/usr/bin/google-chrome', args:['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors:true, viewport:{width:412,height:915}, deviceScaleFactor:2, isMobile:true });
const page = await ctx.newPage();
await page.addInitScript(() => {
  window.__r3shifts=[];
  new PerformanceObserver(list => {
    for (const e of list.getEntries()) {
      if (e.hadRecentInput) continue;
      window.__r3shifts.push({
        value:e.value,
        startTime:e.startTime,
        sources:(e.sources||[]).map(s => ({
          html:s.node?.outerHTML?.slice(0,500) || s.node?.nodeName || null,
          previousRect:s.previousRect || null,
          currentRect:s.currentRect || null,
        }))
      });
    }
  }).observe({type:'layout-shift', buffered:true});
});
await page.goto(base+'/', {waitUntil:'load',timeout:60000});
await page.waitForTimeout(2500);
const data = await page.evaluate(() => ({
  cls: performance.getEntriesByType('layout-shift').filter(e=>!e.hadRecentInput).reduce((a,e)=>a+e.value,0),
  shifts: window.__r3shifts,
  images:[...document.images].slice(0,20).map((img,i)=>({i,src:img.currentSrc||img.src,width:img.getAttribute('width'),height:img.getAttribute('height'),loading:img.loading,fetchpriority:img.fetchPriority,rect:img.getBoundingClientRect().toJSON()})),
  fonts: document.fonts ? {status:document.fonts.status,size:document.fonts.size} : null,
  bodyClass:document.body.className,
}));
console.log(JSON.stringify({site:slug,url:base,...data},null,2));
await ctx.close();
await browser.close();
