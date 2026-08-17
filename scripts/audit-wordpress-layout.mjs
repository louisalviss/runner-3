import { chromium } from 'playwright-core';
import fs from 'fs';
import path from 'path';

const base = (process.env.WP_SITE_URL || 'https://runner3-factory-smoke-2.wasmer.app/').replace(/\/$/, '');
const outDir = process.env.AUDIT_OUT || 'ops/wp-layout-audit/results/latest';
fs.mkdirSync(outDir, { recursive: true });

const targets = [
  { name: 'home', url: `${base}/` },
  { name: 'article', url: `${base}/2026/08/17/the-quiet-machines-running-the-city/` },
];
const viewports = [
  { name: 'desktop-1440', width: 1440, height: 900 },
  { name: 'laptop-1024', width: 1024, height: 768 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'mobile-390', width: 390, height: 844 },
];

const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const summary = { site: base, generatedAt: new Date().toISOString(), results: [] };
try {
  for (const target of targets) {
    for (const vp of viewports) {
      const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 1 });
      const consoleErrors = [];
      page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
      const response = await page.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForTimeout(1800);
      const metrics = await page.evaluate(() => {
        const root = document.documentElement;
        const vw = root.clientWidth;
        const selector = (el) => {
          if (el.id) return `${el.tagName.toLowerCase()}#${el.id}`;
          const classes = typeof el.className === 'string' ? el.className.trim().split(/\s+/).filter(Boolean).slice(0,3) : [];
          return el.tagName.toLowerCase() + (classes.length ? '.' + classes.join('.') : '');
        };
        const offenders = [];
        for (const el of document.querySelectorAll('body *')) {
          const cs = getComputedStyle(el);
          if (cs.position === 'fixed' || cs.display === 'none' || cs.visibility === 'hidden') continue;
          const r = el.getBoundingClientRect();
          if (r.width < 1 || r.height < 1) continue;
          const leftOverflow = Math.max(0, -r.left);
          const rightOverflow = Math.max(0, r.right - vw);
          if (leftOverflow > 2 || rightOverflow > 2) {
            offenders.push({ selector: selector(el), left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width), leftOverflow: Math.round(leftOverflow), rightOverflow: Math.round(rightOverflow), text: (el.textContent || '').trim().replace(/\s+/g,' ').slice(0,100) });
          }
        }
        return {
          viewportWidth: vw,
          rootScrollWidth: root.scrollWidth,
          bodyScrollWidth: document.body.scrollWidth,
          horizontalOverflow: Math.max(root.scrollWidth, document.body.scrollWidth) - vw,
          offenders: offenders.sort((a,b) => (b.leftOverflow+b.rightOverflow) - (a.leftOverflow+a.rightOverflow)).slice(0,40),
          header: (() => { const e=document.querySelector('.site-header'); if(!e) return null; const r=e.getBoundingClientRect(); return {width:Math.round(r.width),height:Math.round(r.height)}; })(),
          hero: (() => { const e=document.querySelector('.edition-hero,.article-shell'); if(!e) return null; const r=e.getBoundingClientRect(); return {left:Math.round(r.left),right:Math.round(r.right),width:Math.round(r.width),height:Math.round(r.height)}; })()
        };
      });
      const screenshot = path.join(outDir, `${target.name}-${vp.name}.png`);
      await page.screenshot({ path: screenshot, fullPage: true });
      summary.results.push({ target: target.name, url: target.url, viewport: vp, status: response?.status() ?? null, title: await page.title(), consoleErrors, screenshot, ...metrics });
      await page.close();
    }
  }
} finally {
  await browser.close();
}
fs.writeFileSync(path.join(outDir, 'audit.json'), JSON.stringify(summary, null, 2));
const bad = summary.results.filter(r => r.status !== 200 || r.horizontalOverflow > 2 || r.consoleErrors.length);
console.log(JSON.stringify({ total: summary.results.length, bad: bad.length, badResults: bad.map(r => ({target:r.target, viewport:r.viewport.name, status:r.status, overflow:r.horizontalOverflow, offenders:r.offenders.slice(0,5)})) }, null, 2));
