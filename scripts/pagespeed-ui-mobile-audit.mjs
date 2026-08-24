import { chromium } from 'playwright-core';
import fs from 'node:fs';

const target = process.env.PSI_URL;
const out = process.env.PSI_UI_OUT || '/tmp/runner3wp-mobile-psi.json';
if (!target) throw new Error('PSI_URL is required');

const candidates = [process.env.CHROME_PATH, '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'].filter(Boolean);
const executablePath = candidates.find((p) => fs.existsSync(p));
if (!executablePath) throw new Error(`Chrome not found: ${candidates.join(', ')}`);

function metric(text, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  for (const re of [
    new RegExp(`${escaped}\\s*\\n\\s*([0-9.]+)\\s*(ms|s)?`, 'i'),
    new RegExp(`${escaped}[^0-9]{0,100}([0-9.]+)\\s*(ms|s)`, 'i'),
  ]) {
    const m = text.match(re);
    if (m) return `${m[1]}${m[2] || ''}`;
  }
  return null;
}

function score(text, label) {
  const lines = text.split('\n').map((x) => x.trim()).filter(Boolean);
  for (let i = 1; i < lines.length; i++) {
    if (lines[i] !== label) continue;
    const n = Number(lines[i - 1]);
    if (Number.isInteger(n) && n >= 0 && n <= 100) return n;
  }
  return null;
}

const browser = await chromium.launch({
  headless: true,
  executablePath,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
const result = {
  status: 'starting',
  target,
  checkedAt: new Date().toISOString(),
  resultUrl: null,
  performance: null,
  fcp: null,
  lcp: null,
  tbt: null,
  cls: null,
  detail: null,
};

try {
  await page.goto('https://pagespeed.web.dev/?hl=en', {
    waitUntil: 'domcontentloaded',
    timeout: 60_000,
  });
  const input = page.locator('input').first();
  await input.waitFor({ state: 'visible', timeout: 30_000 });
  await input.fill(target);
  await page.getByRole('button', { name: /analy[sz]e/i }).first().click();

  // waitForFunction(pageFunction, arg, options): passing the timeout object as
  // arg silently left Playwright's default 30s timeout in effect. Wait directly
  // on the actual result content and let the result URL settle independently.
  await page.waitForFunction(() => {
    const t = document.body.innerText || '';
    return /First Contentful Paint/i.test(t)
      && /Largest Contentful Paint/i.test(t)
      && /\bPerformance\b/i.test(t);
  }, null, { timeout: 75_000, polling: 1000 });

  const started = Date.now();
  let body = '';
  while (Date.now() - started < 45_000) {
    body = await page.locator('body').innerText();
    result.performance = score(body, 'Performance');
    result.fcp = metric(body, 'First Contentful Paint');
    result.lcp = metric(body, 'Largest Contentful Paint');
    result.tbt = metric(body, 'Total Blocking Time');
    result.cls = metric(body, 'Cumulative Layout Shift');
    if (result.performance !== null && result.fcp && result.lcp) break;
    await page.waitForTimeout(1000);
  }

  if (result.performance === null || !result.fcp || !result.lcp) {
    throw new Error('PageSpeed numeric mobile result did not settle');
  }
  result.resultUrl = page.url();
  result.status = 'ready';
} catch (error) {
  result.status = 'failed';
  result.resultUrl = page.url();
  let body = '';
  try {
    body = (await page.locator('body').innerText()).replace(/\s+/g, ' ').trim().slice(0, 1200);
  } catch (_) {}
  result.detail = `${String(error?.stack || error)}${body ? `\nPAGE_BODY: ${body}` : ''}`;
} finally {
  fs.writeFileSync(out, `${JSON.stringify(result, null, 2)}\n`);
  await browser.close();
}

console.log(JSON.stringify(result, null, 2));
if (result.status !== 'ready') process.exitCode = 1;
