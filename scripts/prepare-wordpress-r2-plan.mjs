import fs from 'fs';
import path from 'path';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const baseUrl = String(process.env.R2_BASE_URL || '').replace(/\/$/, '');
const cred = JSON.parse(fs.readFileSync('/tmp/wp-control-credential.json', 'utf8'));
const site = String(cred.siteUrl || '').replace(/\/$/, '');
if (!baseUrl) throw new Error('R2_BASE_URL missing');
if (!site || !cred.username || !cred.applicationPassword) throw new Error('WordPress credential incomplete');
const auth = 'Basic ' + Buffer.from(`${cred.username}:${cred.applicationPassword}`).toString('base64');
const outDir = `media/${slug}`;
const planPath = `/tmp/wp-remote-media-${slug}.plan.json`;

async function api(pathname) {
  const r = await fetch(site + pathname, { headers: { Authorization: auth, Accept: 'application/json' } });
  const text = await r.text();
  if (!r.ok) throw new Error(`${pathname}:${r.status}:${text.slice(0,180)}`);
  return text ? JSON.parse(text) : null;
}

const items = [];
let optimizedBytes = 0;
for (let i = 1; i <= 8; i++) {
  const tag = `offset-demo-${String(i).padStart(2, '0')}`;
  const media = await api(`/wp-json/wp/v2/media?slug=${encodeURIComponent(tag)}&per_page=1&context=edit`);
  if (!Array.isArray(media) || media.length !== 1) throw new Error(`media_not_found:${tag}`);
  const attachment = media[0];
  const state = await api(`/wp-json/runner3/v1/offload/${attachment.id}`);
  const filename = `${tag}.webp`;
  const localPath = path.join(outDir, filename);
  if (!fs.existsSync(localPath)) throw new Error(`optimized_media_missing:${localPath}`);
  const size = fs.statSync(localPath).size;
  optimizedBytes += size;
  const key = `sites/${slug}/${filename}`;
  items.push({
    attachmentId: attachment.id,
    slug: tag,
    localPath,
    r2Key: key,
    remoteUrl: `${baseUrl}/${key}`,
    width: Number(state?.width || attachment?.media_details?.width || 1),
    height: Number(state?.height || attachment?.media_details?.height || 1),
    optimizedBytes: size
  });
}

let previous = {};
try { previous = JSON.parse(fs.readFileSync(`ops/wp-remote-media/results/${slug}.latest.json`, 'utf8')); } catch {}
const originalBytes = Number(previous.originalBytes || optimizedBytes);
const reductionPct = originalBytes ? Math.round((1 - optimizedBytes / originalBytes) * 1000) / 10 : 0;
const plan = {
  siteSlug: slug,
  siteUrl: site + '/',
  provider: 'cloudflare-r2',
  originalBytes,
  optimizedBytes,
  reductionPct,
  r2BaseUrl: baseUrl,
  items
};
fs.writeFileSync(planPath, JSON.stringify(plan, null, 2));
console.log(`R2_MEDIA_PLAN_READY items=${items.length} optimized=${optimizedBytes}`);
