import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const publicBase = String(process.env.WP_PUBLIC_URL || 'https://runner3wp.pntr.dev').replace(/\/$/, '');
const pluginZip = process.env.PLUGIN_ZIP || '/tmp/runner3-r2-responsive.zip';
const stateFile = `ops/site-factory/${slug}.json`;
const out = '/tmp/wp-r2-responsive-result.json';
if (!fs.existsSync(stateFile)) throw new Error(`site factory state missing: ${stateFile}`);
if (!fs.existsSync('/tmp/wasmer-account.json')) throw new Error('decrypted Wasmer account state missing');
if (!fs.existsSync(pluginZip)) throw new Error(`plugin zip missing: ${pluginZip}`);

const site = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const nativeBase = String(site.siteUrl || '').replace(/\/$/, '');
const adminBase = `${nativeBase}/wp-admin/`;
const dashboard = site.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName)}`;

const safe = {
  status: 'starting', siteSlug: slug, publicUrl: publicBase + '/', nativeUrl: nativeBase + '/',
  plugin: 'runner3-r2-responsive', installed: false, activated: false, pluginUpdated: false,
  settingsPageReachable: false, frontendHttp: null, responsiveV2: false,
  preloadMatchesHero: false, r2Preconnect: false, responsiveImageCount: 0,
  heroCurrentSrc: null, heroRenderedWidth: null, heroNaturalWidth: null,
  consoleErrors: [], pageErrors: [], consoleWarnings: [], detail: null, adminDiagnostic: null,
  updatedAt: new Date().toISOString(),
};
function save() { safe.updatedAt = new Date().toISOString(); fs.writeFileSync(out, JSON.stringify(safe, null, 2)); }
async function text(page) { return (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ').trim(); }

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

function isNativeAdmin(raw) {
  try { const u = new URL(raw); return u.host === new URL(nativeBase).host && u.pathname.startsWith('/wp-admin'); }
  catch { return false; }
}

async function enterAdmin(ctx, page) {
  await page.goto(dashboard, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(1000);
  const admin = page.getByText(/WordPress Admin/i).first();
  if (!(await admin.count())) throw new Error('wordpress_admin_control_missing');
  const href = await admin.getAttribute('href').catch(() => null);
  if (href) {
    const wp = await ctx.newPage();
    await wp.goto(new URL(href, 'https://wasmer.io').href, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wp.waitForTimeout(2200);
    if (isNativeAdmin(wp.url())) return wp;
    await wp.close().catch(() => {});
  }
  const popupP = ctx.waitForEvent('page', { timeout: 10000 }).catch(() => null);
  await admin.click().catch(() => {});
  const popup = await popupP;
  await page.waitForTimeout(2500);
  for (const p of [popup, ...ctx.pages()].filter(Boolean)) if (isNativeAdmin(p.url())) return p;
  throw new Error('magic_admin_failed');
}

async function pluginRow(wp) {
  let row = wp.locator('tr[data-slug="runner3-r2-responsive"]').first();
  if (await row.count()) return row;
  row = wp.locator('tr').filter({ hasText: /Runner3 (?:R2 Responsive Images|Media Optimizer)/i }).first();
  return (await row.count()) ? row : null;
}

async function forceUploadCurrentPlugin(wp) {
  await wp.goto(`${adminBase}plugin-install.php?tab=upload`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const input = wp.locator('input[type=file]').first();
  await input.waitFor({ state: 'attached', timeout: 12000 });
  await input.setInputFiles(pluginZip);
  const install = wp.locator('input[type=submit][value*="Install" i],button[type=submit]').first();
  await install.click();
  await wp.waitForLoadState('domcontentloaded').catch(() => {});
  await wp.waitForTimeout(1400);

  const body = await text(wp);
  if (/installation failed|could not be installed|fatal error/i.test(body)) throw new Error(`plugin_install_failed:${body.slice(0, 600)}`);

  const replace = wp.locator('a').filter({ hasText: /replace (current|installed).*uploaded/i }).first();
  if (await replace.count()) {
    const href = await replace.getAttribute('href');
    if (!href) throw new Error('plugin_replace_href_missing');
    await wp.goto(new URL(href, adminBase).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wp.waitForTimeout(1400);
    const replaceBody = await text(wp);
    if (/update failed|installation failed|fatal error/i.test(replaceBody)) throw new Error(`plugin_replace_failed:${replaceBody.slice(0, 600)}`);
    safe.pluginUpdated = true;
  } else if (/plugin installed successfully|successfully installed/i.test(body)) {
    safe.pluginUpdated = true;
  } else {
    throw new Error(`plugin_replace_control_missing:${body.slice(0, 700)}`);
  }
}

async function ensurePlugin(wp) {
  // Always upload the ZIP from the repository. Previously this script skipped upload
  // when the slug already existed, which left an old plugin version on the live site.
  await forceUploadCurrentPlugin(wp);

  await wp.goto(`${adminBase}plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(700);
  let row = await pluginRow(wp);
  if (!row) throw new Error('plugin_not_present_after_upload');
  safe.installed = true;

  let cls = String(await row.getAttribute('class').catch(() => ''));
  if (!/\bactive\b/.test(cls)) {
    const activate = row.locator('a[href*="action=activate"]').first();
    if (!(await activate.count())) throw new Error('plugin_activation_action_missing');
    const href = await activate.getAttribute('href');
    if (!href) throw new Error('plugin_activation_href_missing');
    await wp.goto(new URL(href, adminBase).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wp.waitForTimeout(900);
    const activationBody = await text(wp);
    safe.adminDiagnostic = activationBody.slice(0, 1200);
    if (/fatal error|could not be activated|plugin could not be activated/i.test(activationBody)) throw new Error(`plugin_activation_failed:${activationBody.slice(0, 500)}`);
    await wp.goto(`${adminBase}plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wp.waitForTimeout(600);
    row = await pluginRow(wp);
    cls = row ? String(await row.getAttribute('class').catch(() => '')) : '';
  }
  safe.activated = /\bactive\b/.test(cls);
  if (!safe.activated) throw new Error('plugin_not_active_after_activation');

  await wp.goto(`${adminBase}options-general.php?page=runner3-media-optimizer`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(400);
  safe.settingsPageReachable = /Runner3 Media Optimizer/i.test(await text(wp));
  if (!safe.settingsPageReachable) throw new Error('media_optimizer_settings_page_missing_after_deploy');
  save();
}

function attr(tag, name) {
  const m = tag.match(new RegExp(`\\b${name}\\s*=\\s*["']([^"']*)["']`, 'i'));
  return m?.[1] || '';
}

async function verifyFrontend(browser) {
  const url = `${publicBase}/?runner3_r2_probe=${Date.now()}`;
  const reqCtx = await browser.newContext({ ignoreHTTPSErrors: true });
  const res = await reqCtx.request.get(url, { headers: { Accept: 'text/html' } });
  safe.frontendHttp = res.status();
  const html = await res.text();
  await reqCtx.close();
  const imgs = html.match(/<img\b[^>]*>/gi) || [];
  const responsive = imgs.filter(t => /responsive-v2\/offset-demo-0[1-8]-w360\.webp/i.test(attr(t, 'srcset')));
  safe.responsiveImageCount = responsive.length;
  safe.responsiveV2 = responsive.length > 0;
  safe.r2Preconnect = /<link\b[^>]*rel=["']preconnect["'][^>]*pub-f6e5190178814cd5be8f1eb531f1a164\.r2\.dev/i.test(html) || /<link\b[^>]*pub-f6e5190178814cd5be8f1eb531f1a164\.r2\.dev[^>]*rel=["']preconnect["']/i.test(html);
  const preloads = html.match(/<link\b[^>]*rel=["']preload["'][^>]*as=["']image["'][^>]*>/gi) || [];
  const preload = preloads.find(t => /offset-demo-01\.webp/i.test(attr(t, 'href'))) || '';
  const hero = imgs.find(t => /offset-demo-01\.webp/i.test(attr(t, 'src'))) || '';
  safe.preloadMatchesHero = Boolean(attr(preload, 'imagesrcset') && attr(preload, 'imagesrcset') === attr(hero, 'srcset') && attr(preload, 'imagesizes') && attr(preload, 'imagesizes') === attr(hero, 'sizes'));

  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 393, height: 852 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  page.on('console', msg => {
    const item = { type: msg.type(), text: msg.text(), location: msg.location() };
    if (msg.type() === 'error') safe.consoleErrors.push(item); else if (msg.type() === 'warning') safe.consoleWarnings.push(item);
  });
  page.on('pageerror', e => safe.pageErrors.push(String(e?.message || e)));
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  const heroRuntime = await page.locator('img[src*="offset-demo-01.webp"]').first().evaluate(img => ({ currentSrc: img.currentSrc, renderedWidth: Math.round(img.getBoundingClientRect().width), naturalWidth: img.naturalWidth })).catch(() => null);
  if (heroRuntime) Object.assign(safe, { heroCurrentSrc: heroRuntime.currentSrc, heroRenderedWidth: heroRuntime.renderedWidth, heroNaturalWidth: heroRuntime.naturalWidth });
  await ctx.close();

  if (safe.frontendHttp !== 200) throw new Error(`frontend_http_${safe.frontendHttp}`);
  if (!safe.responsiveV2) throw new Error('responsive_v2_missing_on_public_html');
  if (!safe.preloadMatchesHero) throw new Error('hero_preload_srcset_or_sizes_mismatch');
  if (!safe.r2Preconnect) throw new Error('r2_preconnect_missing');
  if (safe.consoleErrors.length || safe.pageErrors.length) throw new Error('frontend_javascript_error_detected');
}

const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await ctx.newPage();
try {
  save();
  await loginWasmer(page);
  const wp = await enterAdmin(ctx, page);
  await ensurePlugin(wp);
  await verifyFrontend(browser);
  safe.status = 'ok';
  safe.detail = safe.consoleWarnings.length ? 'media_optimizer_v2_deployed; responsive_v2_active; non-fatal browser warning(s) recorded' : 'media_optimizer_v2_deployed; responsive_v2_active';
  save();
  console.log(`WP_R2_RESPONSIVE_OK updated=${safe.pluginUpdated} settings=${safe.settingsPageReachable} images=${safe.responsiveImageCount}`);
} catch (e) {
  safe.status = 'failed'; safe.detail = String(e?.message || e); save();
  console.error(`WP_R2_RESPONSIVE_FAILED ${safe.detail}`); process.exitCode = 1;
} finally {
  await ctx.close().catch(() => {}); await browser.close().catch(() => {});
}
