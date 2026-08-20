import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner5-restore-lab-1';
const state = JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const pluginSource = fs.readFileSync('wordpress/runner3-speed/runner3-speed.php', 'utf8');
const expectedVersion = (pluginSource.match(/\* Version:\s*([^\r\n]+)/i)?.[1] || '').trim();
const base = String(state.siteUrl || '').replace(/\/$/, '');
const dashboard = state.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(state.owner)}/${encodeURIComponent(state.appName)}`;
const out = '/tmp/runner3-speed-safety-matrix.json';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const result = {
  status: 'starting',
  site: slug,
  url: base,
  pluginVersion: expectedVersion,
  currentHit: false,
  headHit: false,
  headEmptyBody: false,
  authCookieBypass: false,
  wooCartCookieBypass: false,
  wooSessionCookieBypass: false,
  cartPathBypass: false,
  checkoutPathBypass: false,
  accountPathBypass: false,
  wcApiPathBypass: false,
  deactivated: false,
  deactivateNoHit: false,
  reactivatedOff: false,
  finalNoHit: false,
  detail: null,
};

function save() {
  fs.writeFileSync(out, JSON.stringify({ ...result, checkedAt: new Date().toISOString() }, null, 2) + '\n');
}

async function login(page) {
  await page.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
  if (!/\/login(?:[/?#]|$)/i.test(page.url())) return;
  const ident = page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  await ident.waitFor({ state: 'visible', timeout: 15000 });
  await ident.fill(account.username || account.email);
  const next = page.locator('button').filter({ hasText: /continue|next|log in|sign in/i }).first();
  if (await next.count() && await next.isVisible().catch(() => false)) await next.click(); else await ident.press('Enter');
  await sleep(500);
  if (!/\/login(?:[/?#]|$)/i.test(page.url())) return;
  const pass = page.locator('input[type=password]').first();
  await pass.waitFor({ state: 'visible', timeout: 20000 });
  await pass.fill(account.password);
  const submit = page.locator('input[type=submit],button').filter({ hasText: /log in|sign in|continue/i }).first();
  if (await submit.count() && await submit.isVisible().catch(() => false)) await submit.click(); else await pass.press('Enter');
  await sleep(2200);
  if (/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('wasmer_login_failed');
}

async function adminPage(ctx, page) {
  await page.goto(dashboard, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await sleep(1000);
  const admin = page.getByText(/WordPress Admin/i).first();
  if (!(await admin.count())) throw new Error('wordpress_admin_control_missing');
  const href = await admin.getAttribute('href').catch(() => null);
  if (href) {
    const wp = await ctx.newPage();
    await wp.goto(new URL(href, 'https://wasmer.io').href, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await sleep(1200);
    if (wp.url().startsWith(base) && /wp-admin/i.test(wp.url())) return wp;
    await wp.close().catch(() => {});
  }
  const popupP = ctx.waitForEvent('page', { timeout: 10000 }).catch(() => null);
  await admin.click();
  const popup = await popupP;
  await sleep(1800);
  for (const p of [popup, ...ctx.pages()].filter(Boolean)) {
    if (p.url().startsWith(base) && /wp-admin/i.test(p.url())) return p;
  }
  throw new Error('magic_admin_failed');
}

async function pluginRow(wp) {
  await wp.goto(`${base}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  return wp.locator('tr[data-slug="runner3-speed"]').first();
}

async function assertVersionAndActive(wp) {
  const row = await pluginRow(wp);
  if (!(await row.count())) throw new Error('runner3_speed_row_missing');
  const text = await row.innerText();
  if (expectedVersion && !text.includes(`Version ${expectedVersion}`)) throw new Error(`plugin_version_mismatch:expected_${expectedVersion}`);
  if (!/\bactive\b/.test(await row.getAttribute('class') || '')) throw new Error('runner3_speed_not_active');
}

async function toggle(wp, want) {
  await wp.goto(`${base}/wp-admin/options-general.php?page=runner3-speed`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const text = await wp.locator('body').innerText();
  const on = /Performance\s*ON/i.test(text);
  if (on === want) return;
  const form = wp.locator('form').filter({ has: wp.locator('input[name="action"][value="runner3_speed_toggle"]') }).first();
  if (!(await form.count())) throw new Error('toggle_missing');
  await Promise.all([
    wp.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => null),
    form.evaluate(el => HTMLFormElement.prototype.submit.call(el)),
  ]);
  await sleep(900);
  const after = await wp.locator('body').innerText();
  if (want && !/Performance\s*ON/i.test(after)) throw new Error(`turn_on_failed:${after.slice(0, 300)}`);
  if (!want && !/Performance\s*OFF/i.test(after)) throw new Error('turn_off_failed');
}

async function request(path = '/', init = {}) {
  const r = await fetch(new URL(path, `${base}/`), { redirect: 'manual', ...init });
  const body = init.method === 'HEAD' ? '' : await r.text();
  return {
    status: r.status,
    location: r.headers.get('location'),
    speed: r.headers.get('x-runner3-speed'),
    speedVersion: r.headers.get('x-runner3-speed-version'),
    body,
  };
}

function assertHealthyBypass(name, response) {
  if (response.status >= 500) throw new Error(`${name}_server_error:${response.status}`);
  if (response.speed === 'HIT') throw new Error(`${name}_unexpected_hit`);
}

async function warmCurrentVersion() {
  for (let i = 0; i < 5; i++) {
    const r = await request('/');
    if (r.speed === 'HIT' && r.speedVersion === expectedVersion) return r;
    await sleep(350);
  }
  throw new Error('current_version_hit_missing');
}

async function deactivate(wp) {
  let row = await pluginRow(wp);
  if (!(await row.count())) throw new Error('runner3_speed_row_missing_before_deactivate');
  if (!/\bactive\b/.test(await row.getAttribute('class') || '')) return;
  const link = row.locator('a').filter({ hasText: /^Deactivate$/i }).first();
  const href = await link.getAttribute('href');
  if (!href) throw new Error('deactivate_link_missing');
  await wp.goto(new URL(href, `${base}/wp-admin/`).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await sleep(900);
  row = await pluginRow(wp);
  if (/\bactive\b/.test(await row.getAttribute('class') || '')) throw new Error('deactivate_failed');
}

async function activate(wp) {
  let row = await pluginRow(wp);
  if (!(await row.count())) throw new Error('runner3_speed_row_missing_before_reactivate');
  if (/\bactive\b/.test(await row.getAttribute('class') || '')) return;
  const link = row.locator('a').filter({ hasText: /^Activate$/i }).first();
  const href = await link.getAttribute('href');
  if (!href) throw new Error('activate_link_missing');
  await wp.goto(new URL(href, `${base}/wp-admin/`).href, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await sleep(900);
  row = await pluginRow(wp);
  if (!/\bactive\b/.test(await row.getAttribute('class') || '')) throw new Error('reactivate_failed');
}

const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await ctx.newPage();
let wp;

try {
  save();
  await login(page);
  wp = await adminPage(ctx, page);
  await assertVersionAndActive(wp);
  await toggle(wp, true);

  const warm = await warmCurrentVersion();
  result.currentHit = warm.speed === 'HIT' && warm.speedVersion === expectedVersion;

  const head = await request('/', { method: 'HEAD' });
  if (head.status !== 200 || head.speed !== 'HIT' || head.speedVersion !== expectedVersion) throw new Error(`head_hit_failed:${head.status}:${head.speed || 'none'}:${head.speedVersion || 'none'}`);
  result.headHit = true;
  result.headEmptyBody = head.body === '';

  const auth = await request('/', { headers: { cookie: 'wordpress_logged_in_runner3_probe=1' } });
  assertHealthyBypass('auth_cookie', auth);
  result.authCookieBypass = true;

  const wooCart = await request('/', { headers: { cookie: 'woocommerce_items_in_cart=1; woocommerce_cart_hash=runner3probe' } });
  assertHealthyBypass('woo_cart_cookie', wooCart);
  result.wooCartCookieBypass = true;

  const wooSession = await request('/', { headers: { cookie: 'wp_woocommerce_session_runner3probe=1' } });
  assertHealthyBypass('woo_session_cookie', wooSession);
  result.wooSessionCookieBypass = true;

  for (const [key, path] of [
    ['cartPathBypass', '/cart/'],
    ['checkoutPathBypass', '/checkout/'],
    ['accountPathBypass', '/my-account/'],
    ['wcApiPathBypass', '/wc-api/'],
  ]) {
    const r = await request(path);
    assertHealthyBypass(key, r);
    result[key] = true;
  }

  await deactivate(wp);
  result.deactivated = true;
  const afterDeactivate = await request('/');
  if (afterDeactivate.status !== 200 || afterDeactivate.speed === 'HIT' || afterDeactivate.body.length < 512) throw new Error(`deactivate_nohit_failed:${afterDeactivate.status}:${afterDeactivate.speed || 'none'}`);
  result.deactivateNoHit = true;

  await activate(wp);
  await toggle(wp, false);
  result.reactivatedOff = true;
  const final = await request('/');
  if (final.status !== 200 || final.speed === 'HIT' || final.body.length < 512) throw new Error(`final_off_nohit_failed:${final.status}:${final.speed || 'none'}`);
  result.finalNoHit = true;

  result.status = 'ready';
  result.detail = 'HEAD, auth/Woo cookie, dynamic path, deactivate and final OFF guards passed';
  save();
  console.log('RUNNER3_SPEED_SAFETY_MATRIX');
  console.log(JSON.stringify(result, null, 2));
} catch (e) {
  result.status = 'failed';
  result.detail = String(e?.message || e);
  save();
  console.error(JSON.stringify(result, null, 2));
  process.exitCode = 1;
} finally {
  if (wp) {
    await activate(wp).catch(() => {});
    await toggle(wp, false).catch(() => {});
  }
  await browser.close().catch(() => {});
}
