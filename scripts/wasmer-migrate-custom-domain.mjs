import { chromium } from 'playwright-core';
import fs from 'fs';

const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const owner = process.env.WASMER_OWNER || 'runner3wp0b90f6b4ab';
const sourceApp = process.env.SOURCE_APP || 'runner3-wp-a94b8fd2';
const targetApp = process.env.TARGET_APP || 'runner3-factory-smoke-2';
const targetOrigin = (process.env.TARGET_ORIGIN || 'https://runner3-factory-smoke-2.wasmer.app').replace(/\/$/, '');
const domain = process.env.TARGET_DOMAIN || 'runner3wp.pntr.dev';
const publicBase = `https://${domain}`;
const outPath = process.env.OUT || '/tmp/runner3wp-domain-migration.json';
const articlePath = '/2026/08/18/bentley-introduces-merino-wool-interior-for-upcoming-torcal-ev/';
const articleNeedle = 'Bentley Introduces Merino Wool Interior';

const result = {
  status: 'starting',
  domain,
  sourceApp,
  targetApp,
  targetOrigin,
  sourceHadDomain: null,
  detached: false,
  targetHadDomain: null,
  attached: false,
  targetValid: false,
  publicHttp: null,
  publicHasExpectedContent: false,
  publicHasNoindex: false,
  publicHasNofollow: false,
  nativeHasExpectedContent: false,
  xEdgeSnapshot: null,
  dnsChangeRequired: null,
  detail: null,
  updatedAt: new Date().toISOString(),
};

function clean(s) {
  return String(s || '')
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig, 'EMAIL_REDACTED')
    .replace(/da_[A-Za-z0-9_-]+/g, 'TOKEN_REDACTED')
    .replace(/(?:password|passwd|token|secret)\s*[:=]\s*[^\s,;}]+/ig, '$1=REDACTED')
    .slice(0, 9000);
}
function save() { result.updatedAt = new Date().toISOString(); fs.writeFileSync(outPath, JSON.stringify(result, null, 2) + '\n'); }
async function bodyText(page) { return (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ').trim(); }
async function firstVisible(locator) {
  const n = await locator.count();
  for (let i = 0; i < n; i++) { const x = locator.nth(i); if (await x.isVisible().catch(() => false)) return x; }
  return null;
}
async function snapshot(page, label) {
  const controls = await page.locator('button,a,input,[role=dialog]').evaluateAll(xs => xs.map(x => ({
    tag: x.tagName.toLowerCase(), text: (x.innerText || x.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 100),
    type: x.getAttribute('type'), name: x.getAttribute('name'), aria: x.getAttribute('aria-label'), title: x.getAttribute('title'),
    value: x.tagName === 'INPUT' && x.getAttribute('type') !== 'password' ? x.value : null,
  })).filter(x => x.text || x.name || x.aria || x.title || x.value).slice(0, 80)).catch(() => []);
  return clean(`${label} url=${page.url()} body=${await bodyText(page)} controls=${JSON.stringify(controls)}`);
}
async function login(page) {
  await page.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(600);
  const ident = page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  await ident.waitFor({ state: 'visible', timeout: 12000 });
  await ident.fill(account.username || account.email);
  const next = page.locator('button').filter({ hasText: /continue|next|log in|sign in/i }).first();
  if (await next.count() && await next.isVisible().catch(() => false)) await next.click(); else await ident.press('Enter');
  const pass = page.locator('input[type=password]').first();
  await pass.waitFor({ state: 'visible', timeout: 12000 });
  await pass.fill(account.password);
  const submit = page.locator('input[type=submit],button').filter({ hasText: /log in|sign in|continue/i }).first();
  if (await submit.count() && await submit.isVisible().catch(() => false)) await submit.click(); else await pass.press('Enter');
  await page.waitForTimeout(3500);
  if (/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('wasmer_login_failed');
}
function domainsUrl(app) { return `https://wasmer.io/apps/${encodeURIComponent(owner)}/${encodeURIComponent(app)}/settings/domains`; }

async function smallestDomainContainer(page) {
  const node = page.getByText(domain, { exact: true }).first();
  if (!(await node.count())) return null;
  return node.evaluateHandle(el => {
    let n = el;
    for (let i = 0; i < 8 && n; i++, n = n.parentElement) {
      const txt = (n.innerText || '').toLowerCase();
      const edits = [...n.querySelectorAll('button,a')].filter(x => /^\s*edit\s*$/i.test(x.innerText || x.textContent || ''));
      if (txt.includes('runner3wp.pntr.dev') && edits.length === 1) return n;
    }
    return el.parentElement;
  });
}

async function detachFromSource(page) {
  await page.goto(domainsUrl(sourceApp), { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(1500);
  let text = await bodyText(page);
  result.sourceHadDomain = text.toLowerCase().includes(domain.toLowerCase()); save();
  if (!result.sourceHadDomain) { result.detached = true; return; }

  const containerHandle = await smallestDomainContainer(page);
  if (!containerHandle) throw new Error('source_domain_container_missing:' + await snapshot(page, 'source_container_missing'));
  const container = page.locator('body').locator('*').filter({ hasText: domain });
  // Use the exact domain node and ascend in-page to click the nearest row's Edit button.
  const node = page.getByText(domain, { exact: true }).first();
  const clicked = await node.evaluate(el => {
    let n = el;
    for (let i = 0; i < 8 && n; i++, n = n.parentElement) {
      const candidates = [...n.querySelectorAll('button,a')].filter(x => /^\s*edit\s*$/i.test(x.innerText || x.textContent || ''));
      if (candidates.length === 1) { candidates[0].click(); return true; }
    }
    return false;
  }).catch(() => false);
  if (!clicked) throw new Error('source_edit_control_missing:' + await snapshot(page, 'source_edit_missing'));
  await page.waitForTimeout(700);

  const dialog = page.locator('[role=dialog]').last();
  const scope = await dialog.count() && await dialog.isVisible().catch(() => false) ? dialog : page;
  let remove = await firstVisible(scope.locator('button').filter({ hasText: /^\s*(Remove|Delete|Detach)(?:\s+Domain)?\s*$/i }));
  if (!remove) remove = await firstVisible(scope.locator('button').filter({ hasText: /remove domain|delete domain|detach domain/i }));
  if (!remove) throw new Error('safe_detach_control_missing:' + await snapshot(page, 'detach_control_missing'));
  await remove.click(); await page.waitForTimeout(500);

  // Confirmation is mandatory when a confirmation UI appears; never click generic destructive controls outside it.
  const confirmDialog = page.locator('[role=dialog]').last();
  if (await confirmDialog.count() && await confirmDialog.isVisible().catch(() => false)) {
    const dtext = (await confirmDialog.innerText().catch(() => '')).toLowerCase();
    if (dtext.includes(domain.toLowerCase()) || /remove|delete|detach/.test(dtext)) {
      const confirm = await firstVisible(confirmDialog.locator('button').filter({ hasText: /^\s*(Remove|Delete|Detach|Confirm)(?:\s+Domain)?\s*$/i }));
      if (confirm) await confirm.click();
    }
  }
  await page.waitForTimeout(2200);
  await page.goto(domainsUrl(sourceApp), { waitUntil: 'domcontentloaded', timeout: 60000 }); await page.waitForTimeout(1000);
  text = await bodyText(page);
  result.detached = !text.toLowerCase().includes(domain.toLowerCase()); save();
  if (!result.detached) throw new Error('source_domain_still_present:' + await snapshot(page, 'source_still_present'));
}

async function attachToTarget(page) {
  await page.goto(domainsUrl(targetApp), { waitUntil: 'domcontentloaded', timeout: 60000 }); await page.waitForTimeout(1200);
  let text = await bodyText(page);
  result.targetHadDomain = text.toLowerCase().includes(domain.toLowerCase());
  if (!result.targetHadDomain) {
    // Current Wasmer domains UI exposes the domain input directly in the page.
    let input = await firstVisible(page.locator('input[name="domainName"],input[placeholder*=domain i],input[type=text]'));
    if (!input) {
      const addOpen = await firstVisible(page.locator('button').filter({ hasText: /^\s*Add\s*$/i }));
      if (addOpen) { await addOpen.click(); await page.waitForTimeout(400); input = await firstVisible(page.locator('input[name="domainName"],input[placeholder*=domain i],input[type=text]')); }
    }
    if (!input) throw new Error('target_domain_input_missing:' + await snapshot(page, 'target_input_missing'));
    await input.fill(domain);
    const add = await firstVisible(page.locator('button').filter({ hasText: /^\s*Add\s*$/i }));
    if (!add) throw new Error('target_add_control_missing:' + await snapshot(page, 'target_add_missing'));
    await add.click(); await page.waitForTimeout(2500);
  }

  for (let i = 0; i < 12; i++) {
    await page.goto(domainsUrl(targetApp), { waitUntil: 'domcontentloaded', timeout: 60000 }); await page.waitForTimeout(900);
    text = await bodyText(page);
    const idx = text.toLowerCase().indexOf(domain.toLowerCase());
    const near = idx >= 0 ? text.slice(Math.max(0, idx - 180), idx + 900) : '';
    result.attached = idx >= 0;
    result.targetValid = result.attached && /valid configuration|verified|active|ready/i.test(near) && !/pending|waiting|invalid configuration|unverified|not verified/i.test(near);
    save();
    if (result.targetValid) return;
    // If already attached but Wasmer needs DNS validation propagation, the existing CNAME should remain valid; wait briefly.
    await page.waitForTimeout(1800);
  }
  if (!result.attached) throw new Error('target_attach_unconfirmed:' + await snapshot(page, 'target_attach_unconfirmed'));
  throw new Error('target_domain_not_valid_yet:' + await snapshot(page, 'target_not_valid'));
}

function inspectRobots(html) {
  const vals = [];
  for (const tag of html.match(/<meta\b[^>]*\bname\s*=\s*["']robots["'][^>]*>/gi) || []) {
    const m = tag.match(/\bcontent\s*=\s*["']([^"']*)["']/i); if (m) vals.push(m[1]);
  }
  const joined = vals.join(',').toLowerCase();
  return { noindex: /(^|[\s,])noindex([\s,]|$)/.test(joined), nofollow: /(^|[\s,])nofollow([\s,]|$)/.test(joined), values: vals };
}

async function verifyPublic(ctx) {
  // First establish that App A itself still contains the expected article.
  const native = await ctx.request.get(targetOrigin + articlePath, { headers: { Accept: 'text/html' } });
  const nativeHtml = await native.text();
  result.nativeHasExpectedContent = native.status() === 200 && nativeHtml.includes(articleNeedle);
  if (!result.nativeHasExpectedContent) throw new Error(`target_native_fingerprint_failed:http=${native.status()}`);

  let last = null;
  for (let i = 0; i < 15; i++) {
    const r = await ctx.request.get(publicBase + articlePath, { headers: { Accept: 'text/html', 'Cache-Control': 'no-cache' } });
    const html = await r.text();
    const robots = inspectRobots(html);
    last = { status: r.status(), html, robots, headers: r.headers() };
    result.publicHttp = r.status();
    result.publicHasExpectedContent = r.status() === 200 && html.includes(articleNeedle);
    result.publicHasNoindex = robots.noindex;
    result.publicHasNofollow = robots.nofollow;
    result.xEdgeSnapshot = r.headers()['x-edge-snapshot'] || null;
    save();
    if (result.publicHasExpectedContent && result.publicHasNoindex) return;
    await new Promise(r => setTimeout(r, 1800));
  }
  throw new Error(`public_verification_failed:http=${last?.status} expected=${result.publicHasExpectedContent} noindex=${result.publicHasNoindex}`);
}

const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await ctx.newPage();
try {
  save();
  await login(page);
  await detachFromSource(page);
  await attachToTarget(page);
  await verifyPublic(ctx);
  result.dnsChangeRequired = false;
  result.status = 'ok';
  result.detail = 'custom_domain_moved_to_target_app_and_public_fingerprint_verified';
  save();
} catch (e) {
  result.status = 'failed';
  result.detail = clean(e?.message || e);
  save();
  console.error(result.detail);
  process.exitCode = 1;
} finally {
  await browser.close().catch(() => {});
}
