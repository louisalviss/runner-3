import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const statusFile = `ops/site-factory/${slug}.json`;
const siteUrlOverride = String(process.env.WP_SITE_URL || '').trim();
const dashboardOverride = String(process.env.WP_DASHBOARD_URL || '').trim();
const adminBaseOverride = String(process.env.WP_ADMIN_BASE || '').trim();
const verifyPath = String(process.env.WP_VERIFY_PATH || '/2026/08/18/bentley-introduces-merino-wool-interior-for-upcoming-torcal-ev/').trim() || '/';

let site = {};
if (fs.existsSync(statusFile)) {
  site = JSON.parse(fs.readFileSync(statusFile, 'utf8'));
} else if (!siteUrlOverride || !dashboardOverride) {
  throw new Error(`site factory state missing: ${statusFile}`);
}
if (!fs.existsSync('/tmp/wasmer-account.json')) throw new Error('decrypted Wasmer account state missing');

const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(siteUrlOverride || site.siteUrl || '').replace(/\/$/, '');
if (!base) throw new Error('site_url_missing');
const dashboard = dashboardOverride || site.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName)}`;
const adminBase = String(adminBaseOverride || base).replace(/\/$/, '');
const out = '/tmp/wp-noindex-result.json';

const allowedAdminHosts = new Set();
for (const candidate of [base, adminBase]) {
  try { allowedAdminHosts.add(new URL(candidate).host); } catch {}
}
function isAllowedAdminUrl(raw) {
  try {
    const u = new URL(raw);
    return allowedAdminHosts.has(u.host) && /\/wp-admin(?:[/?#]|$)/i.test(u.pathname + u.search + u.hash);
  } catch {
    return false;
  }
}

const safe = {
  status: 'starting',
  siteSlug: slug,
  siteUrl: base + '/',
  dashboardUrl: dashboard,
  adminBase,
  readingPageReached: false,
  settingChanged: false,
  saved: false,
  frontendHttp: null,
  metaRobots: [],
  hasNoindex: false,
  hasNofollow: false,
  detail: null,
  updatedAt: new Date().toISOString(),
};
function save() { safe.updatedAt = new Date().toISOString(); fs.writeFileSync(out, JSON.stringify(safe, null, 2)); }
async function bodyText(page) { return (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ').trim(); }

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
    if (isAllowedAdminUrl(wp.url())) return wp;
    await wp.close().catch(() => {});
  }
  const before = new Set(ctx.pages());
  const popupPromise = ctx.waitForEvent('page', { timeout: 10000 }).catch(() => null);
  await admin.click().catch(() => {});
  const popup = await popupPromise;
  await page.waitForTimeout(3000);
  const candidates = [...ctx.pages().filter(p => !before.has(p)), popup, page].filter(Boolean);
  for (const p of candidates) if (isAllowedAdminUrl(p.url())) return p;
  throw new Error('magic_admin_failed');
}

function inspectRobots(html) {
  const metas = [];
  const re = /<meta\b[^>]*\bname\s*=\s*["']robots["'][^>]*>/gi;
  for (const tag of html.match(re) || []) {
    const m = tag.match(/\bcontent\s*=\s*["']([^"']*)["']/i);
    metas.push(m ? m[1] : '');
  }
  const joined = metas.join(',').toLowerCase();
  return {
    metaRobots: metas,
    hasNoindex: /(^|[\s,])noindex([\s,]|$)/.test(joined),
    hasNofollow: /(^|[\s,])nofollow([\s,]|$)/.test(joined),
  };
}

const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await ctx.newPage();
try {
  save();
  await loginWasmer(page);
  const wp = await enterAdmin(ctx, page);
  const wpAdminOrigin = new URL(wp.url()).origin;
  safe.adminOriginUsed = wpAdminOrigin;
  save();

  await wp.goto(`${wpAdminOrigin}/wp-admin/options-reading.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(1000);
  safe.readingPageReached = true; save();

  // WordPress uses blog_public=0 for the "Discourage search engines" control.
  const off = wp.locator('input[name="blog_public"][value="0"]').first();
  if (await off.count()) {
    if (!(await off.isChecked().catch(() => false))) {
      await off.check({ force: true });
      safe.settingChanged = true;
    }
  } else {
    throw new Error('search_engine_visibility_control_missing');
  }
  save();

  let submit = wp.locator('#submit,input[type=submit][name=submit],button[type=submit]').first();
  if (!(await submit.count())) submit = wp.getByRole('button', { name: /save changes/i }).first();
  if (!(await submit.count())) throw new Error('reading_settings_submit_missing');
  await Promise.all([
    wp.waitForLoadState('domcontentloaded').catch(() => {}),
    submit.click(),
  ]);
  await wp.waitForTimeout(1500);
  const txt = await bodyText(wp);
  if (!/settings saved|saved/i.test(txt)) {
    // Hosts can customize the admin notice; persistence and frontend checks below are authoritative.
  }
  safe.saved = true; save();

  // Verify the option survived a reload.
  await wp.goto(`${wpAdminOrigin}/wp-admin/options-reading.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const offAfter = wp.locator('input[name="blog_public"][value="0"]').first();
  if (!(await offAfter.count()) || !(await offAfter.isChecked().catch(() => false))) {
    throw new Error('blog_public_off_not_persisted');
  }

  // Verify the actual public HTML, not only the admin setting.
  const verifyUrl = new URL(verifyPath, base + '/').href;
  safe.verifyUrl = verifyUrl;
  const response = await ctx.request.get(verifyUrl, { headers: { Accept: 'text/html' } });
  safe.frontendHttp = response.status();
  const html = await response.text();
  Object.assign(safe, inspectRobots(html));
  if (!safe.hasNoindex) throw new Error(`frontend_noindex_missing:${safe.metaRobots.join('|')}`);

  safe.status = 'ok';
  save();
  console.log(`WP_NOINDEX_OK site=${slug} robots=${safe.metaRobots.join(',')}`);
} catch (e) {
  safe.status = 'failed';
  safe.detail = String(e?.message || e);
  save();
  console.error(`WP_NOINDEX_FAILED ${safe.detail}`);
  process.exitCode = 1;
} finally {
  await browser.close().catch(() => {});
}
