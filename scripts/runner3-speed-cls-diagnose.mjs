import { chromium } from 'playwright-core';
import fs from 'fs';
import { spawnSync } from 'child_process';

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
const browserData = await page.evaluate(() => ({
  cls: performance.getEntriesByType('layout-shift').filter(e=>!e.hadRecentInput).reduce((a,e)=>a+e.value,0),
  shifts: window.__r3shifts,
  images:[...document.images].slice(0,20).map((img,i)=>({i,src:img.currentSrc||img.src,width:img.getAttribute('width'),height:img.getAttribute('height'),loading:img.loading,fetchpriority:img.fetchPriority,rect:img.getBoundingClientRect().toJSON()})),
  iframes:[...document.querySelectorAll('iframe')].slice(0,20).map((el,i)=>({i,src:el.src,width:el.getAttribute('width'),height:el.getAttribute('height'),loading:el.loading,rect:el.getBoundingClientRect().toJSON(),html:el.outerHTML.slice(0,500)})),
  fonts: document.fonts ? {status:document.fonts.status,size:document.fonts.size} : null,
  bodyClass:document.body.className,
}));
await ctx.close();
await browser.close();

const lhFile='/tmp/runner3-speed-cls-lighthouse.json';
const lh=spawnSync('npx',['lighthouse',base+'/', '--quiet','--chrome-flags=--headless --no-sandbox','--form-factor=mobile','--only-categories=performance','--output=json',`--output-path=${lhFile}`],{encoding:'utf8',timeout:180000});
if(lh.status!==0) throw new Error(`lighthouse_failed:${(lh.stderr||lh.stdout||'').slice(-1000)}`);
const j=JSON.parse(fs.readFileSync(lhFile,'utf8'));
const a=j.audits||{};
const compact = v => JSON.parse(JSON.stringify(v, (k,val) => {
  if (k === 'screenshot' || k === 'debugData') return undefined;
  if (typeof val === 'string' && val.length > 800) return val.slice(0,800);
  return val;
}));
const pickAudit = id => {
  const x=a[id]; if(!x)return null;
  return compact({id,title:x.title,score:x.score,numericValue:x.numericValue,displayValue:x.displayValue,details:x.details});
};
const auditIds=['cumulative-layout-shift','layout-shifts','cls-culprits-insight','largest-contentful-paint-element','lcp-discovery-insight','font-display','render-blocking-resources','render-blocking-insight','server-response-time'];
const audits={}; for(const id of auditIds) audits[id]=pickAudit(id);
console.log(JSON.stringify({site:slug,url:base,browser:browserData,lighthouse:{performanceScore:Math.round((j.categories?.performance?.score||0)*100),audits}},null,2));
