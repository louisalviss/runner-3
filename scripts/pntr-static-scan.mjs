import { chromium } from 'playwright-core';

const needles = [
  'anon_user_id','authjs','callback/github','Sign in with GitHub','signIn','github',
  'migrate','migration','claim','transfer','anonymous','guest','pkce','code_verifier'
];

const browser = await chromium.launch({
  headless:true,
  executablePath:'/usr/bin/google-chrome',
  args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']
});
const page = await browser.newPage();
await page.goto('https://pntr.dev/login', {waitUntil:'networkidle', timeout:60000});
const scripts = await page.locator('script[src]').evaluateAll(ns => ns.map(n => n.src));
console.log('SCRIPT_COUNT='+scripts.length);
let hits = 0;
for (const src of [...new Set(scripts)]) {
  if (!src.includes('pntr.dev')) continue;
  const r = await page.request.get(src, {timeout:30000});
  if (!r.ok()) continue;
  const txt = await r.text();
  const found = needles.filter(n => txt.toLowerCase().includes(n.toLowerCase()));
  if (!found.length) continue;
  hits++;
  const url = new URL(src);
  console.log('CHUNK='+url.pathname+' HITS='+JSON.stringify(found));
  for (const needle of found) {
    const low = txt.toLowerCase();
    let pos = low.indexOf(needle.toLowerCase());
    let count = 0;
    while (pos >= 0 && count < 4) {
      const start = Math.max(0, pos-220);
      const end = Math.min(txt.length, pos+needle.length+300);
      let snip = txt.slice(start,end)
        .replace(/[A-Za-z0-9_-]{40,}/g,'<long-redacted>')
        .replace(/https?:\/\/[^"'`\s)]+/g, m => {
          try { const u=new URL(m); return u.origin+u.pathname+'?<redacted>'; } catch { return '<url-redacted>'; }
        });
      console.log('SNIP['+needle+']='+snip.replace(/\s+/g,' ').slice(0,900));
      pos = low.indexOf(needle.toLowerCase(), pos+needle.length);
      count++;
    }
  }
}
console.log('MATCHED_CHUNKS='+hits);
await browser.close();
