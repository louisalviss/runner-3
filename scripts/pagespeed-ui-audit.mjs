import { chromium } from 'playwright-core';
import fs from 'node:fs';

const target = process.env.PSI_URL || 'https://runner3-factory-smoke-2.wasmer.app/';
const out = process.env.PSI_UI_OUT || 'ops/pagespeed/ui-latest.json';
const screenshotBase = process.env.PSI_UI_SCREENSHOT || 'ops/pagespeed/ui-latest.png';
fs.mkdirSync('ops/pagespeed', { recursive: true });

const chromeCandidates = [
  process.env.CHROME_PATH,
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
].filter(Boolean);
const executablePath = chromeCandidates.find((p) => fs.existsSync(p));
if (!executablePath) throw new Error(`Chrome not found: ${chromeCandidates.join(', ')}`);

const browser = await chromium.launch({
  headless: true,
  executablePath,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
});

function parseMetric(text, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const patterns = [
    new RegExp(`${escaped}\\s*\\n\\s*([0-9.]+)\\s*(ms|s)?`, 'i'),
    new RegExp(`${escaped}[^0-9]{0,100}([0-9.]+)\\s*(ms|s)`, 'i'),
  ];
  for (const re of patterns) {
    const match = text.match(re);
    if (match) return `${match[1]}${match[2] || ''}`;
  }
  return null;
}

function scoreBeforeLabel(lines, label) {
  for (let i = 1; i < lines.length; i++) {
    if (lines[i] !== label) continue;
    const score = Number(lines[i - 1]);
    if (Number.isInteger(score) && score >= 0 && score <= 100) return score;
  }
  return null;
}

function parseScores(text) {
  const lines = text.split('\n').map((s) => s.trim()).filter(Boolean);
  return {
    performance: scoreBeforeLabel(lines, 'Performance') ?? scoreBeforeLabel(lines, 'Hiệu suất'),
    accessibility: scoreBeforeLabel(lines, 'Accessibility') ?? scoreBeforeLabel(lines, 'Hỗ trợ tiếp cận'),
    bestPractices: scoreBeforeLabel(lines, 'Best Practices') ?? scoreBeforeLabel(lines, 'Các phương pháp hay nhất'),
    seo: scoreBeforeLabel(lines, 'SEO'),
  };
}

function extractSavings(text) {
  const rows = [];
  const lines = text.split('\n').map((s) => s.trim()).filter(Boolean);
  for (const line of lines) {
    const match = line.match(/^(.*?)(?:\s+)(Est savings of|Potential savings of|Tiết kiệm ước tính)\s+(.+)$/i);
    if (!match) continue;
    rows.push({ audit: match[1].trim(), savings: `${match[2]} ${match[3]}`.trim() });
    if (rows.length >= 12) break;
  }
  return rows;
}

async function waitForLabResult(page, timeoutMs = 180_000) {
  await page.waitForFunction(() => {
    const text = document.body.innerText || '';
    return /Largest Contentful Paint/i.test(text) && /First Contentful Paint/i.test(text) && /\bPerformance\b/i.test(text) && /\bSEO\b/i.test(text);
  }, { timeout: timeoutMs });
  // PSI can expose the metric headings just before the numeric score settles.
  const started = Date.now();
  while (Date.now() - started < 60_000) {
    const text = await page.locator('body').innerText();
    const scores = parseScores(text);
    const lcp = parseMetric(text, 'Largest Contentful Paint');
    const fcp = parseMetric(text, 'First Contentful Paint');
    if (scores.performance !== null && lcp !== null && fcp !== null) return;
    await page.waitForTimeout(1_500);
  }
  throw new Error('PageSpeed lab result headings appeared but numeric scores did not settle');
}

async function collect(page, strategy) {
  if (strategy === 'desktop') {
    const desktop = page.getByText(/Desktop|Máy tính/i, { exact: true }).first();
    await desktop.waitFor({ state: 'visible', timeout: 30_000 });
    await desktop.click();
    await page.waitForURL(/form_factor=desktop/, { timeout: 30_000 });
    await waitForLabResult(page, 180_000);
    await page.waitForTimeout(1_500);
  }

  const body = await page.locator('body').innerText();
  return {
    scores: parseScores(body),
    metrics: {
      fcp: parseMetric(body, 'First Contentful Paint'),
      lcp: parseMetric(body, 'Largest Contentful Paint'),
      tbt: parseMetric(body, 'Total Blocking Time'),
      cls: parseMetric(body, 'Cumulative Layout Shift'),
      speedIndex: parseMetric(body, 'Speed Index'),
    },
    savings: extractSavings(body),
    textSample: body.slice(0, 28_000),
  };
}

const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
const result = {
  status: 'starting',
  target,
  checkedAt: new Date().toISOString(),
  resultUrl: null,
  mobile: null,
  desktop: null,
  detail: null,
};

try {
  await page.goto('https://pagespeed.web.dev/?hl=en', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  const input = page.locator('input').first();
  await input.waitFor({ state: 'visible', timeout: 30_000 });
  await input.fill(target);
  await page.getByRole('button', { name: /analy[sz]e/i }).first().click();
  await page.waitForURL(/pagespeed\.web\.dev\/analysis\//, { timeout: 90_000 }).catch(() => {});
  await waitForLabResult(page, 180_000);
  await page.waitForTimeout(1_500);

  const body = await page.locator('body').innerText();
  if (/quota exceeded/i.test(body)) throw new Error('Google PageSpeed UI reported quota exceeded');

  result.resultUrl = page.url();
  result.mobile = await collect(page, 'mobile');
  await page.screenshot({ path: screenshotBase, fullPage: true });
  result.desktop = await collect(page, 'desktop');
  await page.screenshot({ path: screenshotBase.replace(/\.png$/i, '-desktop.png'), fullPage: true });
  result.status = 'ready';
} catch (error) {
  result.status = 'failed';
  result.detail = String(error?.stack || error);
  result.resultUrl = page.url();
  result.debugText = (await page.locator('body').innerText().catch(() => '')).slice(0, 28_000);
  await page.screenshot({ path: screenshotBase, fullPage: true }).catch(() => {});
} finally {
  fs.writeFileSync(out, `${JSON.stringify(result, null, 2)}\n`);
  await browser.close();
}

console.log(JSON.stringify({
  status: result.status,
  target: result.target,
  resultUrl: result.resultUrl,
  mobile: result.mobile && { scores: result.mobile.scores, metrics: result.mobile.metrics, savings: result.mobile.savings },
  desktop: result.desktop && { scores: result.desktop.scores, metrics: result.desktop.metrics, savings: result.desktop.savings },
  detail: result.detail,
}, null, 2));

if (result.status !== 'ready') process.exitCode = 1;
