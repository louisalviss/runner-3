# Cloudflare R2 admin workflows: additional fail-closed HOLD — 2026-10-16

**Status: FIVE_LEGACY_WORKFLOWS_GUARDED / THREE_LIVE_PUSH_RUNS_SKIPPED / TWO_STATIC_ONLY / R2_COST_HOLD.**

Source `Ducduy2411` remains production. Target `louisalviss3` is not cut over. Canonical Dropbox `/Task/active/CLOUDFLARE-R2-COST-001.md` observed rev14 `VERIFYING`, residual R2 PUT actor unattributed, current billing unavailable; **no release**. This report is separate from the prior four scheduled-job hardenings and seven manual migration-workflow gates.

## Previously unguarded legacy admin paths

| Workflow | Activation | Network/change risk | Resolution |
|---|---|---|---|
| `cloudflare-rehome-r2-inventory.yml` | manual or push to workflow | Cloudflare R2 bucket/object LIST and metrics; object LIST may incur Class A | HOLD-gated before R2 inventory and GitHub inventory commit |
| `clm-d1-to-r2-migration.yml` | manual | Export CLM D1, R2 PUT/GET, production CLM Worker deploy, live writes, **source D1 deletion** | Independent R2 gate; **removed D1 deletion**, additionally hard-blocked production deploy/smoke even if billing gate later approves |
| `runner3-r2-bootstrap.yml` | manual or workflow push | Cloudflare R2 bucket list/create, then status commit | HOLD-gated both actions |
| `r2-media-bootstrap.yml` | manual or workflow push | Cloudflare R2 bucket API, public URL config, remote delivery proof, status commit | HOLD-gated all steps and status publishing |
| `r2-lifecycle-30d.yml` | manual or push to ops trigger | Read/PUT bucket lifecycle policy that may delete old objects | HOLD-gated policy operations and GitHub status publication |

## Independent release gate

- Created `ops/cloudflare-account-rehome/r2-admin-operations-policy.json` commit `2a806f1cf6abb571e7e661d094d3b68f58322e90`: `status=HOLD`, `permit_admin_r2_operations=false`, all five per-operation flags false, `source_retirement_permitted=false`, `source_account_cutover_permitted=false`.
- Created `scripts/cloudflare_r2_admin_operation_gate.py` commit `85c502f9c742ca7649a40b29dc5b5b95ef2423da`: validates both the **general** R2 billing migration gate and a **separate** per-admin-operation explicit approval. No Cloudflare/credential I/O and no command-line flag/environment override.
- Added offline tests `scripts/tests/test_cloudflare_r2_admin_operation_gate.py` commit `669e9a7d9a8f6540154dd5d33b8237aa79be0e85`. **Executed** on VPS in ephemeral temp directory with sensitive provider/token env removed: tests exit 0; direct current-policy CLI exits expected 3 with `R2_MIGRATION_BILLING_HOLD`. Tests cover independent permissions, all five current holds, source-retention invariants, and account identity.
- Workflow changes: inventory `095682f477479cb71b60030fa2ee2ee3267bc973`; CLM original lock `38cb44dfa0a0d7e47481e38710ecd163a78bc56c`, further production-deploy prohibition `52ffefa27e8961e7f174534e28a75f1ffa4a0bcd`; Runner3 bootstrap `7737365940026d3258ac3eefb64cd28fb5c542e7`; WP media bootstrap `7a23fcbb0cbffdf8323f4631a1c5f89539844043`; lifecycle `a6a983d7c3ff4e8abb472eeb1b2c1c6e62240399`.
- Source CLM D1 `clm-copilot-v1` is no longer deleted by the legacy migration workflow. The former `Retire CLM D1` step now only states that source is retained; production Worker deploy and live smoke require **separately reviewed source cutover** (explicitly set `if: ${{ false }}` in current workflow). This is in addition to R2 budget and individual-operation approval.

## Actual GitHub Actions HOLD acceptance

All are existing `push`-triggered jobs; **no manual workflow dispatch**:
- [Cloudflare Rehome R2 Inventory run #38850390024](https://github.com/louisalviss/runner-3/actions/runs/38850390024), exact patched SHA `095682f4`: job SUCCESS, gate SUCCESS; inventory request and GitHub publish **SKIPPED**.
- [Runner3 R2 Bootstrap run #38850419055](https://github.com/louisalviss/runner-3/actions/runs/38850419055), SHA `77373659`: job SUCCESS, gate SUCCESS; bucket API and proof publication **SKIPPED**.
- [Bootstrap R2 WordPress Media run #38850433497](https://github.com/louisalviss/runner-3/actions/runs/38850433497), SHA `7a23fcbb`: job SUCCESS, gate SUCCESS; all 4 R2/perms/proof steps and GitHub status publishing **SKIPPED**.
- `clm-d1-to-r2-migration.yml` and `r2-lifecycle-30d.yml` were **not dispatched**. Source readback static checks PASS, both parsed via Python PyYAML on VPS: gate present before Cloudflare-facing steps; CLM deletion absent, production deploy/smoke `if:false`. This is NOT live acceptance of those two workflows.

## Bounded additional candidate review

- Historical Oct8 checkout had 18 scheduled workflow files, 12 with *textual* indicators such as `artifact`/Core API/R2; not a current full inventory. Re-fetched eight non-obvious named candidates from GitHub main; several terms refer to GitHub Actions artifacts (not Cloudflare R2), or source Core service of unknown billable behavior. **Did not disable any of those without verified R2 call path.**
- Changes above are workflow-level hold admission, **not an account-wide R2 billing cap**, and do not prove historical `runner3-artifacts` 23–29 PUT/15 minutes came from these jobs.
- No Cloudflare bucket GET/LIST/HEAD/PUT/DELETE, D1 remote SQL, Worker deploy, secret handling, source deletion or production cutover was initiated in this work. Existing four held VPS services and prior independent scheduled-job policy remain unaffected.

## Next evidence gates

1. Attribute residual `PutObject` via authorized same-window provider Analytics and Data Access Logs in separate canonical cost incident, verify fresh billing, keep HOLD.
2. Audit any other confirmed R2 periodic source path by tracing actual Core/Worker calls; no blanket shutdown based only on filenames.
3. Resume D1/Workers current `louisalviss3` parity only through authorized Cloudflare access. Do not deploy from source-account Wrangler config or copy credentials across security blocks.
4. Require explicit source D1 retention/cutover authorization separately from a bounded R2 repair approval.


## 2026-10-17 — Artifact inventory proof workflow suspended under HOLD

- Confirmed a sixth separate **push-triggered**, previously unguarded workflow `.github/workflows/artifact-list-proof.yml` (Runner3 R2 Artifact Inventory Proof), triggered by its own source, `cloudflare/runner3-core/artifact-list-entry.js`, or source `wrangler.jsonc` changes. Its Core endpoint `/artifact-list` calls billable R2 LIST, and authenticated library inventory + signed delivery may touch R2/D1, followed by a GitHub `git push` proof publication. It is **not** a scheduled job and was not among the previously gated five R2 admin operations, seven manual migrations, or four scheduled jobs.
- First attempted to add a separately scoped admin operation entry, but the related regression test GitHub write was **blocked by safety review**. Did **not** reroute or bypass the denied write. **Reverted** the temporary admin gate/allowlist additions in commits `3972439a5afa5d23eff4059c7c9cb4816518440f` and `7254fc97d23490fb1520630d80709c0e549e3b07`, restoring the original five named operations, original `assert len(OPERATIONS)==5` test, and `status=HOLD`; fetched all three and verified consistent.
- Applied an independent **job-level static no-run protection** to `.github/workflows/artifact-list-proof.yml`: `jobs.proof.if: ${{ false }}`. Exact commit `df54c9987bcc3246bfc9eec0fc37d0d40e5adcc3`. Does not modify the Core Worker and does not depend on releasing a general R2 migration gate. **It requires a separate reviewed workflow edit and explicit approval to restore this proof**. Its original network calls and GitHub proof publication remain unchanged but unreachable while held.
- **Live GitHub Actions proof**: [run #38940274192](https://github.com/louisalviss/runner-3/actions/runs/38940274192), created 2026-10-16T17:30:55Z at exact commit `df54c998`, concluded **skipped**. GitHub readback verified the job-level hold. This run did **not** perform Core/R2 access or proof GitHub push.
- This hardening prevents one potential future push-triggered R2 LIST path; it does **not** prove the historical 23–29 PutObject/15min source, disable all possible R2 clients, or lift `COST_HOLD`. Canonical Dropbox R2 Cost task was most recently read as rev14, VERIFYING; fresh Billing and provider PutObject provenance remain open. No Cloudflare R2 request, production Worker deploy, target D1 write or source removal was manually dispatched.
