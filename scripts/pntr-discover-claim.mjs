import { chromium } from 'playwright-core';
import fs from 'fs';

const statePath = '/tmp/pntr-browser-state.json';
if (!fs.existsSync(statePath)) throw new Error('PNTR storage state missing');

function safeUrl(raw) {
  try {
    const u = new URL(raw);
    const keys = [...u.searchParams.keys()];
    return `${u.origin}${u.pathname}${keys.length ? `?${keys.map(k => `${encodeURIComponent(k)}=<redacted>`).join('&')}` : ''}`;
  } catch { return '<invalid-url>'; }
}

const browser = await chromium.launch({
  headless: true,
  executablePath: '/usr/bin/google-chrome',
  args: ['--no-sandbox','--disable-dev-shm-usage','--disable-gpu'],
});
const context = await browser.newContext({ storageState: statePath, viewport: { width: 1360, height: 760 } });
const page = await context.newPage();

const events = [];
page.on('request', req => {
  const u = req.url();
  if (/pntr\.dev|github\.com/i.test(u)) events.push({type:'request', method:req.method(), url:safeUrl(u)});
});
page.on('response', res => {
  const u = res.url();
  if (/pntr\.dev|github\.com/i.test(u)) events.push({type:'response', status:res.status(), url:safeUrl(u)});
});

await page.goto('https://pntr.dev/dashboard', {waitUntil:'domcontentloaded', timeout:60000});
await page.waitForTimeout(2500);

const body = await page.locator('body').innerText();
const hasDomain = body.toLowerCase().includes('runner3wp.pntr.dev');
const isGuest = /guest|sign in to keep them/i.test(body);
console.log(`DASHBOARD_HAS_DOMAIN=${hasDomain}`);
console.log(`DASHBOARD_IS_GUEST=${isGuest}`);

const controls = await page.locator('a,button').evaluateAll(nodes => nodes.map(n => ({
  tag:n.tagName,
  text:(n.textContent||'').trim().replace(/\s+/g,' ').slice(0,120),
  href:n.href||null,
  type:n.getAttribute('type')||null,
})).filter(x => /sign|github|keep|guest/i.test(x.text) || (x.href && /login|auth|github/i.test(x.href))));
for (const c of controls) console.log('CONTROL='+JSON.stringify({...c, href:c.href ? safeUrl(c.href) : null}));

let target = page.getByRole('link', {name:/sign in|keep them|github/i}).first();
if (await target.count() === 0) target = page.getByRole('button', {name:/sign in|keep them|github/i}).first();
if (await target.count() === 0) {
  console.log('CLAIM_CONTROL_FOUND=false');
} else {
  console.log('CLAIM_CONTROL_FOUND=true');
  const preHref = await target.getAttribute('href').catch(()=>null);
  if (preHref) console.log('CLAIM_CONTROL_HREF='+safeUrl(new URL(preHref, page.url()).href));
  try {
    await Promise.allSettled([
      page.waitForURL(url => !url.href.includes('/dashboard'), {timeout:10000}),
      target.click({timeout:5000}),
    ]);
    await page.waitForTimeout(2500);
  } catch (e) {
    console.log('CLICK_RESULT='+String(e).slice(0,160));
  }
  console.log('POST_CLICK_URL='+safeUrl(page.url()));
}

const unique = [];
const seen = new Set();
for (const e of events) {
  const key = JSON.stringify(e);
  if (!seen.has(key)) { seen.add(key); unique.push(e); }
}
for (const e of unique.slice(-80)) console.log('NET='+JSON.stringify(e));

await browser.close();
