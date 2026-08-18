import fs from 'fs';
import path from 'path';
import sharp from 'sharp';

const slug = process.env.WP_SITE_SLUG || 'runner3-factory-smoke-2';
const cred = JSON.parse(fs.readFileSync('/tmp/wp-control-credential.json', 'utf8'));
const base = String(cred.siteUrl || '').replace(/\/$/, '');
const auth = 'Basic ' + Buffer.from(`${cred.username}:${cred.applicationPassword}`).toString('base64');
const outDir = `media/${slug}`;
const planPath = `/tmp/wp-remote-media-${slug}.plan.json`;
fs.mkdirSync(outDir, { recursive: true });

async function wp(pathname) {
  const r = await fetch(base + pathname, { headers: { Authorization: auth, Accept: 'application/json' } });
  const text = await r.text();
  if (!r.ok) throw new Error(`${pathname}:${r.status}:${text.slice(0,180)}`);
  return JSON.parse(text);
}

const items = [];
let originalBytes = 0;
let optimizedBytes = 0;
for (let i = 1; i <= 8; i++) {
  const tag = `offset-demo-${String(i).padStart(2, '0')}`;
  const media = await wp(`/wp-json/wp/v2/media?slug=${encodeURIComponent(tag)}&per_page=1&context=edit`);
  if (!Array.isArray(media) || media.length !== 1) throw new Error(`media_not_found:${tag}`);
  const attachment = media[0];
  const source = attachment.source_url;
  const r = await fetch(source, { redirect: 'follow', headers: { 'User-Agent': 'Runner3MediaOptimizer/1.0' } });
  if (!r.ok) throw new Error(`download_failed:${tag}:${r.status}`);
  const input = Buffer.from(await r.arrayBuffer());
  originalBytes += input.length;
  const filename = `${tag}.webp`;
  const localPath = path.join(outDir, filename);
  const info = await sharp(input).rotate().resize({ width: 1400, height: 1400, fit: 'inside', withoutEnlargement: true }).webp({ quality: 66, effort: 6, smartSubsample: true }).toFile(localPath);
  optimizedBytes += info.size;
  items.push({ attachmentId: attachment.id, slug: tag, sourceUrl: source, localPath, remoteUrl: `https://raw.githubusercontent.com/louisalviss/runner-3/main/${localPath}`, width: info.width, height: info.height, originalBytes: input.length, optimizedBytes: info.size });
}

const plan = { siteSlug: slug, siteUrl: base + '/', provider: 'github-raw-interim', originalBytes, optimizedBytes, reductionPct: originalBytes ? Math.round((1 - optimizedBytes / originalBytes) * 1000) / 10 : 0, items };
fs.writeFileSync(planPath, JSON.stringify(plan, null, 2));
console.log(`REMOTE_MEDIA_PREPARED items=${items.length} original=${originalBytes} optimized=${optimizedBytes} reduction=${plan.reductionPct}%`);
