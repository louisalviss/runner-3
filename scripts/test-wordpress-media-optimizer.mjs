import { chromium } from 'playwright-core';
import fs from 'fs';
import zlib from 'zlib';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const publicBase = String(process.env.WP_PUBLIC_URL || 'https://runner3wp.pntr.dev').replace(/\/$/, '');
const stateFile = `ops/site-factory/${slug}.json`;
const out = '/tmp/runner3-media-selftest.json';

if (!fs.existsSync(stateFile)) throw new Error(`site factory state missing: ${stateFile}`);
if (!fs.existsSync('/tmp/wasmer-account.json')) throw new Error('decrypted Wasmer account state missing');

const site = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const nativeBase = String(site.siteUrl || '').replace(/\/$/, '');
const adminBase = `${nativeBase}/wp-admin/`;
const dashboard = site.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName)}`;

const result = {
  status: 'starting',
  siteSlug: slug,
  publicUrl: publicBase + '/',
  nativeUrl: nativeBase + '/',
  settingsPageReached: false,
  enabled: false,
  autoNew: false,
  rewriteSrcset: false,
  r2Enabled: null,
  optimizedBefore: null,
  optimizedAfter: null,
  mediaTotalBefore: null,
  mediaTotalAfter: null,
  attachmentId: null,
  attachmentUrl: null,
  uploadHttp: null,
  postId: null,
  publicTestUrl: null,
  responsiveVariantCount: 0,
  srcset: null,
  sizes: null,
  generatedWidths: [],
  variantChecks: [],
  consoleErrors: [],
  pageErrors: [],
  cleanupPost: false,
  testAttachmentLeftInLibrary: false,
  detail: null,
  checkedAt: new Date().toISOString(),
};

function save() {
  result.checkedAt = new Date().toISOString();
  fs.writeFileSync(out, `${JSON.stringify(result, null, 2)}\n`);
}

function crc32(buf) {
  let c = 0xffffffff;
  for (const b of buf) {
    c ^= b;
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ ((c & 1) ? 0xedb88320 : 0);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const t = Buffer.from(type, 'ascii');
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length, 0);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(Buffer.concat([t, data])), 0);
  return Buffer.concat([len, t, data, crc]);
}

function makePng(width = 1600, height = 900) {
  const stride = width * 3 + 1;
  const raw = Buffer.alloc(stride * height);
  for (let y = 0; y < height; y++) {
    const row = y * stride;
    raw[row] = 0;
    for (let x = 0; x < width; x++) {
      const i = row + 1 + x * 3;
      raw[i] = (x * 255 / Math.max(1, width - 1)) | 0;
      raw[i + 1] = (y * 255 / Math.max(1, height - 1)) | 0;
      raw[i + 2] = (x + y) % 256;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0); ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([
    Buffer.from([137,80,78,71,13,10,26,10]),
    pngChunk('IHDR', ihdr),
    pngChunk('IDAT', zlib.deflateSync(raw, { level: 6 })),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
}

async function text(page) {
  return (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ').trim();
}

async function loginWasmer(page) {
  await page.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
  const ident = page.locator('input[name=username],input[placeholder*=Username i],input[type=text]').first();
  await ident.waitFor({ state: 'visible', timeout: 15000 });
  await ident.fill(account.username || account.email);
  const next = page.locator('button').filter({ hasText: /continue|next|log in|sign in/i }).first();
  if (await next.count() && await next.isVisible().catch(() => false)) await next.click(); else await ident.press('Enter');
  const pass = page.locator('input[type=password]').first();
  await pass.waitFor({ state: 'visible', timeout: 15000 });
  await pass.fill(account.password);
  const submit = page.locator('input[type=submit],button').filter({ hasText: /log in|sign in|continue/i }).first();
  if (await submit.count() && await submit.isVisible().catch(() => false)) await submit.click(); else await pass.press('Enter');
  await page.waitForTimeout(3500);
  if (/\/login(?:[/?#]|$)/i.test(page.url())) throw new Error('wasmer_login_failed');
}

function isNativeAdmin(raw) {
  try {
    const u = new URL(raw);
    return u.host === new URL(nativeBase).host && u.pathname.startsWith('/wp-admin');
  } catch { return false; }
}

async function enterAdmin(ctx, page) {
  await page.goto(dashboard, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(1000);
  const admin = page.getByText(/WordPress Admin/i).first();
  if (!(await admin.count())) throw new Error('wordpress_admin_control_missing');
  const href = await admin.getAttribute('href').catch(() => null);
  if (href) {
    const wp = await ctx.newPage();
    await wp.goto(new URL(href, 'https://wasmer.io').href, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wp.waitForTimeout(2200);
    if (isNativeAdmin(wp.url())) return wp;
    await wp.close().catch(() => {});
  }
  const popupP = ctx.waitForEvent('page', { timeout: 10000 }).catch(() => null);
  await admin.click().catch(() => {});
  const popup = await popupP;
  await page.waitForTimeout(2500);
  for (const p of [popup, ...ctx.pages()].filter(Boolean)) if (isNativeAdmin(p.url())) return p;
  throw new Error('magic_admin_failed');
}

function parseStats(body) {
  const m = body.match(/Media Library:\s*(\d+)\s+optimized\s*\/\s*(\d+)\s+images/i);
  return m ? { optimized: Number(m[1]), total: Number(m[2]) } : { optimized: null, total: null };
}

async function findUploadedAttachment(wp, stem) {
  const listUrl = `${adminBase}upload.php?mode=list&s=${encodeURIComponent(stem)}`;
  for (let attempt = 0; attempt < 8; attempt++) {
    await wp.goto(listUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wp.waitForTimeout(900 + attempt * 300);
    const rows = wp.locator('table.wp-list-table tbody tr');
    const count = await rows.count();
    for (let i = 0; i < count; i++) {
      const row = rows.nth(i);
      const body = await row.innerText().catch(() => '');
      if (!body.includes(stem)) continue;
      const idAttr = await row.getAttribute('id').catch(() => '');
      let id = Number(String(idAttr || '').replace(/^post-/, '')) || null;
      if (!id) {
        const href = await row.locator('a[href*="post.php?post="]').first().getAttribute('href').catch(() => null);
        const m = href && href.match(/[?&]post=(\d+)/);
        if (m) id = Number(m[1]);
      }
      if (id) return { id, row };
    }
  }
  return null;
}

async function extractAttachmentUrl(wp, attachmentId, stem) {
  await wp.goto(`${adminBase}post.php?post=${attachmentId}&action=edit`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(700);
  const candidates = wp.locator('input[value*="' + stem.replace(/"/g, '') + '"]');
  const count = await candidates.count();
  for (let i = 0; i < count; i++) {
    const value = await candidates.nth(i).inputValue().catch(() => '');
    if (/^https?:\/\//i.test(value) && value.includes('/uploads/')) return value;
  }
  const html = await wp.content();
  const re = new RegExp(`https?:[^"'<>\\s]+${stem.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}[^"'<>\\s]*\\.png`, 'i');
  const m = html.match(re);
  return m ? m[0].replace(/&amp;/g, '&') : null;
}

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome',
  args: ['--no-sandbox'],
});
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const wasmerPage = await ctx.newPage();

try {
  save();
  await loginWasmer(wasmerPage);
  const wp = await enterAdmin(ctx, wasmerPage);

  const settingsUrl = `${adminBase}options-general.php?page=runner3-media-optimizer`;
  await wp.goto(settingsUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(500);
  const body0 = await text(wp);
  if (!/Runner3 Media Optimizer/i.test(body0)) throw new Error('media_optimizer_settings_page_missing');
  result.settingsPageReached = true;
  const before = parseStats(body0);
  result.optimizedBefore = before.optimized;
  result.mediaTotalBefore = before.total;

  const names = {
    enabled: 'runner3_media_optimizer[enabled]',
    autoNew: 'runner3_media_optimizer[auto_new]',
    rewrite: 'runner3_media_optimizer[rewrite_srcset]',
    r2: 'runner3_media_optimizer[r2_enabled]',
  };
  for (const key of [names.enabled, names.autoNew, names.rewrite]) {
    const box = wp.locator(`input[name="${key}"]`).first();
    await box.waitFor({ state: 'attached', timeout: 10000 });
    if (!(await box.isChecked())) await box.check();
  }
  await wp.locator('#submit,input[type=submit][value*="Save" i]').first().click();
  await wp.waitForLoadState('domcontentloaded').catch(() => {});
  await wp.waitForTimeout(600);
  await wp.goto(settingsUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(400);

  result.enabled = await wp.locator(`input[name="${names.enabled}"]`).first().isChecked();
  result.autoNew = await wp.locator(`input[name="${names.autoNew}"]`).first().isChecked();
  result.rewriteSrcset = await wp.locator(`input[name="${names.rewrite}"]`).first().isChecked();
  result.r2Enabled = await wp.locator(`input[name="${names.r2}"]`).first().isChecked().catch(() => false);
  if (!result.enabled || !result.autoNew || !result.rewriteSrcset) throw new Error('required_optimizer_options_not_enabled');

  const stamp = Date.now();
  const stem = `runner3-media-selftest-${stamp}`;
  const filename = `${stem}.png`;
  const testFile = `/tmp/${filename}`;
  fs.writeFileSync(testFile, makePng(1600, 900));

  await wp.goto(`${adminBase}media-new.php`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const fileInput = wp.locator('input[type=file]').first();
  await fileInput.waitFor({ state: 'attached', timeout: 15000 });
  const responsePromise = wp.waitForResponse(
    r => /async-upload\.php|media-new\.php/i.test(r.url()) && ['POST', 'PUT'].includes(r.request().method()),
    { timeout: 45000 },
  ).catch(() => null);
  await fileInput.setInputFiles(testFile);
  const uploadResponse = await responsePromise;
  result.uploadHttp = uploadResponse ? uploadResponse.status() : null;
  await wp.waitForTimeout(6500);

  const uploadBody = await text(wp);
  if (/HTTP error|upload failed|could not be uploaded|error uploading/i.test(uploadBody)) {
    throw new Error(`media_ui_upload_failed:${uploadBody.slice(0, 500)}`);
  }

  const found = await findUploadedAttachment(wp, stem);
  if (!found) throw new Error('uploaded_attachment_not_found_in_media_library');
  result.attachmentId = found.id;
  result.testAttachmentLeftInLibrary = true;

  const attachmentUrl = await extractAttachmentUrl(wp, found.id, stem);
  if (!attachmentUrl) throw new Error('attachment_original_url_not_found');
  result.attachmentUrl = attachmentUrl;

  await wp.goto(settingsUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(500);
  const after = parseStats(await text(wp));
  result.optimizedAfter = after.optimized;
  result.mediaTotalAfter = after.total;
  if (before.optimized !== null && after.optimized !== null && after.optimized <= before.optimized) {
    throw new Error(`optimized_media_count_did_not_increase:${before.optimized}->${after.optimized}`);
  }

  const original = new URL(attachmentUrl);
  const dir = original.pathname.slice(0, original.pathname.lastIndexOf('/') + 1);
  const actualStem = decodeURIComponent(original.pathname.slice(original.pathname.lastIndexOf('/') + 1)).replace(/\.png$/i, '');
  const checks = [];
  for (const width of [360, 480, 640, 960, 1280]) {
    const u = new URL(original.href);
    u.pathname = `${dir}${encodeURIComponent(`${actualStem}-r3-w${width}.webp`)}`;
    const res = await ctx.request.get(u.href, { timeout: 30000 });
    checks.push({ width, url: u.href, http: res.status(), contentType: res.headers()['content-type'] || null });
  }
  result.variantChecks = checks;
  result.generatedWidths = checks.filter(x => x.http === 200 && /image\/webp/i.test(x.contentType || '')).map(x => x.width);
  result.responsiveVariantCount = result.generatedWidths.length;
  result.srcset = checks.filter(x => x.http === 200).map(x => `${x.url} ${x.width}w`).join(', ') || null;
  result.sizes = '(max-width: 767px) 92vw, 1100px';

  if (result.responsiveVariantCount < 3) {
    throw new Error(`automatic_webp_variants_missing:${JSON.stringify(checks)}`);
  }

  result.status = 'ok';
  result.detail = result.r2Enabled
    ? `optimizer_enabled; real Media Library upload PASS; ${result.responsiveVariantCount} WebP variants generated; R2 option enabled`
    : `optimizer_enabled; real Media Library upload PASS; ${result.responsiveVariantCount} local WebP variants generated automatically; R2 remains off`;
} catch (error) {
  result.status = 'failed';
  result.detail = String(error?.stack || error);
  process.exitCode = 1;
} finally {
  save();
  await ctx.close().catch(() => {});
  await browser.close().catch(() => {});
}

console.log(JSON.stringify(result, null, 2));
