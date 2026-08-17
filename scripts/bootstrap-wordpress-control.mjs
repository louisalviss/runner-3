import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const statusFile = `ops/site-factory/${slug}.json`;
if (!fs.existsSync(statusFile)) throw new Error(`site factory state missing: ${statusFile}`);
if (!fs.existsSync('/tmp/wasmer-account.json')) throw new Error('decrypted Wasmer account state missing');

const site = JSON.parse(fs.readFileSync(statusFile, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(site.siteUrl || '').replace(/\/$/, '');
const dashboard = site.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName)}`;
if (!base || !site.appName) throw new Error('site URL/app name missing from factory state');
if (!account.username || !account.password) throw new Error('Wasmer account credentials incomplete');

const out = '/tmp/wp-control-credential.json';
const safeOut = `/tmp/wp-control-${slug}.json`;
const safe = {
  status: 'starting', siteSlug: slug, appName: site.appName, siteUrl: base + '/',
  wordpressAdmin: false, applicationPasswordCreated: false, apiVerified: false,
  apiUserId: null, detail: null, updatedAt: new Date().toISOString()
};
function saveSafe() { safe.updatedAt = new Date().toISOString(); fs.writeFileSync(safeOut, JSON.stringify(safe, null, 2)); }
async function bodyText(page) { return (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ').trim(); }

async function loginWasmer(page) {
  await page.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(800);
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
  await page.waitForTimeout(4000);
  if (/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('wasmer_login_failed');
}

async function enterAdmin(ctx, page) {
  await page.goto(dashboard, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(1200);
  const admin = page.getByText(/WordPress Admin/i).first();
  if (!(await admin.count())) throw new Error('wordpress_admin_control_missing');
  const href = await admin.getAttribute('href').catch(() => null);
  if (href) {
    const wp = await ctx.newPage();
    await wp.goto(new URL(href, 'https://wasmer.io').href, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wp.waitForTimeout(2500);
    if (wp.url().startsWith(base) && /wp-admin/i.test(wp.url())) return wp;
    await wp.close().catch(() => {});
  }
  const before = new Set(ctx.pages());
  const popupPromise = ctx.waitForEvent('page', { timeout: 10000 }).catch(() => null);
  await admin.click().catch(() => {});
  const popup = await popupPromise;
  await page.waitForTimeout(3000);
  const candidates = [...ctx.pages().filter(p => !before.has(p)), popup, page].filter(Boolean);
  for (const p of candidates) if (p.url().startsWith(base) && /wp-admin/i.test(p.url())) return p;
  throw new Error('magic_admin_failed');
}

async function createApplicationPassword(wp) {
  const success = `${base}/?runner3-control=authorized`;
  const authUrl = new URL(`${base}/wp-admin/authorize-application.php`);
  authUrl.searchParams.set('app_name', 'Runner3 Runtime Control');
  authUrl.searchParams.set('success_url', success);
  await wp.goto(authUrl.href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(1000);
  const txt = await bodyText(wp);
  if (/application passwords.*not available|requires https|not currently compatible/i.test(txt)) throw new Error('application_passwords_unavailable');
  let approve = wp.locator('button,input[type=submit]').filter({ hasText: /approve|authorize|yes.*approve/i }).first();
  if (!(await approve.count())) approve = wp.locator('input[type=submit][name=approve],button[name=approve],#approve').first();
  if (!(await approve.count())) throw new Error('application_password_approve_control_missing');
  await approve.click();
  await wp.waitForTimeout(1800);
  const u = new URL(wp.url());
  const username = u.searchParams.get('user_login');
  const password = u.searchParams.get('password');
  if (!username || !password) throw new Error(`application_password_callback_missing:${u.pathname}`);
  return { username, password: password.replace(/\s+/g, ''), createdAt: new Date().toISOString() };
}

async function verifyApi(cred) {
  const auth = Buffer.from(`${cred.username}:${cred.password}`).toString('base64');
  const r = await fetch(`${base}/wp-json/wp/v2/users/me?context=edit`, { headers: { Authorization: `Basic ${auth}`, Accept: 'application/json' } });
  const text = await r.text();
  if (!r.ok) throw new Error(`rest_verify_failed:${r.status}:${text.slice(0,180)}`);
  const me = JSON.parse(text);
  return me;
}

const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await ctx.newPage();
try {
  saveSafe();
  await loginWasmer(page);
  const wp = await enterAdmin(ctx, page);
  safe.wordpressAdmin = true; saveSafe();
  const cred = await createApplicationPassword(wp);
  safe.applicationPasswordCreated = true; saveSafe();
  const me = await verifyApi(cred);
  safe.apiVerified = true;
  safe.apiUserId = me.id || null;
  safe.status = 'ready';
  saveSafe();
  fs.writeFileSync(out, JSON.stringify({ siteSlug: slug, siteUrl: base + '/', username: cred.username, applicationPassword: cred.password, createdAt: cred.createdAt }, null, 2), { mode: 0o600 });
  console.log(`WP_CONTROL_READY site=${slug} apiUserId=${safe.apiUserId ?? 'unknown'}`);
} catch (e) {
  safe.status = 'failed'; safe.detail = String(e?.message || e); saveSafe();
  console.error(`WP_CONTROL_BOOTSTRAP_FAILED ${safe.detail}`);
  process.exitCode = 1;
} finally {
  await browser.close().catch(() => {});
}
