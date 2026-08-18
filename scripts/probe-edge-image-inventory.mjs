import fs from 'node:fs';

const target = process.env.EDGE_URL || 'https://wordpress-edge-proxy.ducduy2411.workers.dev/';
const out = process.env.EDGE_IMAGE_OUT || '/tmp/edge-image-inventory.json';

function attrs(tag) {
  const result = {};
  for (const m of tag.matchAll(/([:\w-]+)\s*=\s*(["'])(.*?)\2/gis)) result[m[1].toLowerCase()] = m[3];
  return result;
}

function candidates(srcset) {
  if (!srcset) return [];
  return srcset.split(',').map((part) => {
    const p = part.trim();
    const m = p.match(/^(\S+)\s+(\d+)w$/);
    return m ? { url: m[1], width: Number(m[2]) } : null;
  }).filter(Boolean);
}

async function head(url) {
  try {
    const r = await fetch(url, { method: 'HEAD', redirect: 'follow' });
    return {
      status: r.status,
      contentType: r.headers.get('content-type'),
      contentLength: Number(r.headers.get('content-length')) || null,
      cacheControl: r.headers.get('cache-control'),
      finalUrl: r.url,
    };
  } catch (e) {
    return { status: 0, error: String(e) };
  }
}

const response = await fetch(target, { redirect: 'follow' });
const html = await response.text();
const tags = [...html.matchAll(/<img\b[^>]*>/gis)].map((m) => m[0]);
const images = [];
for (let i = 0; i < tags.length; i++) {
  const a = attrs(tags[i]);
  const srcset = candidates(a.srcset);
  const srcHead = a.src ? await head(a.src) : null;
  const candidateHeads = [];
  for (const c of srcset) candidateHeads.push({ ...c, ...(await head(c.url)) });
  images.push({
    index: i,
    src: a.src || null,
    srcset,
    sizes: a.sizes || null,
    loading: a.loading || null,
    fetchpriority: a.fetchpriority || null,
    width: a.width || null,
    height: a.height || null,
    alt: a.alt || null,
    srcHead,
    candidateHeads,
  });
}
const result = {
  status: response.ok ? 'ready' : 'failed',
  target,
  homepageStatus: response.status,
  htmlBytes: Buffer.byteLength(html),
  imageCount: images.length,
  images,
  checkedAt: new Date().toISOString(),
};
fs.writeFileSync(out, JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
if (result.status !== 'ready') process.exitCode = 1;
