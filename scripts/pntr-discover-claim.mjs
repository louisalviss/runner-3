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
function queryKeys(raw) {
  try { return [...new URL(raw).searchParams.keys()]; } catch { return []; }
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
  if (/pntr\.dev|github\.com/i.test(u)) {
    let bodyKeys = [];
    try { const j = req.postDataJSON(); if (j && typeof j === 'object') bodyKeys = Object.keys(j); } catch {}
    events.push({type:'request', method:req.method(), url:safeUrl(u), bodyKeys});
  }
});
page.on('response', res => {
  const u = res.url();
  if (/pntr\.dev|github\.com/i.test(u)) {
    const location = res.headers()['location'];
    events.push({type:'response', status:res.status(), url:safeUrl(u), location:location ? safeUrl(new URL(location, u).href) : null});
  }
});

await page.goto('https://pntr.dev/dashboard', {waitUntil:'domcontentloaded', timeout:60000});
await page.waitForTimeout(2200);
const dashBody = await page.locator('body').innerText();
console.log(`DASHBOARD_HAS_DOMAIN=${dashBody.toLowerCase().includes('runner3wp.pntr.dev')}`);
console.log(`DASHBOARD_IS_GUEST=${/guest|sign in to keep them/i.test(dashBody)}`);

let target = page.getByRole('link', {name:/sign in/i}).first();
if (await target.count() === 0) target = page.getByRole('button', {name:/sign in to keep them|sign in/i}).first();
console.log(`DASH_LOGIN_CONTROL_FOUND=${await target.count() > 0}`);
if (await target.count() > 0) {
  const href = await target.getAttribute('href').catch(()=>null);
  if (href) console.log('DASH_LOGIN_HREF='+safeUrl(new URL(href, page.url()).href));
  await target.click({timeout:5000}).catch(()=>{});
  await page.waitForTimeout(2000);
}
console.log('LOGIN_PAGE_URL='+safeUrl(page.url()));

const loginControls = await page.locator('a,button').evaluateAll(nodes => nodes.map(n => ({
  tag:n.tagName,
  text:(n.textContent||'').trim().replace(/\s+/g,' ').slice(0,140),
  href:n.href||null,
  type:n.getAttribute('type')||null,
})).filter(x => /github|sign in|continue|login/i.test(x.text) || (x.href && /github|oauth|auth|callback|login/i.test(x.href))));
for (const c of loginControls) {
  const href = c.href ? safeUrl(c.href) : null;
  const keys = c.href ? queryKeys(c.href) : [];
  console.log('LOGIN_CONTROL='+JSON.stringify({...c, href, queryKeys:keys}));
}

let gh = page.getByRole('link', {name:/github|continue/i}).first();
if (await gh.count() === 0) gh = page.getByRole('button', {name:/github|continue/i}).first();
console.log(`GITHUB_CONTROL_FOUND=${await gh.count() > 0}`);
if (await gh.count() > 0) {
  const href = await gh.getAttribute('href').catch(()=>null);
  if (href) {
    const abs = new URL(href, page.url()).href;
    console.log('GITHUB_CONTROL_HREF='+safeUrl(abs));
    console.log('GITHUB_CONTROL_QUERY_KEYS='+JSON.stringify(queryKeys(abs)));
  }
  await gh.click({timeout:5000}).catch(()=>{});
  await page.waitForTimeout(3500);
  console.log('POST_GITHUB_CLICK_URL='+safeUrl(page.url()));
  console.log('POST_GITHUB_CLICK_QUERY_KEYS='+JSON.stringify(queryKeys(page.url())));
}

const unique = [];
const seen = new Set();
for (const e of events) {
  const key = JSON.stringify(e);
  if (!seen.has(key)) { seen.add(key); unique.push(e); }
}
for (const e of unique.slice(-100)) console.log('NET='+JSON.stringify(e));
await browser.close();
