import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const endpoint = String(process.env.RUNNER3_PURGE_ENDPOINT || 'https://wordpress-edge-proxy.ducduy2411.workers.dev/__runner3/cache/purge');
const stateFile = `ops/site-factory/${slug}.json`;
const outFile = process.env.RUNNER3_EDGE_WP_OUT || '/tmp/runner3-edge-cache-wordpress.json';

if (!endpoint.startsWith('https://')) throw new Error('RUNNER3_PURGE_ENDPOINT must use https');
if (!fs.existsSync(stateFile)) throw new Error(`site factory state missing: ${stateFile}`);
if (!fs.existsSync('/tmp/wasmer-account.json')) throw new Error('decrypted Wasmer account state missing');

const site = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(site.siteUrl || '').replace(/\/$/, '');
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
    await wp.waitForTimeout(1800);
    if (wp.url().startsWith(base) && /wp-admin/i.test(wp.url())) return wp;
    await wp.close().catch(() => {});
  }
  const popupP = ctx.waitForEvent('page', { timeout: 10000 }).catch(() => null);
  await admin.click();
  const popup = await popupP;
  await page.waitForTimeout(2200);
  for (const p of [popup, ...ctx.pages()].filter(Boolean)) {
    if (p.url().startsWith(base) && /wp-admin/i.test(p.url())) return p;
  }
  throw new Error('magic_admin_failed');
}

function safeWrite(data) {
  fs.writeFileSync(outFile, `${JSON.stringify(data, null, 2)}\n`);
}

const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await ctx.newPage();

try {
  await loginWasmer(page);
  const wp = await enterAdmin(ctx, page);
  const settingsUrl = `${base}/wp-admin/options-general.php?page=runner3-edge-cache`;
  await wp.goto(settingsUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(700);

  const enabled = wp.locator('input[name="runner3_edge_cache_purge[enabled]"]').first();
  const endpointInput = wp.locator('input[name="runner3_edge_cache_purge[endpoint]"]').first();
  if (!(await enabled.count()) || !(await endpointInput.count())) throw new Error('edge_cache_settings_controls_missing');

  if (!(await enabled.isChecked())) await enabled.check();
  await endpointInput.fill(endpoint);
  const save = wp.locator('input[type=submit][value*="Save" i],button[type=submit]').first();
  await save.click();
  await wp.waitForLoadState('domcontentloaded').catch(() => {});
  await wp.waitForTimeout(700);

  await wp.goto(settingsUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const savedEndpoint = await wp.locator('input[name="runner3_edge_cache_purge[endpoint]"]').first().inputValue();
  const savedEnabled = await wp.locator('input[name="runner3_edge_cache_purge[enabled]"]').first().isChecked();
  const signingRow = wp.locator('tr').filter({ has: wp.locator('th', { hasText: /^Signing key$/i }) }).first();
  const signingText = await signingRow.count() ? (await signingRow.locator('td').innerText()).trim() : '';
  const signingKeyReady = Boolean(signingText) && !/^UNAVAILABLE$/i.test(signingText) && /[0-9a-f]{8}/i.test(signingText);

  const diagnostics = {
    savedEndpointMatches: savedEndpoint === endpoint,
    savedEnabled,
    signingKeyReady,
    signingKeyRowFound: Boolean(await signingRow.count()),
    signingKeyMarker: signingText ? signingText.slice(0, 24) : null,
  };
  if (!diagnostics.savedEndpointMatches || !savedEnabled || !signingKeyReady) {
    safeWrite({ status: 'failed', siteSlug: slug, endpoint, detail: 'edge_cache_settings_not_persisted', diagnostics, updatedAt: new Date().toISOString() });
    console.log(JSON.stringify(diagnostics, null, 2));
    throw new Error('edge_cache_settings_not_persisted');
  }

  const manual = wp.locator('a').filter({ hasText: /Purge public HTML cache now/i }).first();
  if (!(await manual.count())) throw new Error('manual_purge_control_missing');
  const href = await manual.getAttribute('href');
  if (!href) throw new Error('manual_purge_href_missing');
  await wp.goto(new URL(href, `${base}/wp-admin/`).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(1000);
  const bodyText = await wp.locator('body').innerText();
  const manualPurgeOk = /Last result:\s*OK/i.test(bodyText) && /HTTP\s+2\d\d/i.test(bodyText);

  const result = {
    status: manualPurgeOk ? 'ok' : 'failed',
    siteSlug: slug,
    endpoint,
    enabled: savedEnabled,
    configured: true,
    signingKeyReady,
    manualPurgeOk,
    diagnostics,
    updatedAt: new Date().toISOString(),
  };
  safeWrite(result);
  console.log(JSON.stringify(result, null, 2));
  if (!manualPurgeOk) process.exitCode = 8;
} catch (error) {
  if (!fs.existsSync(outFile)) safeWrite({ status: 'failed', siteSlug: slug, endpoint, detail: String(error?.message || error), updatedAt: new Date().toISOString() });
  throw error;
} finally {
  await browser.close().catch(() => {});
}
