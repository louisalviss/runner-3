import { chromium } from 'playwright-core';
import fs from 'fs';

const site = JSON.parse(fs.readFileSync('ops/site-factory/runner5-restore-lab-1.json', 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(site.siteUrl || 'https://runner5-restore-lab-1.wasmer.app/').replace(/\/$/, '');
const dashboard = site.dashboardUrl;
const out = '/tmp/runner5-oceanwp-origin-repair.json';
const shot = '/tmp/runner5-oceanwp-origin-after.png';
const result = { status:'STARTING', siteUrl:base+'/', before:null, after:null, page:null, fixes:[], plugins:{}, detail:null, updatedAt:new Date().toISOString() };
const save = () => { result.updatedAt = new Date().toISOString(); fs.writeFileSync(out, JSON.stringify(result,null,2)); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const onWasmerLogin = p => /\/login(?:[/?#]|$)/i.test(p.url());

async function loginWasmer(p) {
  await p.goto('https://wasmer.io/login', {waitUntil:'domcontentloaded', timeout:45000}).catch(()=>{});
  await p.waitForTimeout(600);
  if (!onWasmerLogin(p)) return;
  const user = p.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();
  await user.fill(account.username || account.email); await user.press('Enter');
  const pass = p.locator('input[type=password]').first(); await pass.waitFor({state:'visible',timeout:20000});
  await pass.fill(account.password); await pass.press('Enter');
  const end=Date.now()+20000; while(Date.now()<end){ if(!onWasmerLogin(p)) return; await p.waitForTimeout(350); }
  throw new Error('wasmer_login_failed');
}
async function pollWpAdmin(ctx, ms=22000){ const end=Date.now()+ms; while(Date.now()<end){ for(const p of ctx.pages()) if(p.url().startsWith(base)&&/\/wp-admin(?:\/|\?|$)/i.test(p.url())&&!/wp-login\.php/i.test(p.url())) return p; await sleep(400); } return null; }
async function enterWpAdmin(ctx,p){
  for(let attempt=0;attempt<3;attempt++){
    await p.goto(dashboard,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{}); await p.waitForTimeout(800);
    let admin=p.getByText(/WordPress Admin/i).first();
    if(!await admin.isVisible().catch(()=>false)){
      const settings=p.getByText(/^Settings$/i).first(); if(await settings.isVisible().catch(()=>false)){ await settings.click().catch(()=>{}); await p.waitForTimeout(450); const wp=p.getByText(/^WordPress$/i).first(); if(await wp.isVisible().catch(()=>false)){await wp.click().catch(()=>{});await p.waitForTimeout(450);} admin=p.getByText(/WordPress Admin/i).first(); }
    }
    if(await admin.isVisible().catch(()=>false)){
      const href=await admin.getAttribute('href').catch(()=>null); if(href){ const wp=await ctx.newPage(); await wp.goto(new URL(href,'https://wasmer.io').href,{waitUntil:'domcontentloaded',timeout:45000}).catch(()=>{}); const found=await pollWpAdmin(ctx,18000); if(found) return found; }
      await admin.click({noWaitAfter:true}).catch(()=>{}); const found=await pollWpAdmin(ctx,20000); if(found) return found;
    }
  }
  throw new Error('magic_admin_failed');
}
async function getNonce(wp){
  await wp.goto(`${base}/wp-admin/`,{waitUntil:'domcontentloaded',timeout:60000}); await wp.waitForTimeout(500);
  let n=await wp.evaluate(()=>globalThis.wpApiSettings?.nonce||globalThis.wp?.apiSettings?.nonce||null).catch(()=>null);
  if(!n){const html=await wp.content();const m=html.match(/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i);if(m)n=m[1];}
  if(!n) throw new Error('wp_rest_nonce_missing'); return n;
}
async function api(ctx,nonce,path,{method='GET',json=null,soft=false,timeout=180000}={}){
  const headers={'X-WP-Nonce':nonce,Accept:'application/json'}; let data;
  if(json!==null){headers['Content-Type']='application/json';data=JSON.stringify(json);}
  const r=await ctx.request.fetch(`${base}/wp-json${path}`,{method,headers,data,timeout,failOnStatusCode:false}); const text=await r.text(); let body; try{body=JSON.parse(text)}catch{body=text}
  if(!r.ok()){if(soft)return{ok:false,status:r.status(),data:body};throw new Error(`api_${method}_${path}:${r.status()}:${String(text).slice(0,400)}`)} return soft?{ok:true,status:r.status(),data:body}:body;
}
async function ensurePlugin(ctx,nonce,slug,prefix=`${slug}/`){
  const ps=await api(ctx,nonce,'/wp/v2/plugins?context=edit'); let p=Array.isArray(ps)?ps.find(x=>String(x.plugin||'').startsWith(prefix)):null;
  if(!p) p=await api(ctx,nonce,'/wp/v2/plugins',{method:'POST',json:{slug,status:'active'},timeout:180000});
  else if(p.status!=='active') p=await api(ctx,nonce,`/wp/v2/plugins/${encodeURIComponent(p.plugin)}`,{method:'POST',json:{status:'active'},timeout:120000});
  result.plugins[slug]=p?.status||'active'; save(); return p;
}

async function audit(browser,label,screenshotPath=null){
  const ctx=await browser.newContext({viewport:{width:1440,height:1000}}); const p=await ctx.newPage();
  const failed=[]; const consoleErrors=[];
  p.on('response',r=>{ if(r.status()>=400 && ['stylesheet','script','image','font'].includes(r.request().resourceType())) failed.push({status:r.status(),type:r.request().resourceType(),url:r.url()}); });
  p.on('requestfailed',r=>failed.push({status:null,type:r.resourceType(),url:r.url(),error:r.failure()?.errorText||'requestfailed'}));
  p.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text())});
  const response=await p.goto(`${base}/?origin-layout-audit=${Date.now()}`,{waitUntil:'domcontentloaded',timeout:60000});
  await p.waitForTimeout(2500);
  const total=await p.evaluate(()=>document.documentElement.scrollHeight);
  for(let y=0;y<total;y+=700){await p.evaluate(v=>window.scrollTo(0,v),y);await p.waitForTimeout(90);} await p.evaluate(()=>window.scrollTo(0,0)); await p.waitForTimeout(800);
  const metrics=await p.evaluate(()=>{
    const styles=[...document.querySelectorAll('link[rel~="stylesheet"]')].map(x=>x.href);
    const scripts=[...document.scripts].map(x=>x.src).filter(Boolean);
    const firstSection=document.querySelector('.elementor-section,.e-con,.elementor-element');
    const sr=firstSection?.getBoundingClientRect();
    const content=document.querySelector('#content-wrap,#main,#content,.site-main');
    const classes=[...document.querySelectorAll('#content-wrap *,#main *,#content *')].map(x=>typeof x.className==='string'?x.className.trim():'').filter(Boolean).slice(0,50);
    const imgs=[...document.images].map(i=>({src:i.getAttribute('src'),currentSrc:i.currentSrc,naturalWidth:i.naturalWidth,naturalHeight:i.naturalHeight,complete:i.complete}));
    return {
      title:document.title, bodyClass:document.body.className,
      stylesheetCount:styles.length, elementorStylesheets:styles.filter(x=>/elementor/i.test(x)),
      scriptCount:scripts.length, elementorScripts:scripts.filter(x=>/elementor/i.test(x)).length,
      elementorMarker:/elementor-page/.test(document.body.className)||!!document.querySelector('.elementor'),
      elementorElements:document.querySelectorAll('.elementor-element').length,
      eConCount:document.querySelectorAll('.e-con').length,
      widgetCount:document.querySelectorAll('[class*="elementor-widget"]').length,
      imageCount:document.images.length, loadedImages:imgs.filter(i=>i.complete&&i.naturalWidth>0).length,
      brokenImageSample:imgs.filter(i=>i.complete&&i.naturalWidth===0).slice(0,20),
      viewportWidth:document.documentElement.clientWidth, scrollWidth:Math.max(document.documentElement.scrollWidth,document.body.scrollWidth),
      firstElement:firstSection?{tag:firstSection.tagName,cls:firstSection.className,left:Math.round(sr.left),width:Math.round(sr.width),height:Math.round(sr.height),display:getComputedStyle(firstSection).display}:null,
      oceanwp:/oceanwp|oceanwp-theme|ocean/i.test(document.body.className)||!!document.querySelector('#site-header,#outer-wrap'),
      contentHtmlSample:(content?.innerHTML||'').replace(/\s+/g,' ').slice(0,3000), classSample:classes,
      htmlBytes:new Blob([document.documentElement.outerHTML]).size
    };
  });
  if(screenshotPath) await p.screenshot({path:screenshotPath,fullPage:true});
  const a={label,http:response?.status()??null,url:p.url(),failed:failed.slice(0,100),consoleErrors:consoleErrors.slice(0,50),...metrics};
  await ctx.close(); return a;
}

async function clickFirst(page,patterns){
  for(const re of patterns){
    for(const c of [page.getByRole('button',{name:re}).first(),page.getByRole('link',{name:re}).first()]){
      if(await c.count().catch(()=>0) && await c.isVisible().catch(()=>false)){ await c.click().catch(()=>{}); await page.waitForTimeout(1800); return true; }
    }
  }
  return false;
}

async function repairElementor(wp){
  await wp.goto(`${base}/wp-admin/admin.php?page=elementor-tools`,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{}); await wp.waitForTimeout(1200);
  const regen=await clickFirst(wp,[/Regenerate Files.*Data/i,/Regenerate CSS.*Data/i,/Regenerate CSS/i,/Clear Files.*Data/i]);
  if(regen) result.fixes.push('elementor_regenerate_files_data');

  for(const url of [`${base}/wp-admin/admin.php?page=elementor`,`${base}/wp-admin/admin.php?page=elementor-settings`]){
    await wp.goto(url,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{}); await wp.waitForTimeout(900);
    const s=wp.locator('select[name*="css_print_method" i],select[id*="css_print_method" i]').first();
    if(await s.count().catch(()=>0)){
      const values=await s.locator('option').evaluateAll(os=>os.map(o=>o.value));
      if(values.includes('internal')){
        await s.selectOption('internal',{force:true}).catch(async()=>{await s.evaluate(el=>{el.value='internal';el.dispatchEvent(new Event('change',{bubbles:true}));});});
        const form=s.locator('xpath=ancestor::form[1]');
        if(await form.count()) { await form.evaluate(f=>{ if(f.requestSubmit) f.requestSubmit(); else f.submit(); }).catch(()=>{}); await wp.waitForTimeout(2000); }
        result.fixes.push('elementor_css_print_method_internal'); break;
      }
    }
  }
  await wp.goto(`${base}/wp-admin/admin.php?page=elementor-tools`,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{}); await wp.waitForTimeout(900);
  const regen2=await clickFirst(wp,[/Regenerate Files.*Data/i,/Regenerate CSS.*Data/i,/Regenerate CSS/i,/Clear Files.*Data/i]);
  if(regen2) result.fixes.push('elementor_regenerate_after_internal');
}

const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});
try{
  result.before=await audit(browser,'before'); save();
  const adminCtx=await browser.newContext({viewport:{width:1440,height:1100}}); const gate=await adminCtx.newPage();
  await loginWasmer(gate); const wp=await enterWpAdmin(adminCtx,gate); let nonce=await getNonce(wp);
  for(const [slug,prefix] of [['ocean-extra','ocean-extra/'],['ocean-social-sharing','ocean-social-sharing/'],['ocean-custom-sidebar','ocean-custom-sidebar/'],['elementor','elementor/'],['ocean-elementor-widgets','ocean-elementor-widgets/'],['wpforms-lite','wpforms-lite/']]){
    await ensurePlugin(adminCtx,nonce,slug,prefix).catch(e=>{result.plugins[slug]=`warning:${String(e).slice(0,160)}`;save();});
  }
  const home=await api(adminCtx,nonce,'/wp/v2/pages/171?context=edit&_fields=id,slug,title,content,template,meta',{soft:true});
  if(home.ok){const d=home.data||{};const raw=String(d.content?.raw||'');result.page={id:d.id,slug:d.slug,template:d.template,contentRawLength:raw.length,contentRawSample:raw.replace(/\s+/g,' ').slice(0,2500),metaKeys:Object.keys(d.meta||{})};save();}
  await repairElementor(wp);
  await wp.goto(`${base}/wp-admin/options-permalink.php`,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{}); await wp.waitForTimeout(700);
  const savePerm=wp.locator('#submit,input[type=submit],button[type=submit]').first(); if(await savePerm.count()&&await savePerm.isVisible().catch(()=>false)){await savePerm.click().catch(()=>{});await wp.waitForTimeout(1200);result.fixes.push('flush_rewrite_rules');}
  await adminCtx.close();
  await sleep(2500);
  result.after=await audit(browser,'after',shot); save();
  const cssFails=result.after.failed.filter(x=>x.type==='stylesheet'||/\.css(?:\?|$)/i.test(x.url));
  const localImageFails=result.after.failed.filter(x=>x.type==='image'&&x.url.startsWith(base));
  const hasBuilderDom=result.after.elementorElements>0||result.after.eConCount>0||result.after.widgetCount>0;
  const hardBroken=result.after.http!==200||!result.after.oceanwp||result.after.stylesheetCount<3||cssFails.length>0||localImageFails.length>0||(!hasBuilderDom&&result.after.elementorMarker);
  result.status=hardBroken?'FAILED':'READY'; result.detail=hardBroken?`origin_layout_qa_failed builderDom=${hasBuilderDom} cssFails=${cssFails.length} localImageFails=${localImageFails.length} styles=${result.after.stylesheetCount}`:null; save();
  if(hardBroken) process.exitCode=2;
}catch(e){result.status='FAILED';result.detail=String(e?.stack||e);save();console.error(result.detail);process.exitCode=1;}finally{await browser.close();}
console.log(JSON.stringify(result,null,2));
