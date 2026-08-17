import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const cred = JSON.parse(fs.readFileSync('/tmp/wp-control-credential.json', 'utf8'));
const plan = JSON.parse(fs.readFileSync(`/tmp/wp-remote-media-${slug}.plan.json`, 'utf8'));
const base = String(cred.siteUrl || '').replace(/\/$/, '');
const auth = 'Basic ' + Buffer.from(`${cred.username}:${cred.applicationPassword}`).toString('base64');
const safePath = `/tmp/wp-remote-media-${slug}.json`;
const safe = {
  status: 'starting', siteSlug: slug, siteUrl: base + '/', provider: plan.provider,
  mediaTotal: plan.items.length, remoteVerified: 0, mapped: 0, pruned: 0,
  localFilesRemaining: null, originalBytes: plan.originalBytes, optimizedBytes: plan.optimizedBytes,
  reductionPct: plan.reductionPct, detail: null, updatedAt: new Date().toISOString()
};
const save = () => { safe.updatedAt = new Date().toISOString(); fs.writeFileSync(safePath, JSON.stringify(safe, null, 2)); };

async function remoteOk(url) {
  for (let i = 0; i < 8; i++) {
    const r = await fetch(url, { method: 'HEAD', redirect: 'follow', headers: { 'User-Agent': 'Runner3RemoteMediaVerify/1.0' } }).catch(() => null);
    if (r && r.ok) return true;
    await new Promise(r => setTimeout(r, 1500));
  }
  return false;
}

async function api(pathname, options={}) {
  const r = await fetch(base + pathname, { ...options, headers: { Authorization: auth, Accept: 'application/json', ...(options.headers || {}) } });
  const text = await r.text();
  if (!r.ok) throw new Error(`${pathname}:${r.status}:${text.slice(0,220)}`);
  return text ? JSON.parse(text) : null;
}

try {
  save();
  for (const item of plan.items) {
    if (!(await remoteOk(item.remoteUrl))) throw new Error(`remote_not_ready:${item.slug}`);
    safe.remoteVerified++;
    save();
  }

  // Phase 1: map URLs, but keep local files as rollback.
  for (const item of plan.items) {
    const res = await api(`/wp-json/runner3/v1/offload/${item.attachmentId}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ remote_url: item.remoteUrl, width: item.width, height: item.height, prune: false })
    });
    if (!res?.ok || res.remote_url !== item.remoteUrl) throw new Error(`map_failed:${item.slug}`);
    safe.mapped++;
    save();
  }

  // Verify WordPress itself now emits every remote attachment URL before deleting local bytes.
  for (const item of plan.items) {
    const media = await api(`/wp-json/wp/v2/media/${item.attachmentId}?context=edit`);
    if (media.source_url !== item.remoteUrl) throw new Error(`wp_remote_url_verify_failed:${item.slug}:${media.source_url}`);
  }
  const home = await fetch(base + '/', { redirect: 'follow' });
  if (!home.ok) throw new Error(`homepage_failed:${home.status}`);
  const homeHtml = await home.text();
  const visibleRemoteCount = plan.items.filter(x => homeHtml.includes(x.remoteUrl)).length;
  if (visibleRemoteCount < 6) throw new Error(`homepage_remote_media_verify_failed:${visibleRemoteCount}`);

  // Phase 2: remote is proven from both origin and WordPress; prune original + generated thumbnails.
  for (const item of plan.items) {
    const res = await api(`/wp-json/runner3/v1/offload/${item.attachmentId}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ remote_url: item.remoteUrl, width: item.width, height: item.height, prune: true })
    });
    if (!res?.ok || !res.pruned) throw new Error(`prune_failed:${item.slug}`);
    safe.pruned++;
    save();
  }

  let remaining = 0;
  for (const item of plan.items) {
    const state = await api(`/wp-json/runner3/v1/offload/${item.attachmentId}`);
    if (state.local_file_exists) remaining++;
    if (state.remote_url !== item.remoteUrl) throw new Error(`post_prune_url_mismatch:${item.slug}`);
    if (!(await remoteOk(item.remoteUrl))) throw new Error(`post_prune_remote_failed:${item.slug}`);
  }
  safe.localFilesRemaining = remaining;
  if (remaining !== 0) throw new Error(`local_files_remaining:${remaining}`);

  const home2 = await fetch(base + '/', { redirect: 'follow' });
  const html2 = await home2.text();
  const finalVisible = plan.items.filter(x => html2.includes(x.remoteUrl)).length;
  if (!home2.ok || finalVisible < 6) throw new Error(`post_prune_home_verify_failed:${home2.status}:${finalVisible}`);

  safe.status = 'ready';
  safe.detail = null;
  save();
  console.log(`REMOTE_MEDIA_READY mapped=${safe.mapped} pruned=${safe.pruned} remaining=${remaining} optimized=${safe.optimizedBytes}`);
} catch (e) {
  safe.status = 'failed'; safe.detail = String(e?.message || e); save();
  console.error(`REMOTE_MEDIA_FAILED ${safe.detail}`);
  process.exitCode = 1;
}
