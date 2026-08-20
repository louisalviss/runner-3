import { chromium } from 'playwright-core';
import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const zip = process.env.RUNNER3_PLUGIN_ZIP || '/tmp/runner3-speed.zip';
const mode = process.env.RUNNER3_PROBE_MODE || 'full';
const state = JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(state.siteUrl || '').replace(/\/$/, '');
const dashboard = state.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(state.owner)}/${encodeURIComponent(state.appName)}`;
const out = '/tmp/runner3-speed-probe.json';
const result = { status:'starting', mode, installed:false, active:false, hit:false, queryBypass:false, apiBypass:false, adminBypass:false, off:false, productionUnchanged:false, detail:null };
const save = () => fs.writeFileSync(out, JSON.stringify({ ...result, updatedAt:new Date().toISOString() }, null, 2) + '\n');

async function login(page) {
  await page.goto('https://wasmer.io/login', { waitUntil:'domcontentloaded', timeout:60000 });
  const ident = page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  await ident.waitFor({ state:'visible', timeout:15000 });
  await ident.fill(account.username || account.email);
  const next = page.locator('button').filter({ hasText:/continue|next|log in|sign in/i }).first();
  if (await next.count() && await next.isVisible().catch(() => false)) await next.click(); else await ident.press('Enter');
  const pass = page.locator('input[type=password]').first();
  await pass.waitFor({ state:'visible', timeout:15000 });
  await pass.fill(account.password);
  const submit = page.locator('input[type=submit],button').filter({ hasText:/log in|sign in|continue/i }).first();
  if (await submit.count() && await submit.isVisible().catch(() => false)) await submit.click(); else await pass.press('Enter');
  await page.waitForTimeout(2200);
  if (/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('wasmer_login_failed');
}

async function adminPage(ctx, page) {
  await page.goto(dashboard, { waitUntil:'domcontentloaded', timeout:60000 });
  await page.waitForTimeout(1000);
  const admin = page.getByText(/WordPress Admin/i).first();
  if (!(await admin.count())) throw new Error('wordpress_admin_control_missing');
  const href = await admin.getAttribute('href').catch(() => null);
  if (href) {
    const wp = await ctx.newPage();
    await wp.goto(new URL(href, 'https://wasmer.io').href, { waitUntil:'domcontentloaded', timeout:60000 });
    await wp.waitForTimeout(1500);
    if (wp.url().startsWith(base) && /wp-admin/i.test(wp.url())) return wp;
    await wp.close().catch(() => {});
  }
  const popupP = ctx.waitForEvent('page', { timeout:10000 }).catch(() => null);
  await admin.click();
  const popup = await popupP;
  await page.waitForTimeout(1800);
  for (const p of [popup, ...ctx.pages()].filter(Boolean)) if (p.url().startsWith(base) && /wp-admin/i.test(p.url())) return p;
  throw new Error('magic_admin_failed');
}

async function row(wp) {
  await wp.goto(`${base}/wp-admin/plugins.php`, { waitUntil:'domcontentloaded', timeout:60000 });
  return wp.locator('tr[data-slug="runner3-speed"]').first();
}

async function install(wp) {
  await row(wp);
  await wp.goto(`${base}/wp-admin/plugin-install.php?tab=upload`, { waitUntil:'domcontentloaded', timeout:60000 });
  const input = wp.locator('input[type=file][name=pluginzip],input[type=file]').first();
  await input.waitFor({ state:'attached', timeout:15000 });
  await input.setInputFiles(zip);
  const installButton = wp.locator('#install-plugin-submit').first();
  if (!(await installButton.count())) throw new Error('plugin_upload_submit_missing');
  await installButton.click({ force:true });
  await wp.waitForLoadState('domcontentloaded').catch(() => {});
  await wp.waitForTimeout(1800);
  const replace = wp.locator('a,button,input[type=submit]').filter({ hasText:/replace current with uploaded|replace current|overwrite/i }).first();
  if (await replace.count()) {
    const href = await replace.getAttribute('href').catch(() => null);
    if (href) await wp.goto(new URL(href, `${base}/wp-admin/`).href, { waitUntil:'domcontentloaded', timeout:60000 });
    else {
      await replace.click({ force:true });
      await wp.waitForLoadState('domcontentloaded').catch(() => {});
    }
    await wp.waitForTimeout(1800);
  }
  const existing = await row(wp);
  if (!(await existing.count())) throw new Error('runner3_speed_install_missing');
  result.installed = true; save();
}

async function activate(wp) {
  let r = await row(wp);
  if (!(await r.count())) throw new Error('runner3_speed_row_missing');
  if (!/\bactive\b/.test(await r.getAttribute('class') || '')) {
    const a = r.locator('a').filter({ hasText:/^Activate$/i }).first();
    const href = await a.getAttribute('href');
    if (!href) throw new Error('activate_missing');
    await wp.goto(new URL(href, `${base}/wp-admin/`).href, { waitUntil:'domcontentloaded', timeout:60000 });
    await wp.waitForTimeout(800);
    r = await row(wp);
  }
  if (!/\bactive\b/.test(await r.getAttribute('class') || '')) throw new Error('activate_failed');
  result.active = true; save();
}

async function settings(wp) {
  await wp.goto(`${base}/wp-admin/options-general.php?page=runner3-speed`, { waitUntil:'domcontentloaded', timeout:60000 });
  const text = await wp.locator('body').innerText();
  if (!/Runner3 Speed/i.test(text)) throw new Error('settings_missing');
  return text;
}

async function toggle(wp, want) {
  const text = await settings(wp);
  const on = /Performance\s*ON/i.test(text);
  if (on === want) return;
  const form = wp.locator('form').filter({ has:wp.locator('input[name="action"][value="runner3_speed_toggle"]') }).first();
  if (!(await form.count())) throw new Error('toggle_missing');
  const val = await form.locator('input[name="enable"]').inputValue();
  if ((val === '1') !== want) throw new Error('toggle_state_mismatch');
  await Promise.all([
    wp.waitForNavigation({ waitUntil:'domcontentloaded', timeout:60000 }).catch(() => null),
    form.evaluate(el => HTMLFormElement.prototype.submit.call(el)),
  ]);
  await wp.waitForTimeout(900);
  const after = await wp.locator('body').innerText();
  if (want && !/Performance\s*ON/i.test(after)) throw new Error(`turn_on_failed:${after.slice(0,300)}`);
  if (!want && !/Performance\s*OFF/i.test(after)) throw new Error('turn_off_failed');
}

async function check(url) {
  const r = await fetch(url, { redirect:'follow' });
  return { status:r.status, speed:r.headers.get('x-runner3-speed'), body:await r.text() };
}

async function verifyOn(wp) {
  await check(`${base}/`);
  const second = await check(`${base}/`);
  if (second.status !== 200 || second.speed !== 'HIT' || second.body.length < 512) throw new Error(`cache_hit_missing:${second.speed || 'none'}`);
  result.hit = true; save();
  const q = await check(`${base}/?runner3_probe=${Date.now()}`);
  if (q.status !== 200 || q.speed === 'HIT') throw new Error('query_bypass_failed');
  result.queryBypass = true; save();
  const api = await check(`${base}/wp-json/`);
  if (api.status < 200 || api.status >= 500 || api.speed === 'HIT') throw new Error(`api_bypass_failed:${api.status}`);
  result.apiBypass = true; save();
  await wp.goto(`${base}/wp-admin/plugins.php`, { waitUntil:'domcontentloaded', timeout:60000 });
  if (!/wp-admin\/plugins\.php/.test(wp.url())) throw new Error('admin_bypass_failed');
  result.adminBypass = true; save();
}

async function verifyOff() {
  const r = await check(`${base}/`);
  if (r.status !== 200 || r.speed === 'HIT' || r.body.length < 512) throw new Error('off_bypass_failed');
  result.off = true; save();
}

async function production() {
  const r = await fetch(`https://runner3wp.pntr.dev/?__runner3_speed_probe=${Date.now()}`);
  const html = await r.text();
  if (!r.ok || (r.headers.get('x-edge-snapshot') || '').toUpperCase() !== 'HIT' || (r.headers.get('x-edge-cache-policy') || '').toLowerCase() !== 'snapshot-direct' || !/__runner3\/r2-image\/offset-demo-01-w(?:360|480|640)\.webp/.test(html)) throw new Error('production_v2_changed');
  result.productionUnchanged = true; save();
}

const browser = await chromium.launch({ headless:true, executablePath:'/usr/bin/google-chrome', args:['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors:true });
const page = await ctx.newPage();
let wp;
try {
  save(); await login(page); wp = await adminPage(ctx, page);
  if (mode === 'off') {
    await activate(wp).catch(() => {});
    await toggle(wp, false).catch(() => {});
    await verifyOff();
    result.status = 'cleanup_ready'; result.detail = 'forced OFF'; save();
  } else {
    await install(wp); await activate(wp); await toggle(wp, true); await verifyOn(wp); await toggle(wp, false); await verifyOff(); await production();
    result.status = 'ready'; result.detail = 'install/ON/HIT/bypass/OFF guards passed'; save();
  }
  console.log(JSON.stringify(result, null, 2));
} catch (e) {
  result.status = 'failed'; result.detail = String(e?.message || e); save(); console.error(JSON.stringify(result, null, 2)); process.exitCode = 1;
} finally {
  if (mode !== 'off' && wp) await toggle(wp, false).catch(() => {});
  await browser.close().catch(() => {});
}
