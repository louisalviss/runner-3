import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve('.github/workflows');
const allowed = '.github/workflows/runner3-core-public-hosted-reader-deploy.yml';
const files = fs.readdirSync(root)
  .filter((name) => /\.ya?ml$/i.test(name))
  .map((name) => `.github/workflows/${name}`)
  .sort();

function coreDeploySteps(text) {
  const blocks = String(text).split(/\n(?=\s*-\s+(?:name:|uses:|run:))/g);
  return blocks.filter((block) => {
    const deploy = /wrangler(?:@[^\s]+)?[^\n]*\bdeploy\b/i.test(block);
    if (!deploy) return false;
    return /(?:working-directory:\s*(?:cloudflare|workers)\/runner3-core)|(?:cd\s+(?:cloudflare|workers)\/runner3-core)|(?:--config\s+[^\n]*runner3-core)/i.test(block);
  });
}

const violations = [];
for (const file of files) {
  if (file === allowed) continue;
  const text = fs.readFileSync(path.resolve(file), 'utf8');
  const steps = coreDeploySteps(text);
  if (steps.length) violations.push({ file, coreDeployStepCount: steps.length });
}

if (violations.length) {
  console.error('RUNNER3_CORE_MULTI_WRITER_GUARD=FAIL');
  for (const item of violations) console.error(JSON.stringify(item));
  process.exit(1);
}

const owner = fs.readFileSync(path.resolve(allowed), 'utf8');
if (!/group:\s*runner3-core-production/.test(owner)) throw new Error('canonical production concurrency group missing');
if (!/CLOUDFLARE_API_TOKEN/.test(owner)) throw new Error('canonical production credential missing');
if (!coreDeploySteps(owner).length) throw new Error('canonical production deploy step missing');
console.log(`RUNNER3_CORE_SINGLE_DEPLOY_OWNER=PASS owner=${allowed} workflows=${files.length}`);
