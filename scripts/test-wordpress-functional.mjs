import { chromium } from 'playwright-core';
import fs from 'node:fs';

const base = (process.env.WP_SITE_URL || 'https://runner3-factory-smoke-2.wasmer.app/').replace(/\/$/, '');
const out = process.env.FUNCTIONAL_OUT || 'ops/wp-functional-regression/results/latest.json';
const chromeCandidates = [
  process.env.CHROME_PATH,
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
].filter(Boolean);
const executablePath = chromeCandidates.find((p) => fs.existsSync(p));
if (!executablePath) throw new Error(`Chrome not found: ${chromeCandidates.join(', ')}`);

fs.mkdirSync(out.split('/').slice(0, -1).join('/') || '.', { recursive: true });

const report = {
  status: 'running',
  site: base,
  checkedAt: new Date().toISOString(),
  checks: [],
  consoleErrors: [],
  pageErrors: [],
  media: null,
  detail: null,
};

function record(name, pass, detail = null) {
  report.checks.push({ name, pass: Boolean(pass), detail });
}

async function runCheck(name, fn) {
  try {
    const detail = await fn();
    record(name, true, detail ?? null);
  } catch (error) {
    record(name, false, String(error?.message || error));
  }
}

async function freshPage(browser, viewport = { width: 1440, height: 900 }) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  page.on('console', (msg) => {
    if (msg.type() === 'error') report.consoleErrors.push({ url: page.url(), text: msg.text() });
  });
  page.on('pageerror', (error) => report.pageErrors.push({ url: page.url(), text: String(error?.message || error) }));
  return page;
}

async function goto200(page, url) {
  const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45_000 });
  if (!response || response.status() !== 200) throw new Error(`HTTP ${response?.status() ?? 'no-response'} for ${url}`);
  return response;
}

async function clickAndRequire200(page, locator) {
  const href = await locator.getAttribute('href');
  if (!href) throw new Error('Link has no href');
  const nav = page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 30_000 }).catch(() => null);
  await locator.click();
  const response = await nav;
  if (response && response.status() >= 400) throw new Error(`HTTP ${response.status()} after click ${href}`);
  await page.waitForLoadState('domcontentloaded');
  return { href, finalUrl: page.url(), status: response?.status() ?? null };
}

const browser = await chromium.launch({
  headless: true,
  executablePath,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
});

try {
  await runCheck('homepage_200_and_core_sections', async () => {
    const page = await freshPage(browser);
    try {
      await goto200(page, `${base}/`);
      for (const selector of ['.site-header', '.signal-stage', '.reel', '.site-footer']) {
        if (!(await page.locator(selector).count())) throw new Error(`Missing ${selector}`);
      }
      return { title: await page.title() };
    } finally { await page.close(); }
  });

  await runCheck('header_menu_to_category', async () => {
    const page = await freshPage(browser);
    try {
      await goto200(page, `${base}/`);
      let link = page.locator('.nav a[href*="/category/"]').first();
      if (!(await link.count())) link = page.locator('.territory[href*="/category/"]').first();
      if (!(await link.count())) throw new Error('No category link found');
      const nav = await clickAndRequire200(page, link);
      if (!(await page.locator('body').innerText()).trim()) throw new Error('Category rendered empty body');
      return nav;
    } finally { await page.close(); }
  });

  await runCheck('homepage_to_article', async () => {
    const page = await freshPage(browser);
    try {
      await goto200(page, `${base}/`);
      const link = page.locator('.reel-story h3 a, .scene-copy h2 a').first();
      if (!(await link.count())) throw new Error('No article link found');
      const nav = await clickAndRequire200(page, link);
      if (!(await page.locator('.article-shell').count())) throw new Error('Article template did not render');
      if (!(await page.locator('.article-title').innerText()).trim()) throw new Error('Article title is empty');
      return nav;
    } finally { await page.close(); }
  });

  for (const label of ['About', 'Contact']) {
    await runCheck(`footer_${label.toLowerCase()}_link`, async () => {
      const page = await freshPage(browser);
      try {
        await goto200(page, `${base}/`);
        const link = page.locator('.site-footer a', { hasText: label }).first();
        if (!(await link.count())) throw new Error(`${label} link missing`);
        return await clickAndRequire200(page, link);
      } finally { await page.close(); }
    });
  }

  await runCheck('rss_feed', async () => {
    const context = await browser.newContext();
    try {
      const response = await context.request.get(`${base}/feed/`, { timeout: 30_000 });
      const body = await response.text();
      const type = response.headers()['content-type'] || '';
      if (response.status() !== 200) throw new Error(`RSS HTTP ${response.status()}`);
      if (!/(xml|rss|atom)/i.test(type) && !/<(rss|feed)[\s>]/i.test(body)) throw new Error(`Unexpected RSS content-type: ${type}`);
      return { status: response.status(), contentType: type, bytes: Buffer.byteLength(body) };
    } finally { await context.close(); }
  });

  await runCheck('r2_story_images_decode', async () => {
    const page = await freshPage(browser, { width: 390, height: 844 });
    const selector = '.signal-orbit img, .scene-image img, .reel-image img';
    try {
      await goto200(page, `${base}/`);
      const count = await page.locator(selector).count();
      if (count < 7) throw new Error(`Expected >=7 story images, found ${count}`);

      // Force every lazy image through the viewport so a zero naturalWidth cannot be
      // caused merely by the browser deciding not to schedule an off-screen image yet.
      for (let i = 0; i < count; i++) {
        const image = page.locator(selector).nth(i);
        await image.scrollIntoViewIfNeeded();
        await image.evaluate((img) => { img.loading = 'eager'; });
        await page.waitForTimeout(120);
      }
      await page.waitForTimeout(400);

      // decode() distinguishes an actual decode/network failure from a lazy-load race.
      await page.evaluate(async (sel) => {
        const images = [...document.querySelectorAll(sel)];
        await Promise.all(images.map(async (img) => {
          try {
            await Promise.race([
              img.decode(),
              new Promise((_, reject) => setTimeout(() => reject(new Error('decode timeout')), 5000)),
            ]);
          } catch (_) {}
        }));
      }, selector);

      const media = await page.evaluate((sel) => {
        const images = [...document.querySelectorAll(sel)];
        return images.map((img, index) => ({
          index,
          loading: img.loading,
          src: img.getAttribute('src') || '',
          currentSrc: img.currentSrc || img.src || '',
          complete: img.complete,
          naturalWidth: img.naturalWidth,
          naturalHeight: img.naturalHeight,
        }));
      }, selector);

      const broken = media.filter((img) => !img.complete || img.naturalWidth < 1 || img.naturalHeight < 1);
      const local = media.filter((img) => /\/wp-content\/uploads\//i.test(img.currentSrc || img.src));
      const r2 = media.filter((img) => /\.r2\.dev\//i.test(img.currentSrc || img.src));
      const urls = [...new Set(media.map((x) => x.currentSrc || x.src).filter(Boolean))];
      const probes = [];
      for (const url of urls) {
        try {
          const response = await page.context().request.get(url, { timeout: 20_000 });
          const type = response.headers()['content-type'] || '';
          const body = await response.body();
          probes.push({ url, status: response.status(), contentType: type, bytes: body.length });
        } catch (error) {
          probes.push({ url, status: null, contentType: null, bytes: null, error: String(error?.message || error) });
        }
      }
      const badHttp = probes.filter((p) => p.status !== 200 || !/^image\//i.test(p.contentType || '') || !(p.bytes > 0));

      report.media = {
        elements: media.length,
        uniqueUrls: urls.length,
        r2Elements: r2.length,
        localUploadElements: local.length,
        broken: broken.length,
        brokenItems: broken,
        httpProbeFailures: badHttp.length,
        probes,
        hosts: [...new Set(media.map((x) => { try { return new URL(x.currentSrc || x.src).host; } catch { return ''; } }).filter(Boolean))],
      };

      if (local.length) throw new Error(`${local.length} story images still use local wp-content/uploads`);
      if (r2.length !== media.length) throw new Error(`Expected all ${media.length} story images from r2.dev, got ${r2.length}`);
      if (badHttp.length) throw new Error(`${badHttp.length} R2 image URLs failed HTTP/content validation`);
      if (broken.length) throw new Error(`${broken.length} story images failed browser decode: ${broken.map((x) => x.currentSrc || x.src).join(', ')}`);
      return report.media;
    } finally { await page.close(); }
  });

  await runCheck('motion_reveal_js', async () => {
    const page = await freshPage(browser);
    try {
      await goto200(page, `${base}/`);
      const reveal = page.locator('[data-reveal]').first();
      if (!(await reveal.count())) throw new Error('No [data-reveal] element found');
      await reveal.scrollIntoViewIfNeeded();
      await page.waitForTimeout(350);
      const cls = await reveal.getAttribute('class');
      if (!String(cls || '').split(/\s+/).includes('is-visible')) throw new Error(`Reveal did not become visible; class=${cls}`);
      return { class: cls };
    } finally { await page.close(); }
  });

  await runCheck('newsletter_demo_form_no_navigation', async () => {
    const page = await freshPage(browser);
    try {
      await goto200(page, `${base}/`);
      const form = page.locator('.signal-form');
      if (!(await form.count())) throw new Error('Newsletter demo form missing');
      await form.locator('input[type="email"]').fill('qa@example.com');
      const before = page.url();
      await form.locator('button[type="submit"]').click();
      await page.waitForTimeout(250);
      if (page.url() !== before) throw new Error(`Demo form navigated unexpectedly: ${before} -> ${page.url()}`);
      return { url: before, mode: 'demo-no-submit' };
    } finally { await page.close(); }
  });

  await runCheck('no_browser_exceptions', async () => {
    await new Promise((resolve) => setTimeout(resolve, 150));
    if (report.pageErrors.length) throw new Error(`${report.pageErrors.length} page exceptions: ${report.pageErrors.map((e) => e.text).slice(0, 3).join(' | ')}`);
    if (report.consoleErrors.length) throw new Error(`${report.consoleErrors.length} console errors: ${report.consoleErrors.map((e) => e.text).slice(0, 3).join(' | ')}`);
    return { consoleErrors: 0, pageErrors: 0 };
  });
} catch (error) {
  report.detail = String(error?.stack || error);
} finally {
  await browser.close();
}

const failed = report.checks.filter((check) => !check.pass);
report.status = failed.length || report.detail ? 'failed' : 'passed';
report.failed = failed.map((check) => check.name);
fs.writeFileSync(out, `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify({ status: report.status, site: report.site, checks: report.checks, media: report.media, consoleErrors: report.consoleErrors.length, pageErrors: report.pageErrors.length, failed: report.failed }, null, 2));
if (report.status !== 'passed') process.exitCode = 1;
