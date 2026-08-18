import { chromium } from 'playwright-core';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import https from 'node:https';
import { performance } from 'node:perf_hooks';

const owner = process.env.WASMER_APP_OWNER || 'runner3wp0b90f6b4ab';
const slug = process.env.WASMER_APP_SLUG || 'runner3-factory-smoke-2';
const site = (process.env.WP_SITE_URL || `https://${slug}.wasmer.app/`).replace(/\/$/, '');
const outPath = process.env.EDGE_SPEED_OUT || '/tmp/wasmer-edge-speed.json';
const dashboard = `https://wasmer.io/apps/${owner}/${slug}`;
const cdnUrl = `${dashboard}/settings/cdn-cache`;

const result = {
  status: 'starting', owner, slug, site, dashboard,
  runId: process.env.GITHUB_RUN_ID || null,
  cdn: { page: cdnUrl, before: null, mutation: null, purge: null, after: null },
  instaboot: { detected: false, detail: null },
  cacheVerification: null,
  externalConnectionSample: null,
  functionalSmoke: null,
  detail: null,
  updatedAt: new Date().toISOString()
};

const redact = (value) => String(value ?? '')
  .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig, 'EMAIL_REDACTED')
  .replace(/([?&](?:token|magiclogin|key|code|secret|auth|signature)=)[^&\s"']+/ig, '$1REDACTED')
  .slice(0, 12000);

function normalizeHeaderValue(value) {
  if (Array.isArray(value)) return value.join(', ');
  return value == null ? null : String(value);
}

function safeHeaders(headers = {}) {
  const get = (name) => normalizeHeaderValue(headers[name.toLowerCase()]);
  const signals = {};
  for (const [key, raw] of Object.entries(headers)) {
    const k = key.toLowerCase();
    if (/cache|^age$|^via$|server-timing|^x-edge|^x-wasmer|^cf-cache-status$/.test(k)) {
      signals[k] = normalizeHeaderValue(raw);
    }
  }
  return {
    cacheControl: get('cache-control'),
    expires: get('expires'),
    contentLength: get('content-length'),
    transferEncoding: get('transfer-encoding'),
    age: get('age'),
    vary: get('vary'),
    etag: get('etag'),
    lastModified: get('last-modified'),
    setCookiePresent: Boolean(headers['set-cookie']),
    signals
  };
}

function parseHeaderBlock(raw) {
  const blocks = String(raw || '').split(/\r?\n\r?\n/).filter(Boolean);
  const block = [...blocks].reverse().find(x => /^HTTP\//m.test(x)) || '';
  const lines = block.split(/\r?\n/);
  const headers = {};
  for (const line of lines.slice(1)) {
    const i = line.indexOf(':');
    if (i <= 0) continue;
    const key = line.slice(0, i).trim().toLowerCase();
    const value = line.slice(i + 1).trim();
    if (headers[key] === undefined) headers[key] = value;
    else headers[key] = `${headers[key]}, ${value}`;
  }
  return safeHeaders(headers);
}

function curlOne(url) {
  try {
    const marker = '__R3_METRICS__';
    const format = `\n${marker}%{http_code}\t%{time_namelookup}\t%{time_connect}\t%{time_appconnect}\t%{time_starttransfer}\t%{time_total}\t%{size_download}`;
    const text = execFileSync('curl', ['-sS','--max-time','30','-D','-','-o','/dev/null','-w',format,url], { encoding:'utf8' });
    const markerPos = text.lastIndexOf(marker);
    const rawHeaders = markerPos >= 0 ? text.slice(0, markerPos) : '';
    const metrics = markerPos >= 0 ? text.slice(markerPos + marker.length).trim() : '';
    const [status,dns,connect,tls,ttfb,total,bytes] = metrics.split('\t');
    return {
      status:Number(status), dnsMs:+dns*1000, connectMs:+connect*1000,
      tlsMs:+tls*1000, ttfbMs:+ttfb*1000, totalMs:+total*1000,
      bytes:Number(bytes), headers:parseHeaderBlock(rawHeaders)
    };
  } catch (e) { return { error:String(e?.message || e) }; }
}

function sampleExternal(url, n=5) {
  const runs=[];
  for (let i=0;i<n;i++) runs.push(curlOne(url));
  const ok=runs.filter(x=>Number.isFinite(x.ttfbMs));
  const sorted=ok.map(x=>x.ttfbMs).sort((a,b)=>a-b);
  return {
    url, runs,
    medianTtfbMs: sorted.length ? sorted[Math.floor(sorted.length/2)] : null,
    minTtfbMs: sorted[0] ?? null,
    maxTtfbMs: sorted.at(-1) ?? null
  };
}

function requestOnce(url, agent) {
  return new Promise((resolve) => {
    const started = performance.now();
    const req = https.get(url, {
      agent,
      headers: {
        'User-Agent': 'WordPressEdgeCacheProbe/1.0',
        'Accept': 'text/html,application/xhtml+xml'
      }
    }, (res) => {
      const ttfbMs = performance.now() - started;
      let bytes = 0;
      res.on('data', chunk => { bytes += chunk.length; });
      res.on('end', () => resolve({
        status: res.statusCode,
        ttfbMs,
        totalMs: performance.now() - started,
        bytes,
        reusedSocket: Boolean(req.reusedSocket),
        headers: safeHeaders(res.headers)
      }));
    });
    req.setTimeout(30000, () => req.destroy(new Error('request timeout')));
    req.on('error', err => resolve({ error: String(err?.message || err), reusedSocket: Boolean(req.reusedSocket) }));
  });
}

async function keepAliveSeries(url, n=8) {
  const agent = new https.Agent({ keepAlive:true, maxSockets:1, maxFreeSockets:1, timeout:30000 });
  const runs=[];
  for (let i=0;i<n;i++) runs.push(await requestOnce(url, agent));
  agent.destroy();
  const warm = runs.slice(1).filter(x=>Number.isFinite(x.ttfbMs));
  const sorted = warm.map(x=>x.ttfbMs).sort((a,b)=>a-b);
  return {
    url,
    runs,
    firstTtfbMs: Number.isFinite(runs[0]?.ttfbMs) ? runs[0].ttfbMs : null,
    warmMedianTtfbMs: sorted.length ? sorted[Math.floor(sorted.length/2)] : null,
    warmMinTtfbMs: sorted[0] ?? null,
    warmMaxTtfbMs: sorted.at(-1) ?? null
  };
}

function cacheHitSignal(headers) {
  if (!headers) return false;
  const text = Object.entries(headers.signals || {}).map(([k,v])=>`${k}:${v}`).join(' ');
  const age = Number(headers.age);
  return (Number.isFinite(age) && age > 0) || /\b(hit|cached|cache-hit)\b/i.test(text);
}

function evaluateCache(series) {
  const runs = series?.runs || [];
  const first = runs[0] || {};
  const firstHeaders = first.headers || {};
  const cacheControl = firstHeaders.cacheControl || '';
  const contentLength = Number(firstHeaders.contentLength);
  const eligibleResponse = /\bpublic\b/i.test(cacheControl)
    && /(?:s-maxage|max-age)=\d+/i.test(cacheControl)
    && Number.isFinite(contentLength) && contentLength > 0
    && !firstHeaders.setCookiePresent
    && firstHeaders.vary !== '*';

  const warmRuns = runs.slice(1).filter(x=>Number.isFinite(x.ttfbMs));
  const explicitHit = warmRuns.some(x=>cacheHitSignal(x.headers));
  const firstTtfb = series.firstTtfbMs;
  const warmMedian = series.warmMedianTtfbMs;
  const performanceHit = Number.isFinite(firstTtfb) && Number.isFinite(warmMedian)
    && warmMedian <= Math.min(150, firstTtfb * 0.75);

  return {
    eligibleResponse,
    explicitHit,
    performanceHit,
    edgeReuseVerified: eligibleResponse && (explicitHit || performanceHit),
    firstHeaders,
    firstTtfbMs:firstTtfb,
    warmMedianTtfbMs:warmMedian,
    originWorkApproxFirstMs:null,
    notes: eligibleResponse
      ? (explicitHit ? 'cache hit exposed by response headers' : (performanceHit ? 'cache reuse inferred from large keep-alive TTFB drop' : 'response is cache-eligible but edge reuse not yet proven'))
      : 'response is not eligible for Wasmer CDN cache under documented rules'
  };
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

async function purgeCdnIfSafe(page) {
  const button = page.getByRole('button', { name:/^Purge cache$/i }).first();
  if (!(await button.count())) return {attempted:false,reason:'purge-button-missing'};
  if (await button.isDisabled().catch(()=>true)) return {attempted:false,reason:'purge-button-disabled'};
  await button.click();
  await page.waitForTimeout(1800);
  return {attempted:true,completed:true};
}

const browser = await chromium.launch({ headless:true, executablePath:'/usr/bin/google-chrome', args:['--no-sandbox','--disable-dev-shm-usage'] });
try {
  const ctx = await browser.newContext({ storageState:'/tmp/wasmer-browser-state.json', viewport:{width:1440,height:1000} });
  const page = await ctx.newPage();
  await page.goto(cdnUrl,{waitUntil:'domcontentloaded',timeout:60000}); await page.waitForTimeout(1800);
  if (/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('Wasmer browser session expired');
  result.cdn.before = await snapshotPage(page);
  result.cdn.mutation = await enableCdnIfSafe(page);
  await page.reload({waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{}); await page.waitForTimeout(1200);
  result.cdn.after = await snapshotPage(page);
  result.cdn.purge = await purgeCdnIfSafe(page);

  for (const path of ['/settings','/settings/wordpress','/settings/cdn-cache']) {
    await page.goto(`${dashboard}${path}`,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{}); await page.waitForTimeout(800);
    const text=(await page.locator('body').innerText().catch(()=>'' )).replace(/\s+/g,' ').trim();
    if (/Purge Instaboot Snapshots|instaboot|insta\s*boot|startup snapshot/i.test(text)) {
      result.instaboot.detected=true; result.instaboot.detail=redact(text); break;
    }
  }
  await ctx.close();

  await new Promise(r=>setTimeout(r,1200));
  const series = await keepAliveSeries(`${site}/`, 8);
  const evaluation = evaluateCache(series);
  result.cacheVerification = { series, evaluation };
  result.externalConnectionSample = sampleExternal(`${site}/`, 5);

  const home=curlOne(`${site}/`), admin=curlOne(`${site}/wp-login.php`), rest=curlOne(`${site}/wp-json/`);
  const adminPublic = /\bpublic\b/i.test(admin?.headers?.cacheControl || '');
  const restPublic = /\bpublic\b/i.test(rest?.headers?.cacheControl || '');
  result.functionalSmoke={
    home, admin, rest,
    adminPublicCacheHeader:adminPublic,
    restPublicCacheHeader:restPublic,
    pass:home.status===200 && [200,302].includes(admin.status) && rest.status===200 && !adminPublic && !restPublic
  };

  const enabled = result.cdn.after?.controls?.some(c=>c.role==='switch' && (c.ariaChecked==='true'||/^enabled$/i.test(c.text))) || result.cdn.mutation?.enabled;
  result.status = result.functionalSmoke.pass && enabled && evaluation.edgeReuseVerified
    ? 'completed'
    : (!result.functionalSmoke.pass ? 'smoke_failed' : (!enabled ? 'cdn_not_enabled' : 'cache_not_verified'));
} catch(e) {
  result.status='failed'; result.detail=redact(String(e?.stack||e));
} finally {
  result.updatedAt=new Date().toISOString(); fs.writeFileSync(outPath,JSON.stringify(result,null,2)); await browser.close();
}

console.log(JSON.stringify({
  status:result.status,
  cdnMutation:result.cdn.mutation,
  cdnPurge:result.cdn.purge,
  instaboot:result.instaboot.detected,
  cache:result.cacheVerification?.evaluation,
  keepAlive:result.cacheVerification?.series && {
    firstTtfbMs:result.cacheVerification.series.firstTtfbMs,
    warmMedianTtfbMs:result.cacheVerification.series.warmMedianTtfbMs,
    warmMinTtfbMs:result.cacheVerification.series.warmMinTtfbMs,
    warmMaxTtfbMs:result.cacheVerification.series.warmMaxTtfbMs
  },
  externalMedianTtfbMs:result.externalConnectionSample?.medianTtfbMs,
  smoke:result.functionalSmoke?.pass,
  detail:result.detail
},null,2));
if (result.status!=='completed') process.exitCode=1;
