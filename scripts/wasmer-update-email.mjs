import { chromium } from 'playwright-core';
import fs from 'fs';

const state = JSON.parse(fs.readFileSync('/tmp/wasmer-result.json', 'utf8'));
const targetEmail = fs.readFileSync('/tmp/target-email.txt', 'utf8').trim();
const out = {
  status: 'starting',
  dashboard: false,
  verificationOpened: false,
  emailUpdated: false,
  confirmationDetected: false,
  detail: null,
  updatedAt: new Date().toISOString(),
};
function save() {
  out.updatedAt = new Date().toISOString();
  fs.writeFileSync('/tmp/wasmer-email-update.json', JSON.stringify(out, null, 2));
}
function redact(s='') {
  return String(s).replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig, 'EMAIL_REDACTED').slice(0, 1800);
}
async function text(locator) {
  return (await locator.innerText().catch(() => '')).replace(/\s+/g, ' ').trim();
}
async function findVisible(ctx, selector, timeoutMs=9000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    for (const p of ctx.pages()) {
      for (const f of p.frames()) {
        const loc = f.locator(selector).first();
        if (await loc.count().catch(() => 0)) {
          if (await loc.isVisible().catch(() => false)) return { loc, page: p, frame: f };
        }
      }
    }
    await new Promise(r => setTimeout(r, 300));
  }
  return null;
}
async function safeSnapshot(ctx) {
  const items = [];
  for (const p of ctx.pages()) {
    items.push(`url=${p.url()}`);
    for (const f of p.frames()) {
      const controls = await f.locator('input,button,a').evaluateAll(xs => xs.map(x => ({
        tag: x.tagName.toLowerCase(),
        type: x.getAttribute('type'),
        name: x.getAttribute('name'),
        placeholder: x.getAttribute('placeholder'),
        text: (x.innerText || x.textContent || '').replace(/\s+/g,' ').trim().slice(0,80),
      })).filter(x => x.placeholder || x.name || /email|verify|update/i.test(x.text)).slice(0,30)).catch(() => []);
      if (controls.length) items.push(JSON.stringify(controls));
    }
  }
  return redact(items.join(' '));
}

const browser = await chromium.launch({
  headless: true,
  executablePath: '/usr/bin/google-chrome',
  args: ['--no-sandbox'],
});
const ctx = await browser.newContext({ storageState: '/tmp/wasmer-browser-state.json' });
const page = await ctx.newPage();
try {
  save();
  const dash = `https://wasmer.io/apps/${encodeURIComponent(state.username)}/${encodeURIComponent(state.appName)}`;
  await page.goto(dash, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(1500);
  const body = await text(page.locator('body'));
  if (/\/login(?:[/?#]|$)/i.test(page.url()) || /Sign up Log in Username or email/i.test(body)) {
    out.status = 'stored_session_expired';
    out.detail = redact(body);
    save();
    process.exit(0);
  }
  out.dashboard = true;
  save();

  const verify = page.locator('button,a').filter({ hasText: /Verify your account/i }).first();
  if (!(await verify.count()) || !(await verify.isVisible().catch(() => false))) {
    if (!/expire|verify your account/i.test(body)) {
      out.status = 'already_verified_or_no_banner';
      out.confirmationDetected = true;
      save();
      process.exit(0);
    }
    out.status = 'verification_control_missing';
    out.detail = redact(body);
    save();
    process.exit(0);
  }

  await verify.click();
  out.verificationOpened = true;
  save();

  const emailHit = await findVisible(ctx, 'input[placeholder*="email" i], input[type=email], input[name=email]', 10000);
  if (!emailHit) {
    out.status = 'email_input_missing';
    out.detail = await safeSnapshot(ctx);
    save();
    process.exit(0);
  }
  await emailHit.loc.fill(targetEmail);

  const updateHit = await findVisible(ctx, 'button:has-text("Update email"), input[type=submit][value*="Update" i]', 5000);
  if (!updateHit) {
    out.status = 'update_button_missing';
    out.detail = await safeSnapshot(ctx);
    save();
    process.exit(0);
  }
  await updateHit.loc.click();
  await page.waitForTimeout(2500);
  out.emailUpdated = true;

  const allText = [];
  for (const p of ctx.pages()) allText.push(await text(p.locator('body')));
  const after = redact(allText.join(' '));
  out.confirmationDetected = /verify|verification|email sent|check your email|confirmation|resend/i.test(after);
  out.status = out.confirmationDetected ? 'verification_email_requested' : 'email_updated_unconfirmed';
  out.detail = after;
  save();
} catch (e) {
  out.status = 'error';
  out.detail = redact(String(e));
  save();
} finally {
  await browser.close();
}
