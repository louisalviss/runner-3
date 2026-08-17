import { chromium } from 'playwright-core';
import fs from 'fs';

const target = process.env.PSI_URL || 'https://runner3-factory-smoke-2.wasmer.app/';
const out = process.env.PSI_UI_OUT || 'ops/pagespeed/ui-latest.json';
const screenshot = process.env.PSI_UI_SCREENSHOT || 'ops/pagespeed/ui-latest.png';
fs.mkdirSync('ops/pagespeed', {recursive:true});

const browser = await chromium.launch({headless:true, executablePath:'/usr/bin/google-chrome', args:['--no-sandbox','--disable-dev-shm-usage']});
const page = await browser.newPage({viewport:{width:1440,height:1200}});
const result = {status:'starting', target, checkedAt:new Date().toISOString(), url:null, title:null, textSample:null, scores:{}, detail:null};
try {
  await page.goto('https://pagespeed.web.dev/', {waitUntil:'domcontentloaded', timeout:45000});
  const input = page.locator('input').first();
  await input.waitFor({state:'visible', timeout:20000});
  await input.fill(target);
  const button = page.getByRole('button', {name:/analy[sz]e|phân tích/i}).first();
  await button.click();
  await page.waitForURL(/analysis/, {timeout:30000}).catch(()=>{});
  await page.waitForFunction(() => /Performance|Hiệu suất/i.test(document.body.innerText) && /Largest Contentful Paint|LCP/i.test(document.body.innerText), {timeout:120000}).catch(()=>{});
  await page.waitForTimeout(3000);
  result.url = page.url();
  result.title = await page.title();
  const text = await page.locator('body').innerText();
  result.textSample = text.slice(0,20000);
  // PSI renders category scores as numeric text near category labels. Capture via nearby DOM rather than brittle class names.
  result.scores = await page.evaluate(() => {
    const labels = ['Performance','Accessibility','Best Practices','SEO','Hiệu suất','Hỗ trợ tiếp cận','Các phương pháp hay nhất'];
    const out = {};
    for (const el of document.querySelectorAll('body *')) {
      const t=(el.textContent||'').trim();
      if (!labels.includes(t)) continue;
      let p=el.parentElement;
      for(let depth=0;p && depth<5;depth++,p=p.parentElement){
        const nums=(p.innerText||'').match(/\b(?:100|[1-9]?\d)\b/g)||[];
        if(nums.length){ out[t]=nums.slice(0,4); break; }
      }
    }
    return out;
  });
  await page.screenshot({path:screenshot, fullPage:true});
  if (/quota exceeded/i.test(text)) throw new Error('Google PageSpeed UI reported quota exceeded');
  if (!/Performance|Hiệu suất/i.test(text)) throw new Error('PageSpeed result markers not found');
  result.status='ready';
} catch(e) {
  result.status='failed'; result.detail=String(e?.message||e);
  result.url=page.url(); result.title=await page.title().catch(()=>null);
  result.textSample=(await page.locator('body').innerText().catch(()=>'' )).slice(0,20000);
  await page.screenshot({path:screenshot, fullPage:true}).catch(()=>{});
} finally {
  fs.writeFileSync(out, JSON.stringify(result,null,2));
  await browser.close();
}
console.log(JSON.stringify({status:result.status,url:result.url,scores:result.scores,detail:result.detail},null,2));
if(result.status!=='ready') process.exitCode=1;
