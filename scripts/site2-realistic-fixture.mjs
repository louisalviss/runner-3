import { chromium } from 'playwright-core';
import fs from 'node:fs';

const base = 'https://runner3-wp-a94b8fd2.wasmer.app';
const dashboard = 'https://wasmer.io/apps/runner3wp0b90f6b4ab/runner3-wp-a94b8fd2';
const seedZip = process.env.SEED_ZIP || '/tmp/site2-benchmark-seed.zip';
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const out = '/tmp/site2-realistic-fixture.json';
const result = {
  status: 'STARTING', stage: 'init', siteId: 'site2', app: 'runner3-wp-a94b8fd2', siteUrl: `${base}/`,
  fixture: 'astra-woocommerce-gutenberg-v1', theme: null, plugins: {}, counts: {}, routes: {},
  optimizationPluginsActive: [], noindexMeta: false, astraMarker: false, wooMarker: false, detail: null,
  updatedAt: new Date().toISOString(),
};
const save = () => { result.updatedAt = new Date().toISOString(); fs.writeFileSync(out, JSON.stringify(result, null, 2)); };
const stage = s => { result.stage = s; console.log('STAGE', s); save(); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const onLogin = p => /\/login(?:[/?#]|$)/i.test(p.url());

async function loginWasmer(page) {
  stage('wasmer_login');
  for (let attempt = 1; attempt <= 3; attempt++) {
    await page.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => null);
    await sleep(700);
    if (!onLogin(page)) return;
    const ident = page.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();
    if (!await ident.isVisible().catch(() => false)) continue;
    await ident.fill(account.username || account.email);
    await ident.press('Enter').catch(() => {});
    const pass = page.locator('input[type=password]').first();
    if (!await pass.waitFor({ state: 'visible', timeout: 20000 }).then(() => true).catch(() => false)) continue;
    await pass.fill(account.password);
    await pass.press('Enter').catch(() => {});
    const deadline = Date.now() + 25000;
    while (Date.now() < deadline) { if (!onLogin(page)) return; await sleep(500); }
  }
  throw new Error('wasmer_login_failed');
}

async function pollAdmin(ctx, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    for (const p of ctx.pages()) {
      if (p.url().startsWith(base) && /\/wp-admin(?:\/|\?|$)/i.test(p.url()) && !/wp-login\.php/i.test(p.url())) return p;
    }
    await sleep(500);
  }
  return null;
}

async function enterAdmin(ctx, page) {
  stage('wordpress_admin');
  for (let attempt = 1; attempt <= 3; attempt++) {
    await page.goto(dashboard, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => null);
    await sleep(1200);
    let control = page.getByText(/WordPress Admin/i).first();
    if (!await control.isVisible().catch(() => false)) {
      const settings = page.getByText(/^Settings$/i).first();
      if (await settings.isVisible().catch(() => false)) {
        await settings.click().catch(() => {}); await sleep(700);
        const wordpress = page.getByText(/^WordPress$/i).first();
        if (await wordpress.isVisible().catch(() => false)) { await wordpress.click().catch(() => {}); await sleep(700); }
        control = page.getByText(/WordPress Admin/i).first();
      }
    }
    if (!await control.isVisible().catch(() => false)) continue;
    const href = await control.getAttribute('href').catch(() => null);
    if (href) {
      const wp = await ctx.newPage();
      await wp.goto(new URL(href, 'https://wasmer.io').href, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => null);
      const found = await pollAdmin(ctx, 25000); if (found) return found;
    }
    await control.click({ noWaitAfter: true }).catch(() => {});
    const found = await pollAdmin(ctx, 30000); if (found) return found;
  }
  throw new Error('magic_wordpress_admin_failed');
}

async function configureWordPress(wp) {
  stage('wordpress_safety_settings');
  await wp.goto(`${base}/wp-admin/options-reading.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const noindex = wp.locator('input[name="blog_public"]').first();
  if (await noindex.count()) {
    if (!await noindex.isChecked()) await noindex.check();
    await wp.locator('#submit,input[type=submit]').first().click();
    await wp.waitForLoadState('domcontentloaded').catch(() => {});
  }
  await wp.goto(`${base}/wp-admin/options-permalink.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const postname = wp.locator('input[name="selection"][value="/%postname%/"]').first();
  if (await postname.count()) {
    if (!await postname.isChecked().catch(() => false)) await postname.check();
    await wp.locator('#submit,input[type=submit]').first().click();
    await wp.waitForLoadState('domcontentloaded').catch(() => {});
  }
}

async function getNonce(wp) {
  await wp.goto(`${base}/wp-admin/`, { waitUntil: 'domcontentloaded', timeout: 60000 }); await sleep(700);
  let nonce = await wp.evaluate(() => globalThis.wpApiSettings?.nonce || globalThis.wp?.apiSettings?.nonce || null).catch(() => null);
  if (!nonce) {
    const html = await wp.content();
    const m = html.match(/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i);
    if (m) nonce = m[1];
  }
  if (!nonce) throw new Error('wp_rest_nonce_missing');
  return nonce;
}

async function api(ctx, nonce, path, { method = 'GET', json = undefined, soft = false, timeout = 120000 } = {}) {
  const headers = { 'X-WP-Nonce': nonce, Accept: 'application/json' };
  let data;
  if (json !== undefined) { headers['Content-Type'] = 'application/json'; data = JSON.stringify(json); }
  const r = await ctx.request.fetch(`${base}/wp-json${path}`, { method, headers, data, timeout, failOnStatusCode: false });
  const text = await r.text(); let parsed; try { parsed = JSON.parse(text); } catch { parsed = text; }
  if (!r.ok()) {
    if (soft) return { ok: false, status: r.status(), data: parsed };
    throw new Error(`api_${method}_${path}:${r.status()}:${String(text).slice(0, 450)}`);
  }
  return soft ? { ok: true, status: r.status(), data: parsed } : parsed;
}

async function ensurePlugin(ctx, nonce, slug, prefix) {
  const plugins = await api(ctx, nonce, '/wp/v2/plugins?context=edit&per_page=100');
  let p = plugins.find(x => String(x.plugin || '').startsWith(prefix));
  if (!p) p = await api(ctx, nonce, '/wp/v2/plugins', { method: 'POST', json: { slug, status: 'active' } });
  else if (p.status !== 'active') p = await api(ctx, nonce, `/wp/v2/plugins/${encodeURIComponent(p.plugin)}`, { method: 'POST', json: { status: 'active' } });
  return p;
}

async function deactivateKnownOptimizers(ctx, nonce) {
  stage('disable_prebaseline_optimizers');
  const patterns = [/^litespeed-cache\//,/^wp-super-cache\//,/^w3-total-cache\//,/^autoptimize\//,/^wp-optimize\//,/^wp-rocket\//,/^perfmatters\//,/^nitropack\//,/^sg-cachepress\//];
  const plugins = await api(ctx, nonce, '/wp/v2/plugins?context=edit&per_page=100');
  for (const p of plugins) {
    const key = String(p.plugin || '');
    if (p.status === 'active' && patterns.some(re => re.test(key))) {
      await api(ctx, nonce, `/wp/v2/plugins/${encodeURIComponent(key)}`, { method: 'POST', json: { status: 'inactive' } });
    }
  }
  const seed = plugins.find(p => String(p.plugin || '').startsWith('site2-benchmark-seed/'));
  if (seed?.status === 'active') await api(ctx, nonce, `/wp/v2/plugins/${encodeURIComponent(seed.plugin)}`, { method: 'POST', json: { status: 'inactive' } });
}

async function activateAstra(wp) {
  stage('astra_theme');
  await wp.goto(`${base}/wp-admin/themes.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  let active = wp.locator('.theme.active[data-slug="astra"],.theme.active').filter({ hasText: /\bAstra\b/i }).first();
  if (await active.count()) { result.theme = 'astra'; save(); return; }
  let card = wp.locator('.theme[data-slug="astra"],.theme').filter({ hasText: /\bAstra\b/i }).first();
  if (!await card.count()) {
    await wp.goto(`${base}/wp-admin/theme-install.php?search=astra`, { waitUntil: 'domcontentloaded', timeout: 60000 }); await sleep(1500);
    let link = wp.locator('a[href*="action=install-theme"][href*="theme=astra"],a.theme-install[href*="astra"],a[href*="theme=astra"]').first();
    let href = await link.getAttribute('href').catch(() => null);
    if (!href) {
      const html = await wp.content(); const m = html.match(/href=["']([^"']*(?:action=install-theme[^"']*theme=astra|theme=astra[^"']*action=install-theme)[^"']*)["']/i);
      if (m) href = m[1].replaceAll('&amp;', '&');
    }
    if (!href) throw new Error('astra_install_url_missing');
    await wp.goto(new URL(href, `${base}/wp-admin/`).href, { waitUntil: 'domcontentloaded', timeout: 120000 }); await sleep(1200);
  }
  await wp.goto(`${base}/wp-admin/themes.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  card = wp.locator('.theme[data-slug="astra"],.theme').filter({ hasText: /\bAstra\b/i }).first();
  if (!await card.count()) throw new Error('astra_not_installed');
  active = wp.locator('.theme.active[data-slug="astra"],.theme.active').filter({ hasText: /\bAstra\b/i }).first();
  if (!await active.count()) {
    const activate = card.locator('a.activate,a[href*="action=activate"]').first(); let href = await activate.getAttribute('href').catch(() => null);
    if (!href) { const html = await card.innerHTML(); const m = html.match(/href=["']([^"']*action=activate[^"']*)["']/i); if (m) href = m[1].replaceAll('&amp;', '&'); }
    if (!href) throw new Error('astra_activate_url_missing');
    await wp.goto(new URL(href, `${base}/wp-admin/`).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  }
  await wp.goto(`${base}/wp-admin/themes.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  active = wp.locator('.theme.active[data-slug="astra"],.theme.active').filter({ hasText: /\bAstra\b/i }).first();
  if (!await active.count()) throw new Error('astra_activation_failed');
  result.theme = 'astra'; save();
}

async function installSeedPlugin(wp) {
  stage('seed_plugin_upload');
  if (!fs.existsSync(seedZip)) throw new Error(`seed_zip_missing:${seedZip}`);
  await wp.goto(`${base}/wp-admin/plugin-install.php?tab=upload`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const file = wp.locator('input[type="file"]').first();
  await file.waitFor({ state: 'attached', timeout: 20000 });
  await file.setInputFiles(seedZip);
  const submit = wp.locator('#install-plugin-submit,input[type="submit"][value*="Install" i],button[type="submit"]').first();
  await submit.click();
  await wp.waitForLoadState('domcontentloaded').catch(() => {}); await sleep(1500);
  const replace = wp.locator('a').filter({ hasText: /replace (current|installed).*uploaded/i }).first();
  if (await replace.count()) {
    const href = await replace.getAttribute('href'); if (!href) throw new Error('seed_replace_href_missing');
    await wp.goto(new URL(href, `${base}/wp-admin/`).href, { waitUntil: 'domcontentloaded', timeout: 120000 }); await sleep(1500);
  }
  await wp.goto(`${base}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  let row = wp.locator('tr[data-slug="site2-benchmark-seed"]').first();
  if (!await row.count()) throw new Error('seed_plugin_row_missing');
  let cls = await row.getAttribute('class') || '';
  if (!/\bactive\b/.test(cls)) {
    const activate = row.locator('a[href*="action=activate"]').first();
    const href = await activate.getAttribute('href').catch(() => null); if (!href) throw new Error('seed_activate_href_missing');
    await wp.goto(new URL(href, `${base}/wp-admin/`).href, { waitUntil: 'domcontentloaded', timeout: 180000 }); await sleep(1800);
  }
  await wp.goto(`${base}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  row = wp.locator('tr[data-slug="site2-benchmark-seed"]').first(); cls = await row.getAttribute('class') || '';
  if (!/\bactive\b/.test(cls)) {
    const err = await wp.locator('.notice-error,.error').first().innerText().catch(() => '');
    throw new Error(`seed_activation_failed:${err.slice(0, 500)}`);
  }
}

async function verifyAndDeactivate(ctx, wp, nonce) {
  stage('verify_fixture');
  nonce = await getNonce(wp);
  const status = await api(ctx, nonce, '/site2-benchmark/v1/status');
  result.fixture = status.version; result.theme = `${status.theme}@${status.theme_version}`; result.plugins.woocommerce = status.woocommerce; result.counts = status.counts; save();
  if (status.version !== 'astra-woocommerce-gutenberg-v1') throw new Error(`fixture_version_mismatch:${status.version}`);
  if (status.theme !== 'astra') throw new Error(`theme_not_astra:${status.theme}`);
  if (!status.woocommerce) throw new Error('woocommerce_version_missing');
  if ((status.counts?.products || 0) < 30 || (status.counts?.variable_products || 0) < 4 || (status.counts?.categories || 0) < 6 || (status.counts?.fixture_media || 0) < 9) {
    throw new Error(`fixture_counts_incomplete:${JSON.stringify(status.counts)}`);
  }

  const routes = ['/', '/shop/', '/product/canvas-daypack/', '/product-category/apparel/', '/cart/', '/checkout/', '/my-account/'];
  for (const route of routes) {
    const r = await fetch(`${base}${route}?fixture_verify=${Date.now()}`, { redirect: 'manual', headers: { 'Cache-Control': 'no-cache' } });
    const body = await r.text().catch(() => ''); result.routes[route] = { status: r.status, bytes: Buffer.byteLength(body), location: r.headers.get('location') };
  }
  const home = await fetch(`${base}/?fixture_home=${Date.now()}`, { headers: { 'Cache-Control': 'no-cache' } }).then(r => r.text());
  result.noindexMeta = /<meta[^>]+name=["']robots["'][^>]+noindex/i.test(home) || /noindex[^>]+nofollow/i.test(home);
  result.astraMarker = /\bast-(?:desktop|header|container|primary|site|plain-container)/i.test(home) || /astra/i.test(home);
  result.wooMarker = /woocommerce/i.test(home);
  const badRoutes = Object.entries(result.routes).filter(([, v]) => ![200,301,302,303].includes(v.status));
  if (!result.noindexMeta) throw new Error('noindex_meta_missing');
  if (!result.astraMarker) throw new Error('astra_public_marker_missing');
  if (!result.wooMarker) throw new Error('woocommerce_public_marker_missing');
  if (badRoutes.length) throw new Error(`route_failures:${JSON.stringify(badRoutes)}`);

  stage('deactivate_seed_plugin');
  const plugins = await api(ctx, nonce, '/wp/v2/plugins?context=edit&per_page=100');
  const seed = plugins.find(p => String(p.plugin || '').startsWith('site2-benchmark-seed/'));
  if (!seed) throw new Error('seed_plugin_missing_after_seed');
  if (seed.status === 'active') await api(ctx, nonce, `/wp/v2/plugins/${encodeURIComponent(seed.plugin)}`, { method: 'POST', json: { status: 'inactive' } });
  const after = await api(ctx, nonce, '/wp/v2/plugins?context=edit&per_page=100');
  const patterns = [/^litespeed-cache\//,/^wp-super-cache\//,/^w3-total-cache\//,/^autoptimize\//,/^wp-optimize\//,/^wp-rocket\//,/^perfmatters\//,/^nitropack\//,/^sg-cachepress\//];
  result.optimizationPluginsActive = after.filter(p => p.status === 'active' && patterns.some(re => re.test(String(p.plugin || '')))).map(p => p.plugin);
  const seedAfter = after.find(p => String(p.plugin || '').startsWith('site2-benchmark-seed/'));
  if (seedAfter?.status === 'active') throw new Error('seed_plugin_still_active');
  if (result.optimizationPluginsActive.length) throw new Error(`optimization_plugins_active:${result.optimizationPluginsActive.join(',')}`);
  result.plugins.seed = 'inactive';
  save();
}

const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH, args: ['--no-sandbox','--disable-dev-shm-usage'] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
const page = await ctx.newPage();
try {
  await loginWasmer(page);
  const wp = await enterAdmin(ctx, page);
  await configureWordPress(wp);
  await activateAstra(wp);
  let nonce = await getNonce(wp);
  await deactivateKnownOptimizers(ctx, nonce);
  stage('install_woocommerce');
  const woo = await ensurePlugin(ctx, nonce, 'woocommerce', 'woocommerce/'); result.plugins.woocommerce = woo.status || 'active'; save();
  await sleep(2500);
  await installSeedPlugin(wp);
  nonce = await getNonce(wp);
  await verifyAndDeactivate(ctx, wp, nonce);
  result.status = 'READY'; result.stage = 'done'; save();
} catch (e) {
  result.status = 'FAILED'; result.detail = String(e?.stack || e); save(); console.error(result.detail); process.exitCode = 1;
} finally { await browser.close().catch(() => {}); }
console.log(JSON.stringify(result, null, 2));
