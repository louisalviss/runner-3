import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-speed-site3-realistic';
const site = JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(site.siteUrl).replace(/\/$/, '');
const dashboard = site.dashboardUrl;
const out = '/tmp/runner3-speed-site3-inspiro.json';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

const result = {
  status: 'STARTING',
  siteUrl: `${base}/`,
  theme: null,
  demo: 'Architecture (Lite) / Elementor',
  demoImportId: 'inspiro-lite-architecture',
  plugins: {},
  pages: [],
  posts: [],
  media: [],
  verify: null,
  detail: null,
  updatedAt: new Date().toISOString()
};

const save = () => {
  result.updatedAt = new Date().toISOString();
  fs.writeFileSync(out, JSON.stringify(result, null, 2) + '\n');
};

const onLogin = page => /\/login(?:[/?#]|$)/i.test(page.url());

async function login(page) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      await page.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
      if (!onLogin(page)) return;
      const ident = page.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();
      await ident.waitFor({ state: 'visible', timeout: 15000 });
      await ident.fill(account.username || account.email);
      await ident.press('Enter');
      const pass = page.locator('input[type=password]').first();
      await pass.waitFor({ state: 'visible', timeout: 20000 });
      await pass.fill(account.password);
      await pass.press('Enter');
      await sleep(2200);
      if (!onLogin(page)) return;
    } catch {}
    await sleep(1000 * attempt);
  }
  throw new Error('wasmer_login_failed');
}

async function pollAdmin(ctx, timeoutMs = 30000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    for (const page of ctx.pages()) {
      if (page.url().startsWith(base) && /\/wp-admin(?:\/|\?|$)/i.test(page.url()) && !/wp-login\.php/i.test(page.url())) return page;
    }
    await sleep(500);
  }
  return null;
}

async function enterAdmin(ctx, page) {
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.goto(dashboard, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
    await sleep(900);
    const control = page.getByText(/WordPress Admin/i).first();
    if (await control.isVisible().catch(() => false)) {
      const href = await control.getAttribute('href').catch(() => null);
      if (href) {
        const wp = await ctx.newPage();
        await wp.goto(new URL(href, 'https://wasmer.io').href, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
        const found = await pollAdmin(ctx, 18000);
        if (found) return found;
      }
      await control.click({ noWaitAfter: true }).catch(() => {});
      const found = await pollAdmin(ctx, 22000);
      if (found) return found;
    }
  }
  throw new Error('magic_admin_failed');
}

async function nonce(wp) {
  await wp.goto(`${base}/wp-admin/`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await sleep(500);
  let value = await wp.evaluate(() => globalThis.wpApiSettings?.nonce || globalThis.wp?.apiSettings?.nonce || null).catch(() => null);
  if (!value) {
    const html = await wp.content();
    const match = html.match(/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i);
    if (match) value = match[1];
  }
  if (!value) throw new Error('wp_rest_nonce_missing');
  return value;
}

async function api(ctx, n, endpoint, { method = 'GET', json = null, headers = {} } = {}) {
  const requestHeaders = { 'X-WP-Nonce': n, Accept: 'application/json', ...headers };
  let data;
  if (json !== null) {
    requestHeaders['Content-Type'] = 'application/json';
    data = JSON.stringify(json);
  }
  const response = await ctx.request.fetch(`${base}/wp-json${endpoint}`, {
    method,
    headers: requestHeaders,
    data,
    timeout: 120000,
    failOnStatusCode: false
  });
  const text = await response.text();
  let body;
  try { body = JSON.parse(text); } catch { body = text; }
  if (!response.ok()) throw new Error(`api_${method}_${endpoint}:${response.status()}:${String(text).slice(0, 300)}`);
  return body;
}

async function ensureTheme(wp, themeSlug) {
  await wp.goto(`${base}/wp-admin/themes.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  let active = wp.locator(`.theme.active[data-slug="${themeSlug}"]`).first();
  if (await active.count()) return;

  let card = wp.locator(`.theme[data-slug="${themeSlug}"]`).first();
  if (!(await card.count())) {
    await wp.goto(`${base}/wp-admin/theme-install.php?search=${encodeURIComponent(themeSlug)}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await sleep(1600);
    let install = wp.locator(`a[href*="action=install-theme"][href*="theme=${themeSlug}"],a.theme-install[href*="${themeSlug}"]`).first();
    let href = await install.getAttribute('href').catch(() => null);
    if (!href) {
      const html = await wp.content();
      const re = new RegExp(`href=["']([^"']*(?:action=install-theme[^"']*theme=${themeSlug}|theme=${themeSlug}[^"']*action=install-theme)[^"']*)["']`, 'i');
      const match = html.match(re);
      if (match) href = match[1].replaceAll('&amp;', '&');
    }
    if (!href) throw new Error(`${themeSlug}_install_url_missing`);
    await wp.goto(new URL(href, base).href, { waitUntil: 'domcontentloaded', timeout: 120000 });
    await sleep(1200);
  }

  await wp.goto(`${base}/wp-admin/themes.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  card = wp.locator(`.theme[data-slug="${themeSlug}"]`).first();
  if (!(await card.count())) throw new Error(`${themeSlug}_not_installed`);
  active = wp.locator(`.theme.active[data-slug="${themeSlug}"]`).first();
  if (!(await active.count())) {
    const activate = card.locator('a.activate,a[href*="action=activate"]').first();
    const href = await activate.getAttribute('href').catch(() => null);
    if (!href) throw new Error(`${themeSlug}_activate_url_missing`);
    await wp.goto(new URL(href, base).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  }

  await wp.goto(`${base}/wp-admin/themes.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  active = wp.locator(`.theme.active[data-slug="${themeSlug}"]`).first();
  if (!(await active.count())) throw new Error(`${themeSlug}_activation_failed`);
}

async function listPlugins(ctx, n) {
  return api(ctx, n, '/wp/v2/plugins?context=edit');
}

async function ensurePlugin(ctx, n, slug, prefix) {
  const plugins = await listPlugins(ctx, n);
  let plugin = Array.isArray(plugins) ? plugins.find(item => String(item.plugin || '').startsWith(prefix)) : null;
  if (!plugin) plugin = await api(ctx, n, '/wp/v2/plugins', { method: 'POST', json: { slug, status: 'active' } });
  else if (plugin.status !== 'active') plugin = await api(ctx, n, `/wp/v2/plugins/${plugin.plugin.split('/').map(encodeURIComponent).join('/')}`, { method: 'POST', json: { status: 'active' } });
  result.plugins[slug] = plugin.status || 'active';
  return plugin;
}

async function removePlugin(ctx, n, prefix) {
  const plugins = await listPlugins(ctx, n);
  const plugin = Array.isArray(plugins) ? plugins.find(item => String(item.plugin || '').startsWith(prefix)) : null;
  if (!plugin) return false;
  if (plugin.status === 'active') {
    await api(ctx, n, `/wp/v2/plugins/${plugin.plugin.split('/').map(encodeURIComponent).join('/')}`, { method: 'POST', json: { status: 'inactive' } });
  }
  await api(ctx, n, `/wp/v2/plugins/${plugin.plugin.split('/').map(encodeURIComponent).join('/')}`, { method: 'DELETE' });
  return true;
}

async function deleteCollection(ctx, n, type) {
  let items = [];
  try { items = await api(ctx, n, `/wp/v2/${type}?per_page=100&context=edit`); } catch { return 0; }
  if (!Array.isArray(items)) return 0;
  for (const item of items) {
    await api(ctx, n, `/wp/v2/${type}/${item.id}?force=true`, { method: 'DELETE' }).catch(() => null);
  }
  return items.length;
}

async function resetContent(ctx, n) {
  await deleteCollection(ctx, n, 'menu-items');
  await deleteCollection(ctx, n, 'menus');
  await deleteCollection(ctx, n, 'posts');
  await deleteCollection(ctx, n, 'pages');
  await deleteCollection(ctx, n, 'media');
}

async function importArchitecture(wp) {
  const importerUrl = `${base}/wp-admin/admin.php?page=inspiro-demo`;
  await wp.goto(importerUrl, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await wp.waitForFunction(() => Array.isArray(globalThis.inspiro_starter_sites?.import_files), null, { timeout: 30000 });

  const demoMeta = await wp.evaluate(() => {
    const files = globalThis.inspiro_starter_sites?.import_files || [];
    const index = files.findIndex(item => item?.import_id === 'inspiro-lite-architecture');
    return { index, file: index >= 0 ? files[index] : null };
  });
  if (demoMeta.index < 0) throw new Error('inspiro_architecture_demo_not_found');

  const card = wp.locator('li[data-type]').filter({ hasText: /Architecture/i }).first();
  await card.waitFor({ state: 'visible', timeout: 30000 });
  const importLink = card.getByRole('link', { name: /Import Demo|Imported/i }).first();
  const href = await importLink.getAttribute('href');
  if (!href) throw new Error('inspiro_architecture_import_link_missing');

  await wp.goto(new URL(href, base).href, { waitUntil: 'domcontentloaded', timeout: 90000 });
  const launch = wp.locator('.js-inspiro-starter-sites-install-plugins-before-import').first();
  await launch.waitFor({ state: 'visible', timeout: 30000 });
  await launch.click();

  const success = wp.locator('.js-inspiro-starter-sites-imported').first();
  await success.waitFor({ state: 'visible', timeout: 12 * 60 * 1000 });
  const title = await wp.locator('.js-inspiro-starter-sites-ajax-response-title').first().innerText().catch(() => '');
  if (!/successfully imported/i.test(title)) throw new Error(`inspiro_import_not_confirmed:${title}`);
  await sleep(5000);
  return { index: demoMeta.index, title, importFile: demoMeta.file?.import_file_name || null };
}

async function inspectFront(ctx, n) {
  const [pages, posts, media, plugins] = await Promise.all([
    api(ctx, n, '/wp/v2/pages?per_page=100&context=edit'),
    api(ctx, n, '/wp/v2/posts?per_page=100&context=edit'),
    api(ctx, n, '/wp/v2/media?per_page=100&context=edit'),
    listPlugins(ctx, n)
  ]);

  const res = await ctx.request.get(`${base}/`, { timeout: 90000, failOnStatusCode: false });
  const html = await res.text();
  const imageCount = (html.match(/<img\b/gi) || []).length;
  const localImageCount = (html.match(new RegExp(base.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || []).length;
  const navLinks = (html.match(/<a\b/gi) || []).length;
  const elementorMarkers = (html.match(/elementor-/gi) || []).length;
  const activePlugins = Object.fromEntries((Array.isArray(plugins) ? plugins : []).map(p => [p.plugin, p.status]));

  result.pages = (Array.isArray(pages) ? pages : []).map(p => ({ id: p.id, slug: p.slug, title: p.title?.rendered || '' }));
  result.posts = (Array.isArray(posts) ? posts : []).map(p => ({ id: p.id, slug: p.slug, title: p.title?.rendered || '', featured_media: p.featured_media || 0 }));
  result.media = (Array.isArray(media) ? media : []).map(m => ({ id: m.id, slug: m.slug, source_url: m.source_url || '' }));

  return {
    http: res.status(),
    htmlBytes: Buffer.byteLength(html),
    images: imageCount,
    localAssetRefs: localImageCount,
    navLinks,
    elementorMarkers,
    hasElementorFrontend: /elementor-frontend|elementor-page/i.test(html),
    inspiroBodyClass: /wp-theme-inspiro|theme-inspiro/i.test(html),
    pageCount: result.pages.length,
    postCount: result.posts.length,
    mediaCount: result.media.length,
    activePlugins
  };
}

const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
let page = await ctx.newPage();

try {
  save();
  await login(page);
  const wp = await enterAdmin(ctx, page);
  let n = await nonce(wp);

  await removePlugin(ctx, n, 'runner3-speed/').catch(() => false);
  await ensureTheme(wp, 'inspiro');
  n = await nonce(wp);
  await resetContent(ctx, n);

  const required = [
    ['inspiro-starter-sites', 'inspiro-starter-sites/'],
    ['elementor', 'elementor/'],
    ['wpzoom-elementor-addons', 'wpzoom-elementor-addons/'],
    ['wpzoom-portfolio', 'wpzoom-portfolio/'],
    ['social-icons-widget-by-wpzoom', 'social-icons-widget-by-wpzoom/'],
    ['wpzoom-forms', 'wpzoom-forms/']
  ];
  for (const [pluginSlug, prefix] of required) {
    await ensurePlugin(ctx, n, pluginSlug, prefix);
    n = await nonce(wp);
  }

  const imported = await importArchitecture(wp);
  n = await nonce(wp);
  const verify = await inspectFront(ctx, n);
  result.theme = 'inspiro';
  result.verify = { ...verify, imported };

  const hardGates = {
    homepage200: verify.http === 200,
    themeInspiro: verify.inspiroBodyClass,
    trueElementorContent: verify.elementorMarkers >= 10 && verify.hasElementorFrontend,
    pagesImported: verify.pageCount >= 4,
    mediaImported: verify.mediaCount >= 8,
    visuallyRichHomepage: verify.images >= 4 && verify.navLinks >= 5 && verify.htmlBytes >= 30000,
    importerConfirmed: /successfully imported/i.test(imported.title || '')
  };
  result.verify.gates = hardGates;
  if (!Object.values(hardGates).every(Boolean)) throw new Error(`fixture_gates_failed:${JSON.stringify(hardGates)}`);

  result.status = 'READY';
  result.detail = 'Inspiro Architecture Elementor starter site imported through the official Inspiro Starter Sites importer; real demo pages/media/settings are in place.';
} catch (error) {
  result.status = 'FAILED';
  result.detail = error?.stack || String(error);
  throw error;
} finally {
  save();
  await browser.close();
}
