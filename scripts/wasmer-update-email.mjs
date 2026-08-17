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
  return String(s).replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig, 'EMAIL_REDACTED').slice(0, 1600);
}
async function text(locator) {
  return (await locator.innerText().catch(() => '')).replace(/\s+/g, ' ').trim();
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
  await page.waitForTimeout(900);
  out.verificationOpened = true;
  save();

  const dialog = page.locator('[role=dialog]').last();
  const root = (await dialog.count() && await dialog.isVisible().catch(() => false)) ? dialog : page;
  const email = root.locator('input[type=email], input[name=email]').first();
  if (!(await email.count()) || !(await email.isVisible().catch(() => false))) {
    out.status = 'email_input_missing';
    out.detail = redact(await text(root));
    save();
    process.exit(0);
  }
  await email.fill(targetEmail);

  const update = root.locator('button').filter({ hasText: /Update email/i }).first();
  if (!(await update.count()) || !(await update.isVisible().catch(() => false))) {
    out.status = 'update_button_missing';
    out.detail = redact(await text(root));
    save();
    process.exit(0);
  }
  await update.click();
  await page.waitForTimeout(2200);
  out.emailUpdated = true;

  const after = redact(await text(page.locator('body')));
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
