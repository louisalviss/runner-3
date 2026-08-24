import fs from 'node:fs';
import sharp from 'sharp';

const modulePath = process.env.CF_SNAPSHOT_MODULE
  || 'edge/wordpress-edge-proxy/src/snapshot.generated.js';
const marker = process.env.SITE1_INLINE_HERO_MARKER || 'v1';
const maxBytes = Number(process.env.SITE1_INLINE_HERO_MAX_BYTES || 12000);
const width = Number(process.env.SITE1_INLINE_HERO_WIDTH || 320);
const quality = Number(process.env.SITE1_INLINE_HERO_QUALITY || 74);

const sourceCandidates = [
  process.env.SITE1_HERO_SOURCE_URL,
  'https://pub-f6e5190178814cd5be8f1eb531f1a164.r2.dev/sites/runner3-factory-smoke-2/responsive-v2/offset-demo-01-w640.webp',
  'https://runner3wp.pntr.dev/__runner3/r2-image/offset-demo-01-w640.webp',
].filter(Boolean);

async function fetchHero() {
  const failures = [];
  for (const url of sourceCandidates) {
    try {
      const response = await fetch(`${url}${url.includes('?') ? '&' : '?'}canonical=${Date.now()}`, {
        redirect: 'follow',
        headers: {
          Accept: 'image/webp,image/*;q=0.8,*/*;q=0.5',
          'Cache-Control': 'no-cache',
          'User-Agent': 'Runner3Site1LCPBuilder/1.0',
        },
      });
      const contentType = response.headers.get('content-type') || '';
      if (!response.ok || !/image\/webp/i.test(contentType)) {
        failures.push({ url, status: response.status, contentType });
        continue;
      }
      const data = Buffer.from(await response.arrayBuffer());
      if (data.length < 1024) {
        failures.push({ url, status: response.status, bytes: data.length });
        continue;
      }
      return { url, data };
    } catch (error) {
      failures.push({ url, error: String(error?.message || error).slice(0, 160) });
    }
  }
  throw new Error(`Unable to fetch Site1 hero: ${JSON.stringify(failures)}`);
}

const source = await fetchHero();
const output = await sharp(source.data)
  .resize({ width, withoutEnlargement: true })
  .webp({ quality, effort: 6, smartSubsample: true })
  .toBuffer({ resolveWithObject: true });

if (output.info.width !== width || output.info.height < 200 || output.data.length > maxBytes) {
  throw new Error(`Inline hero invariant failed: ${JSON.stringify({
    width: output.info.width,
    height: output.info.height,
    bytes: output.data.length,
    maxBytes,
  })}`);
}

const sourceModule = fs.readFileSync(modulePath, 'utf8');
const parsed = sourceModule.match(
  /export const SNAPSHOT_BUILT_AT = ([^;]+);\nexport const SNAPSHOTS = Object\.freeze\(([\s\S]+)\);\n?$/,
);
if (!parsed) throw new Error(`Snapshot parse failed: ${modulePath}`);

const builtAt = JSON.parse(parsed[1]);
const snapshots = JSON.parse(parsed[2]);
let html = snapshots['/'];
if (typeof html !== 'string') throw new Error('Homepage snapshot is missing');

const dataUri = `data:image/webp;base64,${output.data.toString('base64')}`;
let replaced = false;
html = html.replace(/<img\b[^>]*offset-demo-01[^>]*>/gi, (tag) => {
  if (replaced) return tag;
  replaced = true;
  return `<picture data-runner3-mobile-inline-lcp="${marker}"><source media="(max-width: 767px)" srcset="${dataUri}">${tag}</picture>`;
});
if (!replaced) throw new Error('Homepage hero offset-demo-01 was not found');

html = html.replace(
  /<link\b[^>]*rel=["']preload["'][^>]*as=["']image["'][^>]*offset-demo-01[^>]*>/gi,
  '',
);
html = html.replace(
  /<link\b[^>]*rel=["'](?:preconnect|dns-prefetch)["'][^>]*r2\.dev[^>]*>/gi,
  '',
);
snapshots['/'] = html;

const serialized = JSON.stringify(snapshots)
  .replace(/\u2028/g, '\\u2028')
  .replace(/\u2029/g, '\\u2029');

fs.writeFileSync(modulePath, [
  '// Generated immediately before Cloudflare deployment. Do not hand-edit.',
  `export const SNAPSHOT_BUILT_AT = ${JSON.stringify(builtAt)};`,
  `export const SNAPSHOTS = Object.freeze(${serialized});`,
  '',
].join('\n'));

console.log(JSON.stringify({
  status: 'ready',
  marker,
  source: source.url,
  quality,
  width: output.info.width,
  height: output.info.height,
  heroBytes: output.data.length,
  homepageBytes: Buffer.byteLength(html),
}, null, 2));
