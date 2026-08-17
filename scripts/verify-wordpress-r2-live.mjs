import { chromium } from 'playwright-core';
import fs from 'fs';

const base = String(process.env.WP_SITE_URL || 'https://runner3-factory-smoke-2.wasmer.app/').replace(/\/$/, '');
const out = process.env.R2_VERIFY_OUT || '/tmp/wp-r2-live-verify.json';
const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, ignoreHTTPSErrors: true });
const page = await ctx.newPage();
const consoleErrors = [];
page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
const failedRequests = [];
page.on('requestfailed', req => failedRequests.push({ url: req.url(), error: req.failure()?.errorText || 'failed' }));
const result = { status: 'starting', site: base, viewport: '390x844', r2Images: 0, githubRawImages: 0, localUploadImages: 0, brokenImages: [], consoleErrors: [], failedRequests: [], detail: null, checkedAt: new Date().toISOString() };
try {
  const response = await page.goto(base + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  if (!response || response.status() !== 200) throw new Error(`homepage_http_${response?.status()}`);
  for (let y = 0; y < 14000; y += 650) {
    await page.evaluate(v => window.scrollTo(0, v), y);
    await page.waitForTimeout(120);
    const h = await page.evaluate(() => document.documentElement.scrollHeight);
    if (y > h + 800) break;
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(500);
  const images = await page.evaluate(() => Array.from(document.images).map(img => ({
    src: img.currentSrc || img.src || '',
    naturalWidth: img.naturalWidth,
    naturalHeight: img.naturalHeight,
    complete: img.complete,
    display: getComputedStyle(img).display,
    visibility: getComputedStyle(img).visibility
  })));
  result.r2Images = images.filter(x => /\.r2\.dev\//i.test(x.src)).length;
  result.githubRawImages = images.filter(x => /raw\.githubusercontent\.com/i.test(x.src)).length;
  result.localUploadImages = images.filter(x => /\/wp-content\/uploads\//i.test(x.src)).length;
  result.brokenImages = images.filter(x => x.src && x.display !== 'none' && x.visibility !== 'hidden' && (!x.complete || x.naturalWidth < 2)).map(x => x.src);
  result.consoleErrors = consoleErrors;
  result.failedRequests = failedRequests.filter(x => /\.(webp|jpe?g|png|gif|avif)(\?|$)/i.test(x.url));
  if (result.r2Images < 6) throw new Error(`r2_image_count_${result.r2Images}`);
  if (result.githubRawImages !== 0) throw new Error(`github_raw_images_${result.githubRawImages}`);
  if (result.brokenImages.length) throw new Error(`broken_images_${result.brokenImages.length}`);
  if (result.failedRequests.length) throw new Error(`failed_image_requests_${result.failedRequests.length}`);
  result.status = 'ready';
} catch (e) {
  result.status = 'failed';
  result.detail = String(e?.message || e);
  process.exitCode = 1;
} finally {
  result.checkedAt = new Date().toISOString();
  fs.writeFileSync(out, JSON.stringify(result, null, 2));
  await browser.close().catch(() => {});
  console.log(`R2_LIVE_VERIFY status=${result.status} r2=${result.r2Images} github=${result.githubRawImages} broken=${result.brokenImages.length}`);
}
