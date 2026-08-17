import { chromium } from 'playwright-core';
import fs from 'fs';

const state=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const safe={status:'starting',appName:state.appName,siteUrl:state.siteUrl,dashboardUrl:null,signals:[],links:[],buttons:[],detail:null,updatedAt:new Date().toISOString()};
function save(){safe.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-inspect-status.json',JSON.stringify(safe,null,2));fs.writeFileSync('/tmp/wasmer-result.json',JSON.stringify(state,null,2));}
async function body(page){return (await page.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function pageSummary(page){
  const buttons=await page.locator('button').evaluateAll(bs=>bs.map(b=>(b.innerText||b.textContent||'').replace(/\s+/g,' ').trim()).filter(Boolean).slice(0,50)).catch(()=>[]);
  const links=await page.locator('a').evaluateAll(as=>as.map(a=>({t:(a.innerText||a.textContent||'').replace(/\s+/g,' ').trim(),h:a.href})).filter(x=>x.t||x.h).slice(0,80)).catch(()=>[]);
  safe.buttons=[...new Set(buttons)];
  safe.links=links.filter(x=>/wordpress|admin|settings|configure|secret|environment|database|deploy|app/i.test(x.t+' '+x.h)).map(x=>({text:x.t.slice(0,100),href:x.h.replace(/[?&](token|key|secret|password)=[^&#]+/ig,'?$1=REDACTED')})).slice(0,30);
}
async function login(page){
  await page.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});
  const ident=page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  await ident.waitFor({state:'visible',timeout:12000}).catch(()=>{});
  if(!(await ident.count())) return false;
  await ident.fill(state.email||state.username);
  const c1=page.locator('button').filter({hasText:/continue|next|log in|sign in/i}).first();
  if(await c1.count()) await c1.click(); else await ident.press('Enter');
  const pass=page.locator('input[type=password]').first();
  const p=await pass.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false);
  if(!p) return false;
  await pass.fill(state.password);
  const c2=page.locator('button').filter({hasText:/log in|sign in|continue/i}).first();
  if(await c2.count()) await c2.click(); else await pass.press('Enter');
  await page.waitForTimeout(3000);
  return !/\/login(?:[/?#]|$)/i.test(page.url());
}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext();
const page=await ctx.newPage();
try{
  if(!(await login(page))){safe.status='blocked_login';safe.detail='Could not authenticate existing Wasmer account';save();process.exit(0);}
  const candidates=[
    `https://wasmer.io/apps/${state.username}/${state.appName}`,
    `https://wasmer.io/apps/${state.appName}`,
    'https://wasmer.io/apps'
  ];
  let loaded=false;
  for(const u of candidates){
    await page.goto(u,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>null);
    await page.waitForTimeout(2000);
    const t=await body(page);
    if(!/not found|404/i.test(t) && !/\/login/i.test(page.url())){loaded=true;break;}
  }
  if(!loaded){safe.status='dashboard_not_found';safe.detail='No app dashboard route resolved';save();process.exit(0);}
  safe.dashboardUrl=page.url();
  let t=await body(page);
  safe.signals=[...new Set((t.match(/.{0,55}(?:wordpress|admin|credential|password|database|mysql|environment|secret|configure).{0,90}/ig)||[]).map(s=>s.replace(/\s+/g,' ').replace(/(password|secret|token|key)\s*[:=]\s*\S+/ig,'$1=REDACTED').slice(0,180)))].slice(0,25);
  await pageSummary(page);

  // Explore only provider-native controls that may expose WordPress configuration; never submit destructive actions.
  const exploreNames=[/configure.*wordpress/i,/wordpress.*configure/i,/settings/i,/environment/i,/secrets?/i,/database/i,/credentials?/i];
  for(const re of exploreNames){
    const el=page.locator('button,a').filter({hasText:re}).first();
    if(!(await el.count()) || !(await el.isVisible().catch(()=>false))) continue;
    const before=page.url();
    await el.click().catch(()=>{});
    await page.waitForTimeout(1200);
    const bt=await body(page);
    const sig=(bt.match(/.{0,60}(?:wordpress|admin|credential|password|database|mysql|environment|secret|configure).{0,100}/ig)||[])
      .map(s=>s.replace(/\s+/g,' ').replace(/(password|secret|token|key)\s*[:=]\s*\S+/ig,'$1=REDACTED').slice(0,190));
    safe.signals=[...new Set([...safe.signals,...sig])].slice(0,40);
    await pageSummary(page);
    if(page.url()!==before && !/apps/i.test(page.url())) await page.goBack().catch(()=>{});
  }

  safe.status='inspected';
  save();
}catch(e){safe.status='error';safe.detail=String(e).slice(0,700);save();}
finally{await browser.close();}
