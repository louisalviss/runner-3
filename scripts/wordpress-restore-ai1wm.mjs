import { chromium } from 'playwright-core';
import fs from 'fs';
import crypto from 'crypto';

const requestPath = process.env.RESTORE_REQUEST_PATH;
if (!requestPath) throw new Error('RESTORE_REQUEST_PATH_missing');
const request = JSON.parse(fs.readFileSync(requestPath, 'utf8'));
const requestId = String(request.request_id || '').trim();
const slug = String(request.site_slug || '').trim();
if (!requestId || !slug) throw new Error('request_id_or_site_slug_missing');
if (!/^[a-zA-Z0-9._-]+$/.test(requestId) || !/^[a-z0-9-]+$/.test(slug)) throw new Error('invalid_request_id_or_site_slug');

const sitePath = `ops/site-factory/${slug}.json`;
if (!fs.existsSync(sitePath)) throw new Error(`site_factory_state_missing:${sitePath}`);
const site = JSON.parse(fs.readFileSync(sitePath, 'utf8'));
const account = JSON.parse(fs.readFileSync('/tmp/wasmer-account.json', 'utf8'));
const base = String(site.siteUrl || `https://${slug}.wasmer.app/`).replace(/\/$/, '');
const parsedBase = new URL(base);
if (!parsedBase.hostname.endsWith('.wasmer.app')) throw new Error(`non_disposable_target_rejected:${parsedBase.hostname}`);
const dashboard = site.dashboardUrl || `https://wasmer.io/apps/${encodeURIComponent(site.owner)}/${encodeURIComponent(site.appName || slug)}`;
const out = '/tmp/wordpress-restore-status.json';
const priorPath = `ops/wordpress-restore/${requestId}.json`;
let prior = {};
try { prior = JSON.parse(fs.readFileSync(priorPath, 'utf8')); } catch {}

const verify = request.verify || {};
const backup = request.backup || {};
const watchMinutes = Math.max(5, Math.min(80, Number(request.watch_minutes || 75)));
const safe = {
  status: 'STARTING',
  requestId,
  siteSlug: slug,
  siteUrl: `${base}/`,
  stage: 'init',
  authMode: 'wasmer-magic-admin-cookie-nonce',
  backup: {
    source: backup.source || null,
    name: backup.name || null,
    expectedSha256: backup.sha256 || null,
    bytes: null,
    sha256: null,
  },
  import: {
    jobId: request.resume_import_job_id || prior?.import?.jobId || null,
    started: false,
    uploadStatus: null,
    lastObserved: null,
  },
  verify: {
    title: verify.title || null,
    postSlug: verify.post_slug || null,
    pageSlug: verify.page_slug || null,
    matched: false,
  },
  detail: null,
  updatedAt: new Date().toISOString(),
};
const save = () => {
  safe.updatedAt = new Date().toISOString();
  fs.writeFileSync(out, JSON.stringify(safe, null, 2));
};
const stage = (s) => { safe.stage = s; console.log('STAGE', s); save(); };
const summary = (v, n = 700) => { try { return JSON.stringify(v).slice(0, n); } catch { return String(v).slice(0, n); } };
const stringsDeep = (v, out = []) => {
  if (typeof v === 'string') out.push(v);
  else if (Array.isArray(v)) for (const x of v) stringsDeep(x, out);
  else if (v && typeof v === 'object') for (const x of Object.values(v)) stringsDeep(x, out);
  return out;
};
const findJobId = (v) => {
  if (!v || typeof v !== 'object') return null;
  for (const k of ['job_id', 'jobId', 'id']) {
    const x = v[k];
    if (typeof x === 'string' && /^[a-f0-9]{13,40}$/i.test(x)) return x;
  }
  for (const x of Object.values(v)) { const y = findJobId(x); if (y) return y; }
  return null;
};
const findSecret = (v) => {
  if (!v || typeof v !== 'object') return null;
  for (const k of ['secret_key', 'secretKey', 'secret']) if (typeof v[k] === 'string' && v[k]) return v[k];
  for (const x of Object.values(v)) { const y = findSecret(x); if (y) return y; }
  return null;
};

async function publicJson(path, timeout = 45000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try {
    const r = await fetch(`${base}${path}`, { headers: { Accept: 'application/json', 'Cache-Control': 'no-cache' }, redirect: 'follow', signal: ctrl.signal });
    const t = await r.text();
    let d; try { d = JSON.parse(t); } catch { d = t; }
    return { ok: r.ok, status: r.status, data: d };
  } catch (e) {
    return { ok: false, status: 0, data: String(e?.message || e) };
  } finally { clearTimeout(timer); }
}

async function publicState() {
  const jobs = [publicJson('/wp-json/')];
  if (safe.verify.postSlug) jobs.push(publicJson(`/wp-json/wp/v2/posts?slug=${encodeURIComponent(safe.verify.postSlug)}&_=${Date.now()}`));
  if (safe.verify.pageSlug) jobs.push(publicJson(`/wp-json/wp/v2/pages?slug=${encodeURIComponent(safe.verify.pageSlug)}&_=${Date.now()}`));
  const out = await Promise.all(jobs);
  let i = 1;
  const root = out[0];
  const state = { rootStatus: root.status, title: root.data?.name || null, postCount: null, pageCount: null };
  if (safe.verify.postSlug) { const p = out[i++]; state.postCount = Array.isArray(p.data) ? p.data.length : null; }
  if (safe.verify.pageSlug) { const p = out[i++]; state.pageCount = Array.isArray(p.data) ? p.data.length : null; }
  return state;
}

function markersMatch(s) {
  if (s.rootStatus !== 200) return false;
  if (safe.verify.title && s.title !== safe.verify.title) return false;
  if (safe.verify.postSlug && !(s.postCount >= 1)) return false;
  if (safe.verify.pageSlug && !(s.pageCount >= 1)) return false;
  return Boolean(safe.verify.title || safe.verify.postSlug || safe.verify.pageSlug);
}

function terminalJob(v) {
  const text = stringsDeep(v).join(' | ');
  if (/fail|error|cancel/i.test(text)) return 'failed';
  if (/\bcomplete(?:d)?\b|\bdone\b|\bsuccess(?:ful|fully)?\b|finished/i.test(text)) return 'success';
  return 'running';
}

const onLogin = (p) => /\/login(?:[/?#]|$)/i.test(p.url());
async function loginWasmer(p) {
  stage('wasmer_login');
  for (let attempt = 1; attempt <= 3; attempt++) {
    await p.goto('https://wasmer.io/login', { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => null);
    await p.waitForTimeout(900);
    if (!onLogin(p)) return;
    const ident = p.locator('input[name=username],input[placeholder*=Username i],input[autocomplete=username],input[type=email],input[type=text]').first();
    if (!(await ident.waitFor({ state: 'visible', timeout: 12000 }).then(() => true).catch(() => false))) continue;
    await ident.fill(account.username || account.email);
    const next = p.locator('button,input[type=submit]').filter({ hasText: /continue|next|log in|sign in/i }).first();
    if (await next.count() && await next.isVisible().catch(() => false)) await next.click({ noWaitAfter: true }).catch(() => {}); else await ident.press('Enter').catch(() => {});
    let pass = null; const passEnd = Date.now() + 30000;
    while (Date.now() < passEnd) {
      if (!onLogin(p)) return;
      const x = p.locator('input[type=password]').first();
      if (await x.count() && await x.isVisible().catch(() => false)) { pass = x; break; }
      await p.waitForTimeout(500);
    }
    if (!pass) continue;
    await pass.fill(account.password);
    const submit = p.locator('button,input[type=submit]').filter({ hasText: /continue|log in|sign in/i }).first();
    if (await submit.count() && await submit.isVisible().catch(() => false)) await submit.click({ noWaitAfter: true }).catch(() => {}); else await pass.press('Enter').catch(() => {});
    const end = Date.now() + 20000; while (Date.now() < end) { if (!onLogin(p)) return; await p.waitForTimeout(500); }
  }
  throw new Error('wasmer_login_failed');
}

async function pollAdmin(ctx, ms = 26000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    for (const p of ctx.pages()) {
      const u = p.url();
      if (u.startsWith(base) && /\/wp-admin(?:\/|\?|$)/i.test(u) && !/wp-login\.php/i.test(u)) return p;
    }
    await new Promise(r => setTimeout(r, 500));
  }
  return null;
}
async function adminControl(p) {
  const t = p.getByText(/WordPress Admin/i).first();
  if (!(await t.count()) || !(await t.isVisible().catch(() => false))) return null;
  const a = t.locator('xpath=ancestor-or-self::a[@href] | ancestor-or-self::button').first();
  return await a.count() ? a : t;
}
async function enterAdmin(ctx, p) {
  stage('wordpress_admin');
  for (let k = 0; k < 3; k++) {
    await p.goto(dashboard, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => null);
    await p.waitForTimeout(1400);
    let c = await adminControl(p);
    if (!c) {
      const st = p.getByText(/^Settings$/i).first();
      if (await st.count() && await st.isVisible().catch(() => false)) {
        await st.click({ noWaitAfter: true }).catch(() => {}); await p.waitForTimeout(700);
        const w = p.getByText(/^WordPress$/i).first();
        if (await w.count() && await w.isVisible().catch(() => false)) { await w.click({ noWaitAfter: true }).catch(() => {}); await p.waitForTimeout(900); }
        c = await adminControl(p);
      }
    }
    if (c) {
      const href = await c.getAttribute('href').catch(() => null);
      if (href) {
        const wp = await ctx.newPage();
        await wp.goto(new URL(href, 'https://wasmer.io').href, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => null);
        const found = await pollAdmin(ctx, 18000); if (found) return found;
        await wp.close().catch(() => {});
      }
      await c.click({ noWaitAfter: true }).catch(() => {});
      const found = await pollAdmin(ctx, 22000); if (found) return found;
    }
  }
  throw new Error('magic_admin_failed');
}
async function getNonce(wp) {
  stage('rest_nonce');
  await wp.goto(`${base}/wp-admin/`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wp.waitForTimeout(900);
  let n = await wp.evaluate(() => globalThis.wpApiSettings?.nonce || globalThis.wp?.apiSettings?.nonce || null).catch(() => null);
  if (!n) {
    const h = await wp.content();
    for (const re of [/wpApiSettings\s*=\s*\{[^}]*["']nonce["']\s*:\s*["']([A-Za-z0-9_-]+)["']/i, /["']nonce["']\s*:\s*["']([A-Fa-f0-9]{10,})["']/i]) {
      const m = h.match(re); if (m) { n = m[1]; break; }
    }
  }
  if (!n) throw new Error('wp_rest_nonce_missing');
  return n;
}
async function api(ctx, nonce, path, { method = 'GET', json = null, soft = false, timeout = 60000 } = {}) {
  const headers = { 'X-WP-Nonce': nonce, Accept: 'application/json' };
  let data;
  if (json !== null) { headers['Content-Type'] = 'application/json'; data = JSON.stringify(json); }
  const r = await ctx.request.fetch(`${base}/wp-json${path}`, { method, headers, data, timeout, failOnStatusCode: false });
  const t = await r.text(); let d; try { d = JSON.parse(t); } catch { d = t; }
  if (!r.ok()) { if (soft) return { ok: false, status: r.status(), data: d }; throw new Error(`api_${method}_${path}:${r.status()}:${String(t).slice(0, 260)}`); }
  return soft ? { ok: true, status: r.status(), data: d } : d;
}

async function ensureAi1wm(ctx, nonce) {
  stage('ensure_ai1wm');
  const cap = await api(ctx, nonce, '/ai1wm/v1/capabilities', { soft: true });
  if (cap.ok) return;
  const plugins = await api(ctx, nonce, '/wp/v2/plugins?context=edit');
  let p = Array.isArray(plugins) ? plugins.find(x => String(x.plugin || '').startsWith('all-in-one-wp-migration/') || x.textdomain === 'all-in-one-wp-migration') : null;
  if (!p) p = await api(ctx, nonce, '/wp/v2/plugins', { method: 'POST', json: { slug: 'all-in-one-wp-migration', status: 'active' } });
  else if (p.status !== 'active') p = await api(ctx, nonce, `/wp/v2/plugins/${encodeURIComponent(p.plugin)}`, { method: 'POST', json: { status: 'active' } });
  const check = await api(ctx, nonce, '/ai1wm/v1/capabilities', { soft: true });
  if (!check.ok) throw new Error(`ai1wm_rest_unavailable_after_install:${check.status}`);
}

async function downloadBackup(ctx, nonce) {
  stage('download_backup');
  let buf;
  if (backup.source === 'server') {
    if (!backup.name) throw new Error('server_backup_name_missing');
    let r = await ctx.request.get(`${base}/wp-json/ai1wm/v1/backups/${encodeURIComponent(backup.name)}/download`, { headers: { 'X-WP-Nonce': nonce, Accept: 'application/octet-stream' }, timeout: 180000, failOnStatusCode: false });
    if (!r.ok()) throw new Error(`backup_download_http_${r.status()}:${(await r.text()).slice(0, 220)}`);
    buf = await r.body();
    const ct = (r.headers()['content-type'] || '').toLowerCase();
    if (ct.includes('application/json')) {
      let d; try { d = JSON.parse(buf.toString('utf8')); } catch {}
      const url = d && stringsDeep(d).find(s => /^https?:\/\//i.test(s));
      if (!url) throw new Error('backup_download_json_without_url');
      r = await ctx.request.get(url, { timeout: 180000, failOnStatusCode: false });
      if (!r.ok()) throw new Error(`backup_url_http_${r.status()}`);
      buf = await r.body();
    }
  } else if (backup.source === 'url') {
    if (!backup.url) throw new Error('backup_url_missing');
    const r = await fetch(backup.url, { redirect: 'follow' });
    if (!r.ok) throw new Error(`external_backup_http_${r.status}`);
    buf = Buffer.from(await r.arrayBuffer());
  } else {
    throw new Error(`unsupported_backup_source:${backup.source || 'missing'}`);
  }
  if (!buf || buf.length < 1024) throw new Error(`backup_too_small:${buf?.length || 0}`);
  const head = buf.subarray(0, 120).toString('utf8').toLowerCase();
  if (head.includes('<html') || head.includes('<!doctype')) throw new Error('backup_download_returned_html');
  const sha = crypto.createHash('sha256').update(buf).digest('hex');
  safe.backup.bytes = buf.length; safe.backup.sha256 = sha; save();
  if (backup.sha256 && sha.toLowerCase() !== String(backup.sha256).toLowerCase()) throw new Error(`backup_sha_mismatch:${sha}`);
  console.log(`BACKUP_READY bytes=${buf.length} sha256=${sha}`);
  return buf;
}

async function startImport(ctx, nonce) {
  const buf = await downloadBackup(ctx, nonce);
  stage('create_import_job');
  const started = await api(ctx, nonce, '/ai1wm/v1/imports', { method: 'POST', json: {} });
  const jobId = findJobId(started);
  if (!jobId) throw new Error(`import_job_id_missing:${summary(started)}`);
  safe.import.jobId = jobId; safe.import.started = true; save();
  stage('upload_import_file');
  const filename = backup.name || `restore-${requestId}.wpress`;
  const r = await ctx.request.post(`${base}/wp-json/ai1wm/v1/imports/${encodeURIComponent(jobId)}/file?auto_confirm=true`, {
    headers: { 'X-WP-Nonce': nonce, Accept: 'application/json' },
    multipart: { upload_file: { name: filename, mimeType: 'application/octet-stream', buffer: buf } },
    timeout: 12 * 60 * 1000,
    failOnStatusCode: false,
  });
  const text = await r.text(); safe.import.uploadStatus = r.status(); save();
  console.log(`IMPORT_UPLOAD status=${r.status()} body=${text.slice(0, 500)}`);
  if (!r.ok()) throw new Error(`import_upload_http_${r.status()}:${text.slice(0, 300)}`);
  let data; try { data = JSON.parse(text); } catch { data = text; }
  const secret = findSecret(data);
  if (/waiting for confirmation|confirm/i.test(summary(data)) && !/running/i.test(summary(data))) {
    const c = await api(ctx, nonce, `/ai1wm/v1/imports/${encodeURIComponent(jobId)}/confirm`, { method: 'POST', json: { proceed: true }, soft: true, timeout: 120000 });
    console.log(`IMPORT_CONFIRM status=${c.status} body=${summary(c.data)}`);
  }
  return { jobId, secret };
}

async function jobState(ctx, nonce, jobId) {
  return api(ctx, nonce, `/ai1wm/v1/imports/${encodeURIComponent(jobId)}`, { soft: true, timeout: 45000 });
}

save();
const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
const p = await ctx.newPage();
try {
  await loginWasmer(p);
  const wp = await enterAdmin(ctx, p);
  const nonce = await getNonce(wp);
  await ensureAi1wm(ctx, nonce);

  let jobId = safe.import.jobId;
  if (!jobId) {
    const started = await startImport(ctx, nonce);
    jobId = started.jobId;
  } else {
    stage('resume_existing_import');
    console.log(`RESUME_IMPORT job=${jobId}`);
  }

  stage('watch_import');
  const startedAt = Date.now();
  const end = startedAt + watchMinutes * 60 * 1000;
  let lastJob = null;
  let lastPublic = await publicState();
  let lastLog = 0;
  while (Date.now() < end) {
    lastPublic = await publicState();
    if (markersMatch(lastPublic)) {
      safe.verify.matched = true;
      safe.status = 'RESTORE_VERIFIED'; safe.stage = 'complete'; safe.detail = null; save();
      console.log(`RESTORE_VERIFIED ${summary(lastPublic)}`);
      break;
    }
    lastJob = await jobState(ctx, nonce, jobId);
    safe.import.lastObserved = lastJob.data; save();
    const terminal = terminalJob(lastJob.data);
    if (terminal === 'failed') throw new Error(`import_job_failed:${summary(lastJob.data)}`);
    if (terminal === 'success' && lastPublic.rootStatus === 200) {
      safe.status = safe.verify.title || safe.verify.postSlug || safe.verify.pageSlug ? 'RESTORE_COMPLETE_UNVERIFIED_MARKERS' : 'RESTORE_COMPLETE';
      safe.stage = 'complete'; safe.detail = null; save();
      console.log(`${safe.status} ${summary(lastPublic)}`);
      break;
    }
    if (Date.now() - lastLog > 30000) {
      console.log(`IMPORT_WATCH public=${summary(lastPublic)} job=${summary(lastJob.data)}`);
      lastLog = Date.now();
    }
    await new Promise(r => setTimeout(r, 10000));
  }
  if (!['RESTORE_VERIFIED', 'RESTORE_COMPLETE', 'RESTORE_COMPLETE_UNVERIFIED_MARKERS'].includes(safe.status)) {
    safe.status = 'RESTORE_IN_PROGRESS';
    safe.stage = 'watch_timeout';
    safe.detail = `resume request ${requestId}; import job ${jobId} still active`;
    save();
    console.log(`RESTORE_IN_PROGRESS job=${jobId} public=${summary(lastPublic)} jobState=${summary(lastJob?.data)}`);
  }
} catch (e) {
  safe.status = 'FAILED'; safe.detail = String(e?.message || e); save(); console.error(e); process.exitCode = 1;
} finally {
  await browser.close().catch(() => {});
}
