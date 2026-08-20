import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const zip = process.env.RUNNER3_PLUGIN_ZIP || '/tmp/runner3-speed.zip';
const mode = process.env.RUNNER3_PROBE_MODE || 'full';
const stateFile = `ops/site-factory/${slug}.json`;
const outFile = '/tmp/runner3-speed-probe.json';
const result = { status: 'starting', mode, siteSlug: slug, installed: false, active: false, on: false, hit: false, queryBypass: false, apiBypass: false, adminBypass: false, off: false, productionUnchanged: false, detail: null, updatedAt: new Date().toISOString() };
const save = () => { result.updatedAt = new Date().toISOString(); fs.writeFileSync(outFile, JSON.stringify(result, null, 2) + '\n'); };

if (!fs.existsSync(stateFile)) throw new Error(`site state missing: ${stateFile}`);
if (!fs.existsSync('/tmp/wasmer-account.json')) throw new Error('Wasmer account state missing');
if (mode !== 'off' && !fs.existsSync(zip)) throw new Error(`plugin zip missing: ${zip}`);
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
  await page.waitForTimeout(2500);
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
  for (const p of [popup, ...ctx.pages()].filter(Boolean)) if (p.url().startsWith(base) && /wp-admin/i.test(p.url())) return p;
  throw new Error('magic_admin_failed');
}

async function pluginRow(wp) {
  await wp.goto(`${base}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  return wp.locator('tr[data-slug="runner3-edge-optimizer"]').first();
}

async function installOrReplace(wp) {
  await wp.goto(`${base}/wp-admin/plugin-install.php?tab=upload`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const input = wp.locator('input[type=file][name=pluginzip],input[type=file]').first();
  await input.waitFor({ state: 'attached', timeout: 15000 });
  await input.setInputFiles(zip);
  const install = wp.locator('#install-plugin-submit,input[type=submit],button').filter({ hasText: /install now|install/i }).first();
  await install.click();
  await wp.waitForLoadState('domcontentloaded').catch(() => {});
  await wp.waitForTimeout(1500);
  const replace = wp.locator('a,button,input[type=submit]').filter({ hasText: /replace current with uploaded|replace current|overwrite/i }).first();
  if (await replace.count() && await replace.isVisible().catch(() => false)) {
    const href = await replace.getAttribute('href').catch(() => null);
    if (href) await wp.goto(new URL(href, `${base}/wp-admin/`).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
    else await replace.click({ force: true });
    await wp.waitForLoadState('domcontentloaded').catch(() => {});
    await wp.waitForTimeout(1500);
  }
  const row = await pluginRow(wp);
  if (!(await row.count())) throw new Error('plugin_install_not_visible');
  result.installed = true; save();
}

async function ensureActive(wp) {
  let row = await pluginRow(wp);
  const classes = await row.getAttribute('class') || '';
  if (!/\bactive\b/.test(classes)) {
    const activate = row.locator('a').filter({ hasText: /^Activate$/i }).first();
    if (!(await activate.count())) throw new Error('plugin_activate_control_missing');
    const href = await activate.getAttribute('href');
    if (!href) throw new Error('plugin_activate_href_missing');
    await wp.goto(new URL(href, `${base}/wp-admin/`).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wp.waitForTimeout(900);
    row = await pluginRow(wp);
  }
  const cls2 = await row.getAttribute('class') || '';
  if (!/\bactive\b/.test(cls2)) throw new Error('plugin_not_active');
  result.active = true; save();
}

async function speedPage(wp) {
  await wp.goto(`${base}/wp-admin/options-general.php?page=runner3-speed`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.locator('body').waitFor({ state: 'visible', timeout: 10000 });
  const text = await wp.locator('body').innerText();
  if (!/Runner3 Speed/i.test(text)) throw new Error('runner3_speed_settings_missing');
  return text;
}

async function setEnabled(wp, wantOn) {
  const text = await speedPage(wp);
  const isOn = /Performance\s*ON/i.test(text);
  if (isOn === wantOn) return;
  const form = wp.locator('form').filter({ has: wp.locator('input[name="action"][value="runner3_speed_toggle"]') }).first();
  if (!(await form.count())) throw new Error('toggle_form_missing');
  const value = await form.locator('input[name="enable"]').inputValue();
  if ((value === '1') !== wantOn) throw new Error('toggle_form_state_mismatch');
  await Promise.all([
    wp.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => null),
    form.evaluate((el) => HTMLFormElement.prototype.submit.call(el)),
  ]);
  await wp.waitForTimeout(900);
  const after = await wp.locator('body').innerText().catch(() => '');
  if (wantOn && !/Performance\s*ON/i.test(after)) throw new Error(`turn_on_failed: ${after.slice(0,300)}`);
  if (!wantOn && !/Performance\s*OFF/i.test(after)) throw new Error(`turn_off_failed: ${after.slice(0,300)}`);
}

async function fetchCheck(url, options={}) {
  const r = await fetch(url, { redirect: 'follow', ...options });
  const body = await r.text();
  return { status: r.status, speed: r.headers.get('x-runner3-speed'), body };
}

async function verifyOn(wp) {
  const first = await fetchCheck(`${base}/`);
  const second = await fetchCheck(`${base}/`);
  if (first.status !== 200 || second.status !== 200 || second.body.length < 512) throw new Error('homepage_failed_while_on');
  if (second.speed !== 'HIT') throw new Error(`cache_hit_missing:${second.speed || 'none'}`);
  result.hit = true; save();
  const query = await fetchCheck(`${base}/?runner3_probe=${Date.now()}`);
  if (query.status !== 200 || query.speed === 'HIT') throw new Error('query_bypass_failed');
  result.queryBypass = true; save();
  const api = await fetchCheck(`${base}/wp-json/`);
  if (api.status !== 200 || api.speed === 'HIT') throw new Error('api_bypass_failed');
  result.apiBypass = true; save();
  await wp.goto(`${base}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  if (!/wp-admin\/plugins\.php/.test(wp.url())) throw new Error('admin_bypass_failed');
  result.adminBypass = true; save();
}

async function verifyOff() {
  const r = await fetchCheck(`${base}/`);
  if (r.status !== 200 || r.body.length < 512 || r.speed === 'HIT') throw new Error('off_bypass_failed');
  result.off = true; save();
}

async function verifyProduction() {
  const r = await fetch(`https://runner3wp.pntr.dev/?__runner3_speed_probe=${Date.now()}`, { redirect: 'follow' });
  const html = await r.text();
  const snap = (r.headers.get('x-edge-snapshot') || '').toUpperCase();
  const policy = (r.headers.get('x-edge-cache-policy') || '').toLowerCase();
  if (!r.ok || snap !== 'HIT' || policy !== 'snapshot-direct' || !/__runner3\/r2-image\/offset-demo-01-w(?:360|480|640)\.webp/.test(html)) throw new Error('production_v2_changed');
  result.productionUnchanged = true; save();
}

const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await ctx.newPage();
let wp;
try {
  save();
  await loginWasmer(page);
  wp = await enterAdmin(ctx, page);
  if (mode !== 'off') {
    await installOrReplace(wp);
    await ensureActive(wp);
    await setEnabled(wp, true); result.on = true; save();
    await verifyOn(wp);
    await setEnabled(wp, false); result.on = false; result.off = true; save();
    await verifyOff();
    await verifyProduction();
    result.status = 'ready'; result.detail = 'ON/HIT/bypass/OFF/production guards passed'; save();
  } else {
    await ensureActive(wp).catch(() => {});
    await setEnabled(wp, false).catch(() => {});
    await verifyOff();
    result.status = 'cleanup_ready'; result.detail = 'Runner3 Speed forced OFF'; save();
  }
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  result.status = 'failed'; result.detail = String(error?.message || error); save(); console.error(JSON.stringify(result, null, 2)); process.exitCode = 1;
} finally {
  if (mode !== 'off' && wp) await setEnabled(wp, false).catch(() => {});
  await browser.close().catch(() => {});
}
