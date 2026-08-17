import { chromium } from 'playwright-core';
import fs from 'fs';

const url = 'https://runner3-factory-smoke-2.wasmer.app/';
const out = 'ops/wp-layout-audit/results/story-grid.json';
fs.mkdirSync('ops/wp-layout-audit/results', { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(1500);
  const data = await page.evaluate(() => {
    const rect = e => { const r=e.getBoundingClientRect(); return {top:Math.round(r.top), bottom:Math.round(r.bottom), left:Math.round(r.left), right:Math.round(r.right), width:Math.round(r.width), height:Math.round(r.height)}; };
    return [...document.querySelectorAll('.story-card')].map((card,i) => {
      const image=card.querySelector('.story-image'); const h3=card.querySelector('h3'); const p=card.querySelector('p'); const meta=card.querySelector('.story-meta');
      const cs=getComputedStyle(card); const is=image?getComputedStyle(image):null; const hs=h3?getComputedStyle(h3):null;
      return {i:i+1, card:rect(card), image:image?rect(image):null, meta:meta?rect(meta):null, h3:h3?rect(h3):null, p:p?rect(p):null,
        cardDisplay:cs.display, cardPosition:cs.position, cardOverflow:cs.overflow, imageDisplay:is?.display, imagePosition:is?.position, imageAspect:is?.aspectRatio,
        h3Display:hs?.display, h3Position:hs?.position, h3MarginTop:hs?.marginTop, h3MarginBottom:hs?.marginBottom,
        overlapsNext:null};
    }).map((x,i,a) => ({...x, overlapsNext: i<a.length-1 ? x.card.bottom > a[i+1].card.top : false, nextTop: i<a.length-1 ? a[i+1].card.top : null}));
  });
  fs.writeFileSync(out, JSON.stringify(data,null,2));
  console.log(JSON.stringify(data,null,2));
} finally { await browser.close(); }
