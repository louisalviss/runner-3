import { chromium } from 'playwright-core';
import fs from 'fs';

const statePath = '/tmp/pntr-browser-state.json';
const storageState = fs.existsSync(statePath) ? statePath : undefined;
const browser = await chromium.launch({headless:true, executablePath:'/usr/bin/google-chrome', args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx = await browser.newContext({storageState, ignoreHTTPSErrors:true});
const page = await ctx.newPage();
try {
  await page.goto('https://pntr.dev/login', {waitUntil:'networkidle', timeout:60000}).catch(async()=>{
    await page.goto('https://pntr.dev/login', {waitUntil:'domcontentloaded', timeout:60000});
    await page.waitForTimeout(2500);
  });
  const clean = s => String(s||'').replace(/\s+/g,' ').trim();
  const buttons = await page.locator('button,input[type=submit]').evaluateAll(els => els.map(e => ({text:(e.innerText||e.value||'').replace(/\s+/g,' ').trim(), type:e.getAttribute('type'), name:e.getAttribute('name'), formaction:e.getAttribute('formaction')})).filter(x=>x.text));
  const links = await page.locator('a').evaluateAll(els => els.map(e => ({text:(e.innerText||'').replace(/\s+/g,' ').trim(), href:e.getAttribute('href')})).filter(x=>x.text));
  const forms = await page.locator('form').evaluateAll(els => els.map(e => ({action:e.getAttribute('action'), method:e.getAttribute('method')||'get', inputs:[...e.querySelectorAll('input')].map(i=>({type:i.getAttribute('type')||'text',name:i.getAttribute('name'),hasValue:!!i.getAttribute('value')}))})));
  const body = clean(await page.locator('body').innerText().catch(()=>''));
  console.log('PNTR_LOGIN_URL=' + page.url());
  console.log('PNTR_LOGIN_TITLE=' + clean(await page.title()));
  console.log('PNTR_LOGIN_BUTTONS=' + JSON.stringify(buttons));
  console.log('PNTR_LOGIN_LINKS=' + JSON.stringify(links.slice(0,30)));
  console.log('PNTR_LOGIN_FORMS=' + JSON.stringify(forms));
  console.log('PNTR_LOGIN_BODY=' + JSON.stringify(body.slice(0,1800)));
} finally {
  await browser.close().catch(()=>{});
}
