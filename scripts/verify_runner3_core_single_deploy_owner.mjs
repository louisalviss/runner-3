import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve('.github/workflows');
const allowed = '.github/workflows/runner3-core-public-hosted-reader-deploy.yml';
const files = fs.readdirSync(root)
  .filter((name) => /\.ya?ml$/i.test(name))
  .map((name) => `.github/workflows/${name}`)
  .sort();

function compact(text) {
  return String(text || '').replace(/\r/g, '');
}

function directCoreDeployEvidence(text) {
  const source = compact(text);
  const evidence = [];
  const blocks = source.split(/\n(?=\s*-\s+(?:name:|uses:|run:))/g);
  for (const block of blocks) {
    const directWrangler = /wrangler(?:@[^\s]+)?[^\n]*\b(?:deploy|publish)\b/i.test(block)
      || /wrangler(?:@[^\s]+)?[^\n]*\bversions\s+deploy\b/i.test(block);
    const coreCwd = /(?:working-directory:\s*(?:cloudflare|workers)\/runner3-core)|(?:cd\s+(?:cloudflare|workers)\/runner3-core)|(?:--config\s+[^\n]*runner3-core)|(?:--name\s+runner3-core)/i.test(block);
    if (directWrangler && coreCwd) evidence.push('direct-core-wrangler-step');
  }

  const mentionsCore = /(?:cloudflare|workers)\/runner3-core|\brunner3-core\b/i.test(source);
  const fileDeployCommand = /wrangler(?:@[^\s]+)?[^\n]*\b(?:deploy|publish)\b/i.test(source)
    || /wrangler(?:@[^\s]+)?[^\n]*\bversions\s+deploy\b/i.test(source)
    || /cloudflare\/wrangler-action@/i.test(source)
    || /(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:deploy|publish)\b/i.test(source);
  const inheritedCoreCwd = /defaults:[\s\S]{0,500}?working-directory:\s*(?:cloudflare|workers)\/runner3-core/i.test(source);
  if (mentionsCore && fileDeployCommand) evidence.push('workflow-mentions-core-and-deploy-command');
  if (inheritedCoreCwd && fileDeployCommand) evidence.push('inherited-core-working-directory');

  if (/runner3[_-]core[^\n]{0,100}deploy|deploy[^\n]{0,100}runner3[_-]core/i.test(source)) {
    evidence.push('core-deploy-helper-or-command');
  }
  if (/workers\/scripts\/runner3-core/i.test(source) && /(?:curl|fetch|api\.cloudflare\.com)/i.test(source)) {
    evidence.push('cloudflare-api-core-script-write');
  }

  return [...new Set(evidence)];
}

const violations = [];
for (const file of files) {
  if (file === allowed) continue;
  const text = fs.readFileSync(path.resolve(file), 'utf8');
  const evidence = directCoreDeployEvidence(text);
  if (evidence.length) violations.push({ file, evidence });
}

if (violations.length) {
  console.error('RUNNER3_CORE_MULTI_WRITER_GUARD=FAIL');
  for (const item of violations) console.error(JSON.stringify(item));
  process.exit(1);
}

const owner = fs.readFileSync(path.resolve(allowed), 'utf8');
const ownerEvidence = directCoreDeployEvidence(owner);
if (!/group:\s*runner3-core-production/.test(owner)) throw new Error('canonical production concurrency group missing');
if (!/CLOUDFLARE_API_TOKEN/.test(owner)) throw new Error('canonical production credential missing');
if (!ownerEvidence.length) throw new Error('canonical production deploy evidence missing');
if (!/reader-v31-high-speed-serialized-follow-entry\.js/.test(owner)) throw new Error('canonical Reader v31 composition missing');
console.log(`RUNNER3_CORE_SINGLE_DEPLOY_OWNER=PASS owner=${allowed} workflows=${files.length} detection=hardened`);
