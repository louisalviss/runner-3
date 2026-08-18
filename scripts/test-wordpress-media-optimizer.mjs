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
  consoleErrors: [],
  pageErrors: [],
  cleanupPost: false,
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
      raw[i + 2] = ((x + y) % 256);
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0); ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
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
  try { const u = new URL(raw); return u.host === new URL(nativeBase).host && u.pathname.startsWith('/wp-admin'); }
  catch { return false; }
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

async function getRestNonce(wp) {
  const direct = await wp.evaluate(() => window.wpApiSettings?.nonce || null).catch(() => null);
  if (direct) return direct;
  const html = await wp.content();
  const m = html.match(/wpApiSettings\s*=\s*(\{[^;]+\});/s);
  if (m) {
    try { return JSON.parse(m[1]).nonce || null; } catch {}
  }
  const generic = html.match(/"nonce"\s*:\s*"([a-zA-Z0-9]+)"/);
  return generic?.[1] || null;
}

function htmlAttr(tag, name) {
  const m = tag.match(new RegExp(`\\b${name}\\s*=\\s*["']([^"']*)["']`, 'i'));
  return m?.[1] || '';
}

const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const wasmerPage = await ctx.newPage();
let testPostId = null;

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
  const submit = wp.locator('#submit,input[type=submit][value*="Save" i]').first();
  await submit.click();
  await wp.waitForLoadState('domcontentloaded').catch(() => {});
  await wp.waitForTimeout(700);
  await wp.goto(settingsUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(400);

  result.enabled = await wp.locator(`input[name="${names.enabled}"]`).first().isChecked();
  result.autoNew = await wp.locator(`input[name="${names.autoNew}"]`).first().isChecked();
  result.rewriteSrcset = await wp.locator(`input[name="${names.rewrite}"]`).first().isChecked();
  result.r2Enabled = await wp.locator(`input[name="${names.r2}"]`).first().isChecked().catch(() => false);
  if (!result.enabled || !result.autoNew || !result.rewriteSrcset) throw new Error('required_optimizer_options_not_enabled');

  const nonce = await getRestNonce(wp);
  if (!nonce) throw new Error('wordpress_rest_nonce_missing');

  const png = makePng();
  const stamp = Date.now();
  const filename = `runner3-media-selftest-${stamp}.png`;
  const upload = await ctx.request.post(`${nativeBase}/wp-json/wp/v2/media`, {
    headers: {
      'X-WP-Nonce': nonce,
      'Content-Type': 'image/png',
      'Content-Disposition': `attachment; filename="${filename}"`,
    },
    data: png,
    timeout: 120000,
  });
  result.uploadHttp = upload.status();
  const uploadText = await upload.text();
  if (upload.status() !== 201) throw new Error(`media_upload_failed_${upload.status()}:${uploadText.slice(0, 400)}`);
  const media = JSON.parse(uploadText);
  result.attachmentId = media.id;
  result.attachmentUrl = media.source_url;

  await wp.goto(settingsUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(500);
  const after = parseStats(await text(wp));
  result.optimizedAfter = after.optimized;
  result.mediaTotalAfter = after.total;
  if (before.optimized !== null && after.optimized !== null && after.optimized <= before.optimized) throw new Error('optimized_media_count_did_not_increase');

  const block = `<!-- wp:image {"id":${media.id},"sizeSlug":"full","linkDestination":"none"} --><figure class="wp-block-image size-full"><img src="${media.source_url}" alt="Runner3 optimizer self-test" class="wp-image-${media.id}"/></figure><!-- /wp:image -->`;
  const postRes = await ctx.request.post(`${nativeBase}/wp-json/wp/v2/posts`, {
    headers: { 'X-WP-Nonce': nonce, 'Content-Type': 'application/json' },
    data: { title: `Runner3 Media Optimizer Self-Test ${stamp}`, status: 'publish', content: block },
    timeout: 60000,
  });
  const postText = await postRes.text();
  if (postRes.status() !== 201) throw new Error(`test_post_create_failed_${postRes.status()}:${postText.slice(0, 400)}`);
  const post = JSON.parse(postText);
  testPostId = post.id;
  result.postId = post.id;
  const path = new URL(post.link).pathname + new URL(post.link).search;
  result.publicTestUrl = publicBase + path;

  const publicCtx = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 393, height: 852 }, deviceScaleFactor: 2 });
  const page = await publicCtx.newPage();
  page.on('console', msg => { if (msg.type() === 'error') result.consoleErrors.push({ text: msg.text(), location: msg.location() }); });
  page.on('pageerror', e => result.pageErrors.push(String(e?.message || e)));
  const publicRes = await page.goto(result.publicTestUrl, { waitUntil: 'networkidle', timeout: 60000 });
  if (!publicRes || publicRes.status() !== 200) throw new Error(`public_test_post_http_${publicRes?.status() ?? 'none'}`);
  const html = await page.content();
  const tags = html.match(/<img\b[^>]*>/gi) || [];
  const tag = tags.find(t => new RegExp(`wp-image-${media.id}\\b`).test(t)) || tags.find(t => t.includes(media.source_url));
  if (!tag) throw new Error('test_attachment_img_missing_on_frontend');
  result.srcset = htmlAttr(tag, 'srcset') || null;
  result.sizes = htmlAttr(tag, 'sizes') || null;
  result.generatedWidths = Array.from(new Set((result.srcset?.match(/-r3-w(\d+)\.webp/g) || []).map(x => Number(x.match(/-r3-w(\d+)\.webp/)[1])))).sort((a,b)=>a-b);
  result.responsiveVariantCount = result.generatedWidths.length;
  await publicCtx.close();

  if (result.responsiveVariantCount < 3) throw new Error(`native_srcset_missing_runner3_variants:${result.srcset || 'empty'}`);
  if (result.consoleErrors.length || result.pageErrors.length) throw new Error('frontend_javascript_error_detected');

  result.status = 'ok';
  result.detail = result.r2Enabled
    ? 'optimizer_enabled; auto-new PASS; native srcset PASS; R2 option enabled'
    : 'optimizer_enabled; auto-new PASS; native srcset PASS; R2 remains off because no stored R2 credentials were forced';
} catch (error) {
  result.status = 'failed';
  result.detail = String(error?.stack || error);
  process.exitCode = 1;
} finally {
  if (testPostId) {
    try {
      const wpPage = ctx.pages().find(p => isNativeAdmin(p.url()));
      const nonce = wpPage ? await getRestNonce(wpPage) : null;
      if (nonce) {
        const del = await ctx.request.delete(`${nativeBase}/wp-json/wp/v2/posts/${testPostId}?force=true`, { headers: { 'X-WP-Nonce': nonce }, timeout: 30000 });
        result.cleanupPost = del.ok();
      }
    } catch {}
  }
  save();
  await ctx.close().catch(() => {});
  await browser.close().catch(() => {});
}

console.log(JSON.stringify(result, null, 2));
