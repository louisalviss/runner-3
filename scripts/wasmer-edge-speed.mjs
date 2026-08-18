import { chromium } from 'playwright-core';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';

const owner = process.env.WASMER_APP_OWNER || 'runner3wp0b90f6b4ab';
const slug = process.env.WASMER_APP_SLUG || 'runner3-factory-smoke-2';
const site = (process.env.WP_SITE_URL || `https://${slug}.wasmer.app/`).replace(/\/$/, '');
const outPath = process.env.EDGE_SPEED_OUT || '/tmp/wasmer-edge-speed.json';
const dashboard = `https://wasmer.io/apps/${owner}/${slug}`;
const cdnUrl = `${dashboard}/settings/cdn-cache`;

const result = {
  status: 'starting', owner, slug, site, dashboard,
  baseline: null, cdn: { page: cdnUrl, before: null, mutation: null, after: null },
  instaboot: { detected: false, detail: null }, after: null,
  functionalSmoke: null, detail: null, updatedAt: new Date().toISOString()
};

const redact = (value) => String(value ?? '')
  .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig, 'EMAIL_REDACTED')
  .replace(/([?&](?:token|magiclogin|key|code|secret|auth|signature)=)[^&\s"']+/ig, '$1REDACTED')
  .slice(0, 12000);

function curlOne(url) {
  try {
    const format = '%{http_code}\t%{time_namelookup}\t%{time_connect}\t%{time_appconnect}\t%{time_starttransfer}\t%{time_total}\t%{size_download}';
    const text = execFileSync('curl', ['-L','-sS','--max-time','30','-o','/dev/null','-w',format,url], { encoding:'utf8' }).trim();
    const [status,dns,connect,tls,ttfb,total,bytes] = text.split('\t');
    return { status:Number(status), dnsMs:+dns*1000, connectMs:+connect*1000, tlsMs:+tls*1000, ttfbMs:+ttfb*1000, totalMs:+total*1000, bytes:Number(bytes) };
  } catch (e) { return { error:String(e?.message || e) }; }
}

function sample(url, n=5) {
  const runs=[];
  for (let i=0;i<n;i++) runs.push(curlOne(`${url}${url.includes('?')?'&':'?'}r3probe=${Date.now()}-${i}`));
  const ok=runs.filter(x=>Number.isFinite(x.ttfbMs));
  const sorted=ok.map(x=>x.ttfbMs).sort((a,b)=>a-b);
  return { url, runs, medianTtfbMs: sorted.length ? sorted[Math.floor(sorted.length/2)] : null, minTtfbMs: sorted[0] ?? null, maxTtfbMs: sorted.at(-1) ?? null };
}

async function snapshotPage(page) {
  const text = (await page.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();
  const controls = await page.locator('button,input,[role="switch"],[role="checkbox"],label').evaluateAll(nodes => nodes.slice(0,160).map((n,i)=>({
    i, tag:n.tagName.toLowerCase(), role:n.getAttribute('role'), type:n.getAttribute('type'),
    text:(n.innerText||n.textContent||n.getAttribute('aria-label')||n.getAttribute('value')||'').replace(/\s+/g,' ').trim().slice(0,180),
    ariaChecked:n.getAttribute('aria-checked'), checked:'checked' in n ? n.checked : null, disabled:'disabled' in n ? n.disabled : null
  })).filter(x=>/cache|cdn|enable|disable|purge|insta|boot|snapshot/i.test(x.text)));
  return { url:page.url(), text:redact(text), controls };
}

async function enableCdnIfSafe(page) {
  // Only act on explicit CDN-cache controls; never click generic Save/Deploy buttons blindly.
  const explicit = page.getByRole('button', { name:/enable\s+(cdn\s+)?cache|enable\s+cdn/i }).first();
  if (await explicit.count()) {
    if (await explicit.isVisible().catch(()=>false)) {
      await explicit.click();
      await page.waitForTimeout(1200);
      const confirm = page.getByRole('button', { name:/^(enable|confirm|save)$/i }).first();
      if (await confirm.count() && await confirm.isVisible().catch(()=>false)) { await confirm.click(); await page.waitForTimeout(1800); }
      return { attempted:true, method:'explicit-enable-button' };
    }
  }
  const switches = page.locator('[role="switch"], input[type="checkbox"]');
  const count = await switches.count();
  for (let i=0;i<count;i++) {
    const sw=switches.nth(i);
    const contextText = await sw.evaluate(el => (el.closest('label,div,section,fieldset')?.innerText || el.getAttribute('aria-label') || '').replace(/\s+/g,' ').trim().slice(0,500)).catch(()=> '');
    if (!/cdn\s*cache|cache\s+eligible|edge\s+cache/i.test(contextText)) continue;
    const checked = await sw.isChecked().catch(async()=> (await sw.getAttribute('aria-checked'))==='true');
    if (checked) return { attempted:false, method:'already-enabled', context:redact(contextText) };
    await sw.click(); await page.waitForTimeout(800);
    const save = page.getByRole('button', { name:/^(save|update|apply)$/i }).first();
    if (await save.count() && await save.isVisible().catch(()=>false)) { await save.click(); await page.waitForTimeout(1800); }
    return { attempted:true, method:'cdn-labeled-switch', context:redact(contextText) };
  }
  return { attempted:false, method:'no-safe-control-found' };
}

const browser = await chromium.launch({ headless:true, executablePath:'/usr/bin/google-chrome', args:['--no-sandbox','--disable-dev-shm-usage'] });
try {
  result.baseline = { homepage: sample(`${site}/`,5) };
  const ctx = await browser.newContext({ storageState:'/tmp/wasmer-browser-state.json', viewport:{width:1440,height:1000} });
  const page = await ctx.newPage();
  await page.goto(cdnUrl,{waitUntil:'domcontentloaded',timeout:60000}); await page.waitForTimeout(1800);
  if (/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('Wasmer browser session expired');
  result.cdn.before = await snapshotPage(page);
  result.cdn.mutation = await enableCdnIfSafe(page);
  await page.reload({waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{}); await page.waitForTimeout(1200);
  result.cdn.after = await snapshotPage(page);

  // Search the current managed-app settings for an InstaBoot control, but do not guess/mutate if none is explicit.
  for (const path of ['/settings','/settings/wordpress','/settings/cdn-cache']) {
    await page.goto(`${dashboard}${path}`,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{}); await page.waitForTimeout(800);
    const text=(await page.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();
    if (/instaboot|insta\s*boot|startup snapshot/i.test(text)) {
      result.instaboot.detected=true; result.instaboot.detail=redact(text); break;
    }
  }
  await ctx.close();

  // Warm once, then measure normal URL repeatedly (no cache-busting) to capture edge-cache behavior.
  curlOne(`${site}/`);
  const normalRuns=[]; for(let i=0;i<7;i++) normalRuns.push(curlOne(`${site}/`));
  const ttfbs=normalRuns.filter(x=>Number.isFinite(x.ttfbMs)).map(x=>x.ttfbMs).sort((a,b)=>a-b);
  result.after = { homepage:{ runs:normalRuns, medianTtfbMs:ttfbs.length?ttfbs[Math.floor(ttfbs.length/2)]:null, minTtfbMs:ttfbs[0]??null, maxTtfbMs:ttfbs.at(-1)??null } };

  const home=curlOne(`${site}/`), admin=curlOne(`${site}/wp-login.php`), rest=curlOne(`${site}/wp-json/`);
  result.functionalSmoke={home,admin,rest,pass:home.status===200 && [200,302].includes(admin.status) && rest.status===200};
  result.status=result.functionalSmoke.pass?'completed':'smoke_failed';
} catch(e) {
  result.status='failed'; result.detail=redact(String(e?.stack||e));
} finally {
  result.updatedAt=new Date().toISOString(); fs.writeFileSync(outPath,JSON.stringify(result,null,2)); await browser.close();
}
console.log(JSON.stringify({status:result.status, baseline:result.baseline?.homepage && {medianTtfbMs:result.baseline.homepage.medianTtfbMs,minTtfbMs:result.baseline.homepage.minTtfbMs,maxTtfbMs:result.baseline.homepage.maxTtfbMs}, cdnMutation:result.cdn.mutation, instaboot:result.instaboot.detected, after:result.after?.homepage && {medianTtfbMs:result.after.homepage.medianTtfbMs,minTtfbMs:result.after.homepage.minTtfbMs,maxTtfbMs:result.after.homepage.maxTtfbMs}, smoke:result.functionalSmoke?.pass, detail:result.detail},null,2));
if (!['completed'].includes(result.status)) process.exitCode=1;
