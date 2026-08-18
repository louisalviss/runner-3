import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const pluginSlug = process.env.WP_PLUGIN_SLUG || 'runner3-r2-media';
const expectedVersion = String(process.env.WP_PLUGIN_EXPECT_VERSION || '').trim();
const zipPath = process.env.WP_PLUGIN_ZIP || `/tmp/${pluginSlug}.zip`;
const stateFile = `ops/site-factory/${slug}.json`;
if (!fs.existsSync(stateFile)) throw new Error(`site factory state missing: ${stateFile}`);
if (!fs.existsSync('/tmp/wasmer-account.json')) throw new Error('decrypted Wasmer account state missing');
if (!fs.existsSync(zipPath)) throw new Error(`plugin zip missing: ${zipPath}`);

const site = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(site.siteUrl || '').replace(/\/$/, '');
const adminBase = `${base}/wp-admin/`;
const dashboard = site.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName)}`;
if (!base || !account.username || !account.password) throw new Error('site or Wasmer credentials incomplete');

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
  await page.waitForTimeout(3500);
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
  const wp = await popupP;
  await page.waitForTimeout(2500);
  for (const p of [wp, ...ctx.pages()].filter(Boolean)) {
    if (p.url().startsWith(base) && /wp-admin/i.test(p.url())) return p;
  }
  throw new Error('magic_admin_failed');
}

async function installPlugin(wp) {
  await wp.goto(`${base}/wp-admin/plugin-install.php?tab=upload`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(800);
  const uploadToggle = wp.getByRole('button', { name: /upload plugin/i }).first();
  if (await uploadToggle.count() && await uploadToggle.isVisible().catch(() => false)) await uploadToggle.click();
  const file = wp.locator('input[type=file]').first();
  await file.waitFor({ state: 'attached', timeout: 10000 });
  await file.setInputFiles(zipPath);
  const installByValue = wp.locator('input[type=submit][value*="Install" i]').first();
  const install = await installByValue.count() ? installByValue : wp.getByRole('button', { name: /install now/i }).first();
  await install.click();
  await wp.waitForLoadState('domcontentloaded').catch(() => {});
  await wp.waitForTimeout(1800);

  const replace = wp.locator('a').filter({ hasText: /replace (current|installed).*uploaded/i }).first();
  if (await replace.count()) {
    const href = await replace.getAttribute('href');
    if (!href) throw new Error('plugin_replace_href_missing');
    await wp.goto(new URL(href, adminBase).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wp.waitForTimeout(1800);
    const replaceError = await wp.locator('.notice-error,.error').first().innerText().catch(() => '');
    if (replaceError && /failed|error|could not/i.test(replaceError)) throw new Error(`plugin_replace_failed:${replaceError.slice(0,160)}`);
  }

  await wp.goto(`${base}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(700);
  let row = wp.locator(`tr[data-slug="${pluginSlug}"]`).first();
  if (!(await row.count())) throw new Error('plugin_row_missing_after_upload');
  let cls = await row.getAttribute('class') || '';
  if (!/\bactive\b/.test(cls)) {
    const activate = row.locator('a').filter({ hasText: /^activate$/i }).first();
    if (!(await activate.count())) throw new Error('plugin_activate_link_missing');
    const href = await activate.getAttribute('href');
    if (!href) throw new Error('plugin_activate_href_missing');
    await wp.goto(new URL(href, adminBase).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wp.waitForTimeout(900);
    await wp.goto(`${base}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    row = wp.locator(`tr[data-slug="${pluginSlug}"]`).first();
    cls = await row.getAttribute('class') || '';
  }
  if (!/\bactive\b/.test(cls)) throw new Error('plugin_not_active');
  if (expectedVersion) {
    const text = await row.innerText();
    const escaped = expectedVersion.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (!new RegExp(`Version\\s+${escaped}(?:\\s|$)`, 'i').test(text)) {
      throw new Error(`plugin_version_mismatch_expected_${expectedVersion}`);
    }
  }
}

const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await ctx.newPage();
try {
  await loginWasmer(page);
  const wp = await enterAdmin(ctx, page);
  await installPlugin(wp);
  console.log(`WP_PLUGIN_DEPLOY_OK slug=${pluginSlug}${expectedVersion ? ` version=${expectedVersion}` : ''}`);
} finally {
  await browser.close().catch(() => {});
}
