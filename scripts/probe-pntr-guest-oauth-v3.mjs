import { chromium } from 'playwright-core';
import fs from 'fs';

const statePath='/tmp/pntr-browser-state.json';
if(!fs.existsSync(statePath)) throw new Error('PNTR state missing');
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({storageState:statePath,ignoreHTTPSErrors:true});
const page=await ctx.newPage();
const clean=s=>String(s||'').replace(/\s+/g,' ').trim();
let authorizeSafe=null;
page.on('request',req=>{
  try{
    const u=new URL(req.url());
    if(u.hostname==='github.com' && u.pathname==='/login/oauth/authorize'){
      const redirect=u.searchParams.get('redirect_uri');
      let callback=null;
      if(redirect){ const r=new URL(redirect); callback={origin:r.origin,path:r.pathname}; }
      authorizeSafe={host:u.hostname,path:u.pathname,callback};
    }
  }catch{}
});
try{
  const cookies=await ctx.cookies('https://pntr.dev/');
  console.log('COOKIE_META='+JSON.stringify(cookies.filter(c=>c.name==='anon_user_id').map(c=>({name:c.name,domain:c.domain,path:c.path,secure:c.secure,httpOnly:c.httpOnly,sameSite:c.sameSite,expires:c.expires}))));

  await page.goto('https://pntr.dev/dashboard',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1200);
  const body=clean(await page.locator('body').innerText().catch(()=>''));
  console.log('GUEST_HAS_TARGET='+body.includes('runner3wp.pntr.dev'));
  console.log('DASHBOARD_SIGNED_GUEST='+/guest|sign in to keep|browsing as guest/i.test(body));

  await page.goto('https://pntr.dev/login',{waitUntil:'domcontentloaded',timeout:60000});
  const btn=page.getByRole('button',{name:/Sign in with GitHub/i}).first();
  if(!(await btn.count())) throw new Error('GitHub sign-in button missing');
  await btn.click();
  await page.waitForTimeout(3500);
  console.log('AUTHORIZE_SAFE='+JSON.stringify(authorizeSafe));
  console.log('FINAL_HOST='+new URL(page.url()).hostname);
  console.log('FINAL_PATH='+new URL(page.url()).pathname);
} finally {
  await browser.close().catch(()=>{});
}
