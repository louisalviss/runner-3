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
function cookieSummary(cookies) {
  return cookies
    .filter(c => /pntr\.dev$/.test(c.domain || ''))
    .map(c => ({name:c.name, domain:c.domain, path:c.path, httpOnly:c.httpOnly, secure:c.secure, sameSite:c.sameSite, expires:c.expires}))
    .sort((a,b)=>a.name.localeCompare(b.name));
}
function setCookieNames(headersArray=[]) {
  return headersArray
    .filter(h => h.name.toLowerCase() === 'set-cookie')
    .map(h => String(h.value).split('=',1)[0])
    .filter(Boolean);
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
  const raw = req.url();
  if (!/pntr\.dev|github\.com/i.test(raw)) return;
  let bodyKeys = [];
  try { const j = req.postDataJSON(); if (j && typeof j === 'object') bodyKeys = Object.keys(j); } catch {}
  const evt = {type:'request', method:req.method(), url:safeUrl(raw), bodyKeys};
  try {
    const u = new URL(raw);
    if (u.hostname === 'github.com' && u.pathname === '/login/oauth/authorize') {
      const redirect = u.searchParams.get('redirect_uri');
      evt.oauth = {
        redirectUri: redirect ? safeUrl(redirect) : null,
        scope: u.searchParams.get('scope'),
        responseType: u.searchParams.get('response_type'),
        codeChallengeMethod: u.searchParams.get('code_challenge_method'),
        hasCodeChallenge: !!u.searchParams.get('code_challenge'),
        hasState: u.searchParams.has('state'),
      };
    }
  } catch {}
  events.push(evt);
});
page.on('response', async res => {
  const raw = res.url();
  if (!/pntr\.dev|github\.com/i.test(raw)) return;
  const h = res.headers();
  let headersArray = [];
  try { headersArray = await res.headersArray(); } catch {}
  const redirectHeader = h['location'] || h['x-action-redirect'] || h['x-nextjs-redirect'] || null;
  events.push({
    type:'response',
    status:res.status(),
    url:safeUrl(raw),
    redirect: redirectHeader ? safeUrl(new URL(redirectHeader, raw).href) : null,
    setCookieNames:setCookieNames(headersArray),
  });
});

await page.goto('https://pntr.dev/dashboard', {waitUntil:'domcontentloaded', timeout:60000});
await page.waitForTimeout(2200);
const dashBody = await page.locator('body').innerText();
console.log(`DASHBOARD_HAS_DOMAIN=${dashBody.toLowerCase().includes('runner3wp.pntr.dev')}`);
console.log(`DASHBOARD_IS_GUEST=${/guest|sign in to keep them/i.test(dashBody)}`);
console.log('COOKIES_BEFORE_LOGIN='+JSON.stringify(cookieSummary(await context.cookies('https://pntr.dev'))));

let target = page.getByRole('link', {name:/^sign in$/i}).first();
if (await target.count() === 0) target = page.getByRole('button', {name:/sign in to keep them/i}).first();
if (await target.count() > 0) {
  await target.click({timeout:5000}).catch(()=>{});
  await page.waitForTimeout(1800);
}
console.log('LOGIN_PAGE_URL='+safeUrl(page.url()));
console.log('COOKIES_ON_LOGIN_PAGE='+JSON.stringify(cookieSummary(await context.cookies('https://pntr.dev'))));

let gh = page.getByRole('button', {name:/^sign in with github$/i}).first();
if (await gh.count() === 0) gh = page.getByRole('link', {name:/^sign in with github$/i}).first();
console.log(`GITHUB_CONTROL_FOUND=${await gh.count() > 0}`);
if (await gh.count() > 0) {
  await gh.click({timeout:5000}).catch(e => console.log('GITHUB_CLICK_ERROR='+String(e).slice(0,120)));
  await page.waitForTimeout(4500);
}
console.log('POST_GITHUB_CLICK_URL='+safeUrl(page.url()));
console.log('COOKIES_AFTER_GITHUB_CLICK='+JSON.stringify(cookieSummary(await context.cookies('https://pntr.dev'))));

const unique = [];
const seen = new Set();
for (const e of events) {
  const key = JSON.stringify(e);
  if (!seen.has(key)) { seen.add(key); unique.push(e); }
}
for (const e of unique.slice(-140)) {
  if (/pntr\.dev\/login|github\.com\/login\/oauth\/authorize/.test(e.url) || e.setCookieNames?.length || e.oauth) {
    console.log('AUTH_NET='+JSON.stringify(e));
  }
}
await browser.close();
