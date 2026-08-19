import fs from 'node:fs';

const entryPath = 'edge/wordpress-edge-proxy/src/entry.js';
const responsivePath = 'edge/wordpress-edge-proxy/src/responsive-images.js';

const widths = [360, 480, 640];
const encoded = Object.fromEntries(widths.map((w) => {
  const p = `/tmp/lcp-v1/offset-demo-01-w${w}.webp`;
  if (!fs.existsSync(p)) throw new Error(`missing ${p}`);
  return [w, fs.readFileSync(p).toString('base64')];
}));

let responsive = fs.readFileSync(responsivePath, 'utf8');
const oldBlock = "    const variantDir = HERO_IMAGE_RE.test(filename) ? HERO_VARIANT_DIR : VARIANT_DIR;\n    const base = `https://${R2_HOST}${SITE_PREFIX}${variantDir}/${stem}`;";
const newBlock = "    const isHero = HERO_IMAGE_RE.test(filename);\n    const base = isHero ? `/__runner3/lcp/${stem}` : `https://${R2_HOST}${SITE_PREFIX}${VARIANT_DIR}/${stem}`;";
if (!responsive.includes(oldBlock)) throw new Error('responsive patch anchor missing');
responsive = responsive.replace(oldBlock, newBlock);
fs.writeFileSync(responsivePath, responsive);

let entry = fs.readFileSync(entryPath, 'utf8');
const constAnchor = "const HTML_CACHE_TAG = 'runner3-html';\n";
if (!entry.includes(constAnchor)) throw new Error('entry const anchor missing');
const payload = `const LCP_EMBEDDED_PREFIX = '/__runner3/lcp/';\nconst LCP_EMBEDDED = {\n  'offset-demo-01-w360.webp': '${encoded[360]}',\n  'offset-demo-01-w480.webp': '${encoded[480]}',\n  'offset-demo-01-w640.webp': '${encoded[640]}',\n};\n`;
entry = entry.replace(constAnchor, constAnchor + payload);

const fetchAnchor = "    const incoming = new URL(request.url); if (incoming.pathname === PURGE_PATH) return handlePurge(request, env, ctx);\n";
if (!entry.includes(fetchAnchor)) throw new Error('entry fetch anchor missing');
const handler = `    const incoming = new URL(request.url); if (incoming.pathname === PURGE_PATH) return handlePurge(request, env, ctx);\n    if (incoming.pathname.startsWith(LCP_EMBEDDED_PREFIX) && request.method.toUpperCase() === 'GET') {\n      const name = incoming.pathname.slice(LCP_EMBEDDED_PREFIX.length);\n      const value = LCP_EMBEDDED[name];\n      if (!value) return new Response('Not Found', { status: 404 });\n      return new Response(base64Bytes(value), { status: 200, headers: { 'Content-Type': 'image/webp', 'Cache-Control': 'public, max-age=31536000, immutable', 'X-Runner3-LCP': 'embedded-same-origin' } });\n    }\n`;
entry = entry.replace(fetchAnchor, handler);
fs.writeFileSync(entryPath, entry);

console.log(JSON.stringify({status:'patched', widths, entryPath, responsivePath, encodedBytes:Object.fromEntries(widths.map(w=>[w,Buffer.byteLength(encoded[w])]))}, null, 2));
