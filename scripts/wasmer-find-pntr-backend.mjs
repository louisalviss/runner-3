import { chromium } from 'playwright-core';
import fs from 'fs';

const TARGET_DOMAIN='runner3wp.pntr.dev';
const TARGET_CNAME='lnh8iwtjmk3x.id.wasmer.app';
const account=JSON.parse(fs.readFileSync('/tmp/wasmer-account.json','utf8'));
if(!account?.username||!account?.password) throw new Error('Wasmer account state incomplete');
const owner=account.username;

function clean(s){return String(s||'').replace(/\s+/g,' ').trim();}
async function text(p){return clean(await p.locator('body').innerText().catch(()=>''));}
async function freshLogin(page){
  await page.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(800);
  const ident=page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  if(!(await ident.count())) return false;
  await ident.fill(account.username||account.email);
  let b=page.locator('button').filter({hasText:/continue|next|log in|sign in/i}).first();
  if(await b.count()) await b.click().catch(()=>{}); else await ident.press('Enter').catch(()=>{});
  const pass=page.locator('input[type=password]').first();
  if(!(await pass.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false))) return false;
  await pass.fill(account.password);
  b=page.locator('button,input[type=submit]').filter({hasText:/log in|sign in|continue/i}).first();
  if(await b.count()) await b.click().catch(()=>{}); else await pass.press('Enter').catch(()=>{});
  await page.waitForTimeout(3000);
  return !/\/login(?:[/?#]|$)/i.test(page.url());
}

const storage=fs.existsSync('/tmp/wasmer-browser-state.json')?'/tmp/wasmer-browser-state.json':undefined;
const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--disable-dev-shm-usage']});
const ctx=await browser.newContext({storageState:storage,ignoreHTTPSErrors:true,viewport:{width:1440,height:900}});
const page=await ctx.newPage();
try{
  await page.goto('https://wasmer.io/apps',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1600);
  if(/\/login(?:[/?#]|$)/i.test(page.url()) || /log in|sign in/i.test((await text(page)).slice(0,400))){
    if(!(await freshLogin(page))) throw new Error('Wasmer login failed');
    await page.goto('https://wasmer.io/apps',{waitUntil:'domcontentloaded',timeout:60000});
    await page.waitForTimeout(1800);
  }

  // Collect app links visible to this account from /apps and owner page.
  const urls=new Set();
  for(const seed of ['https://wasmer.io/apps',`https://wasmer.io/apps/${encodeURIComponent(owner)}`]){
    await page.goto(seed,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{});
    await page.waitForTimeout(1500);
    const hrefs=await page.locator('a[href]').evaluateAll(as=>as.map(a=>a.href));
    for(const h of hrefs){
      try{
        const u=new URL(h);
        const parts=u.pathname.split('/').filter(Boolean);
        if(parts[0]==='apps' && parts.length>=3 && parts[1].toLowerCase()===owner.toLowerCase()){
          // app root only
          urls.add(`https://wasmer.io/apps/${parts[1]}/${parts[2]}`);
        }
      }catch{}
    }
  }
  console.log('WASMER_APP_COUNT='+urls.size);
  let found=[];
  for(const root of [...urls].sort()){
    const app=root.split('/').pop();
    const candidates=[root,`${root}/settings`,`${root}/settings/domains`,`${root}/domains`];
    let match=false;
    let seenText='';
    let relevantLinks=[];
    for(const url of candidates){
      const r=await page.goto(url,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>null);
      if(!r) continue;
      await page.waitForTimeout(800);
      const b=await text(page);
      seenText+=' '+b;
      const hrefs=await page.locator('a[href]').evaluateAll(as=>as.map(a=>({t:(a.textContent||'').trim(),h:a.href})));
      relevantLinks.push(...hrefs.filter(x=>/domain|setting/i.test(x.t)||/domain|setting/i.test(x.h)).slice(0,12));
      if(b.toLowerCase().includes(TARGET_DOMAIN)||b.toLowerCase().includes(TARGET_CNAME)) match=true;
      if(match) break;
    }
    const nativeMention=(seenText.match(/https?:\/\/[a-z0-9.-]+\.wasmer\.app/ig)||[]).slice(0,5);
    console.log('APP_SCAN='+JSON.stringify({app,match,nativeMention:[...new Set(nativeMention)],relevantLinkCount:relevantLinks.length}));
    if(match) found.push(app);
  }
  console.log('TARGET_MATCH_APPS='+JSON.stringify(found));

  // Also inspect target host headers/body for non-secret backend hints.
  const resp=await ctx.request.get('https://'+TARGET_DOMAIN+'/',{failOnStatusCode:false,timeout:30000});
  const body=await resp.text().catch(()=> '');
  const headers=resp.headers();
  const safeHeaders={};
  for(const k of ['server','x-powered-by','x-wasmer-edge','x-wasmer-app','x-wasmer-deployment','via']) if(headers[k]) safeHeaders[k]=headers[k];
  console.log('TARGET_HTTP='+resp.status());
  console.log('TARGET_SAFE_HEADERS='+JSON.stringify(safeHeaders));
  console.log('TARGET_BODY_TITLE_MATCH='+JSON.stringify((body.match(/<title[^>]*>([^<]{0,160})<\/title>/i)||[])[1]||null));
} finally { await browser.close().catch(()=>{}); }
