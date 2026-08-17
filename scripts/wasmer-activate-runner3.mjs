import { chromium } from 'playwright-core';
import fs from 'fs';

const account=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const base=(account.siteUrl||'').replace(/\/$/,'');
const out={status:'starting',wordpressAdmin:false,themeInstalled:false,themeActive:false,frontHttp:null,frontContainsRunner3:false,detail:null,updatedAt:new Date().toISOString()};
const save=()=>{out.updatedAt=new Date().toISOString();fs.writeFileSync('/tmp/wasmer-activate-runner3.json',JSON.stringify(out,null,2));};
async function body(p){return (await p.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext({storageState:'/tmp/wasmer-browser-state.json',ignoreHTTPSErrors:true});
const p=await ctx.newPage();
try{
  save();
  const settings=`https://wasmer.io/apps/${encodeURIComponent(account.username)}/${encodeURIComponent(account.appName)}/settings/wordpress`;
  await p.goto(settings,{waitUntil:'domcontentloaded',timeout:60000});await p.waitForTimeout(1200);
  const admin=p.locator('a').filter({hasText:/WordPress Admin/i}).first();
  if(!(await admin.count())){out.status='admin_link_missing';out.detail=(await body(p)).slice(0,900);save();process.exit(0);}
  const href=await admin.getAttribute('href');
  if(!href){out.status='admin_href_missing';save();process.exit(0);}

  const handoff=await ctx.newPage();
  await handoff.goto(new URL(href,p.url()).toString(),{waitUntil:'domcontentloaded',timeout:60000});await handoff.waitForTimeout(3500);
  const wp=ctx.pages().find(x=>{try{return new URL(x.url()).host===new URL(base).host}catch{return false}})||handoff;
  await wp.goto(base+'/wp-admin/themes.php',{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1500);
  if(/wp-login\.php/i.test(wp.url())){out.status='wp_session_missing';save();process.exit(0);}
  out.wordpressAdmin=true;

  const cards=wp.locator('.theme');let card=null;
  for(let i=0;i<await cards.count();i++){
    const c=cards.nth(i);if(/runner3 starter/i.test(await c.innerText().catch(()=>''))){card=c;break;}
  }
  if(!card){out.status='theme_missing';out.detail=(await body(wp)).slice(0,900);save();process.exit(0);}
  out.themeInstalled=true;
  const before=await card.innerText().catch(()=> '');
  if(/active:/i.test(before)||await card.evaluate(el=>el.classList.contains('active')).catch(()=>false)){
    out.themeActive=true;
  }else{
    const activate=card.locator('a[href*="action=activate"][href*="runner3-starter"],a[aria-label*="Activate Runner3 Starter" i]').first();
    if(!(await activate.count())){out.status='activate_link_missing';out.detail=before.slice(0,700);save();process.exit(0);}
    const ahref=await activate.getAttribute('href');
    if(!ahref){out.status='activate_href_missing';save();process.exit(0);}
    await wp.goto(new URL(ahref,wp.url()).toString(),{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1800);
    await wp.goto(base+'/wp-admin/themes.php',{waitUntil:'domcontentloaded',timeout:60000});await wp.waitForTimeout(1200);
    const activeCard=wp.locator('.theme.active').filter({hasText:/Runner3 Starter/i}).first();
    out.themeActive=await activeCard.count()>0;
  }

  const front=await ctx.newPage();
  const resp=await front.goto(base+'/',{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>null);await front.waitForTimeout(1000);
  out.frontHttp=resp?.status()||null;
  const ft=await body(front);
  out.frontContainsRunner3=/Runner3 Site|fast, clean WordPress site|Fast Responsive Deployable/i.test(ft);
  out.status=out.themeActive&&out.frontHttp===200?'ready':'partial';
  if(out.status!=='ready')out.detail=ft.slice(0,1000);
  save();
}catch(e){out.status='error';out.detail=String(e).slice(0,900);save();}finally{await browser.close();}
