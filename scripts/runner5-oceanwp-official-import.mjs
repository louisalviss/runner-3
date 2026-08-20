import { chromium } from 'playwright-core';
import fs from 'fs';

const site = JSON.parse(fs.readFileSync('ops/site-factory/runner5-restore-lab-1.json', 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(site.siteUrl || 'https://runner5-restore-lab-1.wasmer.app/').replace(/\/$/, '');
const dashboard = site.dashboardUrl;
const out = '/tmp/runner5-oceanwp-official-demo.json';
const result = {
  status: 'STARTING', siteUrl: base + '/', theme: 'oceanwp', demo: 'Travel', source: 'OceanWP official importer',
  noindex: false, template: null, pages: [], posts: [], mediaCount: 0, homeImages: 0, uploadRefs: 0,
  imports: {}, plugins: {}, stage: 'init', detail: null, updatedAt: new Date().toISOString(),
};
const save = () => { result.updatedAt = new Date().toISOString(); fs.writeFileSync(out, JSON.stringify(result, null, 2)); };
const stage = (s) => { result.stage = s; console.log('STAGE', s); save(); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const onWasmerLogin = (p) => /\/login(?:[/?#]|$)/i.test(p.url());

async function loginWasmer(p) {
  stage('wasmer_login');
  await p.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
  await p.waitForTimeout(600);
  if (!onWasmerLogin(p)) return;
  const user = p.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();
  await user.fill(account.username || account.email); await user.press('Enter');
  const pass = p.locator('input[type=password]').first(); await pass.waitFor({ state: 'visible', timeout: 20000 });
  await pass.fill(account.password); await pass.press('Enter');
  const end = Date.now() + 20000;
  while (Date.now() < end) { if (!onWasmerLogin(p)) return; await p.waitForTimeout(350); }
  throw new Error('wasmer_login_failed');
}

async function pollWpAdmin(ctx, ms = 22000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    for (const p of ctx.pages()) if (p.url().startsWith(base) && /\/wp-admin(?:\/|\?|$)/i.test(p.url()) && !/wp-login\.php/i.test(p.url())) return p;
    await sleep(400);
  }
  return null;
}

async function enterWpAdmin(ctx, p) {
  stage('wordpress_admin');
  for (let attempt = 0; attempt < 3; attempt++) {
    await p.goto(dashboard, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {}); await p.waitForTimeout(800);
    let admin = p.getByText(/WordPress Admin/i).first();
    if (!await admin.isVisible().catch(() => false)) {
      const settings = p.getByText(/^Settings$/i).first();
      if (await settings.isVisible().catch(() => false)) {
        await settings.click().catch(() => {}); await p.waitForTimeout(450);
        const wp = p.getByText(/^WordPress$/i).first();
        if (await wp.isVisible().catch(() => false)) { await wp.click().catch(() => {}); await p.waitForTimeout(450); }
        admin = p.getByText(/WordPress Admin/i).first();
      }
    }
    if (await admin.isVisible().catch(() => false)) {
      const href = await admin.getAttribute('href').catch(() => null);
      if (href) {
        const wp = await ctx.newPage();
        await wp.goto(new URL(href, 'https://wasmer.io').href, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
        const found = await pollWpAdmin(ctx, 18000); if (found) return found;
      }
      await admin.click({ noWaitAfter: true }).catch(() => {});
      const found = await pollWpAdmin(ctx, 20000); if (found) return found;
    }
  }
  throw new Error('magic_admin_failed');
}

async function getNonce(wp) {
  await wp.goto(`${base}/wp-admin/`, { waitUntil: 'domcontentloaded', timeout: 60000 }); await wp.waitForTimeout(500);
  let nonce = await wp.evaluate(() => globalThis.wpApiSettings?.nonce || globalThis.wp?.apiSettings?.nonce || null).catch(() => null);
  if (!nonce) { const html = await wp.content(); const m = html.match(/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i); if (m) nonce = m[1]; }
  if (!nonce) throw new Error('wp_rest_nonce_missing');
  return nonce;
}

async function api(ctx, nonce, path, { method = 'GET', json = null, soft = false, timeout = 180000 } = {}) {
  const headers = { 'X-WP-Nonce': nonce, Accept: 'application/json' }; let data;
  if (json !== null) { headers['Content-Type'] = 'application/json'; data = JSON.stringify(json); }
  const r = await ctx.request.fetch(`${base}/wp-json${path}`, { method, headers, data, timeout, failOnStatusCode: false });
  const text = await r.text(); let body; try { body = JSON.parse(text); } catch { body = text; }
  if (!r.ok()) { if (soft) return { ok: false, status: r.status(), data: body }; throw new Error(`api_${method}_${path}:${r.status()}:${String(text).slice(0,400)}`); }
  return soft ? { ok: true, status: r.status(), data: body } : body;
}

async function ensurePlugin(ctx, nonce, slug, prefix = `${slug}/`) {
  const ps = await api(ctx, nonce, '/wp/v2/plugins?context=edit');
  let p = Array.isArray(ps) ? ps.find((x) => String(x.plugin || '').startsWith(prefix)) : null;
  if (!p) p = await api(ctx, nonce, '/wp/v2/plugins', { method: 'POST', json: { slug, status: 'active' }, timeout: 180000 });
  else if (p.status !== 'active') p = await api(ctx, nonce, `/wp/v2/plugins/${encodeURIComponent(p.plugin)}`, { method: 'POST', json: { status: 'active' }, timeout: 120000 });
  result.plugins[slug] = p?.status || 'active'; save(); return p;
}

async function ensureOceanTheme(wp) {
  stage('oceanwp_theme');
  await wp.goto(`${base}/wp-admin/themes.php`, { waitUntil: 'domcontentloaded', timeout: 60000 }); await wp.waitForTimeout(1000);
  let card = wp.locator('.theme[data-slug="oceanwp"]').first();
  if (!await card.count()) {
    await wp.goto(`${base}/wp-admin/theme-install.php?search=oceanwp`, { waitUntil: 'domcontentloaded', timeout: 60000 }); await wp.waitForTimeout(1500);
    card = wp.locator('.theme[data-slug="oceanwp"]').first();
    await card.waitFor({ state: 'visible', timeout: 15000 });
    const install = card.getByRole('button', { name: /Install/i }).first();
    const installLink = card.getByRole('link', { name: /Install/i }).first();
    if (await install.isVisible().catch(() => false)) await install.click();
    else if (await installLink.isVisible().catch(() => false)) await installLink.click();
    else throw new Error('oceanwp_install_control_missing');
    const end = Date.now() + 90000;
    while (Date.now() < end) {
      const active = card.getByRole('button', { name: /Activate/i }).first();
      const activeLink = card.getByRole('link', { name: /Activate/i }).first();
      if (await active.isVisible().catch(() => false)) { await active.click(); break; }
      if (await activeLink.isVisible().catch(() => false)) { await activeLink.click(); break; }
      await wp.waitForTimeout(1000);
    }
  } else {
    if (!/active/i.test(await card.getAttribute('class') || '')) {
      const activate = card.getByRole('link', { name: /Activate/i }).first();
      if (await activate.isVisible().catch(() => false)) await activate.click();
      else {
        await wp.goto(`${base}/wp-admin/themes.php?theme=oceanwp`, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
        const a = wp.getByRole('link', { name: /Activate/i }).first(); if (await a.isVisible().catch(() => false)) await a.click();
      }
    }
  }
  await wp.waitForTimeout(1800);
  await wp.goto(`${base}/wp-admin/themes.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const activeOcean = wp.locator('.theme.active[data-slug="oceanwp"]').first();
  if (!await activeOcean.count()) throw new Error('oceanwp_activation_failed');
}

async function setNoindex(wp) {
  stage('confirm_noindex');
  await wp.goto(`${base}/wp-admin/options-reading.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const box = wp.locator('input[name="blog_public"]').first(); await box.waitFor({ state: 'attached', timeout: 15000 });
  if (!await box.isChecked()) { await box.check(); await wp.locator('#submit,input[type=submit]').first().click(); await wp.waitForLoadState('domcontentloaded').catch(() => {}); }
  result.noindex = await wp.locator('input[name="blog_public"]').first().isChecked().catch(() => false); save();
  if (!result.noindex) throw new Error('noindex_not_set');
}

async function getOceanAjaxNonce(wp) {
  await wp.goto(`${base}/wp-admin/admin.php?page=oceanwp-panel`, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {}); await wp.waitForTimeout(1200);
  let n = await wp.evaluate(() => globalThis.oeOnboardingLoc?.nonce || null).catch(() => null);
  if (!n) {
    const html = await wp.content();
    const m = html.match(/oeOnboardingLoc\s*=\s*\{[\s\S]*?["']nonce["']\s*:\s*["']([^"']+)/i); if (m) n = m[1];
  }
  if (!n) throw new Error('oceanwp_onboarding_nonce_missing');
  return n;
}

async function oceanAjax(ctx, nonce, action, fields = {}, timeout = 300000) {
  const params = new URLSearchParams({ action, nonce, ...Object.fromEntries(Object.entries(fields).map(([k,v]) => [k, String(v)])) });
  const r = await ctx.request.fetch(`${base}/wp-admin/admin-ajax.php`, {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', Accept: 'application/json' },
    data: params.toString(), timeout, failOnStatusCode: false,
  });
  const text = await r.text(); let body; try { body = JSON.parse(text); } catch { body = text; }
  if (!r.ok()) throw new Error(`ocean_ajax_${action}:${r.status()}:${String(text).slice(0,700)}`);
  if (body && typeof body === 'object' && body.success === false) throw new Error(`ocean_ajax_${action}_failed:${JSON.stringify(body).slice(0,1000)}`);
  return body;
}

async function snapshot(ctx, nonce) {
  const [pages, posts, media] = await Promise.all([
    api(ctx, nonce, '/wp/v2/pages?context=edit&per_page=100&_fields=id,slug,title,status'),
    api(ctx, nonce, '/wp/v2/posts?context=edit&per_page=100&_fields=id,slug,title,status'),
    api(ctx, nonce, '/wp/v2/media?context=edit&per_page=100&_fields=id,source_url'),
  ]);
  return { pages: Array.isArray(pages) ? pages : [], posts: Array.isArray(posts) ? posts : [], media: Array.isArray(media) ? media : [] };
}

const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } }); const p = await ctx.newPage();
try {
  await loginWasmer(p);
  const wp = await enterWpAdmin(ctx, p);
  await ensureOceanTheme(wp);
  let nonce = await getNonce(wp);
  await ensurePlugin(ctx, nonce, 'ocean-extra', 'ocean-extra/');
  await ensurePlugin(ctx, nonce, 'elementor', 'elementor/').catch(() => null);
  await ensurePlugin(ctx, nonce, 'ocean-elementor-widgets', 'ocean-elementor-widgets/').catch(() => null);
  await ensurePlugin(ctx, nonce, 'wpforms-lite', 'wpforms-lite/').catch(() => null);
  await setNoindex(wp);
  nonce = await getNonce(wp);

  stage('template_catalog');
  let catalog = await api(ctx, nonce, '/oceanwp/v1/onboarding/get-templates');
  let templates = catalog?.data;
  if (typeof templates === 'string') { try { templates = JSON.parse(templates); } catch {} }
  if (!Array.isArray(templates) || !templates.length) {
    const sync = await api(ctx, nonce, '/oceanwp/v1/onboarding/sync-templates', { method: 'POST', json: {} });
    templates = sync?.data; if (typeof templates === 'string') { try { templates = JSON.parse(templates); } catch {} }
  }
  if (!Array.isArray(templates) || !templates.length) throw new Error('oceanwp_template_catalog_empty');
  let template = templates.find((x) => /travel/i.test(String(x?.slug || ''))) || templates.find((x) => /travel/i.test(String(x?.title || x?.name || '')));
  if (!template) template = templates.find((x) => !(x?.premium || x?.is_premium || x?.pro || x?.is_pro)) || templates[0];
  result.template = template; result.demo = template?.title || template?.name || template?.slug || 'OceanWP Demo'; save();

  stage('select_template');
  await api(ctx, nonce, '/oceanwp/v1/onboarding/select-template', { method: 'POST', json: { selected_template: JSON.stringify(template) } });

  stage('reset_site');
  await api(ctx, nonce, '/oceanwp/v1/onboarding/reset-site', { method: 'POST', json: { resetOptions: ['pages','posts','media','menus','customizer-settings'] }, timeout: 180000 });

  const oceanNonce = await getOceanAjaxNonce(wp);
  stage('import_content'); result.imports.content = await oceanAjax(ctx, oceanNonce, 'oceanwp_onboarding_import_data', { importType: 'content' }, 360000); save();
  stage('import_customizer'); result.imports.customizer = await oceanAjax(ctx, oceanNonce, 'oceanwp_onboarding_import_data', { importType: 'customizer' }, 180000); save();
  stage('import_widgets'); result.imports.widgets = await oceanAjax(ctx, oceanNonce, 'oceanwp_onboarding_import_data', { importType: 'widgets' }, 180000).catch((e) => ({ warning: String(e) })); save();
  stage('import_form'); result.imports.form = await oceanAjax(ctx, oceanNonce, 'oceanwp_onboarding_import_data', { importType: 'form' }, 180000).catch((e) => ({ warning: String(e) })); save();
  stage('after_import'); result.imports.after = await oceanAjax(ctx, oceanNonce, 'oceanwp_onboarding_after_import', { xml_import_status: 'success' }, 180000); save();

  await setNoindex(wp);
  nonce = await getNonce(wp);
  stage('verify');
  const now = await snapshot(ctx, nonce);
  result.pages = now.pages.map((x) => ({ id: x.id, slug: x.slug, title: x.title?.rendered || '', status: x.status }));
  result.posts = now.posts.map((x) => ({ id: x.id, slug: x.slug, title: x.title?.rendered || '', status: x.status }));
  result.mediaCount = now.media.length;
  const r = await fetch(`${base}/?ocean=${Date.now()}`, { headers: { 'Cache-Control': 'no-cache', 'User-Agent': 'Runner5OceanWPVerify/1.0' } });
  const html = await r.text(); result.homeImages = (html.match(/<img\b/gi) || []).length; result.uploadRefs = (html.match(/wp-content\/uploads\//gi) || []).length;
  const oceanMarker = /oceanwp|oceanwp-theme|oceanwp-style/i.test(html);
  const publicNoindex = /<meta[^>]+name=["']robots["'][^>]+noindex/i.test(html) || /noindex[^>]+nofollow/i.test(html);
  result.noindex = result.noindex && publicNoindex; save();
  if (!r.ok) throw new Error(`public_home_http_${r.status}`);
  if (!oceanMarker) throw new Error('oceanwp_marker_missing');
  if (result.pages.length < 3) throw new Error(`oceanwp_pages_too_few:${result.pages.length}`);
  if (result.mediaCount < 5) throw new Error(`oceanwp_media_too_few:${result.mediaCount}`);
  if (result.homeImages + result.uploadRefs < 3) throw new Error(`oceanwp_home_visuals_too_few:${result.homeImages}:${result.uploadRefs}`);
  if (!result.noindex) throw new Error('public_noindex_missing');
  result.status = 'READY'; result.stage = 'done'; result.detail = null; save();
} catch (e) {
  result.status = 'FAILED'; result.detail = String(e?.stack || e); save(); console.error(result.detail); process.exitCode = 1;
} finally { await browser.close(); }
console.log(JSON.stringify(result, null, 2));
