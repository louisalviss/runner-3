import { chromium } from 'playwright-core';
import fs from 'fs';

const state=JSON.parse(fs.readFileSync('/tmp/wasmer-result.json','utf8'));
const safe={status:'continuing_existing_account',appName:state.appName||null,siteUrl:state.siteUrl||null,detail:null,updatedAt:new Date().toISOString()};

function save(){
  state.updatedAt=new Date().toISOString();
  fs.writeFileSync('/tmp/wasmer-result.json',JSON.stringify(state,null,2));
  safe.status=state.status;
  safe.appName=state.appName||null;
  safe.siteUrl=state.siteUrl||null;
  safe.detail=state.detail||null;
  safe.updatedAt=state.updatedAt;
  fs.writeFileSync('/tmp/wasmer-status.json',JSON.stringify(safe,null,2));
}
async function bodyText(page){return (await page.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();}
async function pageState(page,label){
  const body=await bodyText(page);
  const buttons=await page.locator('button').evaluateAll(bs=>bs.map(b=>(b.innerText||b.textContent||'').replace(/\s+/g,' ').trim()).filter(Boolean).slice(0,30)).catch(()=>[]);
  const inputs=await page.locator('input').evaluateAll(xs=>xs.map(x=>({type:x.type,name:x.name,placeholder:x.placeholder,value:(x.type==='password'?'':x.value)})).slice(0,20)).catch(()=>[]);
  return `${label} url=${page.url()} buttons=${JSON.stringify(buttons)} inputs=${JSON.stringify(inputs)} body=${body.slice(0,1000)}`;
}
function actualBlock(body){
  const s=(body||'').toLowerCase();
  if(/recaptcha|hcaptcha|turnstile|verify you are human|security verification|captcha/.test(s)) return 'captcha';
  if(/credit card|payment method|add card|billing information|card details/.test(s)) return 'payment';
  return null;
}
async function twoStepLogin(page){
  await page.goto('https://wasmer.io/login',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(1200);
  const ident=page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  const seenIdent=await ident.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false);
  if(!seenIdent) return {ok:false,stage:'username_missing'};
  await ident.fill(state.email||state.username);

  const firstContinue=page.locator('button').filter({hasText:/continue|next|log in|sign in/i}).first();
  if(await firstContinue.count() && await firstContinue.isVisible().catch(()=>false)) await firstContinue.click().catch(()=>{});
  else await ident.press('Enter').catch(()=>{});

  const pass=page.locator('input[type=password]').first();
  const seenPass=await pass.waitFor({state:'visible',timeout:12000}).then(()=>true).catch(()=>false);
  if(!seenPass) return {ok:false,stage:'password_missing'};
  await pass.fill(state.password);

  const loginBtn=page.locator('button').filter({hasText:/log in|sign in|continue/i}).first();
  if(await loginBtn.count() && await loginBtn.isVisible().catch(()=>false)) await loginBtn.click().catch(()=>{});
  else await pass.press('Enter').catch(()=>{});

  await page.waitForTimeout(3500);
  const body=await bodyText(page);
  const stillLogin=/\/login(?:[/?#]|$)/i.test(page.url());
  if(stillLogin || /incorrect|invalid password|wrong password|authentication failed/i.test(body)) return {ok:false,stage:'login_rejected'};
  return {ok:true,stage:'done'};
}
async function fillAppName(page){
  const candidates=page.locator('input[name*=name i],input[placeholder*=name i],input[type=text]');
  for(let i=0;i<await candidates.count();i++){
    const el=candidates.nth(i);
    if(!(await el.isVisible().catch(()=>false))) continue;
    const ph=(await el.getAttribute('placeholder'))||'';
    const nm=(await el.getAttribute('name'))||'';
    if(/user|email|search/i.test(ph+' '+nm)) continue;
    await el.fill(state.appName).catch(()=>{});
    return true;
  }
  return false;
}

const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
const ctx=await browser.newContext();
const page=await ctx.newPage();
try{
  state.status='continuing_existing_account';state.detail=null;save();
  const login=await twoStepLogin(page);
  if(!login.ok){state.status='blocked_login';state.detail=await pageState(page,login.stage);save();process.exit(0);}

  await page.goto('https://wasmer.io/apps/create?template=wordpress-starter',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(2500);
  let body=await bodyText(page);
  let block=actualBlock(body);
  if(block){state.status='blocked_'+block;state.detail='create_entry';save();process.exit(0);}

  const later=page.locator('button').filter({hasText:/I'll do it later|I’ll do it later/i}).first();
  if(await later.count() && await later.isVisible().catch(()=>false)){
    await later.click().catch(()=>{});
    await page.waitForTimeout(1200);
  }
  const close=page.locator('button').filter({hasText:/^Close$/i}).first();
  if(await close.count() && await close.isVisible().catch(()=>false)){
    await close.click().catch(()=>{});
    await page.waitForTimeout(700);
  }

  await fillAppName(page);
  body=await bodyText(page);block=actualBlock(body);
  if(block){state.status='blocked_'+block;state.detail='before_deploy';save();process.exit(0);}

  let deploy=page.locator('button').filter({hasText:/Deploy now/i}).first();
  if(!(await deploy.count())) deploy=page.getByText(/Deploy now/i).first();
  if(!(await deploy.count())){state.status='blocked_deploy_form';state.detail=await pageState(page,'deploy_button_missing');save();process.exit(0);}
  await deploy.click();

  for(let i=0;i<60;i++){
    await page.waitForTimeout(2500);
    body=await bodyText(page);block=actualBlock(body);
    if(block){state.status='blocked_'+block;state.detail='after_deploy_submit';save();process.exit(0);}
    const links=await page.locator('a[href*=".wasmer.app"]').evaluateAll(as=>as.map(a=>a.href)).catch(()=>[]);
    if(links.length){state.siteUrl=links[0];state.status='deployed';break;}
    const urls=[...body.matchAll(/https?:\/\/[^\s]+\.wasmer\.app\/?/ig)].map(x=>x[0]);
    if(urls.length){state.siteUrl=urls[0];state.status='deployed';break;}
    if(/successfully deployed|site.*live|deployment.*complete|deployment successful/i.test(body)) state.status='deployed_pending_url';
  }

  if(!/^deployed/.test(state.status)){
    state.status='deploy_unconfirmed';
    state.detail=await pageState(page,'deploy_unconfirmed');
  }
  if(state.siteUrl){
    const r=await page.request.get(state.siteUrl,{timeout:30000}).catch(()=>null);
    state.httpStatus=r?.status()||null;
  }
  save();
}catch(e){state.status='automation_error';state.detail=String(e).slice(0,700);save();}
finally{await browser.close();}
