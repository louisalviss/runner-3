import { chromium } from 'playwright-core';
import fs from 'fs';

const statePath = '/tmp/pntr-browser-state.json';
const outPath = '/tmp/pntr-bind-probe.json';
const targetDomain = 'runner3wp.pntr.dev';

function safeUrl(raw) {
  if (!raw) return null;
  try {
    const u = new URL(raw, 'https://pntr.dev');
    return {
      origin: u.origin,
      pathname: u.pathname,
      queryKeys: [...u.searchParams.keys()].slice(0, 20),
    };
  } catch {
    return { raw: String(raw).slice(0, 200) };
  }
}

function cleanText(s) {
  return String(s || '').replace(/\s+/g, ' ').trim().slice(0, 220);
}

const result = {
  status: 'starting',
  targetDomain,
  guestDomainVisible: false,
  pageUrl: null,
  authControls: [],
  scriptPaths: [],
  observedAuthPaths: [],
  detail: null,
  updatedAt: new Date().toISOString(),
};
const save = () => {
  result.updatedAt = new Date().toISOString();
  fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
};

if (!fs.existsSync(statePath)) {
  result.status = 'missing_state';
  save();
  process.exit(2);
}

const browser = await chromium.launch({
  headless: true,
  executablePath: '/usr/bin/google-chrome',
  args: ['--no-sandbox'],
});

try {
  const ctx = await browser.newContext({ storageState: statePath });
  const page = await ctx.newPage();

  page.on('request', req => {
    const u = safeUrl(req.url());
    if (!u?.origin || !u?.pathname) return;
    if (/auth|login|github|oauth|device|session|claim|attach|connect/i.test(u.pathname)) {
      const key = `${u.origin}${u.pathname}`;
      if (!result.observedAuthPaths.includes(key)) result.observedAuthPaths.push(key);
    }
  });

  await page.goto('https://pntr.dev/dashboard', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(1800);

  result.pageUrl = safeUrl(page.url());
  const body = cleanText(await page.locator('body').innerText().catch(() => ''));
  result.guestDomainVisible = body.toLowerCase().includes(targetDomain.toLowerCase());

  const controls = await page.locator('a,button,[role=button]').evaluateAll(nodes =>
    nodes.map(n => ({
      tag: n.tagName.toLowerCase(),
      text: (n.innerText || n.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 140),
      href: n.getAttribute('href'),
      aria: n.getAttribute('aria-label'),
    }))
      .filter(x => /github|sign in|login|attach|connect/i.test(`${x.text} ${x.aria || ''} ${x.href || ''}`))
      .slice(0, 30)
  ).catch(() => []);

  result.authControls = controls.map(x => ({
    tag: x.tag,
    text: cleanText(x.text || x.aria),
    href: safeUrl(x.href),
  }));

  const scripts = await page.locator('script[src]').evaluateAll(nodes => nodes.map(n => n.getAttribute('src')).filter(Boolean));
  result.scriptPaths = [...new Set(scripts.map(safeUrl).filter(Boolean).map(x => `${x.origin || ''}${x.pathname || ''}`))].slice(0, 40);

  // If the login control is a JS button rather than a normal href, click it but
  // stop before leaving PNTR. We only record origin/path, never OAuth query values.
  const login = page.locator('a,button,[role=button]').filter({ hasText: /sign in|login|github|attach|connect/i }).first();
  if (await login.count().catch(() => 0)) {
    const href = await login.getAttribute('href').catch(() => null);
    if (!href) {
      await page.route('**/*', async route => {
        const u = new URL(route.request().url());
        if (u.hostname !== 'pntr.dev' && u.hostname !== 'www.pntr.dev' && u.hostname !== 'api.pntr.dev') {
          const key = `${u.origin}${u.pathname}`;
          if (!result.observedAuthPaths.includes(key)) result.observedAuthPaths.push(key);
          return route.abort();
        }
        return route.continue();
      });
      await login.click({ timeout: 5000 }).catch(() => {});
      await page.waitForTimeout(1000);
    }
  }

  result.status = result.guestDomainVisible ? 'ready' : 'guest_domain_not_visible';
  result.detail = result.guestDomainVisible ? null : `bodySample=${body}`;
  await ctx.storageState({ path: statePath });
  save();
} catch (e) {
  result.status = 'error';
  result.detail = String(e).replace(/[A-Za-z0-9_-]{28,}/g, 'REDACTED').slice(0, 1200);
  save();
  process.exitCode = 1;
} finally {
  await browser.close();
}
