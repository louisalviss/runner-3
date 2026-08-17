import { chromium } from 'playwright-core';
import fs from 'fs';

const statePath='/tmp/pntr-browser-state.json';
if(!fs.existsSync(statePath)) throw new Error('PNTR state missing');
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({storageState:statePath,ignoreHTTPSErrors:true});
const page=await ctx.newPage();
const clean=s=>String(s||'').replace(/\s+/g,' ').trim();
try{
  const cookies=await ctx.cookies('https://pntr.dev/');
  console.log('COOKIE_META='+JSON.stringify(cookies.filter(c=>c.name==='anon_user_id').map(c=>({name:c.name,domain:c.domain,path:c.path,secure:c.secure,httpOnly:c.httpOnly,sameSite:c.sameSite,expires:c.expires}))));

  await page.goto('https://pntr.dev/dashboard',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1800);
  const body=clean(await page.locator('body').innerText().catch(()=>''));
  console.log('DASHBOARD_URL='+page.url());
  console.log('GUEST_HAS_TARGET='+body.includes('runner3wp.pntr.dev'));
  console.log('TARGET_OCCURRENCES='+(body.match(/runner3wp\.pntr\.dev/g)||[]).length);
  console.log('DASHBOARD_SIGNED_GUEST='+/guest|sign in to keep|browsing as guest/i.test(body));

  await page.goto('https://pntr.dev/login',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(700);
  const btn=page.getByRole('button',{name:/Sign in with GitHub/i}).first();
  if(!(await btn.count())) throw new Error('GitHub sign-in button missing');
  await Promise.allSettled([
    page.waitForURL(u=>u.hostname==='github.com',{timeout:20000}),
    btn.click()
  ]);
  await page.waitForTimeout(800);
  const u=new URL(page.url());
  console.log('OAUTH_DEST_HOST='+u.hostname);
  console.log('OAUTH_DEST_PATH='+u.pathname);
  const redirect=u.searchParams.get('redirect_uri');
  if(redirect){
    const r=new URL(redirect);
    console.log('OAUTH_REDIRECT_ORIGIN='+r.origin);
    console.log('OAUTH_REDIRECT_PATH='+r.pathname);
  } else {
    console.log('OAUTH_REDIRECT_ORIGIN=missing');
    console.log('OAUTH_REDIRECT_PATH=missing');
  }
} finally {
  await browser.close().catch(()=>{});
}
