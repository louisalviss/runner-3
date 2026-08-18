import fs from 'node:fs/promises';
import { chromium } from 'playwright';

const target = process.env.EDGE_URL || 'https://wordpress-edge-proxy.ducduy2411.workers.dev/';
const out = process.env.EDGE_IMAGE_BROWSER_OUT || '/tmp/edge-image-browser.json';
const executablePath = process.env.CHROME_PATH || undefined;

const browser = await chromium.launch({ headless: true, executablePath });
const page = await browser.newPage({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  isMobile: true,
  hasTouch: true,
});

const requestFailures = [];
const consoleErrors = [];
page.on('requestfailed', (req) => requestFailures.push({ url: req.url(), error: req.failure()?.errorText || null }));
page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
page.on('pageerror', (err) => consoleErrors.push(String(err)));

let result;
try {
  const response = await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(700);

  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0; y <= height; y += 650) {
    await page.evaluate((scrollY) => window.scrollTo(0, scrollY), y);
    await page.waitForTimeout(180);
  }
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await page.waitForTimeout(1400);

  const images = await page.evaluate(() => [...document.images].map((img, index) => ({
    index,
    src: img.getAttribute('src'),
    srcset: img.getAttribute('srcset'),
    currentSrc: img.currentSrc,
    alt: img.alt,
    loading: img.loading,
    complete: img.complete,
    naturalWidth: img.naturalWidth,
    naturalHeight: img.naturalHeight,
    renderedWidth: Math.round(img.getBoundingClientRect().width),
    renderedHeight: Math.round(img.getBoundingClientRect().height),
  })));

  const broken = images.filter((img) => !img.complete || img.naturalWidth <= 0 || img.naturalHeight <= 0);
  const transformed = images.filter((img) => (img.currentSrc || '').includes('/_img/'));
  const r2Images = images.filter((img) => (img.currentSrc || '').includes('.r2.dev/'));

  result = {
    status: broken.length === 0 && transformed.length === 0 ? 'pass' : 'fail',
    target,
    httpStatus: response?.status() ?? null,
    imageCount: images.length,
    r2ImageCount: r2Images.length,
    brokenCount: broken.length,
    transformedCount: transformed.length,
    images,
    broken,
    transformed,
    requestFailures,
    consoleErrors,
    checkedAt: new Date().toISOString(),
  };
} catch (error) {
  result = {
    status: 'error',
    target,
    detail: error instanceof Error ? error.stack || error.message : String(error),
    requestFailures,
    consoleErrors,
    checkedAt: new Date().toISOString(),
  };
} finally {
  await browser.close();
}

await fs.writeFile(out, JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
if (result.status !== 'pass') process.exitCode = 1;
