import { chromium } from 'playwright-core';
import fs from 'fs';
import crypto from 'crypto';

const requestPath = process.env.SITE_FACTORY_REQUEST || 'ops/site-factory/request.json';
const wasmerAccount = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const pntrAuth = JSON.parse(fs.readFileSync('/tmp/pntr-account.json', 'utf8'));
const request = JSON.parse(fs.readFileSync(requestPath, 'utf8'));
const inventory = fs.existsSync('ops/site-factory/sites.json')
  ? JSON.parse(fs.readFileSync('ops/site-factory/sites.json', 'utf8'))
  : [];

const out = {
  requestId: request.requestId || null,
  status: 'starting',
  success: false,
  subdomain: null,
  domain: null,
  appName: null,
  wasmerUrl: null,
  cnameTarget: null,
  wordpressReady: false,
  pntrSubdomainsBefore: null,
  wasmerAppsBefore: null,
  httpsStatus: null,
  detail: null,
  updatedAt: new Date().toISOString(),
};

const secret = {
  requestId: request.requestId || null,
  domain: null,
  appName: null,
  wasmerUrl: null,
  wordpress: null,
  createdAt: new Date().toISOString(),
};

function save() {
  out.updatedAt = new Date().toISOString();
  fs.writeFileSync('/tmp/site-factory-status.json', JSON.stringify(out, null, 2));
  fs.writeFileSync('/tmp/site-factory-secret.json', JSON.stringify(secret, null, 2), { mode: 0o600 });
}

function slug(value, fallbackPrefix = 'r3wp') {
  let s = String(value || '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
  if (!s) s = `${fallbackPrefix}-${crypto.randomBytes(3).toString('hex')}`;
  s = s.slice(0, 63).replace(/-$/g, '');
  if (!s) s = `${fallbackPrefix}-${crypto.randomBytes(3).toString('hex')}`;
  return s;
}

function safeError(e) {
  return String(e || '')
    .replace(/[A-Za-z0-9_-]{28,}/g, '[REDACTED]')
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig, 'EMAIL_REDACTED')
    .slice(0, 900);
}

async function pntr(path, options = {}) {
  if (!pntrAuth.access_token) throw new Error('PNTR account token missing');
  const r = await fetch(`https://api.pntr.dev${path}`, {
    ...options,
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      Authorization: `Bearer ${pntrAuth.access_token}`,
      ...(options.headers || {}),
    },
  });
  const text = await r.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!r.ok) throw new Error(`PNTR ${options.method || 'GET'} ${path} -> ${r.status} ${typeof data === 'string' ? data.slice(0, 180) : JSON.stringify(data).slice(0, 180)}`);
  return data;
}

async function choosePntrName() {
  if (pntrAuth.expires_at && Date.parse(pntrAuth.expires_at) <= Date.now() + 60_000) {
    throw new Error('PNTR account token expired');
  }
  const subs = await pntr('/api/subdomains');
  const list = Array.isArray(subs) ? subs : [];
  out.pntrSubdomainsBefore = list.length;

  const base = slug(request.subdomain || request.name || request.siteTitle || '');
  const managed = inventory.find((x) => x?.subdomain === base || x?.domain === `${base}.pntr.dev`);
  if (managed) {
    out.status = 'already_managed';
    out.success = true;
    out.subdomain = managed.subdomain;
    out.domain = managed.domain;
    out.appName = managed.appName || null;
    out.wasmerUrl = managed.wasmerUrl || null;
    out.cnameTarget = managed.cnameTarget || null;
    out.httpsStatus = managed.httpsStatus || 200;
    out.detail = 'Existing managed site returned without creating a duplicate';
    save();
    return { done: true };
  }

  if (list.length >= 3) throw new Error(`PNTR free quota reached (${list.length}/3)`);

  const domains = await pntr('/api/domains');
  const domainList = Array.isArray(domains) ? domains : [];
  const activeDomain = domainList.find((d) => d?.is_active) || domainList[0];
  if (!activeDomain?.id) throw new Error('PNTR domain_id unavailable');

  const occupied = new Set(list.map((s) => s?.name).filter(Boolean));
  const candidates = [base];
  if (!request.strictName) {
    for (let i = 2; i <= 5; i++) candidates.push(slug(`${base}-${i}`));
    candidates.push(slug(`${base}-${crypto.randomBytes(2).toString('hex')}`));
  }

  for (const name of candidates) {
    if (occupied.has(name)) continue;
    const check = await pntr(`/api/check/${encodeURIComponent(activeDomain.id)}/${encodeURIComponent(name)}`).catch(() => null);
    if (check?.available) return { done: false, name, domainId: activeDomain.id };
  }
  throw new Error(`No available PNTR name found for base ${base}`);
}

async function bodyText(page) {
  return (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ').trim();
}

async function firstVisible(locator) {
  const n = await locator.count();
  for (let i = 0; i < n; i++) {
    const el = locator.nth(i);
    if (await el.isVisible().catch(() => false)) return el;
  }
  return null;
}

async function loginWasmer(page) {
  await page.goto('https://wasmer.io/apps', { waitUntil: 'domcontentloaded', timeout: 60_000 }).catch(() => null);
  await page.waitForTimeout(900);
  if (!/\/login(?:[/?#]|$)/i.test(page.url())) return true;

  await page.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  const ident = page.locator('input[name=username],input[name=email],input[type=email],input[placeholder*=Username i],input[type=text]').first();
  await ident.waitFor({ state: 'visible', timeout: 15_000 }).catch(() => {});
  if (!(await ident.count())) return false;
  await ident.fill(wasmerAccount.email || wasmerAccount.username);
  const c1 = page.locator('button').filter({ hasText: /continue|next|log in|sign in/i }).first();
  if (await c1.count()) await c1.click(); else await ident.press('Enter');
  await page.waitForTimeout(500);

  const pass = page.locator('input[type=password]').first();
  const hasPass = await pass.waitFor({ state: 'visible', timeout: 15_000 }).then(() => true).catch(() => false);
  if (!hasPass) return !/\/login(?:[/?#]|$)/i.test(page.url());
  await pass.fill(wasmerAccount.password);
  const c2 = page.locator('button').filter({ hasText: /log in|sign in|continue/i }).first();
  if (await c2.count()) await c2.click(); else await pass.press('Enter');
  await page.waitForTimeout(2_500);
  return !/\/login(?:[/?#]|$)/i.test(page.url());
}

async function countWasmerApps(page) {
  await page.goto('https://wasmer.io/apps', { waitUntil: 'domcontentloaded', timeout: 60_000 }).catch(() => null);
  await page.waitForTimeout(1_000);
  const owner = String(wasmerAccount.username || '').toLowerCase();
  const links = await page.locator('a[href*="/apps/"]').evaluateAll((as) => as.map((a) => a.href)).catch(() => []);
  const names = new Set();
  for (const href of links) {
    try {
      const u = new URL(href);
      const parts = u.pathname.split('/').filter(Boolean);
      if (parts[0] !== 'apps' || parts.length < 3) continue;
      if (owner && parts[1].toLowerCase() !== owner) continue;
      if (['create', 'templates'].includes(parts[2])) continue;
      names.add(parts[2]);
    } catch {}
  }
  return names.size;
}

async function chooseDefaults(page) {
  const selects = page.locator('select');
  for (let i = 0; i < await selects.count(); i++) {
    const s = selects.nth(i);
    const opts = await s.locator('option').evaluateAll((os) => os.map((o) => ({ v: o.value, t: o.textContent?.trim() || '', d: o.disabled }))).catch(() => []);
    const pick = opts.find((o) => !o.d && o.v && !/select|choose/i.test(o.t));
    if (pick) await s.selectOption(pick.v).catch(() => {});
  }
  const combos = page.getByRole('combobox');
  for (let i = 0; i < Math.min(await combos.count(), 5); i++) {
    const c = combos.nth(i);
    if (!(await c.isVisible().catch(() => false))) continue;
    await c.click().catch(() => {});
    await page.waitForTimeout(200);
    const opts = page.getByRole('option');
    for (let j = 0; j < Math.min(await opts.count(), 12); j++) {
      const o = opts.nth(j);
      if (await o.isVisible().catch(() => false)) { await o.click().catch(() => {}); break; }
    }
  }
}

async function createWasmerApp(page, appName) {
  await page.goto('https://wasmer.io/apps/create?template=wordpress-starter', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.waitForTimeout(1_500);
  if (/\/login(?:[/?#]|$)/i.test(page.url())) {
    if (!(await loginWasmer(page))) throw new Error('Wasmer login failed before app create');
    await page.goto('https://wasmer.io/apps/create?template=wordpress-starter', { waitUntil: 'domcontentloaded', timeout: 60_000 });
    await page.waitForTimeout(1_500);
  }

  const text = await bodyText(page);
  if (/credit card|payment method|billing information/i.test(text)) throw new Error('Wasmer requested payment method');
  if (/captcha|verify you are human|security verification/i.test(text)) throw new Error('Wasmer blocked app creation with verification');

  const named = page.locator('input[name*=name i],input[placeholder*=name i]').first();
  if (await named.count()) await named.fill(appName);
  else {
    const inputs = page.locator('input:not([type=hidden]):not([type=password]):not([type=email])');
    if (await inputs.count()) await inputs.first().fill(appName).catch(() => {});
  }
  await chooseDefaults(page);

  const deploy = page.getByRole('button', { name: /deploy now|deploy/i }).first();
  if (!(await deploy.count())) throw new Error(`Wasmer deploy button missing: ${(await bodyText(page)).slice(0, 300)}`);
  await deploy.click();

  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(2_000);
    const t = await bodyText(page);
    if (/quota|limit reached|maximum.*apps/i.test(t)) throw new Error('Wasmer app quota reached');
    if (/credit card|payment method|billing information/i.test(t)) throw new Error('Wasmer requested payment after deploy');
    const links = await page.locator('a[href*=".wasmer.app"]').evaluateAll((as) => as.map((a) => a.href)).catch(() => []);
    const direct = links.find((x) => /\.wasmer\.app\/?$/i.test(x));
    if (direct) return direct.endsWith('/') ? direct : `${direct}/`;
    const m = t.match(/https:\/\/[^\s]+\.wasmer\.app\/?/i);
    if (m) return m[0].endsWith('/') ? m[0] : `${m[0]}/`;
  }
  throw new Error('Wasmer deployment did not expose a site URL');
}

async function installWordPress(browser, siteUrl) {
  const base = siteUrl.replace(/\/$/, '');
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  const wp = {
    adminUser: `r3admin${crypto.randomBytes(3).toString('hex')}`,
    adminPassword: crypto.randomBytes(30).toString('base64url'),
    adminEmail: request.adminEmail || wasmerAccount.email,
    siteTitle: request.siteTitle || request.name || out.subdomain || 'Runner3 Site',
  };
  try {
    await page.goto(`${base}/`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
    await page.waitForTimeout(1_000);
    let text = await bodyText(page);
    const installLike = /wp-admin\/install\.php/i.test(page.url()) || /information needed|five-minute wordpress installation|install wordpress/i.test(text);
    if (installLike) {
      const title = page.locator('input[name=weblog_title],input#weblog_title').first();
      const user = page.locator('input[name=user_name],input#user_login').first();
      const pass = page.locator('input[name=admin_password],input#pass1,input[type=password]').first();
      const email = page.locator('input[name=admin_email],input[type=email]').first();
      await title.waitFor({ state: 'visible', timeout: 15_000 }).catch(() => {});
      if (await title.count()) await title.fill(wp.siteTitle);
      if (await user.count()) await user.fill(wp.adminUser);
      if (await pass.count()) await pass.fill(wp.adminPassword);
      if (await email.count()) await email.fill(wp.adminEmail || 'admin@example.com');
      const weak = page.locator('input[name=pw_weak]').first();
      if (await weak.count() && !(await weak.isChecked().catch(() => false))) await weak.check().catch(() => {});
      const submit = page.locator('input[type=submit],button').filter({ hasText: /install wordpress/i }).first();
      if (await submit.count()) await submit.click(); else await page.locator('input[type=submit]').first().click();
      await page.waitForTimeout(3_000);
      text = await bodyText(page);
      if (!/success|wordpress has been installed|log in/i.test(text) && !/wp-login\.php/i.test(page.url())) {
        throw new Error(`WordPress install unconfirmed: ${text.slice(0, 260)}`);
      }
    } else if (/wp-login|wp-admin|wordpress/i.test(text)) {
      wp.adminUser = null;
      wp.adminPassword = null;
    }
    return wp;
  } finally {
    await ctx.close();
  }
}

async function attachWasmerDomain(page, appName, targetDomain, siteUrl) {
  const owner = wasmerAccount.username;
  const settingsUrl = `https://wasmer.io/apps/${encodeURIComponent(owner)}/${encodeURIComponent(appName)}/settings/domains`;
  await page.goto(settingsUrl, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.waitForTimeout(1_200);
  if (/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('Wasmer session expired before domain attachment');
  let t = await bodyText(page);

  if (!t.toLowerCase().includes(targetDomain.toLowerCase())) {
    let add = await firstVisible(page.locator('button').filter({ hasText: /^\s*Add\s*$/i }));
    if (!add) add = await firstVisible(page.locator('button').filter({ hasText: /Add Domain/i }));
    if (!add) throw new Error(`Wasmer Add Domain control missing: ${t.slice(0, 300)}`);
    await add.click();
    await page.waitForTimeout(500);
    const input = await firstVisible(page.locator('input[type=text],input[name*=domain i],input[placeholder*=domain i],input[type=url]'));
    if (!input) throw new Error('Wasmer domain input missing');
    await input.fill(targetDomain);
    const dialog = page.locator('[role=dialog]').last();
    let submit = null;
    if (await dialog.count() && await dialog.isVisible().catch(() => false)) {
      submit = await firstVisible(dialog.locator('button').filter({ hasText: /^\s*(Add|Save|Continue)\s*$/i }));
    }
    if (!submit) {
      const all = page.locator('button').filter({ hasText: /^\s*(Add|Save|Continue)\s*$/i });
      for (let i = (await all.count()) - 1; i >= 0; i--) {
        const el = all.nth(i);
        if (await el.isVisible().catch(() => false)) { submit = el; break; }
      }
    }
    if (!submit) throw new Error('Wasmer domain submit control missing');
    await submit.click();
    await page.waitForTimeout(3_000);
    t = await bodyText(page);
  }

  if (!t.toLowerCase().includes(targetDomain.toLowerCase())) throw new Error('Wasmer did not confirm custom domain was added');
  const idx = t.toLowerCase().indexOf(targetDomain.toLowerCase());
  const nearby = idx >= 0 ? t.slice(Math.max(0, idx - 180), idx + 1_000) : t;
  const vals = await page.locator('input,code,pre').evaluateAll((xs) => xs.map((x) => ('value' in x && x.value ? x.value : x.textContent || '').trim()).filter(Boolean)).catch(() => []);
  const all = [nearby, ...vals].join('\n');
  const hosts = [...all.matchAll(/(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:wasmer\.app|edge\.wasmer\.io|wasmer\.io)/ig)].map((m) => m[0].toLowerCase());
  const siteHost = new URL(siteUrl).hostname.toLowerCase();
  const unique = [...new Set(hosts)].filter((h) => h !== targetDomain.toLowerCase());
  return unique.find((h) => /\.id\.wasmer\.app$/i.test(h))
    || unique.find((h) => h !== siteHost && /\.wasmer\.app$/i.test(h))
    || unique.find((h) => /\.wasmer\.app$/i.test(h))
    || siteHost;
}

async function createPntrSubdomain(name, domainId, cnameTarget) {
  let created = null;
  try {
    created = await pntr('/api/subdomains', {
      method: 'POST',
      body: JSON.stringify({
        name,
        domain_id: domainId,
        description: `Runner3 site factory -> ${out.appName}`,
      }),
    });
    if (!created?.id) throw new Error('PNTR create response missing id');
    await pntr(`/api/subdomains/${encodeURIComponent(created.id)}/records`, {
      method: 'POST',
      body: JSON.stringify({ record_type: 'CNAME', record_value: cnameTarget }),
    });
    return created;
  } catch (e) {
    if (created?.id) {
      await pntr(`/api/subdomains/${encodeURIComponent(created.id)}`, { method: 'DELETE' }).catch(() => null);
    }
    throw e;
  }
}

async function verifyHttps(domain) {
  for (let i = 0; i < 12; i++) {
    await new Promise((r) => setTimeout(r, i === 0 ? 2_000 : 5_000));
    try {
      const r = await fetch(`https://${domain}/`, { redirect: 'follow', signal: AbortSignal.timeout(20_000) });
      out.httpsStatus = r.status;
      if (r.status >= 200 && r.status < 500) return true;
    } catch {}
  }
  return false;
}

async function main() {
  save();
  const choice = await choosePntrName();
  if (choice.done) return;

  out.subdomain = choice.name;
  out.domain = `${choice.name}.pntr.dev`;
  out.appName = slug(request.appName || `r3-${choice.name}`, 'r3app').slice(0, 55);
  secret.domain = out.domain;
  secret.appName = out.appName;
  save();

  const storageState = fs.existsSync('/tmp/wasmer-browser-state.json') ? '/tmp/wasmer-browser-state.json' : undefined;
  const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const ctx = await browser.newContext(storageState ? { storageState } : {});
  const page = await ctx.newPage();
  try {
    if (!(await loginWasmer(page))) throw new Error('Could not authenticate existing Wasmer account');
    out.wasmerAppsBefore = await countWasmerApps(page);
    const siteUrl = await createWasmerApp(page, out.appName);
    out.wasmerUrl = siteUrl;
    secret.wasmerUrl = siteUrl;
    save();

    secret.wordpress = await installWordPress(browser, siteUrl);
    out.wordpressReady = true;
    save();

    const cnameTarget = await attachWasmerDomain(page, out.appName, out.domain, siteUrl);
    out.cnameTarget = cnameTarget;
    save();

    await createPntrSubdomain(out.subdomain, choice.domainId, cnameTarget);
    const live = await verifyHttps(out.domain);

    await ctx.storageState({ path: '/tmp/wasmer-browser-state-new.json' }).catch(() => null);
    out.status = live ? 'ready' : 'ready_dns_pending';
    out.success = true;
    out.detail = live ? null : 'Resources created; custom-domain HTTPS has not converged yet';
    save();
  } finally {
    await ctx.close().catch(() => null);
    await browser.close().catch(() => null);
  }
}

try {
  await main();
} catch (e) {
  out.status = 'error';
  out.success = false;
  out.detail = safeError(e);
  save();
}
