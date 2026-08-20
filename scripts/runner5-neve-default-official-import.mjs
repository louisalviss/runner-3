import { chromium } from 'playwright-core';
import fs from 'fs';

const site = JSON.parse(fs.readFileSync('ops/site-factory/runner5-restore-lab-1.json', 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(site.siteUrl || 'https://runner5-restore-lab-1.wasmer.app/').replace(/\/$/, '');
const dashboard = site.dashboardUrl;
const out = '/tmp/runner5-neve-official-demo.json';
const result = {
  status: 'STARTING',
  siteUrl: base + '/',
  theme: 'neve',
  demo: 'Default',
  tier: 'Free',
  source: 'Neve > Starter Sites official UI',
  noindex: false,
  pages: [],
  posts: [],
  mediaCount: 0,
  homeImages: 0,
  homeUploadRefs: 0,
  stage: 'init',
  detail: null,
  uiTail: null,
  updatedAt: new Date().toISOString(),
};
const save = () => {
  result.updatedAt = new Date().toISOString();
  fs.writeFileSync(out, JSON.stringify(result, null, 2));
};
const stage = (s) => { result.stage = s; console.log('STAGE', s); save(); };
const onWasmerLogin = (p) => /\/login(?:[/?#]|$)/i.test(p.url());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function loginWasmer(p) {
  stage('wasmer_login');
  await p.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
  await p.waitForTimeout(600);
  if (!onWasmerLogin(p)) return;
  const user = p.locator('input[name=username],input[autocomplete=username],input[type=email],input[type=text]').first();
  await user.fill(account.username || account.email);
  await user.press('Enter');
  const pass = p.locator('input[type=password]').first();
  await pass.waitFor({ state: 'visible', timeout: 20000 });
  await pass.fill(account.password);
  await pass.press('Enter');
  const end = Date.now() + 20000;
  while (Date.now() < end) {
    if (!onWasmerLogin(p)) return;
    await p.waitForTimeout(350);
  }
  throw new Error('wasmer_login_failed');
}

async function pollWpAdmin(ctx, ms = 22000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    for (const p of ctx.pages()) {
      if (p.url().startsWith(base) && /\/wp-admin(?:\/|\?|$)/i.test(p.url()) && !/wp-login\.php/i.test(p.url())) return p;
    }
    await sleep(400);
  }
  return null;
}

async function enterWpAdmin(ctx, p) {
  stage('wordpress_admin');
  for (let attempt = 0; attempt < 3; attempt++) {
    await p.goto(dashboard, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
    await p.waitForTimeout(800);
    let admin = p.getByText(/WordPress Admin/i).first();
    if (!await admin.isVisible().catch(() => false)) {
      const settings = p.getByText(/^Settings$/i).first();
      if (await settings.isVisible().catch(() => false)) {
        await settings.click().catch(() => {});
        await p.waitForTimeout(450);
        const wp = p.getByText(/^WordPress$/i).first();
        if (await wp.isVisible().catch(() => false)) {
          await wp.click().catch(() => {});
          await p.waitForTimeout(450);
        }
        admin = p.getByText(/WordPress Admin/i).first();
      }
    }
    if (await admin.isVisible().catch(() => false)) {
      const href = await admin.getAttribute('href').catch(() => null);
      if (href) {
        const wp = await ctx.newPage();
        await wp.goto(new URL(href, 'https://wasmer.io').href, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
        const found = await pollWpAdmin(ctx, 18000);
        if (found) return found;
      }
      await admin.click({ noWaitAfter: true }).catch(() => {});
      const found = await pollWpAdmin(ctx, 20000);
      if (found) return found;
    }
  }
  throw new Error('magic_admin_failed');
}

async function getNonce(wp) {
  await wp.goto(`${base}/wp-admin/`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(500);
  let nonce = await wp.evaluate(() => globalThis.wpApiSettings?.nonce || globalThis.wp?.apiSettings?.nonce || null).catch(() => null);
  if (!nonce) {
    const html = await wp.content();
    const m = html.match(/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i);
    if (m) nonce = m[1];
  }
  if (!nonce) throw new Error('wp_rest_nonce_missing');
  return nonce;
}

async function api(ctx, nonce, path) {
  const r = await ctx.request.fetch(`${base}/wp-json${path}`, {
    headers: { 'X-WP-Nonce': nonce, Accept: 'application/json' },
    timeout: 60000,
    failOnStatusCode: false,
  });
  const text = await r.text();
  let data;
  try { data = JSON.parse(text); } catch { data = text; }
  if (!r.ok()) throw new Error(`api_${path}:${r.status()}:${String(text).slice(0, 220)}`);
  return data;
}

async function snapshot(ctx, nonce) {
  const [pages, posts, media] = await Promise.all([
    api(ctx, nonce, '/wp/v2/pages?context=edit&per_page=100&_fields=id,slug,title,status'),
    api(ctx, nonce, '/wp/v2/posts?context=edit&per_page=100&_fields=id,slug,title,status'),
    api(ctx, nonce, '/wp/v2/media?context=edit&per_page=100&_fields=id,source_url'),
  ]);
  return { pages: Array.isArray(pages) ? pages : [], posts: Array.isArray(posts) ? posts : [], media: Array.isArray(media) ? media : [] };
}

async function setNoindex(wp) {
  stage('confirm_noindex');
  await wp.goto(`${base}/wp-admin/options-reading.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const box = wp.locator('input[name="blog_public"]').first();
  await box.waitFor({ state: 'attached', timeout: 15000 });
  if (!await box.isChecked()) {
    await box.check();
    await wp.locator('#submit,input[type=submit]').first().click();
    await wp.waitForLoadState('domcontentloaded').catch(() => {});
  }
  result.noindex = await wp.locator('input[name="blog_public"]').first().isChecked().catch(() => false);
  save();
  if (!result.noindex) throw new Error('noindex_not_set');
}

async function bodyText(wp) {
  return (await wp.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ').trim();
}

async function clickAny(wp, patterns, timeout = 500) {
  for (const re of patterns) {
    const candidates = [
      wp.getByRole('button', { name: re }).first(),
      wp.getByRole('link', { name: re }).first(),
      wp.getByText(re).first(),
    ];
    for (const loc of candidates) {
      if (await loc.isVisible({ timeout }).catch(() => false)) {
        console.log('CLICK', String(re));
        await loc.click().catch(() => {});
        await wp.waitForTimeout(650);
        return true;
      }
    }
  }
  return false;
}

async function openDefaultStarter(wp) {
  stage('starter_sites_ui');
  await wp.goto(`${base}/wp-admin/admin.php?page=neve-onboarding`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(3000);
  let text = await bodyText(wp);
  result.uiTail = text.slice(-1800); save();
  if (!/Choose a design|starter sites|Nearly 200 starter sites/i.test(text)) throw new Error('neve_starter_catalog_not_loaded:' + text.slice(-900));

  // The current Neve catalog exposes the official free "Default" starter near the top.
  const root = wp.locator('#wpbody-content');
  const titles = root.getByText(/^Default$/i);
  let chosen = null;
  const count = await titles.count();
  for (let i = 0; i < count; i++) {
    const c = titles.nth(i);
    if (await c.isVisible().catch(() => false)) { chosen = c; break; }
  }
  if (!chosen) throw new Error('official_free_default_card_missing:' + text.slice(-1200));
  await chosen.scrollIntoViewIfNeeded().catch(() => {});
  await chosen.click();
  await wp.waitForTimeout(1800);
  text = await bodyText(wp);
  result.uiTail = text.slice(-1800); save();
  if (/Default\s+PRO/i.test(text)) throw new Error('default_unexpectedly_pro');
}

async function triggerImportAndWait(ctx, wp, nonce, before) {
  stage('official_import');
  const beforePageIds = new Set(before.pages.map((x) => x.id));
  const beforeMediaIds = new Set(before.media.map((x) => x.id));
  let importClicked = false;
  const end = Date.now() + 4 * 60 * 1000;

  while (Date.now() < end) {
    const text = await bodyText(wp);
    result.uiTail = text.slice(-1900); save();
    if (/Import Failed|Failed to Import|Import Error/i.test(text)) throw new Error('official_ui_import_failed:' + text.slice(-1000));

    // Prefer complete-site import. These are only official Neve UI actions.
    if (!importClicked) {
      const clicked = await clickAny(wp, [
        /Import Complete Site/i,
        /Import Website/i,
        /Import Site/i,
        /Start Import/i,
        /^Import$/i,
      ], 450);
      if (clicked) { importClicked = true; await wp.waitForTimeout(1000); }
      else {
        // Some versions expose builder/plugin/setup screens first.
        if (await clickAny(wp, [/^Gutenberg$/i, /Block Editor/i, /WordPress Editor/i], 250)) continue;
        if (await clickAny(wp, [/Continue/i, /Next/i], 250)) continue;
      }
    } else {
      // A confirmation screen may expose a second explicit import button.
      await clickAny(wp, [/Import Website/i, /Import Site/i, /Start Import/i, /^Import$/i], 250);
      await clickAny(wp, [/Continue/i], 180);
    }

    let now;
    try { now = await snapshot(ctx, nonce); } catch { now = null; }
    if (now) {
      const newPages = now.pages.filter((x) => !beforePageIds.has(x.id));
      const newMedia = now.media.filter((x) => !beforeMediaIds.has(x.id));
      console.log('IMPORT_COUNTS', { pages: now.pages.length, media: now.media.length, newPages: newPages.length, newMedia: newMedia.length });
      if (now.pages.length >= 3 && now.media.length >= 3 && (newPages.length >= 3 || before.pages.length === 0)) return now;
    }
    await wp.waitForTimeout(1800);
  }
  throw new Error('official_import_timeout:' + result.uiTail);
}

async function verify(ctx, wp, nonce) {
  stage('verify_official_demo');
  const now = await snapshot(ctx, nonce);
  result.pages = now.pages.map((x) => ({ id: x.id, slug: x.slug, title: x.title?.rendered || '', status: x.status }));
  result.posts = now.posts.map((x) => ({ id: x.id, slug: x.slug, title: x.title?.rendered || '', status: x.status }));
  result.mediaCount = now.media.length;
  const r = await fetch(`${base}/?official=${Date.now()}`, { headers: { 'Cache-Control': 'no-cache', 'User-Agent': 'Runner5NeveDefaultVerify/1.0' } });
  const html = await r.text();
  result.homeImages = (html.match(/<img\b/gi) || []).length;
  result.homeUploadRefs = (html.match(/wp-content\/uploads\//gi) || []).length;
  const noidx = /<meta[^>]+name=["']robots["'][^>]+noindex/i.test(html) || /noindex[^>]+nofollow/i.test(html);
  result.noindex = result.noindex && noidx;
  save();

  if (!r.ok) throw new Error(`public_home_http_${r.status}`);
  if (result.pages.length < 3) throw new Error(`official_pages_too_few:${result.pages.length}`);
  if (result.mediaCount < 3) throw new Error(`official_media_too_few:${result.mediaCount}`);
  if (result.homeImages + result.homeUploadRefs < 3) throw new Error(`official_home_visuals_too_few:img=${result.homeImages}:uploads=${result.homeUploadRefs}`);
  if (!result.noindex) throw new Error('public_noindex_missing');
}

const chromePath = process.env.CHROME_PATH;
if (!chromePath) throw new Error('CHROME_PATH_missing');
const browser = await chromium.launch({ headless: true, executablePath: chromePath, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
const p = await ctx.newPage();
try {
  await loginWasmer(p);
  const wp = await enterWpAdmin(ctx, p);
  await setNoindex(wp);
  const nonce = await getNonce(wp);
  const before = await snapshot(ctx, nonce);
  await openDefaultStarter(wp);
  await triggerImportAndWait(ctx, wp, nonce, before);
  await setNoindex(wp);
  const verifyNonce = await getNonce(wp);
  await verify(ctx, wp, verifyNonce);
  result.status = 'READY';
  result.stage = 'done';
  result.detail = null;
  save();
} catch (e) {
  result.status = 'FAILED';
  result.detail = String(e?.stack || e);
  try { result.uiTail = (await bodyText(ctx.pages().at(-1))).slice(-2200); } catch {}
  save();
  console.error(result.detail);
  process.exitCode = 1;
} finally {
  await browser.close();
}
console.log(JSON.stringify(result, null, 2));
