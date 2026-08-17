import fs from 'fs';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const credPath = '/tmp/wp-control-credential.json';
const safeOut = `/tmp/wp-demo-media-${slug}.json`;

if (!fs.existsSync(credPath)) throw new Error('decrypted WordPress control credential missing');
const cred = JSON.parse(fs.readFileSync(credPath, 'utf8'));
const base = String(cred.siteUrl || '').replace(/\/$/, '');
if (!base || !cred.username || !cred.applicationPassword) throw new Error('WordPress credential incomplete');

const auth = 'Basic ' + Buffer.from(`${cred.username}:${cred.applicationPassword}`).toString('base64');
const headers = { Authorization: auth, Accept: 'application/json' };
const sourceImages = [
  'https://images.unsplash.com/photo-1518770660439-4636190af475?fit=crop&w=1400&q=72&fm=jpg',
  'https://images.unsplash.com/photo-1497366754035-f200968a6e72?fit=crop&w=1400&q=72&fm=jpg',
  'https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?fit=crop&w=1400&q=72&fm=jpg',
  'https://images.unsplash.com/photo-1521737711867-e3b97375f902?fit=crop&w=1400&q=72&fm=jpg',
  'https://images.unsplash.com/photo-1523726491678-bf852e717f6a?fit=crop&w=1400&q=72&fm=jpg',
  'https://images.unsplash.com/photo-1497366811353-6870744d04b2?fit=crop&w=1400&q=72&fm=jpg',
  'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?fit=crop&w=1400&q=72&fm=jpg',
  'https://images.unsplash.com/photo-1484417894907-623942c8ee29?fit=crop&w=1400&q=72&fm=jpg'
];

const safe = {
  status: 'starting', siteSlug: slug, siteUrl: base + '/',
  mediaTotal: 0, mediaCreated: 0, mediaReused: 0,
  postsUpdated: 0, localMediaVerified: false, localUrls: [],
  detail: null, updatedAt: new Date().toISOString()
};
function save() { safe.updatedAt = new Date().toISOString(); fs.writeFileSync(safeOut, JSON.stringify(safe, null, 2)); }
function fail(label, status, body='') { throw new Error(`${label}:${status}:${String(body).slice(0,240)}`); }

async function wpJson(path, options={}) {
  const r = await fetch(`${base}${path}`, {
    ...options,
    headers: { ...headers, ...(options.headers || {}) }
  });
  const text = await r.text();
  if (!r.ok) fail(path, r.status, text);
  return text ? JSON.parse(text) : null;
}

async function findExisting(index) {
  const tag = `offset-demo-${String(index + 1).padStart(2,'0')}`;
  const items = await wpJson(`/wp-json/wp/v2/media?slug=${encodeURIComponent(tag)}&per_page=1&context=edit`);
  return Array.isArray(items) && items.length ? items[0] : null;
}

async function uploadOne(index) {
  const existing = await findExisting(index);
  if (existing) {
    safe.mediaReused++;
    return existing;
  }

  const src = sourceImages[index];
  const imageRes = await fetch(src, { redirect: 'follow', headers: { 'User-Agent': 'Mozilla/5.0 Runner3DemoMedia/1.0' } });
  if (!imageRes.ok) fail(`image_download_${index+1}`, imageRes.status, await imageRes.text().catch(()=>''));
  const bytes = Buffer.from(await imageRes.arrayBuffer());
  if (bytes.length < 5000) throw new Error(`image_download_too_small:${index+1}:${bytes.length}`);
  if (bytes.length > 2_500_000) throw new Error(`image_download_too_large:${index+1}:${bytes.length}`);

  const filename = `offset-demo-${String(index + 1).padStart(2,'0')}.jpg`;
  const r = await fetch(`${base}/wp-json/wp/v2/media`, {
    method: 'POST',
    headers: {
      ...headers,
      'Content-Type': 'image/jpeg',
      'Content-Disposition': `attachment; filename="${filename}"`
    },
    body: bytes
  });
  const text = await r.text();
  if (!r.ok) fail(`media_upload_${index+1}`, r.status, text);
  const media = JSON.parse(text);

  await wpJson(`/wp-json/wp/v2/media/${media.id}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: `OFFSET Demo ${String(index + 1).padStart(2,'0')}`,
      alt_text: `OFFSET editorial demo image ${index + 1}`,
      caption: ''
    })
  });
  safe.mediaCreated++;
  return media;
}

try {
  save();
  await wpJson('/wp-json/wp/v2/users/me?context=edit');
  const posts = await wpJson('/wp-json/wp/v2/posts?per_page=8&status=publish&orderby=date&order=desc&context=edit');
  if (!Array.isArray(posts) || posts.length < 1) throw new Error('no_published_posts');

  const media = [];
  for (let i = 0; i < Math.min(8, sourceImages.length); i++) {
    media.push(await uploadOne(i));
    safe.mediaTotal = media.length;
    save();
  }

  for (let i = 0; i < posts.length; i++) {
    const m = media[i % media.length];
    if (Number(posts[i].featured_media) !== Number(m.id)) {
      await wpJson(`/wp-json/wp/v2/posts/${posts[i].id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ featured_media: m.id })
      });
    }
    safe.postsUpdated++;
    save();
  }

  const verify = await wpJson('/wp-json/wp/v2/posts?per_page=8&status=publish&orderby=date&order=desc&_embed=wp:featuredmedia');
  const urls = [];
  for (const post of verify) {
    const u = post?._embedded?.['wp:featuredmedia']?.[0]?.source_url || '';
    if (u) urls.push(u);
  }
  safe.localUrls = urls.map(u => u.replace(/^https?:\/\/[^/]+/i, 'LOCAL'));
  safe.localMediaVerified = urls.length === verify.length && urls.every(u => u.startsWith(base + '/'));
  if (!safe.localMediaVerified) throw new Error(`local_media_verify_failed:${urls.length}/${verify.length}`);

  safe.status = 'ready';
  safe.detail = null;
  save();
  console.log(`WP_DEMO_MEDIA_READY site=${slug} media=${media.length} posts=${posts.length}`);
} catch (e) {
  safe.status = 'failed';
  safe.detail = String(e?.message || e);
  save();
  console.error(`WP_DEMO_MEDIA_FAILED ${safe.detail}`);
  process.exitCode = 1;
}
