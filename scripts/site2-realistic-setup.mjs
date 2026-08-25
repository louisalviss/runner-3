#!/usr/bin/env node

import fs from 'node:fs';
import { chromium } from 'playwright-core';

const target = (process.env.SITE2_URL || 'https://runner3-wp-a94b8fd2.wasmer.app').replace(/\/$/, '');
const fixtureZip = process.env.FIXTURE_ZIP;
const fixturePluginSlug = process.env.FIXTURE_PLUGIN_SLUG || 'runner3-site2-fixture-v2';
const out = process.env.SETUP_OUT || '/tmp/site2-realistic-setup.json';
let token = String(process.env.WASMER_TOKEN || '').replace(/[\r\n]/g, '').trim();
if (!token) throw new Error('WASMER_TOKEN is required');
if (!token.startsWith('wap_')) token = `wap_${token}`;
if (!fixtureZip || !fs.existsSync(fixtureZip)) throw new Error('FIXTURE_ZIP is required');
if (!/^[a-z0-9-]+$/.test(fixturePluginSlug)) throw new Error('invalid FIXTURE_PLUGIN_SLUG');

const expectedHost = new URL(target).host;
const liveconfigUrl = `${target}/?rest_route=/wasmer/v1/liveconfig`;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function sanitize(value) {
  return String(value || '')
    .replaceAll(token, '[REDACTED]')
    .replace(/magiclogin=[^&\s"']+/gi, 'magiclogin=[REDACTED]');
}

async function readLiveconfig() {
  const response = await fetch(`${liveconfigUrl}&_=${Date.now()}`, {
    headers: { 'cache-control': 'no-cache' },
    redirect: 'follow',
  });
  if (!response.ok) throw new Error(`liveconfig returned HTTP ${response.status}`);
  const data = await response.json();
  const wpUrl = data?.wordpress?.url;
  if (!wpUrl) throw new Error('liveconfig missing wordpress.url');
  if (new URL(wpUrl).host !== expectedHost) throw new Error(`target guard failed: ${wpUrl}`);
  return data;
}

function compactLiveconfig(data) {
  const plugins = Array.isArray(data?.wordpress?.plugins) ? data.wordpress.plugins : [];
  const themes = Array.isArray(data?.wordpress?.themes) ? data.wordpress.themes : [];
  return {
    wordpress_version: data?.wordpress?.version ?? null,
    url: data?.wordpress?.url ?? null,
    posts: data?.wordpress?.posts ?? null,
    pages: data?.wordpress?.pages ?? null,
    active_theme: themes.find((x) => x.status === 'active')?.name ?? null,
    active_plugins: plugins
      .filter((x) => ['active', 'active-network', 'must-use'].includes(x.status))
      .map((x) => x.name),
  };
}

async function gotoAdminHref(page, locator) {
  const href = await locator.getAttribute('href');
  if (!href) throw new Error('WordPress admin action link has no href');
  const resolved = new URL(href, `${target}/wp-admin/`);
  if (resolved.host !== expectedHost || !resolved.pathname.startsWith('/wp-admin/')) {
    throw new Error('WordPress admin action target guard failed');
  }
  await page.goto(resolved.href, { waitUntil: 'domcontentloaded', timeout: 90_000 });
}

function fixtureRow(page) {
  return page.locator('tr').filter({
    has: page.locator(`a[href*="${fixturePluginSlug}"]`),
  });
}

async function activateRowIfNeeded(page, rows) {
  if (!(await rows.count())) return;
  const activate = rows.first().getByRole('link', { name: /^Activate$/i });
  if (await activate.count()) await gotoAdminHref(page, activate.first());
}

async function deactivateFixtureHelper(page) {
  await page.goto(`${target}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  const rows = fixtureRow(page);
  if (!(await rows.count())) throw new Error(`fixture helper ${fixturePluginSlug} missing before cleanup`);
  const deactivate = rows.first().getByRole('link', { name: /^Deactivate$/i });
  if (await deactivate.count()) await gotoAdminHref(page, deactivate.first());

  await page.goto(`${target}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  const postRows = fixtureRow(page);
  if (!(await postRows.count())) throw new Error('fixture helper disappeared during cleanup');
  const deactivateAfter = postRows.first().getByRole('link', { name: /^Deactivate$/i });
  if (await deactivateAfter.count()) throw new Error('fixture helper remained active after cleanup');
  return {
    verified_inactive: true,
    source: 'wp-admin/plugins.php:no-deactivate-action',
  };
}

async function ensureFixturePlugin(page) {
  await page.goto(`${target}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  if (new URL(page.url()).host !== expectedHost) throw new Error('wp-admin target host changed unexpectedly');

  let row = fixtureRow(page);
  if (await row.count()) {
    await activateRowIfNeeded(page, row);
    return 'reused';
  }

  await page.goto(`${target}/wp-admin/plugin-install.php?tab=upload`, {
    waitUntil: 'domcontentloaded',
    timeout: 60_000,
  });
  const input = page.locator('input[type="file"][name="pluginzip"]');
  await input.waitFor({ state: 'visible', timeout: 30_000 });
  await input.setInputFiles(fixtureZip);
  await page.locator('#install-plugin-submit').click();
  await page.waitForLoadState('domcontentloaded', { timeout: 120_000 }).catch(() => {});

  const body = await page.locator('body').innerText();
  if (/Destination folder already exists/i.test(body)) {
    await page.goto(`${target}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
    row = fixtureRow(page);
    if (!(await row.count())) {
      throw new Error(`fixture package ${fixturePluginSlug} exists but is not enumerable; use a new package slug rather than deleting unknown state`);
    }
    await activateRowIfNeeded(page, row);
    return 'reused';
  }

  const activateNow = page.locator('a.button.activate-now, a.button[href*="action=activate"]');
  if (await activateNow.count()) await gotoAdminHref(page, activateNow.first());

  await page.goto(`${target}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  row = fixtureRow(page);
  if (!(await row.count())) throw new Error(`fixture plugin ${fixturePluginSlug} was not installed`);
  await activateRowIfNeeded(page, row);
  return 'installed';
}

function parseFixtureSummary(message) {
  const marker = 'RUNNER3_SETUP_DONE';
  const idx = String(message || '').indexOf(marker);
  if (idx < 0) throw new Error('fixture success marker missing');
  const jsonText = String(message).slice(idx + marker.length).trim();
  let summary;
  try { summary = JSON.parse(jsonText); }
  catch { throw new Error(`fixture summary JSON invalid: ${jsonText.slice(0, 500)}`); }
  const required = {
    theme: summary?.theme === 'astra',
    woocommerce: Boolean(summary?.woocommerce),
    media: Number(summary?.media) >= 6,
    products: Number(summary?.products) >= 36,
    posts: Number(summary?.posts) >= 12,
    pages: Number(summary?.pages) >= 5,
  };
  const failed = Object.entries(required).filter(([, ok]) => !ok).map(([key]) => key);
  if (failed.length) throw new Error(`fixture summary incomplete (${failed.join(',')}): ${JSON.stringify(summary)}`);
  return summary;
}

async function runFixture(page) {
  await page.goto(`${target}/wp-admin/tools.php?page=runner3-site2-fixture`, {
    waitUntil: 'domcontentloaded',
    timeout: 60_000,
  });
  if (!/runner3-site2-fixture/.test(page.url())) throw new Error('fixture admin page unavailable');
  const button = page.locator('input[name="runner3_build"]');
  await button.waitFor({ state: 'visible', timeout: 30_000 });
  await button.click({ timeout: 30_000 });
  await page.waitForLoadState('domcontentloaded', { timeout: 300_000 }).catch(() => {});
  await page.getByText('RUNNER3_SETUP_DONE').waitFor({ state: 'visible', timeout: 300_000 });
  const message = (await page.getByText('RUNNER3_SETUP_DONE').locator('xpath=..').innerText()).slice(0, 5000);
  return { message, summary: parseFixtureSummary(message) };
}

async function verifyFrontend(page) {
  const checks = {};
  for (const path of ['/', '/shop/', '/about/', '/contact/', '/faq/', '/field-note-1/', '/cart/', '/checkout/', '/my-account/']) {
    const response = await page.goto(`${target}${path}?__fixture_verify=${Date.now()}`, {
      waitUntil: 'domcontentloaded',
      timeout: 90_000,
    });
    checks[path] = {
      status: response?.status() ?? null,
      title: await page.title(),
      h1: (await page.locator('h1').first().textContent().catch(() => ''))?.trim() || '',
    };
    if (!response || response.status() >= 400) throw new Error(`frontend verification failed for ${path}`);
  }

  await page.goto(`${target}/shop/?__fixture_products=${Date.now()}`, {
    waitUntil: 'domcontentloaded',
    timeout: 90_000,
  });
  const productCards = await page.locator('li.product, .wc-block-product, .products .product').count();
  if (productCards < 8) throw new Error(`expected >=8 visible shop product cards, got ${productCards}`);
  checks.shop_product_cards = productCards;
  return checks;
}

async function readPostCleanupLiveconfig() {
  let compact = null;
  for (let attempt = 1; attempt <= 6; attempt++) {
    compact = compactLiveconfig(await readLiveconfig());
    if (!(compact.active_plugins || []).includes(fixturePluginSlug)) return { compact, attempts: attempt, stale: false };
    if (attempt < 6) await sleep(3000);
  }
  return { compact, attempts: 6, stale: true };
}

const result = {
  target,
  fixture: 'astra-woo-v1',
  fixture_plugin_slug: fixturePluginSlug,
  started_at: new Date().toISOString(),
  status: 'starting',
  before: null,
  after: null,
  plugin_action: null,
  fixture_message: null,
  fixture_summary: null,
  frontend: null,
  fixture_helper_cleanup: null,
  fixture_helper_active_after_setup: null,
  fixture_helper_liveconfig_active_after_setup: null,
  fixture_helper_liveconfig_stale_after_admin_cleanup: false,
  liveconfig_cleanup_poll_attempts: 0,
  optimization_plugins_active_after_setup: [],
};

let browser;
try {
  result.before = compactLiveconfig(await readLiveconfig());

  const executablePath = [
    process.env.CHROME_PATH,
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
  ].filter(Boolean).find((p) => fs.existsSync(p));
  if (!executablePath) throw new Error('Chrome executable not found');

  browser = await chromium.launch({
    headless: true,
    executablePath,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  page.setDefaultTimeout(60_000);
  page.setDefaultNavigationTimeout(120_000);

  const magicUrl = `${target}/?rest_route=/wasmer/v1/magiclogin&magiclogin=${encodeURIComponent(token)}`;
  await page.goto(magicUrl, { waitUntil: 'domcontentloaded', timeout: 90_000 })
    .catch(() => { throw new Error('Wasmer magic-login navigation failed'); });
  if (new URL(page.url()).host !== expectedHost || !page.url().includes('/wp-admin')) {
    throw new Error('Wasmer magic-login did not reach the expected Site2 wp-admin');
  }

  result.plugin_action = await ensureFixturePlugin(page);
  const fixtureRun = await runFixture(page);
  result.fixture_message = fixtureRun.message;
  result.fixture_summary = fixtureRun.summary;
  result.fixture_helper_cleanup = await deactivateFixtureHelper(page);
  result.frontend = await verifyFrontend(page);

  const liveconfigAfterCleanup = await readPostCleanupLiveconfig();
  result.after = liveconfigAfterCleanup.compact;
  result.liveconfig_cleanup_poll_attempts = liveconfigAfterCleanup.attempts;
  const plugins = new Set(result.after.active_plugins || []);
  result.fixture_helper_active_after_setup = !result.fixture_helper_cleanup?.verified_inactive;
  result.fixture_helper_liveconfig_active_after_setup = plugins.has(fixturePluginSlug);
  result.fixture_helper_liveconfig_stale_after_admin_cleanup = Boolean(
    result.fixture_helper_cleanup?.verified_inactive && result.fixture_helper_liveconfig_active_after_setup
  );
  const optimizerPattern = /(litespeed|wp-super-cache|w3-total-cache|autoptimize|wp-optimize|wp-rocket|perfmatters|nitropack|sg-cachepress)/i;
  result.optimization_plugins_active_after_setup = [...plugins].filter((name) => optimizerPattern.test(String(name)));
  if (result.after.active_theme !== 'astra') throw new Error(`expected active theme astra, got ${result.after.active_theme}`);
  if (!plugins.has('woocommerce')) throw new Error('WooCommerce is not active after fixture setup');
  if (result.fixture_helper_active_after_setup) throw new Error('fixture helper must be inactive in authoritative wp-admin state before baseline');
  if (result.optimization_plugins_active_after_setup.length) {
    throw new Error(`optimization/cache plugins active before baseline: ${result.optimization_plugins_active_after_setup.join(',')}`);
  }

  result.status = 'ready';
  result.completed_at = new Date().toISOString();
} catch (error) {
  result.status = 'failed';
  result.error = sanitize(error?.stack || error?.message || error);
  result.completed_at = new Date().toISOString();
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => {});
  fs.writeFileSync(out, `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify({ ...result, error: result.error ? sanitize(result.error) : undefined }, null, 2));
}
