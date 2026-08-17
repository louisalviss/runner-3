import { chromium } from 'playwright-core';
import fs from 'fs';

const statePath = '/tmp/pntr-browser-state.json';
if (!fs.existsSync(statePath)) throw new Error('PNTR storage state missing');

const browser = await chromium.launch({
  headless: false,
  executablePath: '/usr/bin/google-chrome',
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--disable-gpu',
    '--window-size=1400,850',
  ],
});

const context = await browser.newContext({
  storageState: statePath,
  viewport: { width: 1360, height: 760 },
});
const page = await context.newPage();
await page.goto('https://pntr.dev/dashboard', { waitUntil: 'domcontentloaded', timeout: 60000 });
await page.waitForTimeout(2500);

console.log('PNTR_INTERACTIVE_BROWSER_READY');

const interval = setInterval(async () => {
  try {
    const body = await page.locator('body').innerText({ timeout: 1000 });
    const hasDomain = body.toLowerCase().includes('runner3wp.pntr.dev');
    const isGuest = /guest session|sign in to keep them/i.test(body);
    if (hasDomain && !isGuest) {
      fs.writeFileSync('/tmp/pntr-bind-success', new Date().toISOString());
      console.log('PNTR_BIND_CONFIRMED');
      clearInterval(interval);
    }
  } catch {}
}, 2500);

const stop = async () => {
  clearInterval(interval);
  await browser.close().catch(() => {});
  process.exit(0);
};
process.on('SIGTERM', stop);
process.on('SIGINT', stop);
await new Promise(() => {});
