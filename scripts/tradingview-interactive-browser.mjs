import fs from 'node:fs';
import { chromium } from 'playwright-core';

const profileDir = '/tmp/tv-profile';
const confirmFile = '/tmp/tv-session-confirmed';
const executableCandidates = [
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium-browser',
  '/usr/bin/chromium'
];
const executablePath = executableCandidates.find((p) => fs.existsSync(p));
if (!executablePath) throw new Error('No Chrome/Chromium executable found');

fs.mkdirSync(profileDir, { recursive: true });
try { fs.unlinkSync(confirmFile); } catch {}

const context = await chromium.launchPersistentContext(profileDir, {
  executablePath,
  headless: false,
  viewport: null,
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--disable-blink-features=AutomationControlled',
    '--window-size=1440,900'
  ]
});

await context.exposeFunction('__tvSaveSession', async () => {
  fs.writeFileSync(confirmFile, new Date().toISOString(), { mode: 0o600 });
  return true;
});

const injectButton = async (page) => {
  try {
    await page.evaluate(() => {
      const mount = () => {
        if (document.getElementById('__tv_session_save_button')) return;
        const b = document.createElement('button');
        b.id = '__tv_session_save_button';
        b.textContent = 'SAVE LOGIN';
        Object.assign(b.style, {
          position: 'fixed', top: '12px', right: '12px', zIndex: '2147483647',
          padding: '12px 16px', border: '0', borderRadius: '10px',
          background: '#16a34a', color: '#fff', fontSize: '15px', fontWeight: '700',
          boxShadow: '0 2px 10px rgba(0,0,0,.35)', cursor: 'pointer'
        });
        b.onclick = async () => {
          b.disabled = true;
          b.textContent = 'SAVING...';
          try {
            await window.__tvSaveSession();
            b.textContent = 'SAVED';
          } catch {
            b.disabled = false;
            b.textContent = 'SAVE LOGIN';
          }
        };
        document.documentElement.appendChild(b);
      };
      mount();
      setInterval(mount, 1500);
    });
  } catch {}
};

context.on('page', (page) => {
  page.on('domcontentloaded', () => injectButton(page));
});

let page = context.pages()[0];
if (!page) page = await context.newPage();
await page.goto('https://www.tradingview.com/chart/', { waitUntil: 'domcontentloaded', timeout: 90000 });
await injectButton(page);
console.log('TV_INTERACTIVE_BROWSER_READY');

for (;;) {
  if (fs.existsSync(confirmFile)) break;
  await new Promise((r) => setTimeout(r, 1000));
}

await new Promise((r) => setTimeout(r, 5000));
await context.close();
console.log('TV_INTERACTIVE_PROFILE_CLOSED');
