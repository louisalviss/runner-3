import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve('.github/workflows');
const allowed = '.github/workflows/runner3-core-public-hosted-reader-deploy.yml';
const files = fs.readdirSync(root)
  .filter((name) => /\.ya?ml$/i.test(name))
  .map((name) => `.github/workflows/${name}`)
  .sort();

function executableText(text) {
  return String(text || '')
    .replace(/\r/g, '')
    .split('\n')
    .filter((line) => !/^\s*#/.test(line))
    .join('\n');
}

function coreDeployEvidence(text) {
  const source = executableText(text);
  const evidence = [];
  const inheritedCoreCwd = /defaults:[\s\S]{0,500}?working-directory:\s*(?:cloudflare|workers)\/runner3-core\b/i.test(source);
  const blocks = source.split(/\n(?=\s*-\s+(?:name:|uses:|run:))/g);

  for (const block of blocks) {
    const wranglerDeploy = /wrangler(?:@[^\s]+)?[^\n]*\b(?:deploy|publish)\b/i.test(block)
      || /wrangler(?:@[^\s]+)?[^\n]*\bversions\s+deploy\b/i.test(block);
    const packageDeploy = /(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:deploy|publish)\b/i.test(block);
    const coreCwd = /working-directory:\s*(?:cloudflare|workers)\/runner3-core\b/i.test(block)
      || /cd\s+(?:cloudflare|workers)\/runner3-core\b/i.test(block);
    const coreTarget = /--config\s+[^\n]*runner3-core|--name\s+runner3-core\b/i.test(block);
    const wranglerAction = /cloudflare\/wrangler-action@/i.test(block)
      && /(?:workingDirectory|working-directory|command):[^\n]*runner3-core/i.test(block);

    if ((wranglerDeploy || packageDeploy) && (coreCwd || coreTarget || inheritedCoreCwd)) {
      evidence.push('runner3-core-deploy-step');
    }
    if (wranglerAction) evidence.push('runner3-core-wrangler-action');
  }

  if (/workers\/scripts\/runner3-core/i.test(source) && /(?:curl|fetch|api\.cloudflare\.com)/i.test(source)) {
    evidence.push('cloudflare-api-core-script-write');
  }

  return [...new Set(evidence)];
}

const violations = [];
for (const file of files) {
  if (file === allowed) continue;
  const evidence = coreDeployEvidence(fs.readFileSync(path.resolve(file), 'utf8'));
  if (evidence.length) violations.push({ file, evidence });
}

if (violations.length) {
  console.error('RUNNER3_CORE_MULTI_WRITER_GUARD=FAIL');
  for (const item of violations) console.error(JSON.stringify(item));
  process.exit(1);
}

const owner = fs.readFileSync(path.resolve(allowed), 'utf8');
const ownerEvidence = coreDeployEvidence(owner);
if (!/group:\s*runner3-core-production/.test(owner)) throw new Error('canonical production concurrency group missing');
if (!/CLOUDFLARE_API_TOKEN/.test(owner)) throw new Error('canonical production credential missing');
if (!ownerEvidence.length) throw new Error('canonical production deploy evidence missing');
if (!/reader-v31-high-speed-serialized-follow-entry\.js/.test(owner)) throw new Error('canonical Reader v31 composition missing');
console.log(`RUNNER3_CORE_SINGLE_DEPLOY_OWNER=PASS owner=${allowed} workflows=${files.length} detection=step-aware`);
