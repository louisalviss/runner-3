import { chromium } from 'playwright-core';
import fs from 'fs';

const requestPath = process.env.SITE_FACTORY_REQUEST;
if (!requestPath || !fs.existsSync(requestPath)) throw new Error('SITE_FACTORY_REQUEST missing or not found');
const cfg = JSON.parse(fs.readFileSync(requestPath, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));

const required = ['site_name', 'site_slug', 'app_name', 'domain_mode', 'fingerprint'];
for (const k of required) if (!cfg[k]) throw new Error(`request missing ${k}`);
if (!/^[a-z0-9][a-z0-9-]{2,62}$/.test(cfg.app_name)) throw new Error('invalid app_name');
if (cfg.domain_mode !== 'wasmer') throw new Error('factory v1 smoke run currently requires domain_mode=wasmer');

const owner = account.username;
if (!owner || !account.password) throw new Error('encrypted Wasmer account state is incomplete');
const dashboard = (app) => `https://wasmer.io/apps/${encodeURIComponent(owner)}/${encodeURIComponent(app)}`;
const nativeUrl = (app) => `https://${app}.wasmer.app/`;
const statusPath = `/tmp/site-factory-${cfg.site_slug}.json`;
const safe = {
  status: 'starting',
  stage: 'init',
  siteName: cfg.site_name,
  siteSlug: cfg.site_slug,
  appName: cfg.app_name,
  owner,
  domainMode: cfg.domain_mode,
  siteUrl: null,
  dashboardUrl: null,
  httpCode: null,
  wordpressAdmin: false,
  themeInstalled: false,
  themeActive: false,
  settingsApplied: false,
  fingerprintVerified: false,
  reusedExistingApp: false,
  detail: null,
  updatedAt: new Date().toISOString(),
};
function save() {
  safe.updatedAt = new Date().toISOString();
  fs.writeFileSync(statusPath, JSON.stringify(safe, null, 2));
}
function setStage(stage) { safe.stage = stage; save(); }
async function text(page) { return (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ').trim(); }
async function visibleBlock(page) {
  const s = (await text(page)).toLowerCase();
  if (/recaptcha|hcaptcha|turnstile|verify you are human|security verification|captcha/.test(s)) return 'captcha';
  if (/credit card|payment method|add card|billing information|card details/.test(s)) return 'payment';
  return null;
}
async function publicCheck(ctx, url, fingerprint = null) {
  const r = await ctx.request.get(url, { timeout: 5000, failOnStatusCode: false }).catch(() => null);
  if (!r) return { code: null, hasFingerprint: false };
  const body = await r.text().catch(() => '');
  return { code: r.status(), hasFingerprint: fingerprint ? body.toLowerCase().includes(String(fingerprint).toLowerCase()) : false };
}
async function freshLogin(page) {
  setStage('wasmer_login');
  await page.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(900);
  const ident = page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  if (!(await ident.waitFor({ state: 'visible', timeout: 12000 }).then(() => true).catch(() => false))) return false;
  await ident.fill(account.username || account.email);
  const first = page.locator('button').filter({ hasText: /continue|next|log in|sign in/i }).first();
  if (await first.count() && await first.isVisible().catch(() => false)) await first.click().catch(() => {});
  else await ident.press('Enter').catch(() => {});
  const pass = page.locator('input[type=password]').first();
  if (!(await pass.waitFor({ state: 'visible', timeout: 12000 }).then(() => true).catch(() => false))) return false;
  await pass.fill(account.password);
  const submit = page.locator('input[type=submit],button').filter({ hasText: /log in|sign in|continue/i }).first();
  if (await submit.count() && await submit.isVisible().catch(() => false)) await submit.click().catch(() => {});
  else await pass.press('Enter').catch(() => {});
  await page.waitForTimeout(4500);
  const body = await text(page);
  return !/\/login(?:[/?#]|$)/i.test(page.url()) && !/incorrect|invalid password|wrong password|authentication failed/i.test(body);
}
async function appDashboardExists(page, app) {
  await page.goto(dashboard(app), { waitUntil: 'domcontentloaded', timeout: 60000 });
  for (let i = 0; i < 6; i++) {
    await page.waitForTimeout(i === 0 ? 1000 : 700);
    const body = await text(page);
    const onExpectedRoute = page.url().includes(`/apps/${owner}/${app}`);
    if (onExpectedRoute && /wordpress admin|settings|deployments|domains|ready|wordpress/i.test(body)) return true;
    if (/page not found|404|does not exist|could not be found/i.test(body) && !/wordpress/i.test(body)) return false;
  }
  return false;
}
async function createApp(page) {
  setStage('create_app');
  await page.goto('https://wasmer.io/apps/create?template=wordpress-starter', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(2200);
  const block = await visibleBlock(page);
  if (block) throw new Error(`provider_block:${block}:create_entry`);

  const later = page.locator('button').filter({ hasText: /I'll do it later|I’ll do it later/i }).first();
  if (await later.count() && await later.isVisible().catch(() => false)) { await later.click().catch(() => {}); await page.waitForTimeout(600); }
  const close = page.locator('button').filter({ hasText: /^Close$/i }).first();
  if (await close.count() && await close.isVisible().catch(() => false)) { await close.click().catch(() => {}); await page.waitForTimeout(400); }

  const inputs = page.locator('input[name*=name i],input[placeholder*=name i],input[type=text]');
  let filled = false;
  for (let i = 0; i < await inputs.count(); i++) {
    const el = inputs.nth(i);
    if (!(await el.isVisible().catch(() => false))) continue;
    const hint = `${await el.getAttribute('name') || ''} ${await el.getAttribute('placeholder') || ''}`;
    if (/user|email|search/i.test(hint)) continue;
    await el.fill(cfg.app_name).catch(() => {});
    filled = true;
    break;
  }
  if (!filled) throw new Error('app_name_input_missing');

  let deploy = page.locator('button').filter({ hasText: /Deploy now/i }).first();
  if (!(await deploy.count())) deploy = page.getByText(/Deploy now/i).first();
  if (!(await deploy.count()) || !(await deploy.isVisible().catch(() => false))) throw new Error('deploy_button_missing');
  await deploy.click();

  let actualApp = cfg.app_name;
  for (let i = 0; i < 72; i++) {
    await page.waitForTimeout(2500);
    const b = await visibleBlock(page);
    if (b) throw new Error(`provider_block:${b}:after_deploy`);
    const u = page.url();
    const mDash = u.match(/\/apps\/[^/]+\/([^/?#]+)/i);
    if (mDash) actualApp = decodeURIComponent(mDash[1]);
    const links = await page.locator('a[href*=".wasmer.app"]').evaluateAll(as => as.map(a => a.href)).catch(() => []);
    const preferred = links.find(x => x.includes(actualApp)) || links[0];
    if (preferred) return { app: actualApp, url: preferred.replace(/\/$/, '') + '/' };
    const probe = await publicCheck(page.context(), nativeUrl(actualApp));
    if (probe.code && probe.code < 500 && probe.code !== 404) return { app: actualApp, url: nativeUrl(actualApp) };
  }
  throw new Error('deploy_unconfirmed');
}
async function waitDashboardReady(page, app) {
  setStage('wait_app_ready');
  for (let i = 0; i < 48; i++) {
    await page.goto(dashboard(app), { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => null);
    await page.waitForTimeout(1000);
    const admin = page.getByText(/WordPress Admin/i).first();
    if (await admin.count() && await admin.isVisible().catch(() => false)) return true;
    const b = await visibleBlock(page);
    if (b) throw new Error(`provider_block:${b}:dashboard`);
    await page.waitForTimeout(1500);
  }
  return false;
}
async function enterWordPressAdmin(ctx, page, app, base) {
  setStage('wordpress_admin');
  await page.goto(dashboard(app), { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(1200);
  const admin = page.getByText(/WordPress Admin/i).first();
  if (!(await admin.count())) throw new Error('wordpress_admin_control_missing');

  const href = await admin.getAttribute('href').catch(() => null);
  if (href) {
    const magic = new URL(href, 'https://wasmer.io').href;
    const wp = await ctx.newPage();
    await wp.goto(magic, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wp.waitForTimeout(2800);
    if (wp.url().startsWith(base) && /wp-admin/i.test(wp.url())) return wp;
    await wp.close().catch(() => {});
  }

  const before = new Set(ctx.pages());
  const popupPromise = ctx.waitForEvent('page', { timeout: 10000 }).catch(() => null);
  await admin.click().catch(() => {});
  const popup = await popupPromise;
  await page.waitForTimeout(3200);
  const candidates = [...ctx.pages().filter(p => !before.has(p)), popup, page].filter(Boolean);
  for (const p of candidates) {
    await p.waitForTimeout(300).catch(() => {});
    if (p.url().startsWith(base) && /wp-admin/i.test(p.url())) return p;
  }
  for (const p of ctx.pages()) if (p.url().startsWith(base) && /wp-admin/i.test(p.url())) return p;
  throw new Error('magic_admin_failed');
}
async function ensureTheme(wp) {
  setStage('theme');
  await wp.goto(new URL('/wp-admin/themes.php', safe.siteUrl).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(900);
  if (/wp-login\.php/i.test(wp.url())) throw new Error('wp_session_lost');

  const findCard = async () => {
    const cards = wp.locator('.theme');
    for (let i = 0; i < await cards.count(); i++) {
      const c = cards.nth(i);
      if (/runner3 starter/i.test(await c.innerText().catch(() => ''))) return c;
    }
    return null;
  };
  let card = await findCard();
  if (!card) {
    await wp.goto(new URL('/wp-admin/theme-install.php?upload', safe.siteUrl).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wp.waitForTimeout(900);
    let fi = wp.locator('input[type=file]').first();
    if (!(await fi.count())) {
      const up = wp.locator('button,a').filter({ hasText: /Upload Theme/i }).first();
      if (await up.count()) await up.click().catch(() => {});
      await wp.waitForTimeout(400);
      fi = wp.locator('input[type=file]').first();
    }
    if (!(await fi.count())) throw new Error('theme_upload_input_missing');
    await fi.setInputFiles('/tmp/runner3-starter.zip');
    let install = wp.locator('#install-theme-submit,input[type=submit]').first();
    if (!(await install.count()) || !(await install.isVisible().catch(() => false))) install = wp.locator('button').filter({ hasText: /Install Now/i }).first();
    if (!(await install.count())) throw new Error('theme_install_control_missing');
    await install.click();
    await wp.waitForTimeout(5000);
  }

  await wp.goto(new URL('/wp-admin/themes.php', safe.siteUrl).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(900);
  card = await findCard();
  if (!card) throw new Error('theme_not_present_after_install');
  safe.themeInstalled = true; save();
  const ct = await card.innerText().catch(() => '');
  if (/active:/i.test(ct) || /customize/i.test(ct)) { safe.themeActive = true; save(); return; }
  const activate = card.locator('a,button').filter({ hasText: /^Activate$/i }).first();
  if (!(await activate.count())) throw new Error('theme_activate_control_missing');
  const href = await activate.getAttribute('href').catch(() => null);
  if (href) await wp.goto(new URL(href, safe.siteUrl).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  else await activate.click();
  await wp.waitForTimeout(1500);
  await wp.goto(new URL('/wp-admin/themes.php', safe.siteUrl).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(700);
  card = await findCard();
  const after = card ? await card.innerText().catch(() => '') : '';
  safe.themeActive = /active:/i.test(after) || /customize/i.test(after); save();
  if (!safe.themeActive) throw new Error('theme_activation_unconfirmed');
}
async function applySettings(wp) {
  setStage('site_settings');
  await wp.goto(new URL('/wp-admin/options-general.php', safe.siteUrl).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(800);
  if (/wp-login\.php/i.test(wp.url())) throw new Error('wp_session_lost_settings');
  const name = wp.locator('#blogname,input[name=blogname]').first();
  const desc = wp.locator('#blogdescription,input[name=blogdescription]').first();
  if (!(await name.count())) throw new Error('site_title_field_missing');
  await name.fill(cfg.site_name);
  if (await desc.count()) await desc.fill(cfg.site_purpose || `Built automatically by Runner3 Site Factory — ${cfg.site_name}`);
  let saveBtn = wp.locator('#submit,input[type=submit],button').filter({ hasText: /Save Changes/i }).first();
  if (!(await saveBtn.count())) saveBtn = wp.locator('input[type=submit]').first();
  if (!(await saveBtn.count())) throw new Error('settings_save_missing');
  await saveBtn.click();
  await wp.waitForTimeout(1500);
  safe.settingsApplied = true; save();
}

const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await ctx.newPage();
try {
  save();
  if (!(await freshLogin(page))) throw new Error('wasmer_login_failed');

  let app = cfg.app_name;
  let exists = await appDashboardExists(page, app);
  if (exists) {
    safe.reusedExistingApp = true;
    safe.siteUrl = nativeUrl(app);
    safe.dashboardUrl = dashboard(app);
    save();
  } else {
    const made = await createApp(page);
    app = made.app;
    safe.appName = app;
    safe.siteUrl = made.url || nativeUrl(app);
    safe.dashboardUrl = dashboard(app);
    save();
  }

  if (!(await waitDashboardReady(page, app))) throw new Error('app_not_ready_timeout');
  const initial = await publicCheck(ctx, safe.siteUrl);
  safe.httpCode = initial.code; save();

  const wp = await enterWordPressAdmin(ctx, page, app, safe.siteUrl.replace(/\/$/, ''));
  safe.wordpressAdmin = true; save();
  await ensureTheme(wp);
  await applySettings(wp);

  setStage('public_verify');
  let final = { code: null, hasFingerprint: false };
  for (let i = 0; i < 12; i++) {
    final = await publicCheck(ctx, safe.siteUrl, cfg.fingerprint);
    if (final.code && final.code >= 200 && final.code < 300 && final.hasFingerprint) break;
    await new Promise(r => setTimeout(r, 2500));
  }
  safe.httpCode = final.code;
  safe.fingerprintVerified = final.hasFingerprint;
  safe.status = safe.wordpressAdmin && safe.themeInstalled && safe.themeActive && safe.settingsApplied && final.code >= 200 && final.code < 300 && final.hasFingerprint ? 'live' : 'partial';
  safe.stage = 'complete';
  if (safe.status !== 'live') safe.detail = `completion_gate_failed http=${final.code} fingerprint=${final.hasFingerprint}`;
  save();
  if (safe.status !== 'live') process.exitCode = 2;
} catch (e) {
  safe.status = 'error';
  safe.detail = String(e?.message || e).slice(0, 500);
  save();
  process.exitCode = 1;
} finally {
  await ctx.storageState({ path: '/tmp/wasmer-browser-state.factory.json' }).catch(() => {});
  await browser.close();
}
