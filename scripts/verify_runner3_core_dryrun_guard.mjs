import {coreDeployEvidence} from "./verify_runner3_core_single_deploy_owner.mjs";
const assert=(ok,label)=>{if(!ok)throw Error(label)};
const safe = `steps:
  - name: Dry-run bundle Runner3 Core without Cloudflare credentials
    shell: bash
    working-directory: cloudflare/runner3-core
    run: |
      set -euo pipefail
      npx --yes wrangler@4 deploy --dry-run --outdir /tmp/runner3-core-ci-bundle
`;
const actual=coreDeployEvidence(safe);
assert(actual.length===0,"dryrun falsely classified as deploy");
for(const [label,bad] of [
 ["real deploy",safe.replace(" --dry-run --outdir /tmp/runner3-core-ci-bundle","")],
 ["mixed deploy",safe+"      npx --yes wrangler@4 deploy\n"],
 ["shell chain",safe.replace("ci-bundle","ci-bundle; npx --yes wrangler@4 deploy")],
 ["credentialed",safe+"    env:\n      CLOUDFLARE_API_TOKEN: secret\n"],
 ["package deploy",safe+"      npm run deploy\n"],
 ["wrangler publish",safe+"      npx --yes wrangler@4 publish\n"],
]){
  assert(coreDeployEvidence(bad).length>0,"unsafe deploy bypassed guard: "+label);
}
console.log("RUNNER3_DRYRUN_OWNER_GUARD_PASS 7 cases");
