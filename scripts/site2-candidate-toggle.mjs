#!/usr/bin/env node

import fs from 'node:fs';
import { chromium } from 'playwright-core';

const target = (process.env.SITE2_URL || 'https://runner3-wp-a94b8fd2.wasmer.app').replace(/\/$/, '');
const action = process.env.CANDIDATE_ACTION || 'activate';
const pluginZip = process.env.CANDIDATE_ZIP || '';
const pluginSlug = process.env.CANDIDATE_PLUGIN_SLUG || 'runner3-site2-hero-preload';
const preloadId = process.env.CANDIDATE_PRELOAD_ID || 'runner3-site2-hero-preload';
const expectedLcpUrl = process.env.EXPECTED_LCP_URL || '';
const out = process.env.CANDIDATE_OUT || '/tmp/site2-candidate-toggle.json';
let token = String(process.env.WASMER_TOKEN || '').replace(/[\r\n]/g, '').trim();
if (!token) throw new Error('WASMER_TOKEN is required');
if (!token.startsWith('wap_')) token = `wap_${token}`;
if (!['activate', 'deactivate'].includes(action)) throw new Error(`unsupported CANDIDATE_ACTION=${action}`);
if (action === 'activate' && (!pluginZip || !fs.existsSync(pluginZip))) throw new Error('CANDIDATE_ZIP is required for activation');
if (!/^[a-z0-9-]+$/.test(pluginSlug)) throw new Error('invalid CANDIDATE_PLUGIN_SLUG');

const expectedHost = new URL(target).host;

function sanitize(value) {
  return String(value || '')
    .replaceAll(token, '[REDACTED]')
    .replace(/magiclogin=[^&\s"']+/gi, 'magiclogin=[REDACTED]');
}

async function gotoAdminHref(page, locator) {
  const href = await locator.getAttribute('href');
  if (!href) throw new Error('WordPress admin action link has no href');
  const resolved = new URL(href, `${target}/wp-admin/`);
  if (resolved.host !== expectedHost || !resolved.pathname.startsWith('/wp-admin/')) {
    throw new Error('WordPress admin target guard failed');
  }
  await page.goto(resolved.href, { waitUntil: 'domcontentloaded', timeout: 90_000 });
}

function pluginRow(page) {
  return page.locator('tr').filter({ has: page.locator(`a[href*="${pluginSlug}"]`) });
}

async function readState(page) {
  await page.goto(`${target}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  const rows = pluginRow(page);
  if (!(await rows.count())) return { installed: false, active: false };
  const row = rows.first();
  const deactivate = row.locator('a[href*="action=deactivate"]');
  const activate = row.locator('a[href*="action=activate"]');
  return {
    installed: true,
    active: (await deactivate.count()) > 0,
    activateActionVisible: (await activate.count()) > 0,
    deactivateActionVisible: (await deactivate.count()) > 0,
  };
}

async function uploadCandidateZip(page) {
  await page.goto(`${target}/wp-admin/plugin-install.php?tab=upload`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  const input = page.locator('input[type="file"][name="pluginzip"]');
  await input.waitFor({ state: 'visible', timeout: 30_000 });
  await input.setInputFiles(pluginZip);
  await page.locator('#install-plugin-submit').click();
  await page.waitForLoadState('domcontentloaded', { timeout: 120_000 }).catch(() => {});
}

async function ensureInstalled(page) {
  const before = await readState(page);
  if (before.active) throw new Error('candidate must be inactive before replacing its package');

  // Always upload the exact candidate ZIP for an activation run. Reusing an
  // already-installed slug can silently execute stale candidate code from a
  // previous A/B attempt, invalidating the experiment.
  await uploadCandidateZip(page);

  let body = await page.locator('body').innerText();
  let installAction = before.installed ? 'replaced' : 'installed';

  if (/Destination folder already exists|already installed/i.test(body)) {
    const replace = page.locator(
      'a.update-from-upload-overwrite, a.button[href*="overwrite=update-plugin"], a.button:has-text("Replace current with uploaded")'
    ).first();
    if (!(await replace.count())) {
      throw new Error('candidate package already exists but WordPress replace-upload action is unavailable');
    }
    await gotoAdminHref(page, replace);
    await page.waitForLoadState('domcontentloaded', { timeout: 120_000 }).catch(() => {});
    body = await page.locator('body').innerText();
    if (/Plugin update failed|Installation failed/i.test(body)) {
      throw new Error(`candidate package replacement failed: ${body.slice(0, 500)}`);
    }
  } else if (before.installed) {
    // If an installed candidate was present, WordPress must explicitly take
    // the overwrite path. Otherwise we cannot prove the new ZIP was deployed.
    throw new Error('installed candidate did not enter WordPress replace-upload flow');
  }

  const state = await readState(page);
  if (!state.installed) throw new Error(`candidate plugin ${pluginSlug} was not installed`);
  return installAction;
}

async function setActive(page, shouldBeActive) {
  const state = await readState(page);
  if (!state.installed && !shouldBeActive) return state;
  if (!state.installed) throw new Error('candidate plugin missing');
  if (state.active === shouldBeActive) return state;

  const row = pluginRow(page).first();
  const locator = shouldBeActive
    ? row.locator('a[href*="action=activate"]').first()
    : row.locator('a[href*="action=deactivate"]').first();
  if (!(await locator.count())) throw new Error(`candidate ${shouldBeActive ? 'activate' : 'deactivate'} action unavailable`);
  await gotoAdminHref(page, locator);

  const after = await readState(page);
  if (after.active !== shouldBeActive) throw new Error(`candidate active state mismatch after ${action}`);
  return after;
}

async function verifyFrontend(page, shouldBeActive) {
  const homeResponse = await page.goto(`${target}/?__candidate_verify=${Date.now()}`, { waitUntil: 'domcontentloaded', timeout: 90_000 });
  if (!homeResponse || homeResponse.status() >= 400) throw new Error(`homepage failed with ${homeResponse?.status()}`);

  const preload = page.locator(`link#${preloadId}[rel="preload"][as="image"]`);
  const count = await preload.count();
  if (shouldBeActive && count !== 1) throw new Error(`expected exactly one candidate hero preload, got ${count}`);
  if (!shouldBeActive && count !== 0) throw new Error('candidate preload remained after rollback');
  const href = count ? await preload.first().getAttribute('href') : null;
  if (href && new URL(href, target).host !== expectedHost) throw new Error('candidate preload points off origin');
  if (shouldBeActive && expectedLcpUrl && new URL(href, target).href !== new URL(expectedLcpUrl, target).href) {
    throw new Error(`candidate preloads wrong LCP resource: ${href}`);
  }

  const homeText = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
  if (!homeText.includes('Best Quality Products') || !homeText.includes('Join The Organic Movement!')) {
    throw new Error('official Organic Store homepage identity regression');
  }
  const homeProductCards = await page.locator('li.product, .wc-block-product, .products .product').count();
  if (homeProductCards < 8) throw new Error(`Organic Store homepage product regression: ${homeProductCards}`);

  const apiResponse = await page.context().request.get(`${target}/?rest_route=/wc/store/v1/products&per_page=100&__candidate_verify=${Date.now()}`);
  if (!apiResponse.ok()) throw new Error(`Store API failed with ${apiResponse.status()}`);
  const products = await apiResponse.json();
  if (!Array.isArray(products) || products.length < 30) throw new Error(`Store API product regression: ${Array.isArray(products) ? products.length : 'non-array'}`);

  let catalog = null;
  for (const path of ['/shop-3/', '/shop-2/', '/shop/']) {
    const response = await page.goto(`${target}${path}?__candidate_verify=${Date.now()}`, { waitUntil: 'domcontentloaded', timeout: 90_000 }).catch(() => null);
    if (!response || response.status() >= 400) continue;
    const productCards = await page.locator('li.product, .wc-block-product, .products .product').count();
    if (productCards >= 8) {
      catalog = { path, status: response.status(), productCards };
      break;
    }
  }
  if (!catalog) throw new Error('no healthy official Woo catalog route found');

  return {
    preloadCount: count,
    preloadHref: href,
    homeProductCards,
    storeApiProducts: products.length,
    catalog,
  };
}

const result = { target, action, pluginSlug, status: 'starting', startedAt: new Date().toISOString() };
let browser;
try {
  const executablePath = [process.env.CHROME_PATH, '/usr/bin/google-chrome-stable', '/usr/bin/google-chrome', '/usr/bin/chromium']
    .filter(Boolean).find((p) => fs.existsSync(p));
  if (!executablePath) throw new Error('Chrome executable not found');

  browser = await chromium.launch({ headless: true, executablePath, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  page.setDefaultTimeout(60_000);
  page.setDefaultNavigationTimeout(120_000);

  const magicUrl = `${target}/?rest_route=/wasmer/v1/magiclogin&magiclogin=${encodeURIComponent(token)}`;
  await page.goto(magicUrl, { waitUntil: 'domcontentloaded', timeout: 90_000 });
  if (new URL(page.url()).host !== expectedHost || !page.url().includes('/wp-admin')) {
    throw new Error('Wasmer magic login did not reach Site2 wp-admin');
  }

  if (action === 'activate') result.installAction = await ensureInstalled(page);
  result.plugin = await setActive(page, action === 'activate');
  result.frontend = await verifyFrontend(page, action === 'activate');
  result.status = 'ready';
  result.completedAt = new Date().toISOString();
} catch (error) {
  result.status = 'failed';
  result.error = sanitize(error?.stack || error?.message || error);
  result.completedAt = new Date().toISOString();
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => {});
  fs.writeFileSync(out, `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify(result, null, 2));
}
