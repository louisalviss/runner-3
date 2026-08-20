import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const zip = process.env.RUNNER3_PLUGIN_ZIP || '/tmp/runner3-edge-optimizer.zip';
const endpoint = String(process.env.RUNNER3_CONTROL_ENDPOINT || '');
const secret = String(process.env.RUNNER3_AUTOMATION_SECRET || '');
const stateFile = `ops/site-factory/${slug}.json`;
const outFile = '/tmp/runner3-edge-optimizer-install.json';
const safe = { status: 'starting', siteSlug: slug, installed: false, active: false, configured: false, testEvent: false, detail: null, updatedAt: new Date().toISOString() };
const save = () => { safe.updatedAt = new Date().toISOString(); fs.writeFileSync(outFile, JSON.stringify(safe, null, 2) + '\n'); };

if (!fs.existsSync(stateFile)) throw new Error(`site state missing: ${stateFile}`);
if (!fs.existsSync('/tmp/wasmer-account.json')) throw new Error('Wasmer account state missing');
if (!fs.existsSync(zip)) throw new Error(`plugin zip missing: ${zip}`);
if (!endpoint.startsWith('https://')) throw new Error('control endpoint invalid');
if (secret.length < 32) throw new Error('automation secret too short');

const site = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(site.siteUrl || '').replace(/\/$/, '');
const dashboard = site.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName)}`;

async function loginWasmer(page) {
  await page.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
  const ident = page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  await ident.waitFor({ state: 'visible', timeout: 15000 });
  await ident.fill(account.username || account.email);
  const next = page.locator('button').filter({ hasText: /continue|next|log in|sign in/i }).first();
  if (await next.count() && await next.isVisible().catch(() => false)) await next.click(); else await ident.press('Enter');
  const pass = page.locator('input[type=password]').first();
  await pass.waitFor({ state: 'visible', timeout: 15000 });
  await pass.fill(account.password);
  const submit = page.locator('input[type=submit],button').filter({ hasText: /log in|sign in|continue/i }).first();
  if (await submit.count() && await submit.isVisible().catch(() => false)) await submit.click(); else await pass.press('Enter');
  await page.waitForTimeout(3000);
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
    await wp.waitForTimeout(2200);
    if (wp.url().startsWith(base) && /wp-admin/i.test(wp.url())) return wp;
    await wp.close().catch(() => {});
  }
  const popupP = ctx.waitForEvent('page', { timeout: 10000 }).catch(() => null);
  await admin.click();
  const popup = await popupP;
  await page.waitForTimeout(2500);
  for (const p of [popup, ...ctx.pages()].filter(Boolean)) if (p.url().startsWith(base) && /wp-admin/i.test(p.url())) return p;
  throw new Error('magic_admin_failed');
}

async function pluginRow(wp) {
  await wp.goto(`${base}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  return wp.locator('tr[data-slug="runner3-edge-optimizer"]').first();
}

async function ensureInstalled(wp) {
  let row = await pluginRow(wp);
  if (await row.count()) return;
  await wp.goto(`${base}/wp-admin/plugin-install.php?tab=upload`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const input = wp.locator('input[type=file][name=pluginzip],input[type=file]').first();
  await input.waitFor({ state: 'attached', timeout: 15000 });
  await input.setInputFiles(zip);
  const install = wp.locator('#install-plugin-submit,input[type=submit],button').filter({ hasText: /install now|install/i }).first();
  await install.click();
  await wp.waitForLoadState('domcontentloaded').catch(() => {});
  await wp.waitForTimeout(1800);
  const replace = wp.locator('a,button,input[type=submit]').filter({ hasText: /replace current with uploaded|replace current|overwrite/i }).first();
  if (await replace.count() && await replace.isVisible().catch(() => false)) {
    await replace.click(); await wp.waitForLoadState('domcontentloaded').catch(() => {}); await wp.waitForTimeout(1600);
  }
  row = await pluginRow(wp);
  if (!(await row.count())) throw new Error('plugin_install_not_visible');
}

async function ensureActive(wp) {
  const row = await pluginRow(wp);
  if (!(await row.count())) throw new Error('plugin_row_missing');
  const classes = await row.getAttribute('class') || '';
  if (/\bactive\b/.test(classes)) return;
  const activate = row.locator('a').filter({ hasText: /^Activate$/i }).first();
  if (!(await activate.count())) throw new Error('plugin_activate_control_missing');
  const href = await activate.getAttribute('href');
  if (!href) throw new Error('plugin_activate_href_missing');
  await wp.goto(new URL(href, `${base}/wp-admin/`).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(1000);
  const row2 = await pluginRow(wp); const cls2 = await row2.getAttribute('class') || '';
  if (!/\bactive\b/.test(cls2)) throw new Error('plugin_not_active_after_activation');
}

async function configureAndTest(wp) {
  const settings = `${base}/wp-admin/options-general.php?page=runner3-edge-optimizer`;
  await wp.goto(settings, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const endpointInput = wp.locator('#runner3-edge-endpoint').first();
  const secretInput = wp.locator('#runner3-edge-secret').first();
  await endpointInput.waitFor({ state: 'visible', timeout: 12000 });
  await endpointInput.fill(endpoint); await secretInput.fill(secret);
  const saveButton = wp.locator('input[type=submit],button').filter({ hasText: /save settings/i }).first();
  await saveButton.click(); await wp.waitForLoadState('domcontentloaded').catch(() => {}); await wp.waitForTimeout(700);
  await wp.goto(settings, { waitUntil: 'domcontentloaded', timeout: 60000 });
  if ((await wp.locator('#runner3-edge-endpoint').inputValue()) !== endpoint) throw new Error('endpoint_not_persisted');
  const placeholder = await wp.locator('#runner3-edge-secret').getAttribute('placeholder');
  if (!/Configured/i.test(placeholder || '')) throw new Error('secret_not_persisted');
  const test = wp.locator('input[type=submit],button').filter({ hasText: /send test event/i }).first();
  const href = await test.getAttribute('formaction').catch(() => null);
  if (href) await wp.goto(new URL(href, `${base}/wp-admin/`).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  else { await test.click(); await wp.waitForLoadState('domcontentloaded').catch(() => {}); }
  await wp.waitForTimeout(900);
  const body = await wp.locator('body').innerText().catch(() => '');
  if (!/Connection test:\s*ok/i.test(body)) throw new Error('plugin_test_event_failed');
}

const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await ctx.newPage();
try {
  save();
  await loginWasmer(page);
  const wp = await enterAdmin(ctx, page);
  await ensureInstalled(wp); safe.installed = true; save();
  await ensureActive(wp); safe.active = true; save();
  await configureAndTest(wp); safe.configured = true; safe.testEvent = true; safe.status = 'ready'; save();
  console.log(JSON.stringify(safe, null, 2));
} catch (error) {
  safe.status = 'failed'; safe.detail = String(error?.message || error); save(); console.error(JSON.stringify(safe, null, 2)); process.exitCode = 1;
} finally { await browser.close().catch(() => {}); }
