import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const statusFile = `ops/site-factory/${slug}.json`;
const publicBase = String(process.env.WP_PUBLIC_URL || 'https://runner3wp.pntr.dev').replace(/\/$/, '');
const pluginZip = process.env.PLUGIN_ZIP || '/tmp/runner3-r2-responsive.zip';
const out = '/tmp/wp-r2-responsive-result.json';

if (!fs.existsSync(statusFile)) throw new Error(`site factory state missing: ${statusFile}`);
if (!fs.existsSync('/tmp/wasmer-account.json')) throw new Error('decrypted Wasmer account state missing');
if (!fs.existsSync(pluginZip)) throw new Error(`plugin zip missing: ${pluginZip}`);

const site = JSON.parse(fs.readFileSync(statusFile, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const nativeBase = String(site.siteUrl || '').replace(/\/$/, '');
const dashboard = site.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName)}`;
if (!nativeBase) throw new Error('native site url missing');

const safe = {
  status: 'starting',
  siteSlug: slug,
  publicUrl: publicBase + '/',
  nativeUrl: nativeBase + '/',
  plugin: 'runner3-r2-responsive',
  installed: false,
  activated: false,
  frontendHttp: null,
  responsiveV2: false,
  preloadMatchesHero: false,
  r2Preconnect: false,
  responsiveImageCount: 0,
  heroCurrentSrc: null,
  heroRenderedWidth: null,
  heroNaturalWidth: null,
  consoleErrors: [],
  pageErrors: [],
  consoleWarnings: [],
  detail: null,
  updatedAt: new Date().toISOString(),
};

function save() {
  safe.updatedAt = new Date().toISOString();
  fs.writeFileSync(out, JSON.stringify(safe, null, 2));
}

async function bodyText(page) {
  return (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ').trim();
}

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

function isNativeAdmin(raw) {
  try {
    const u = new URL(raw);
    return u.host === new URL(nativeBase).host && /\/wp-admin(?:[/?#]|$)/i.test(u.pathname + u.search + u.hash);
  } catch {
    return false;
  }
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
    if (isNativeAdmin(wp.url())) return wp;
    await wp.close().catch(() => {});
  }

  const before = new Set(ctx.pages());
  const popupPromise = ctx.waitForEvent('page', { timeout: 10000 }).catch(() => null);
  await admin.click().catch(() => {});
  const popup = await popupPromise;
  await page.waitForTimeout(3000);
  const candidates = [...ctx.pages().filter(p => !before.has(p)), popup, page].filter(Boolean);
  for (const p of candidates) if (isNativeAdmin(p.url())) return p;
  throw new Error('magic_admin_failed');
}

async function ensurePlugin(wp) {
  const origin = new URL(wp.url()).origin;
  await wp.goto(`${origin}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(600);

  let row = wp.locator('tr[data-slug="runner3-r2-responsive"]').first();
  if (await row.count()) {
    safe.installed = true;
    const cls = String(await row.getAttribute('class').catch(() => ''));
    if (/\bactive\b/.test(cls)) {
      safe.activated = true;
      save();
      return;
    }
    const activate = row.getByRole('link', { name: /^activate$/i }).first();
    if (await activate.count()) {
      await activate.click();
      await wp.waitForLoadState('domcontentloaded').catch(() => {});
      await wp.waitForTimeout(800);
    }
  } else {
    await wp.goto(`${origin}/wp-admin/plugin-install.php?tab=upload`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    const input = wp.locator('input[type=file][name=pluginzip],input[type=file]').first();
    await input.waitFor({ state: 'attached', timeout: 15000 });
    await input.setInputFiles(pluginZip);
    const install = wp.locator('#install-plugin-submit,input[type=submit][value*="Install" i],button[type=submit]').first();
    if (!(await install.count())) throw new Error('plugin_install_submit_missing');
    await install.click();
    await wp.waitForLoadState('domcontentloaded').catch(() => {});
    await wp.waitForTimeout(1200);

    const replace = wp.getByRole('link', { name: /replace current with uploaded/i }).first();
    const replaceButton = wp.locator('input[type=submit][value*="Replace current" i],button').filter({ hasText: /replace current with uploaded/i }).first();
    if (await replace.count()) {
      await replace.click();
      await wp.waitForLoadState('domcontentloaded').catch(() => {});
      await wp.waitForTimeout(1000);
    } else if (await replaceButton.count()) {
      await replaceButton.click();
      await wp.waitForLoadState('domcontentloaded').catch(() => {});
      await wp.waitForTimeout(1000);
    }

    const txt = await bodyText(wp);
    if (/installation failed|could not be installed|fatal error/i.test(txt)) {
      throw new Error(`plugin_install_failed:${txt.slice(0, 500)}`);
    }

    const activate = wp.getByRole('link', { name: /activate plugin/i }).first();
    const activateButton = wp.locator('a.button-primary').filter({ hasText: /activate/i }).first();
    if (await activate.count()) {
      await activate.click();
      await wp.waitForLoadState('domcontentloaded').catch(() => {});
      await wp.waitForTimeout(800);
    } else if (await activateButton.count()) {
      await activateButton.click();
      await wp.waitForLoadState('domcontentloaded').catch(() => {});
      await wp.waitForTimeout(800);
    }
  }

  await wp.goto(`${origin}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  row = wp.locator('tr[data-slug="runner3-r2-responsive"]').first();
  if (!(await row.count())) throw new Error('plugin_not_present_after_install');
  safe.installed = true;
  const cls = String(await row.getAttribute('class').catch(() => ''));
  safe.activated = /\bactive\b/.test(cls);
  if (!safe.activated) throw new Error('plugin_not_active_after_install');
  save();
}

function firstAttr(tag, name) {
  const re = new RegExp(`\\b${name}\\s*=\\s*["']([^"']*)["']`, 'i');
  return tag.match(re)?.[1] || '';
}

async function verifyFrontend(browser) {
  const requestUrl = `${publicBase}/?runner3_r2_probe=${Date.now()}`;
  const requestContext = await browser.newContext({ ignoreHTTPSErrors: true });
  const response = await requestContext.request.get(requestUrl, { headers: { Accept: 'text/html' } });
  safe.frontendHttp = response.status();
  const html = await response.text();
  const imageTags = html.match(/<img\b[^>]*>/gi) || [];
  const responsiveTags = imageTags.filter(tag => /responsive-v2\/offset-demo-0[1-8]-w360\.webp/i.test(firstAttr(tag, 'srcset')));
  safe.responsiveImageCount = responsiveTags.length;
  safe.responsiveV2 = responsiveTags.length >= 1;
  safe.r2Preconnect = /<link\b[^>]*rel=["']preconnect["'][^>]*pub-f6e5190178814cd5be8f1eb531f1a164\.r2\.dev/i.test(html)
    || /<link\b[^>]*pub-f6e5190178814cd5be8f1eb531f1a164\.r2\.dev[^>]*rel=["']preconnect["']/i.test(html);

  const preload = (html.match(/<link\b[^>]*rel=["']preload["'][^>]*as=["']image["'][^>]*>/i) || [])[0] || '';
  const hero = imageTags.find(tag => /offset-demo-01\.webp/i.test(firstAttr(tag, 'src'))) || '';
  const preloadSrcset = firstAttr(preload, 'imagesrcset');
  const heroSrcset = firstAttr(hero, 'srcset');
  const preloadSizes = firstAttr(preload, 'imagesizes');
  const heroSizes = firstAttr(hero, 'sizes');
  safe.preloadMatchesHero = Boolean(preloadSrcset && heroSrcset && preloadSrcset === heroSrcset && preloadSizes && heroSizes && preloadSizes === heroSizes);
  await requestContext.close();

  const ctx = await browser.newContext({
    ignoreHTTPSErrors: true,
    viewport: { width: 393, height: 852 },
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  page.on('console', msg => {
    const item = { type: msg.type(), text: msg.text(), location: msg.location() };
    if (msg.type() === 'error') safe.consoleErrors.push(item);
    else if (msg.type() === 'warning') safe.consoleWarnings.push(item);
  });
  page.on('pageerror', error => safe.pageErrors.push(String(error?.message || error)));
  await page.goto(requestUrl, { waitUntil: 'networkidle', timeout: 60000 });
  await page.locator('img').evaluateAll(imgs => imgs.forEach(img => img.scrollIntoView({ block: 'center' }))).catch(() => {});
  await page.waitForTimeout(1500);
  const heroRuntime = await page.locator('img[src*="offset-demo-01.webp"]').first().evaluate(img => ({
    currentSrc: img.currentSrc,
    renderedWidth: Math.round(img.getBoundingClientRect().width),
    naturalWidth: img.naturalWidth,
    srcset: img.srcset,
    sizes: img.sizes,
  })).catch(() => null);
  if (heroRuntime) {
    safe.heroCurrentSrc = heroRuntime.currentSrc;
    safe.heroRenderedWidth = heroRuntime.renderedWidth;
    safe.heroNaturalWidth = heroRuntime.naturalWidth;
  }
  await ctx.close();

  if (safe.frontendHttp !== 200) throw new Error(`frontend_http_${safe.frontendHttp}`);
  if (!safe.responsiveV2) throw new Error('responsive_v2_missing_on_public_html');
  if (!safe.preloadMatchesHero) throw new Error('hero_preload_srcset_or_sizes_mismatch');
  if (!safe.r2Preconnect) throw new Error('r2_preconnect_missing');
  if (safe.consoleErrors.length || safe.pageErrors.length) throw new Error('frontend_javascript_error_detected');
}

const browser = await chromium.launch({
  headless: true,
  executablePath: '/usr/bin/google-chrome',
  args: ['--no-sandbox'],
});

const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await ctx.newPage();
try {
  save();
  await loginWasmer(page);
  const wp = await enterAdmin(ctx, page);
  await ensurePlugin(wp);
  await verifyFrontend(browser);
  safe.status = 'ok';
  safe.detail = safe.consoleWarnings.length ? 'responsive_v2_active; non-fatal browser warning(s) recorded' : 'responsive_v2_active';
  save();
  console.log(`WP_R2_RESPONSIVE_OK images=${safe.responsiveImageCount} hero=${safe.heroCurrentSrc}`);
} catch (e) {
  safe.status = 'failed';
  safe.detail = String(e?.message || e);
  save();
  console.error(`WP_R2_RESPONSIVE_FAILED ${safe.detail}`);
  process.exitCode = 1;
} finally {
  await ctx.close().catch(() => {});
  await browser.close().catch(() => {});
}
