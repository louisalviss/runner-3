import { chromium } from 'playwright-core';
import fs from 'fs';
import { execFileSync, spawnSync } from 'child_process';

const slug = process.env.WP_SITE_SLUG || 'runner3-speed-site3-realistic';
const state = JSON.parse(fs.readFileSync(`ops/site-factory/${slug}.json`, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(state.siteUrl || '').replace(/\/$/, '');
const dashboard = state.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(state.owner)}/${encodeURIComponent(state.appName)}`;
const out = '/tmp/runner3-speed-site3-a.json';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const median = values => {
  const rows = [...values].filter(Number.isFinite).sort((a, b) => a - b);
  if (!rows.length) return null;
  const mid = Math.floor(rows.length / 2);
  return rows.length % 2 ? rows[mid] : (rows[mid - 1] + rows[mid]) / 2;
};
const round = (value, digits = 1) => Number.isFinite(value) ? Number(value.toFixed(digits)) : null;

async function login(page) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      await page.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
      if (!/\/login(?:[/?#]|$)/i.test(page.url())) return;
      const ident = page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
      await ident.waitFor({ state: 'visible', timeout: 15000 });
      await ident.fill(account.username || account.email);
      await ident.press('Enter');
      const pass = page.locator('input[type=password]').first();
      await pass.waitFor({ state: 'visible', timeout: 20000 });
      await pass.fill(account.password);
      await pass.press('Enter');
      await sleep(2200);
      if (!/\/login(?:[/?#]|$)/i.test(page.url())) return;
    } catch {}
    await sleep(1000 * attempt);
  }
  throw new Error('wasmer_login_failed');
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
  const popupPromise = ctx.waitForEvent('page', { timeout: 10000 }).catch(() => null);
  await admin.click().catch(() => {});
  const popup = await popupPromise;
  await sleep(1800);
  for (const candidate of [popup, ...ctx.pages()].filter(Boolean)) {
    if (candidate.url().startsWith(base) && /wp-admin/i.test(candidate.url())) return candidate;
  }
  throw new Error('magic_admin_failed');
}

function curlRuns(n = 15) {
  const rows = [];
  for (let i = 0; i < n; i++) {
    const raw = execFileSync('curl', ['-L', '-sS', '-D', '-', '-o', '/dev/null', '-w', '\n__R3_METRICS__ %{http_code} %{time_starttransfer} %{time_total} %{size_download}', `${base}/`], { encoding: 'utf8' });
    const [head, metricRaw = ''] = raw.split('__R3_METRICS__');
    const [code, ttfb, total, size] = metricRaw.trim().split(/\s+/);
    rows.push({ code: Number(code), ttfbMs: Number(ttfb) * 1000, totalMs: Number(total) * 1000, size: Number(size), runner3: /^x-runner3-speed:/im.test(head) });
  }
  return {
    runs: rows,
    medianTtfbMs: round(median(rows.map(item => item.ttfbMs))),
    medianTotalMs: round(median(rows.map(item => item.totalMs))),
    medianBytes: round(median(rows.map(item => item.size)), 0)
  };
}

async function browserRuns(browser, n = 7) {
  const rows = [];
  for (let i = 0; i < n; i++) {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    const page = await ctx.newPage();
    const cdp = await ctx.newCDPSession(page);
    await cdp.send('Network.enable');
    await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
    await page.addInitScript(() => {
      window.__r3Lcp = 0;
      window.__r3Cls = 0;
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) window.__r3Lcp = Math.max(window.__r3Lcp, entry.startTime || 0);
      }).observe({ type: 'largest-contentful-paint', buffered: true });
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) if (!entry.hadRecentInput) window.__r3Cls += entry.value || 0;
      }).observe({ type: 'layout-shift', buffered: true });
    });
    const started = Date.now();
    const response = await page.goto(`${base}/`, { waitUntil: 'load', timeout: 60000 });
    await sleep(800);
    const perf = await page.evaluate(() => {
      const nav = performance.getEntriesByType('navigation')[0];
      const fcp = performance.getEntriesByName('first-contentful-paint')[0];
      return {
        ttfb: nav?.responseStart || 0,
        fcp: fcp?.startTime || 0,
        lcp: window.__r3Lcp || 0,
        cls: window.__r3Cls || 0,
        load: nav?.loadEventEnd || 0
      };
    });
    rows.push({ status: response?.status() || 0, wallMs: Date.now() - started, ...perf });
    await ctx.close();
  }
  const pick = (key, digits = 1) => round(median(rows.map(item => Number(item[key]))), digits);
  return {
    runs: rows,
    medianTtfbMs: pick('ttfb'),
    medianFcpMs: pick('fcp'),
    medianLcpMs: pick('lcp'),
    medianCls: pick('cls', 3),
    medianLoadMs: pick('load'),
    medianWallMs: pick('wallMs')
  };
}

function lighthouseRuns(n = 5) {
  const rows = [];
  for (let i = 0; i < n; i++) {
    const file = `/tmp/lh-site3-a-${i}.json`;
    const proc = spawnSync('npx', ['lighthouse', `${base}/`, '--quiet', '--chrome-flags=--headless --no-sandbox', '--form-factor=mobile', '--only-categories=performance', '--output=json', `--output-path=${file}`], { encoding: 'utf8', timeout: 180000 });
    if (proc.status !== 0) throw new Error(`lighthouse_a_${i}_failed:${(proc.stderr || proc.stdout || '').slice(-500)}`);
    const json = JSON.parse(fs.readFileSync(file, 'utf8'));
    const audits = json.audits || {};
    rows.push({
      score: Math.round((json.categories?.performance?.score || 0) * 100),
      fcp: audits['first-contentful-paint']?.numericValue || null,
      lcp: audits['largest-contentful-paint']?.numericValue || null,
      si: audits['speed-index']?.numericValue || null,
      tbt: audits['total-blocking-time']?.numericValue || null,
      cls: audits['cumulative-layout-shift']?.numericValue || null,
      ttfb: audits['server-response-time']?.numericValue || null
    });
  }
  const pick = (key, digits = 1) => round(median(rows.map(item => Number(item[key]))), digits);
  return {
    runs: rows,
    medianScore: pick('score', 0),
    medianFcpMs: pick('fcp'),
    medianLcpMs: pick('lcp'),
    medianSpeedIndexMs: pick('si'),
    medianTbtMs: pick('tbt'),
    medianCls: pick('cls', 3),
    medianServerResponseMs: pick('ttfb')
  };
}

const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const adminCtx = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await adminCtx.newPage();
const report = {
  status: 'starting',
  site: slug,
  url: base,
  state: 'A_NO_PLUGIN',
  pluginAbsent: false,
  cloudflare: null,
  richness: null,
  curl: null,
  browser: null,
  lighthouse: null,
  checkedAt: null
};

try {
  await login(page);
  const wp = await adminPage(adminCtx, page);

  await wp.goto(`${base}/wp-admin/plugins.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  report.pluginAbsent = (await wp.locator('tr[data-slug="runner3-speed"]').count()) === 0;
  if (!report.pluginAbsent) throw new Error('runner3_speed_already_installed_clean_room_invalid');
  const elementorActive = (await wp.locator('tr.active[data-slug="elementor"]').count()) > 0;

  await wp.goto(`${base}/wp-admin/themes.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const blocksyActive = (await wp.locator('.theme.active[data-slug="blocksy"]').count()) > 0;

  const headers = execFileSync('curl', ['-sSI', `${base}/`], { encoding: 'utf8' });
  report.cloudflare = /^cf-ray:/im.test(headers);
  if (report.cloudflare) throw new Error('cloudflare_detected_invalid_direct_host_test');

  const html = await fetch(`${base}/?richness=${Date.now()}`, { headers: { 'Cache-Control': 'no-cache' } }).then(response => response.text());
  const pages = await fetch(`${base}/wp-json/wp/v2/pages?per_page=100&_fields=id,slug,title`).then(response => response.json()).catch(() => []);
  const media = await fetch(`${base}/wp-json/wp/v2/media?per_page=100&_fields=id,source_url,media_type`).then(response => response.json()).catch(() => []);
  const posts = await fetch(`${base}/wp-json/wp/v2/posts?per_page=100&_fields=id,slug,title,featured_media`).then(response => response.json()).catch(() => []);
  const localMedia = Array.isArray(media) ? media.filter(item => String(item?.source_url || '').startsWith(base)).length : 0;
  const featuredPosts = Array.isArray(posts) ? posts.filter(item => Number(item?.featured_media) > 0).length : 0;

  report.richness = {
    htmlBytes: Buffer.byteLength(html),
    pages: Array.isArray(pages) ? pages.length : 0,
    posts: Array.isArray(posts) ? posts.length : 0,
    media: Array.isArray(media) ? media.length : 0,
    localMedia,
    featuredPosts,
    images: (html.match(/<img\b/gi) || []).length,
    stylesheets: (html.match(/<link[^>]+rel=["']stylesheet["']/gi) || []).length,
    scripts: (html.match(/<script\b/gi) || []).length,
    navLinks: (html.match(/<nav[\s\S]*?<\/nav>/gi) || []).join('').match(/<a\b/gi)?.length || 0,
    sections: (html.match(/data-r3-section=/g) || []).length,
    elementorActive,
    elementorFrontend: /\belementor(?:-|_)/i.test(html),
    blocksy: blocksyActive && /\bct-(?:container|header|footer|panel)|themes\/blocksy\//i.test(html)
  };
  const richness = report.richness;
  if (
    richness.pages !== 8 || richness.posts !== 18 || richness.localMedia !== 18 || richness.featuredPosts !== 18 ||
    richness.images < 8 || richness.navLinks < 5 || richness.sections < 6 || !richness.elementorActive || !richness.blocksy
  ) throw new Error(`site_not_deterministic_or_realistic:${JSON.stringify(richness)}`);

  report.curl = curlRuns(15);
  report.browser = await browserRuns(browser, 7);
  report.lighthouse = lighthouseRuns(5);
  report.status = 'ready';
  report.checkedAt = new Date().toISOString();
} catch (error) {
  report.status = 'failed';
  report.error = String(error?.message || error);
  report.checkedAt = new Date().toISOString();
  process.exitCode = 1;
} finally {
  fs.writeFileSync(out, JSON.stringify(report, null, 2) + '\n');
  await adminCtx.close().catch(() => {});
  await browser.close().catch(() => {});
}

console.log(JSON.stringify(report, null, 2));
