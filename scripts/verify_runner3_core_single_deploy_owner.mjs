import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve('.github/workflows');
const allowed = '.github/workflows/runner3-core-public-hosted-reader-deploy.yml';
const files = fs.readdirSync(root)
  .filter((name) => /\.ya?ml$/i.test(name))
  .map((name) => `.github/workflows/${name}`)
  .sort();

const violations = [];
for (const file of files) {
  if (file === allowed) continue;
  const text = fs.readFileSync(path.resolve(file), 'utf8');
  const mentionsCore = /(?:cloudflare|workers)\/runner3-core|runner3-core\.ducduy2411\.workers\.dev|\brunner3[-_]core\b/i.test(text);
  if (!mentionsCore) continue;
  const exposesDeployCredential = /CLOUDFLARE_API_TOKEN/.test(text);
  const invokesWranglerDeploy = /wrangler(?:@[^\s]+)?[^\n]*\bdeploy\b/i.test(text);
  if (exposesDeployCredential || invokesWranglerDeploy) {
    violations.push({ file, exposesDeployCredential, invokesWranglerDeploy });
  }
}

if (violations.length) {
  console.error('RUNNER3_CORE_MULTI_WRITER_GUARD=FAIL');
  for (const item of violations) console.error(JSON.stringify(item));
  process.exit(1);
}

const owner = fs.readFileSync(path.resolve(allowed), 'utf8');
if (!/group:\s*runner3-core-production/.test(owner)) throw new Error('canonical production concurrency group missing');
if (!/CLOUDFLARE_API_TOKEN/.test(owner) || !/wrangler(?:@[^\s]+)?[^\n]*\bdeploy\b/i.test(owner)) {
  throw new Error('canonical production owner no longer contains the deploy path');
}
console.log(`RUNNER3_CORE_SINGLE_DEPLOY_OWNER=PASS owner=${allowed} workflows=${files.length}`);
