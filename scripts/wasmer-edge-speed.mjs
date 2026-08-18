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

function sample(url, n=5, cacheBust=true) {
  const runs=[];
  for (let i=0;i<n;i++) {
    const probe=cacheBust ? `${url}${url.includes('?')?'&':'?'}r3probe=${Date.now()}-${i}` : url;
    runs.push(curlOne(probe));
  }
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
  const bodyText=(await page.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();
  if (!/CDN Cache Control/i.test(bodyText) || !/App CDN caching/i.test(bodyText)) return {attempted:false,method:'cdn-page-signature-missing'};
  const sw=page.locator('button[role="switch"]').first();
  if (!(await sw.count())) return {attempted:false,method:'cdn-switch-missing'};
  const disabled=await sw.isDisabled().catch(()=>true);
  const aria=await sw.getAttribute('aria-checked');
  const text=(await sw.innerText().catch(()=>'' )).trim();
  if (disabled) return {attempted:false,method:'cdn-switch-disabled'};
  if (aria==='true' || /^enabled$/i.test(text)) return {attempted:false,method:'already-enabled',enabled:true};
  if (aria!=='false' && !/^disabled$/i.test(text)) return {attempted:false,method:'unexpected-switch-state',state:{aria,text}};
  await sw.click(); await page.waitForTimeout(1800);
  const ariaAfter=await sw.getAttribute('aria-checked').catch(()=>null);
  const textAfter=(await sw.innerText().catch(()=>'' )).trim();
  return {attempted:true,method:'verified-app-cdn-switch',before:{aria,text},after:{aria:ariaAfter,text:textAfter},enabled:ariaAfter==='true'||/^enabled$/i.test(textAfter)};
}

const browser = await chromium.launch({ headless:true, executablePath:'/usr/bin/google-chrome', args:['--no-sandbox','--disable-dev-shm-usage'] });
try {
  result.baseline = { homepage: sample(`${site}/`,5,true) };
  const ctx = await browser.newContext({ storageState:'/tmp/wasmer-browser-state.json', viewport:{width:1440,height:1000} });
  const page = await ctx.newPage();
  await page.goto(cdnUrl,{waitUntil:'domcontentloaded',timeout:60000}); await page.waitForTimeout(1800);
  if (/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('Wasmer browser session expired');
  result.cdn.before = await snapshotPage(page);
  result.cdn.mutation = await enableCdnIfSafe(page);
  await page.reload({waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{}); await page.waitForTimeout(1200);
  result.cdn.after = await snapshotPage(page);

  for (const path of ['/settings','/settings/wordpress','/settings/cdn-cache']) {
    await page.goto(`${dashboard}${path}`,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{}); await page.waitForTimeout(800);
    const text=(await page.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();
    if (/Purge Instaboot Snapshots|instaboot|insta\s*boot|startup snapshot/i.test(text)) {
      result.instaboot.detected=true; result.instaboot.detail=redact(text); break;
    }
  }
  await ctx.close();

  await new Promise(r=>setTimeout(r,2500));
  curlOne(`${site}/`);
  result.after={homepage:sample(`${site}/`,9,false)};

  const home=curlOne(`${site}/`), admin=curlOne(`${site}/wp-login.php`), rest=curlOne(`${site}/wp-json/`);
  result.functionalSmoke={home,admin,rest,pass:home.status===200 && [200,302].includes(admin.status) && rest.status===200};
  const enabled = result.cdn.after?.controls?.some(c=>c.role==='switch' && (c.ariaChecked==='true'||/^enabled$/i.test(c.text))) || result.cdn.mutation?.enabled;
  result.status=result.functionalSmoke.pass && enabled ? 'completed' : (result.functionalSmoke.pass ? 'cdn_not_enabled' : 'smoke_failed');
} catch(e) {
  result.status='failed'; result.detail=redact(String(e?.stack||e));
} finally {
  result.updatedAt=new Date().toISOString(); fs.writeFileSync(outPath,JSON.stringify(result,null,2)); await browser.close();
}
console.log(JSON.stringify({status:result.status, baseline:result.baseline?.homepage && {medianTtfbMs:result.baseline.homepage.medianTtfbMs,minTtfbMs:result.baseline.homepage.minTtfbMs,maxTtfbMs:result.baseline.homepage.maxTtfbMs}, cdnMutation:result.cdn.mutation, cdnAfter:result.cdn.after?.controls, instaboot:result.instaboot.detected, after:result.after?.homepage && {medianTtfbMs:result.after.homepage.medianTtfbMs,minTtfbMs:result.after.homepage.minTtfbMs,maxTtfbMs:result.after.homepage.maxTtfbMs}, smoke:result.functionalSmoke?.pass, detail:result.detail},null,2));
if (result.status!=='completed') process.exitCode=1;
