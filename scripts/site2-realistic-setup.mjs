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
  // data-slug is not stable for arbitrary uploaded plugins. The plugin title is
  // controlled by this fixture and remains stable across resumable package folders.
  return page.locator('tr').filter({ hasText: 'Runner3 Site2 Realistic Fixture' });
}

async function activateRowIfNeeded(page, rows) {
  if (!(await rows.count())) return;
  const row = rows.first();
  const activate = row.getByRole('link', { name: /^Activate$/i });
  if (await activate.count()) await gotoAdminHref(page, activate.first());
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
  return (await page.getByText('RUNNER3_SETUP_DONE').locator('xpath=..').innerText()).slice(0, 3000);
}

async function verifyFrontend(page) {
  const checks = {};
  for (const path of ['/', '/shop/', '/about/', '/contact/', '/faq/', '/field-note-1/']) {
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
  frontend: null,
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
  result.fixture_message = await runFixture(page);
  result.frontend = await verifyFrontend(page);

  result.after = compactLiveconfig(await readLiveconfig());
  const plugins = new Set(result.after.active_plugins || []);
  if (result.after.active_theme !== 'astra') throw new Error(`expected active theme astra, got ${result.after.active_theme}`);
  if (!plugins.has('woocommerce')) throw new Error('WooCommerce is not active after fixture setup');

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
