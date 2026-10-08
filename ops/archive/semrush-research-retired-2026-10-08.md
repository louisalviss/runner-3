<!-- HISTORICAL ARCHIVE: NOT AN ACTIVE FLOW. Semrush Research ended at R35 on 2026-10-08 (Asia/Ho_Chi_Minh). Do not use as instructions for new keyword-first scans. -->

# Semrush Research — Canonical

Updated: 2026-09-21
Status: ACTIVE / SINGLE SOURCE OF TRUTH
Parent: `AI-MEMORY/FLOWS/Business Opportunity Radar.md`
Runtime child: `AI-MEMORY/FLOWS/SEO/SEO Runtime Tooling - Semrush via NoxTools.md`

This file is the canonical scanner/flow/current-run authority for the Semrush Research lane. Candidate lifecycle/status is canonical in `Semrush Candidate Registry.md`. Do not recreate competing Business/candidate summary files.

<!-- SEMRUSH_CANDIDATE_SYNC_AUTOMATION_20261007 -->
## Candidate registry terminal-sync automation

Active implementation:
- `candidate_registry_sync.py` renders Candidate Registry from the exact-SERP tested registry + `candidate-lifecycle-v1.json`.
- `discovery_cycle.py` invokes it on `COMPLETE_NO_CANDIDATE`, post-SERP terminal close, and `RESUME_NO_BACKTRACK`.
- Dropbox human authority: `Semrush Candidate Registry.md`.
- Dropbox machine recovery mirror: `Semrush Tested Registry.json`.
- VPS machine authority: `/var/lib/semrush-research/config/discovery-tested-v1.json`.
- GitHub code/config authority: `louisalviss/runner-3` PR #363, squash `612456e0fe5bbab5c16e45752ab20271ce08fc8c`.
- GitHub tested-registry recovery baseline: PR #362, squash `69b3897a3b47c80d36f701a4fd10c03781875c86`.

Fail-safe semantics:
- If SERP finalization is already complete but Dropbox registry sync fails, the cycle blocks at sync.
- The next invocation reuses terminal artifacts and retries only registry sync.
- It must not reacquire the universe or rerun exact SERP work.
- Repeated successful resume is idempotent: unchanged Dropbox files are not rewritten.
<!-- /SEMRUSH_CANDIDATE_SYNC_AUTOMATION_20261007 -->

<!-- SEMRUSH_FILE_TAXONOMY_20261007 -->
- machine tested-registry recovery snapshot: GitHub runner-3/jobs/semrush-research/config/discovery-tested-v1.json @ 69b3897a3b47c80d36f701a4fd10c03781875c86 (PR #362).

## File taxonomy / candidate lifecycle

Canonical roles:
- `Semrush Research.md` = scanner rules, run history, current scanner state, recovery/resume logic.
- `Semrush Candidate Registry.md` = all tested candidate lifecycle states, ranking, final overrides, NO_RECHECK summary.
- `/var/lib/semrush-research/config/discovery-tested-v1.json` = machine exact-SERP anti-repeat authority.
- `PROJECTS/<name>/` = only candidates promoted to BUILD_TEST / ACTIVE VALIDATION / EXECUTION.

Hard promotion rule:
`SERP_DD_PASS` alone never creates a project.
A candidate remains in Candidate Registry until build/business validation promotes it.

Terminal-close rule for every future R26+ discovery run:
1. finalize SERP results;
2. update machine tested registry;
3. reconcile Candidate Registry lifecycle/ranking;
4. only then mark the run terminal;
5. create a PROJECTS entry only if promotion threshold is crossed.

Current state:
- machine tested registry: 135 exact-SERP records;
- R20-R25 terminal;
- current #1: Psychrometric HVAC Toolkit — WATCH_STRONG_CANDIDATE;
- Fisch — WATCH / NO BUILD;
- next discovery identity: R26+.
<!-- /SEMRUSH_FILE_TAXONOMY_20261007 -->

## CURRENT TERMINAL STATE — Fresh demand-first run — 2026-09-21

Run: `/var/lib/semrush-research/runs/fresh-2026-09-21/`

Input identity:
- seed bank: 61 themes / 253 seeds;
- seed-bank SHA256: `099dc6a8994971e6cdf4fa77a72875ab3c196ebd286773ac1c73b9aa15b36680`;
- universe SHA256: `31ad7fc9ed4748a4b9440060777312e2dd70e7c032d860c1d3b55bb9c466a000`;
- live Semrush shard: `6.semrush.com.in`.

Verified collection:
- 253/253 seeds have exact info + related summary;
- 251/253 seeds have related keyword rows;
- 7,140 raw keyword rows;
- 7,064 deduped keyword rows.

Demand gate:
- 61 projects total;
- 17 projects passed numeric demand gate;
- 50 clusters queued for exact SERP DD.

Exact SERP DD:
- 50/50 clusters complete;
- 2 keywords/cluster;
- 100/100 SERP queries complete;
- mechanical result: 44 `DROP_SERP_SATURATED`, 4 `WATCH_COMPETITION`, 2 `SERP_DD_PASS`.

Manual terminal review of all six non-saturated clusters:
- `compliance-safety-001` → `DROP_SEMANTIC_MIXED`;
- `compliance-safety-002` → `DROP_SEMANTIC_MIXED_SAFETY_LIABILITY`;
- `manufacturing-002` → `DROP_SEMANTIC_POLLUTION`;
- `manufacturing-004` → `DROP_NAVIGATIONAL_HISTORICAL`;
- `trucking-002` → `DROP_OFFICIAL_AUTHORITY`;
- `trucking-003` → `DROP_LOW_SCALE_INCUMBENTS`.

Terminal business result:
- `PASS_CANDIDATE: 0`;
- 50/50 clusters rejected after mechanical + semantic/business review;
- no new standalone greenfield opportunity was promoted from this batch.

Previous durable survivor decisions remain:
- RBT → `WATCH_NO_BUILD / ACQUIRE-ONLY`;
- HR Performance → `DROP_GREENFIELD / ACQUISITION_ONLY`;
- Local Reputation → `ABSORB_INTO_GROWTH_OPS / NO_STANDALONE_BUILD`.

Proof artifacts:
- `/var/lib/semrush-research/runs/fresh-2026-09-21/collection-state.json`
- `/var/lib/semrush-research/runs/fresh-2026-09-21/universe.json`
- `/var/lib/semrush-research/runs/fresh-2026-09-21/demand-gate/state.json`
- `/var/lib/semrush-research/runs/fresh-2026-09-21/serp-dd-live/state.json`
- `/var/lib/semrush-research/runs/fresh-2026-09-21/serp-dd-live/results.json`
- `/var/lib/semrush-research/runs/fresh-2026-09-21/serp-dd-live/raw-serps.jsonl`
- `/var/lib/semrush-research/runs/fresh-2026-09-21/serp-dd-live/terminal-verdicts.json`

## CURRENT COVERAGE — Full Dropbox idea scan — 2026-09-21

Run: `/var/lib/semrush-research/runs/dropbox-all-ideas-2026-09-21/`

Terminal coverage:
- state `COMPLETE`;
- 106 themes / 427 seed queries;
- 427 completed / 0 pending / 0 errors;
- databases: US, VN, CA, UK, AU;
- includes the original 91-theme inventory plus all 15 later delta themes.

Proof hashes:
- `state.json`: `e5a5c5a3dc04aaad1cbde72b846bfb0bd2221ec4f183644f0f5e5ea813964ac3`;
- `theme-summary.json`: `4c3ef3c1a47191a27d5261dd9c0e7ebe1e216a832fd12962751f603f958e7db1`;
- `universe-top30.json`: `f319efdb7c988450b957ee1a592e830aa921f51293e19ac58641044cf08909eb`;
- `seed-results.jsonl`: `8333c820f801cfbb9c32e3b3ebe06a79061816f858ba87dd4a26cb0c93b14458`.

Raw numeric screening passes from stored top30 unions — NOT approved opportunities:
- `finance-affiliate-vn` — union 501,370; KD<29 volume 130,170; LT5 low-KD 71; median KD 23;
- `3d-parts-intelligence` — 67,320; KD<29 54,430; LT5 47; median KD 16.5;
- `visa-atlas` — 63,890; KD<29 31,730; LT5 14; median KD 27;
- `rbt-practice` — 41,990; KD<29 35,300; LT5 14; median KD 11;
- `hr-performance-ai` — 37,970; KD<29 18,600; LT5 31; median KD 26.5;
- `local-reputation-ops` — 16,240; KD<29 6,270; LT5 23; median KD 24.

Former 15-delta set is fully reconciled and has zero pending themes. Selected terminal quantitative notes:
- `ai-study-tools` — union 29,770; KD<29 2,070; median KD 54;
- `hr-performance-ai` — 37,970; KD<29 18,600; median KD 26.5; semantic pollution remains;
- `affiliatex-category` — 2,970; KD<29 1,860; median KD 19;
- `stackposts-category` — 47,790; KD<29 1,010; median KD 38;
- `vector-marketplace` — 56,790; KD<29 12,450; median KD 51;
- `new-tab-extension` — 7,110; KD<29 500; median KD 36;
- `aeo-visibility` — 94,310; KD<29 23,450; LT5 20; median KD 36;
- `saas-boilerplate` — 3,900; KD<29 2,120; median KD 19;
- `nsw-development-apps` — 17,790; KD<29 7,270; median KD 30; LT5 count 4;
- `canada-npn-lookup` — 3,820; KD<29 540; median KD 49;
- `canada-cfia-lookup` — 3,750; KD<29 320; median KD 36.5;
- `canada-ised-rel` — 100; KD<29 0;
- `uk-hse-enforcement` — 4,540; KD<29 2,780; median KD 22;
- `uk-cqc-intelligence` — 8,320; KD<29 1,550; median KD 28;
- `po-pdf-shopify` — 210; KD<29 0.

Historical preliminary artifacts remain provenance only and are superseded by the 106-theme full scan:
- `/var/lib/semrush-research/runs/dropbox-idea-prelim-2026-09-21/prelim-summary.json` SHA256 `c89af69d4108c08f46cb57ed976bd8d4df19f3d52726a9baa36a7f67f716cbeb`;
- `/var/lib/semrush-research/runs/dropbox-idea-prelim-2026-09-21/rows.json` SHA256 `64435bd584b8934bf610e68deea6c523636fe4a061e3cfe67646ae7934b7d1f8`;
- `/var/lib/semrush-research/config/dropbox-idea-scan-skip-map-2026-09-21.json` SHA256 `078b2341094f945e37bd88ac657d83907e434f3942433450ee59d64bad1fedb4`.

## HARD ANTI-REPEAT CONTRACT

```text
same theme identity + same material thesis + same source/input identity
→ DO NOT rebuild seed bank
→ DO NOT rerun exact seed metrics
→ DO NOT rerun related-keyword universe collection
→ DO NOT rerun completed demand gate
→ DO NOT rerun completed SERP batch
→ load recorded artifacts and continue only from the next unfinished stage
```

For the 61-theme fresh run above, the whole batch is terminal. Do not run it again.

For the 106-theme Dropbox inventory above, quantitative discovery is complete. A new theme is additive and only that delta is scanned. A materially changed thesis may reopen only the affected theme.

Backtrack only when:
1. source/input materially changed;
2. thesis materially changed;
3. the user explicitly requests a forced rerun.

Old states such as `BLOCKED_LIVE_AUTH_CF`, RPC `Invalid params`, `PENDING_RECONCILE`, or `SERP_DD_PENDING` are historical/superseded and must never override the terminal states above.

## Purpose

Discover SEO/business niche opportunities from search demand itself: broad themes → related keyword universe → demand/KD/long-tail gate → exact SERP weakness → competition/economic validation.

This is a standalone lane. It is not SeoTrends/domain-first discovery and not `Niche research.md` pain/structural-neglect discovery.

## Trigger

Route here when Louis asks for:
- Semrush research / Semrush niche research;
- keyword-first or demand-first niche discovery;
- high-volume + low-KD + long-tail market scanning;
- scan search demand without requiring a known site/domain.

## Ownership boundaries

- **Semrush Research** owns keyword-first methodology, stage state, cluster decisions and resume point.
- `SeoTrends Semrush Unified Funnel.md` owns only SeoTrends/domain-origin discovery and validation.
- `Niche research.md` owns pain/structural-neglect hypothesis research.
- `SEO Runtime Tooling - Semrush via NoxTools.md` owns Semrush access/runtime only.
- `Semrush-RPC-Exporter-Canonical.md` owns domain Organic Positions extraction only.
- `Business Opportunity Radar.md` receives only survivors for downstream business validation.

## Canonical pipeline

```text
RESUME current state
→ broad seed/theme bank
→ Semrush related-keyword universe
→ normalize + intent-aware dedupe
→ aggregate demand scale gate
→ low-KD + long-tail gate
→ deterministic intent/task/entity clustering
→ exact live SERP DD
→ exact-product/incumbent competition
→ monetization/WTP/buildability validation
→ DROP / WATCH / PASS_CANDIDATE
→ Business Opportunity Radar
```

## Semrush acquisition

Preferred keyword-universe RPC through authenticated NoxTools session:
- `keywords.GetInfo` — exact keyword metrics;
- `ideas.GetKeywordsSummary` — related-keyword aggregate summary;
- `ideas.GetKeywords` — related keyword rows.

Known baseline params:
- `device=0`, `currency=USD`, `database=us`, `location=0`, `date=""`;
- omit empty `domain` instead of sending `domain=""`.

Hard data rule: UI-hydration `null` is UNKNOWN, never zero. A failed request is not demand=0.

## Demand gate — current defaults

Evaluate the deduped universe, not one attractive keyword.

Default triage:
- aggregate US volume >=10,000/mo;
- US volume carried by KD<29 >=2,000/mo;
- >=20 deduped metric-bearing keywords;
- >=10 long-tail keywords with KD<29;
- median non-null KD <30;
- largest keyword <=60% of universe volume.

Scale bands:
- 10k–50k → `CONDITIONAL_10K_50K`;
- 50k–200k → `VALID_TEST_50K_200K`;
- >=200k → `PRIORITY_200K_PLUS`.

Scale is not BUILD proof. CPC, intent, SERP structure, competition, monetization and legal/platform constraints remain downstream gates.

## SERP / economic DD

For each surviving cluster inspect:
- exact live SERP composition and freshness;
- dedicated exact tools vs generic articles;
- strong-domain dominance;
- Reddit/forum/weak-site presence;
- AI Overview/direct-answer/zero-click risk;
- local/shopping/navigation/brand distortion;
- programmatic surface size;
- commercial/transactional intent and CPC/value;
- incumbent product coverage;
- feasible monetization: tool/SaaS/lead-gen/affiliate/data/service;
- build complexity, legal/platform dependency and defensibility.

Do not promote merely because volume and KD look attractive.

## Persistence / resume rules

After every material main point persist:
- runtime `state.json`;
- append-only `main-points.jsonl`;
- gate/cluster/SERP queue artifacts as applicable;
- this Dropbox canonical file when durable state changes.

Resume invariant:
```text
same source/input SHA + same config + recorded stage
→ resume that exact stage
→ never restart an earlier completed stage merely because chat context is missing
```

## Implementation

- GitHub source: `louisalviss/runner-3/jobs/semrush-research/demand_first.py`;
- runtime: `/var/lib/semrush-research/scripts/demand_first.py`;
- live collector: `/var/lib/semrush-research/scripts/live_collect.py`;
- run data: `/var/lib/semrush-research/runs/<run-id>/`.

## Research terminal rule

`DROP`, `WATCH`, and `PASS_CANDIDATE` are valid terminal outcomes. Do not force a winner. `PASS_CANDIDATE` still requires downstream Business Opportunity Radar validation before BUILD.

## Exact future resume

1. Load this file first.
2. Treat fresh-2026-09-21 as terminal: 50/50 DROP, no rerun.
3. Treat the 106-theme Dropbox idea scan as full quantitative coverage authority.
4. Reconcile any incoming idea against existing identities before sending a Semrush query.
5. Scan only genuinely new/delta themes or materially changed theses.
6. For an existing theme, continue from semantic cleanup / exact SERP / competitor / monetization DD, never from generic seed collection.

<!-- SEMRUSH_EXACT_SEED_SNAPSHOT_20260921 -->
## Exact seed snapshot — HARD anti-repeat authority

This block stores the literal seeds, not only counts/hashes. It is the reconstruction authority for future chats.

```json
{
  "anti_repeat_contract": [
    "Exact same theme_id + same seed list + no material thesis change => NEVER rerun seed/preflight/universe collection.",
    "Existing fresh-2026-09-21 universe SHA 31ad7fc9ed4748a4b9440060777312e2dd70e7c032d860c1d3b55bb9c466a000 => do not rerun demand gate or SERP-DD.",
    "New theme => scan only that delta. Material thesis change => reopen only affected theme.",
    "If runtime artifacts are unavailable, this embedded seed snapshot is the reconstruction authority; do not rediscover old seeds from scratch."
  ],
  "date": "2026-09-21",
  "dropbox_idea_inventory": {
    "banks": [
      {
        "database": "us",
        "file": "idea-bank-dropbox-2026-09-21-us.json",
        "seed_count": 341,
        "sha256": "e1ef5f0b978971926badcffdabe367b2040e277b0fbe666bd742af7069ee679a",
        "theme_count": 85
      },
      {
        "database": "us",
        "file": "idea-bank-dropbox-2026-09-21-acq-delta-us.json",
        "seed_count": 32,
        "sha256": "1ad1712357c94508e14c8557d8a30a64b9a9c377076d81cf4d0e4cd100fbd200",
        "theme_count": 8
      },
      {
        "database": "us",
        "file": "idea-bank-dropbox-2026-09-21-us-delta2.json",
        "seed_count": 4,
        "sha256": "d1a2dcbcf89dbbe6c4b8ef3cdae949febabe4e63b58ec29eda10fb754acae590",
        "theme_count": 1
      },
      {
        "database": "vn",
        "file": "idea-bank-dropbox-2026-09-21-vn.json",
        "seed_count": 17,
        "sha256": "8eac103dbb97b241d080b73e359068f166361ddede1871a00af6442f816ec128",
        "theme_count": 4
      },
      {
        "database": "ca",
        "file": "idea-bank-dropbox-2026-09-21-ca.json",
        "seed_count": 5,
        "sha256": "00704d8c9e645d07061c62a070c467c94759e77844df4e2d1d07905c3c63d852",
        "theme_count": 1
      },
      {
        "database": "ca",
        "file": "idea-bank-dropbox-2026-09-21-ca-delta.json",
        "seed_count": 12,
        "sha256": "fb2a31360b3077d2b63034a2bbe3870d28426538ddc3f58b3288be22de81b9a0",
        "theme_count": 3
      },
      {
        "database": "uk",
        "file": "idea-bank-dropbox-2026-09-21-uk.json",
        "seed_count": 4,
        "sha256": "940fa7f325917e8de9e205c434fe2b3d4ae9d58626d5e80079694a05485e66da",
        "theme_count": 1
      },
      {
        "database": "uk",
        "file": "idea-bank-dropbox-2026-09-21-uk-delta.json",
        "seed_count": 8,
        "sha256": "ebcb2ba4a48a8fd860469e4ad1d050cd67f1693cc8fd6311eaed8be41cb67e64",
        "theme_count": 2
      },
      {
        "database": "au",
        "file": "idea-bank-dropbox-2026-09-21-au-delta.json",
        "seed_count": 4,
        "sha256": "593f5fe4e448868ede9efb6c6845d304ead9b2acc892a7d7718788c1e48684b8",
        "theme_count": 1
      }
    ],
    "seed_count": 427,
    "state_sha256": "e5a5c5a3dc04aaad1cbde72b846bfb0bd2221ec4f183644f0f5e5ea813964ac3",
    "theme_count": 106,
    "themes": [
      {
        "database": "us",
        "label": "Managed WordPress / Technical Growth Ops",
        "search_channel_fit": "secondary",
        "seeds": [
          "wordpress speed optimization service",
          "wordpress maintenance service",
          "wordpress technical seo service",
          "woocommerce optimization service"
        ],
        "theme_id": "wp-growth-ops"
      },
      {
        "database": "us",
        "label": "Launch Distribution / Startup Submission Ops",
        "search_channel_fit": "primary",
        "seeds": [
          "submit startup",
          "submit saas",
          "startup directory submission",
          "submit ai tool"
        ],
        "theme_id": "launch-ops"
      },
      {
        "database": "us",
        "label": "Search Execution Engine / SEO Experimentation",
        "search_channel_fit": "secondary",
        "seeds": [
          "seo testing tool",
          "seo experiment tracking",
          "seo a b testing",
          "seo change monitoring"
        ],
        "theme_id": "search-execution-engine"
      },
      {
        "database": "us",
        "label": "Woo Stack Failure Intelligence",
        "search_channel_fit": "primary",
        "seeds": [
          "woocommerce plugin conflict",
          "woocommerce compatibility checker",
          "woocommerce update broke site",
          "wordpress plugin conflict checker"
        ],
        "theme_id": "woo-stack-failure"
      },
      {
        "database": "us",
        "label": "WordPress Plugin Intelligence Graph",
        "search_channel_fit": "primary",
        "seeds": [
          "wordpress plugin compatibility",
          "wordpress plugin alternatives",
          "wordpress plugin closed replacement",
          "wordpress plugin status checker"
        ],
        "theme_id": "wp-plugin-intelligence"
      },
      {
        "database": "us",
        "label": "AI Managed WordPress Hosting Operations",
        "search_channel_fit": "secondary",
        "seeds": [
          "ai wordpress hosting",
          "managed wordpress automation",
          "wordpress management service",
          "wordpress hosting management"
        ],
        "theme_id": "ai-managed-wordpress"
      },
      {
        "database": "us",
        "label": "WordPress Performance Engineer",
        "search_channel_fit": "secondary",
        "seeds": [
          "wordpress performance audit",
          "wordpress speed optimization",
          "core web vitals wordpress",
          "wordpress performance service"
        ],
        "theme_id": "wordpress-performance"
      },
      {
        "database": "us",
        "label": "Visa / Immigration Intelligence",
        "search_channel_fit": "primary",
        "seeds": [
          "digital nomad visa",
          "retirement visa",
          "work visa requirements",
          "visa requirements by country"
        ],
        "theme_id": "visa-atlas"
      },
      {
        "database": "us",
        "label": "API Deprecation CI + Migration Automation",
        "search_channel_fit": "secondary",
        "seeds": [
          "api deprecation monitoring",
          "deprecated api checker",
          "api migration tool",
          "sdk migration tool"
        ],
        "theme_id": "deprecation-ci"
      },
      {
        "database": "us",
        "label": "Agent Runtime / Session Integrity Recovery",
        "search_channel_fit": "secondary",
        "seeds": [
          "ai agent monitoring",
          "ai agent observability",
          "agent session recovery",
          "llm agent reliability"
        ],
        "theme_id": "agent-runtime-recovery"
      },
      {
        "database": "us",
        "label": "Agent Transaction Safety / Reversible Execution",
        "search_channel_fit": "secondary",
        "seeds": [
          "ai agent guardrails",
          "ai agent approval workflow",
          "ai agent audit log",
          "ai agent transaction safety"
        ],
        "theme_id": "agent-transaction-safety"
      },
      {
        "database": "us",
        "label": "Local Reputation Operations",
        "search_channel_fit": "primary",
        "seeds": [
          "review management service",
          "google review management",
          "local reputation management",
          "review monitoring tool"
        ],
        "theme_id": "local-reputation-ops"
      },
      {
        "database": "us",
        "label": "Website Exit Readiness / Acquisition Due Diligence",
        "search_channel_fit": "secondary",
        "seeds": [
          "website due diligence service",
          "website acquisition due diligence",
          "sell website due diligence",
          "saas due diligence checklist"
        ],
        "theme_id": "website-exit-dd"
      },
      {
        "database": "us",
        "label": "Conversion Tracking / Measurement Ops",
        "search_channel_fit": "secondary",
        "seeds": [
          "conversion tracking audit",
          "ga4 audit service",
          "google ads conversion tracking audit",
          "crm attribution audit"
        ],
        "theme_id": "measurement-ops"
      },
      {
        "database": "us",
        "label": "AI Content Ops / SEO Automation Service",
        "search_channel_fit": "secondary",
        "seeds": [
          "seo automation service",
          "ai seo service",
          "content operations service",
          "programmatic seo service"
        ],
        "theme_id": "ai-content-ops"
      },
      {
        "database": "us",
        "label": "Local Lead Gen + Buyer Liquidation",
        "search_channel_fit": "secondary",
        "seeds": [
          "local lead generation service",
          "pay per lead local business",
          "lead generation websites",
          "local seo lead generation"
        ],
        "theme_id": "local-lead-gen"
      },
      {
        "database": "us",
        "label": "Shopify Stocky Migration / Inventory Continuity",
        "search_channel_fit": "secondary",
        "seeds": [
          "shopify stocky alternative",
          "stocky migration",
          "shopify inventory migration",
          "shopify pos inventory migration"
        ],
        "theme_id": "shopify-stocky-migration"
      },
      {
        "database": "us",
        "label": "eSIM / OTP / Keep-number Intelligence",
        "search_channel_fit": "primary",
        "seeds": [
          "esim for sms verification",
          "keep phone number esim",
          "receive otp esim",
          "temporary esim number"
        ],
        "theme_id": "esim-otp-intelligence"
      },
      {
        "database": "us",
        "label": "WordPress Theme Intelligence",
        "search_channel_fit": "primary",
        "seeds": [
          "wordpress theme compatibility",
          "wordpress theme alternatives",
          "wordpress theme checker",
          "wordpress theme detector"
        ],
        "theme_id": "wp-theme-intelligence"
      },
      {
        "database": "us",
        "label": "CVE / Security Decision Engine",
        "search_channel_fit": "primary",
        "seeds": [
          "cve checker",
          "vulnerability impact checker",
          "software vulnerability checker",
          "cve risk assessment"
        ],
        "theme_id": "cve-decision-engine"
      },
      {
        "database": "us",
        "label": "3D Printer Parts Intelligence",
        "search_channel_fit": "primary",
        "seeds": [
          "3d printer parts",
          "3d printer nozzle",
          "3d printer build plate",
          "3d printer hotend",
          "3d printer extruder"
        ],
        "theme_id": "3d-parts-intelligence"
      },
      {
        "database": "us",
        "label": "Florida Permit / Product Approval Preflight",
        "search_channel_fit": "primary",
        "seeds": [
          "florida product approval search",
          "miami dade noa",
          "florida window permit",
          "window design pressure florida"
        ],
        "theme_id": "florida-permit-preflight"
      },
      {
        "database": "us",
        "label": "Manufactured Home Record Resolver",
        "search_channel_fit": "primary",
        "seeds": [
          "mobile home serial number lookup",
          "mobile home vin lookup",
          "mobile home title search",
          "manufactured home title search"
        ],
        "theme_id": "manufactured-home-resolver"
      },
      {
        "database": "us",
        "label": "HOA Transition Vault / Handoff Audit",
        "search_channel_fit": "secondary",
        "seeds": [
          "hoa transition checklist",
          "hoa management company transition",
          "hoa board transition checklist",
          "hoa document management"
        ],
        "theme_id": "hoa-transition-audit"
      },
      {
        "database": "us",
        "label": "Commercial AV Budget Estimator / RFQ Router",
        "search_channel_fit": "primary",
        "seeds": [
          "av installation companies",
          "commercial av integrator",
          "conference room av cost",
          "audio visual companies near me"
        ],
        "theme_id": "commercial-av-rfq"
      },
      {
        "database": "us",
        "label": "China Product Market Access Checker",
        "search_channel_fit": "primary",
        "seeds": [
          "ccc certification",
          "china product certification",
          "srrc certification",
          "china rohs compliance"
        ],
        "theme_id": "china-market-access"
      },
      {
        "database": "us",
        "label": "SaaS Stack Transferability / Acquisition Handover",
        "search_channel_fit": "secondary",
        "seeds": [
          "saas acquisition checklist",
          "saas transfer checklist",
          "software acquisition due diligence",
          "saas handover checklist"
        ],
        "theme_id": "saas-transferability"
      },
      {
        "database": "us",
        "label": "IGA Flat-file Feed Health",
        "search_channel_fit": "secondary",
        "seeds": [
          "identity governance flat file feed",
          "iga data feed monitoring",
          "identity governance integration monitoring",
          "identity data reconciliation"
        ],
        "theme_id": "iga-feed-health"
      },
      {
        "database": "us",
        "label": "Funeral Provider Regulatory Trust Graph",
        "search_channel_fit": "primary",
        "seeds": [
          "funeral home license lookup",
          "funeral director license lookup",
          "crematory license lookup",
          "funeral home disciplinary action"
        ],
        "theme_id": "funeral-trust-graph"
      },
      {
        "database": "us",
        "label": "Fibery Scheduled Backup / Restore",
        "search_channel_fit": "primary",
        "seeds": [
          "fibery backup",
          "fibery export",
          "fibery restore",
          "fibery backup to s3"
        ],
        "theme_id": "fibery-backup"
      },
      {
        "database": "us",
        "label": "Elevator Inspection / Certificate Lookup",
        "search_channel_fit": "primary",
        "seeds": [
          "elevator inspection lookup",
          "elevator certificate lookup",
          "elevator violations lookup",
          "elevator permit lookup"
        ],
        "theme_id": "elevator-inspection"
      },
      {
        "database": "us",
        "label": "Migration Loss / SaaS Exit Intelligence",
        "search_channel_fit": "primary",
        "seeds": [
          "saas migration checklist",
          "software migration data loss",
          "migration compatibility checker",
          "saas export migration"
        ],
        "theme_id": "migration-loss"
      },
      {
        "database": "us",
        "label": "Shopify App Exit Preflight",
        "search_channel_fit": "primary",
        "seeds": [
          "uninstall shopify app",
          "shopify app leftover code",
          "remove shopify app code",
          "shopify app data after uninstall"
        ],
        "theme_id": "shopify-app-exit"
      },
      {
        "database": "us",
        "label": "Website SaaS Removal Impact Scanner",
        "search_channel_fit": "primary",
        "seeds": [
          "website dependency scanner",
          "third party script scanner",
          "find all scripts on website",
          "remove third party script website"
        ],
        "theme_id": "website-saas-removal"
      },
      {
        "database": "us",
        "label": "Woo Google Merchant Feed Health Watchdog",
        "search_channel_fit": "primary",
        "seeds": [
          "woocommerce google merchant sync",
          "google merchant center product sync issue",
          "woocommerce product feed error",
          "google merchant feed monitoring"
        ],
        "theme_id": "woo-feed-health"
      },
      {
        "database": "us",
        "label": "Woo MCP Action Firewall / Policy Layer",
        "search_channel_fit": "secondary",
        "seeds": [
          "woocommerce mcp",
          "ai agent action approval",
          "mcp security gateway",
          "mcp policy engine"
        ],
        "theme_id": "woo-mcp-firewall"
      },
      {
        "database": "us",
        "label": "Clinical Trial Site Revenue Recovery",
        "search_channel_fit": "secondary",
        "seeds": [
          "clinical trial site payment reconciliation",
          "clinical trial revenue cycle",
          "clinical trial site invoicing",
          "clinical trial payment tracking"
        ],
        "theme_id": "clinical-trial-revenue"
      },
      {
        "database": "us",
        "label": "Legal Conflict Graph",
        "search_channel_fit": "primary",
        "seeds": [
          "law firm conflict check",
          "legal conflict check software",
          "conflict of interest checker law firm",
          "law firm conflict search"
        ],
        "theme_id": "legal-conflict-graph"
      },
      {
        "database": "us",
        "label": "Scientific Testing Lab Revenue Auditor",
        "search_channel_fit": "secondary",
        "seeds": [
          "laboratory billing audit",
          "lims billing reconciliation",
          "lab revenue leakage",
          "laboratory invoice reconciliation"
        ],
        "theme_id": "lab-revenue-audit"
      },
      {
        "database": "us",
        "label": "Contract Manufacturing Revenue Auditor",
        "search_channel_fit": "secondary",
        "seeds": [
          "manufacturing revenue leakage",
          "contract manufacturing billing",
          "manufacturing invoice audit",
          "production billing reconciliation"
        ],
        "theme_id": "contract-manufacturing-audit"
      },
      {
        "database": "us",
        "label": "Data Center / Colocation Revenue Auditor",
        "search_channel_fit": "secondary",
        "seeds": [
          "colocation billing software",
          "data center billing reconciliation",
          "colocation billing audit",
          "data center revenue leakage"
        ],
        "theme_id": "colocation-revenue-audit"
      },
      {
        "database": "us",
        "label": "Fiber / Telecom Contractor Revenue Recovery",
        "search_channel_fit": "secondary",
        "seeds": [
          "telecom contractor billing",
          "fiber construction billing",
          "fiber contractor closeout",
          "telecom revenue leakage"
        ],
        "theme_id": "fiber-revenue-recovery"
      },
      {
        "database": "us",
        "label": "Managed Print Billing Exception Queue",
        "search_channel_fit": "secondary",
        "seeds": [
          "managed print billing software",
          "meter billing reconciliation",
          "managed print billing audit",
          "printer meter billing"
        ],
        "theme_id": "managed-print-billing"
      },
      {
        "database": "us",
        "label": "Commercial Service Revenue Leakage Monitor",
        "search_channel_fit": "secondary",
        "seeds": [
          "service revenue leakage",
          "field service billing reconciliation",
          "servicechannel invoice reconciliation",
          "corrigo invoice reconciliation"
        ],
        "theme_id": "commercial-service-leakage"
      },
      {
        "database": "us",
        "label": "Contractor Multi Portal Compliance Layer",
        "search_channel_fit": "secondary",
        "seeds": [
          "contractor compliance software",
          "isnetworld avetta management",
          "contractor prequalification software",
          "vendor compliance portal"
        ],
        "theme_id": "contractor-compliance-portals"
      },
      {
        "database": "us",
        "label": "3PL Operational Billing Auditor",
        "search_channel_fit": "secondary",
        "seeds": [
          "3pl billing audit",
          "warehouse billing software",
          "3pl revenue leakage",
          "3pl invoice reconciliation"
        ],
        "theme_id": "3pl-billing-audit"
      },
      {
        "database": "us",
        "label": "Appliance Replacement Part Compatibility",
        "search_channel_fit": "primary",
        "seeds": [
          "appliance parts compatibility",
          "replacement part finder",
          "appliance model parts lookup",
          "does this part fit my appliance"
        ],
        "theme_id": "appliance-compatibility"
      },
      {
        "database": "us",
        "label": "Return Deadline Tracker",
        "search_channel_fit": "primary",
        "seeds": [
          "return deadline tracker",
          "return window tracker",
          "receipt return reminder",
          "return period calculator"
        ],
        "theme_id": "return-deadline"
      },
      {
        "database": "us",
        "label": "Parking Sign Reader / Can I Park Here",
        "search_channel_fit": "primary",
        "seeds": [
          "parking sign reader",
          "can i park here app",
          "parking sign scanner",
          "parking restriction checker"
        ],
        "theme_id": "parking-sign-reader"
      },
      {
        "database": "us",
        "label": "Best Value on Shelf / Unit Price",
        "search_channel_fit": "primary",
        "seeds": [
          "unit price comparison app",
          "grocery unit price calculator",
          "price per unit calculator",
          "compare grocery prices"
        ],
        "theme_id": "shelf-unit-price"
      },
      {
        "database": "us",
        "label": "Meal Sync Cooking Timeline",
        "search_channel_fit": "primary",
        "seeds": [
          "cooking timeline planner",
          "meal timing planner",
          "multiple dishes cooking timer",
          "recipe timeline planner"
        ],
        "theme_id": "meal-sync"
      },
      {
        "database": "us",
        "label": "Will This Fit Through",
        "search_channel_fit": "primary",
        "seeds": [
          "furniture fit through door calculator",
          "will furniture fit through door",
          "moving furniture calculator",
          "sofa door fit calculator"
        ],
        "theme_id": "furniture-fit"
      },
      {
        "database": "us",
        "label": "Fastest Checkout Line",
        "search_channel_fit": "primary",
        "seeds": [
          "fastest checkout line app",
          "queue prediction app",
          "checkout wait time",
          "supermarket queue app"
        ],
        "theme_id": "checkout-line"
      },
      {
        "database": "us",
        "label": "Yellow Sticker Markdown Radar",
        "search_channel_fit": "primary",
        "seeds": [
          "supermarket markdown times",
          "grocery clearance times",
          "yellow sticker times",
          "supermarket reduced food times"
        ],
        "theme_id": "yellow-sticker"
      },
      {
        "database": "us",
        "label": "Got Money Back / Price Adjustment Tracker",
        "search_channel_fit": "primary",
        "seeds": [
          "price adjustment tracker",
          "price drop refund app",
          "receipt price drop alert",
          "price protection tracker"
        ],
        "theme_id": "price-drop-refund"
      },
      {
        "database": "us",
        "label": "Food Delivery Checkout Compare",
        "search_channel_fit": "primary",
        "seeds": [
          "food delivery price comparison",
          "compare food delivery prices",
          "doordash uber eats price comparison",
          "food delivery fee comparison"
        ],
        "theme_id": "food-delivery-compare"
      },
      {
        "database": "us",
        "label": "Buy It For Life / Repairability Scanner",
        "search_channel_fit": "primary",
        "seeds": [
          "repairability score",
          "product repairability checker",
          "parts availability checker",
          "right to repair product database"
        ],
        "theme_id": "buy-it-for-life"
      },
      {
        "database": "us",
        "label": "Marketplace Claim Guard / Unboxing Evidence",
        "search_channel_fit": "secondary",
        "seeds": [
          "unboxing video proof return",
          "package damage evidence app",
          "marketplace dispute evidence",
          "unboxing proof app"
        ],
        "theme_id": "marketplace-claim-guard"
      },
      {
        "database": "us",
        "label": "monday.com Progress Logic",
        "search_channel_fit": "primary",
        "seeds": [
          "monday.com progress bar",
          "monday status percentage",
          "monday.com weighted progress",
          "monday.com status to percentage"
        ],
        "theme_id": "monday-progress"
      },
      {
        "database": "us",
        "label": "Visual Tutorial to PDF",
        "search_channel_fit": "primary",
        "seeds": [
          "video tutorial to pdf",
          "youtube tutorial to pdf",
          "convert tutorial video to pdf",
          "video to step by step guide"
        ],
        "theme_id": "visual-tutorial-pdf"
      },
      {
        "database": "us",
        "label": "Vacation Rental Guest Guide",
        "search_channel_fit": "primary",
        "seeds": [
          "vacation rental guest guide",
          "airbnb digital guidebook",
          "vacation rental welcome book",
          "airbnb guest guide app"
        ],
        "theme_id": "vacation-rental-guide"
      },
      {
        "database": "us",
        "label": "Digital Legacy / Last Message",
        "search_channel_fit": "primary",
        "seeds": [
          "digital legacy service",
          "dead man switch message",
          "after death message service",
          "digital legacy app"
        ],
        "theme_id": "digital-legacy"
      },
      {
        "database": "us",
        "label": "Ebook to Audio",
        "search_channel_fit": "primary",
        "seeds": [
          "ebook to audiobook converter",
          "epub to audiobook",
          "pdf to audiobook",
          "text to audiobook converter"
        ],
        "theme_id": "ebook-audio"
      },
      {
        "database": "us",
        "label": "Subtitle / Manga Translation",
        "search_channel_fit": "primary",
        "seeds": [
          "subtitle translation service",
          "ai subtitle translator",
          "manga translation tool",
          "comic translation app"
        ],
        "theme_id": "subtitle-translation"
      },
      {
        "database": "us",
        "label": "Video Production Storage Planner",
        "search_channel_fit": "primary",
        "seeds": [
          "video storage calculator",
          "camera storage calculator",
          "prores storage calculator",
          "braw storage calculator"
        ],
        "theme_id": "braw-storage"
      },
      {
        "database": "us",
        "label": "Recipe Normalization Engine",
        "search_channel_fit": "primary",
        "seeds": [
          "recipe unit converter",
          "recipe scale calculator",
          "ingredient conversion calculator",
          "recipe cost calculator"
        ],
        "theme_id": "recipe-normalization"
      },
      {
        "database": "us",
        "label": "RBT Practice Exam",
        "search_channel_fit": "primary",
        "seeds": [
          "rbt practice exam",
          "rbt mock exam",
          "rbt practice test",
          "registered behavior technician practice test"
        ],
        "theme_id": "rbt-practice"
      },
      {
        "database": "us",
        "label": "Nutrition / Nutrients Calculator",
        "search_channel_fit": "primary",
        "seeds": [
          "nutrient calculator",
          "nutrition calculator",
          "macro calculator food",
          "vitamin intake calculator"
        ],
        "theme_id": "nutrition-calculator"
      },
      {
        "database": "us",
        "label": "Markdown / Document Conversion Tools",
        "search_channel_fit": "primary",
        "seeds": [
          "markdown converter",
          "markdown to html",
          "markdown to pdf",
          "html to markdown"
        ],
        "theme_id": "markdown-converters"
      },
      {
        "database": "us",
        "label": "Local SEO NAP / Entity Consistency",
        "search_channel_fit": "primary",
        "seeds": [
          "nap checker",
          "local citation checker",
          "business listing consistency checker",
          "local seo citation audit"
        ],
        "theme_id": "local-nap"
      },
      {
        "database": "us",
        "label": "Woo Catalog Change Gate / Supplier Drift",
        "search_channel_fit": "secondary",
        "seeds": [
          "woocommerce product feed validation",
          "woocommerce catalog sync",
          "supplier feed validation",
          "product feed diff"
        ],
        "theme_id": "catalog-change-gate"
      },
      {
        "database": "us",
        "label": "Fresh Clone / Release Acceptance Gate",
        "search_channel_fit": "secondary",
        "seeds": [
          "deployment verification tool",
          "release validation",
          "post deployment testing",
          "deployment smoke test"
        ],
        "theme_id": "release-acceptance"
      },
      {
        "database": "us",
        "label": "AI App Builder / AppAlchemy Category",
        "search_channel_fit": "primary",
        "seeds": [
          "ai app builder",
          "no code app builder",
          "mobile app builder",
          "ai mobile app builder"
        ],
        "theme_id": "ai-app-builder"
      },
      {
        "database": "us",
        "label": "AI Vector / Image Converter Tools",
        "search_channel_fit": "primary",
        "seeds": [
          "image to vector",
          "png to svg",
          "jpg to svg",
          "image vectorizer"
        ],
        "theme_id": "ai-vector-tools"
      },
      {
        "database": "us",
        "label": "Keyword Research / Clustering SaaS",
        "search_channel_fit": "primary",
        "seeds": [
          "keyword clustering tool",
          "keyword cannibalization checker",
          "content brief generator",
          "topical map generator"
        ],
        "theme_id": "keyword-seo-tools"
      },
      {
        "database": "us",
        "label": "WordPress Travel / Tour Booking",
        "search_channel_fit": "primary",
        "seeds": [
          "wordpress travel plugin",
          "tour booking wordpress",
          "travel booking wordpress",
          "travel itinerary plugin"
        ],
        "theme_id": "wp-travel"
      },
      {
        "database": "us",
        "label": "AI Website Builder",
        "search_channel_fit": "primary",
        "seeds": [
          "ai website builder",
          "website generator",
          "ai landing page builder",
          "ai ecommerce website builder"
        ],
        "theme_id": "ai-website-builder"
      },
      {
        "database": "us",
        "label": "AI Coding Context / Documentation",
        "search_channel_fit": "primary",
        "seeds": [
          "code documentation generator",
          "ai code documentation",
          "codebase documentation",
          "repository documentation"
        ],
        "theme_id": "coding-context"
      },
      {
        "database": "us",
        "label": "LinkedIn Content / UpLinked Category",
        "search_channel_fit": "primary",
        "seeds": [
          "linkedin post generator",
          "linkedin content generator",
          "linkedin carousel maker",
          "linkedin scheduler"
        ],
        "theme_id": "linkedin-content"
      },
      {
        "database": "us",
        "label": "Popular Times / Foot Traffic API",
        "search_channel_fit": "primary",
        "seeds": [
          "popular times api",
          "foot traffic api",
          "busy times api",
          "venue traffic data"
        ],
        "theme_id": "popular-times-api"
      },
      {
        "database": "us",
        "label": "Amazon KDP Research Tools",
        "search_channel_fit": "primary",
        "seeds": [
          "kdp keyword research",
          "kdp niche research",
          "kdp calculator",
          "amazon kdp keywords"
        ],
        "theme_id": "kdp-tools"
      },
      {
        "database": "us",
        "label": "Google Maps Rank Tracker / AI Coach",
        "search_channel_fit": "primary",
        "seeds": [
          "google maps rank tracker",
          "local rank tracker",
          "map rank tracker",
          "google business profile rank tracker"
        ],
        "theme_id": "google-maps-rank"
      },
      {
        "database": "us",
        "label": "WordPress Themes / Templates",
        "search_channel_fit": "primary",
        "seeds": [
          "wordpress themes",
          "wordpress template marketplace",
          "premium wordpress themes",
          "wordpress theme subscription"
        ],
        "theme_id": "wp-themes-business"
      },
      {
        "database": "us",
        "label": "AI Social Media Content SaaS",
        "search_channel_fit": "primary",
        "seeds": [
          "ai social media content generator",
          "social media ai tool",
          "ai content planner",
          "ai social media scheduler"
        ],
        "theme_id": "social-content-saas"
      },
      {
        "database": "us",
        "label": "AI Document Review SaaS",
        "search_channel_fit": "primary",
        "seeds": [
          "ai document review",
          "document review software ai",
          "contract review ai",
          "ai document analyzer"
        ],
        "theme_id": "document-review-ai"
      },
      {
        "database": "us",
        "label": "AI Study SaaS",
        "search_channel_fit": "primary",
        "seeds": [
          "ai study tool",
          "ai study assistant",
          "ai flashcard generator",
          "ai quiz generator"
        ],
        "theme_id": "ai-study-tools"
      },
      {
        "database": "us",
        "label": "AI HR Performance Management",
        "search_channel_fit": "primary",
        "seeds": [
          "performance management software",
          "employee performance management",
          "ai performance review",
          "employee review software"
        ],
        "theme_id": "hr-performance-ai"
      },
      {
        "database": "us",
        "label": "WordPress Affiliate Marketing Plugin",
        "search_channel_fit": "primary",
        "seeds": [
          "wordpress affiliate plugin",
          "amazon affiliate wordpress plugin",
          "affiliate product box wordpress",
          "affiliate marketing plugin wordpress"
        ],
        "theme_id": "affiliatex-category"
      },
      {
        "database": "us",
        "label": "Social Media Management / StackPosts Category",
        "search_channel_fit": "primary",
        "seeds": [
          "social media management software",
          "social media scheduling tool",
          "social media automation tool",
          "social media posting software"
        ],
        "theme_id": "stackposts-category"
      },
      {
        "database": "us",
        "label": "Vector Graphics / Stock Vector Traffic Asset",
        "search_channel_fit": "primary",
        "seeds": [
          "free vector graphics",
          "vector download",
          "stock vectors",
          "vector illustrations"
        ],
        "theme_id": "vector-marketplace"
      },
      {
        "database": "us",
        "label": "Chrome New Tab Extension Distribution Asset",
        "search_channel_fit": "secondary",
        "seeds": [
          "new tab extension",
          "chrome new tab extension",
          "custom new tab chrome",
          "new tab page extension"
        ],
        "theme_id": "new-tab-extension"
      },
      {
        "database": "us",
        "label": "AI Search Visibility / AEO / AIRIX Category",
        "search_channel_fit": "primary",
        "seeds": [
          "ai search visibility",
          "answer engine optimization",
          "generative engine optimization",
          "ai search optimization"
        ],
        "theme_id": "aeo-visibility"
      },
      {
        "database": "us",
        "label": "AI SaaS Boilerplate",
        "search_channel_fit": "primary",
        "seeds": [
          "saas boilerplate",
          "nextjs saas boilerplate",
          "ai saas boilerplate",
          "saas starter kit"
        ],
        "theme_id": "saas-boilerplate"
      },
      {
        "database": "us",
        "label": "B2B PO/PDF to Shopify Draft Order",
        "search_channel_fit": "primary",
        "seeds": [
          "shopify purchase order import",
          "shopify order import pdf",
          "create shopify draft order",
          "shopify b2b order import"
        ],
        "theme_id": "po-pdf-shopify"
      },
      {
        "database": "vn",
        "label": "Vietnam Finance Affiliate Engine",
        "search_channel_fit": "primary",
        "seeds": [
          "vay online",
          "vay tín chấp",
          "mở thẻ tín dụng",
          "thẻ tín dụng",
          "vay theo lương"
        ],
        "theme_id": "finance-affiliate-vn"
      },
      {
        "database": "vn",
        "label": "Vietnam Label Compliance Preflight",
        "search_channel_fit": "primary",
        "seeds": [
          "nhãn hàng hóa việt nam",
          "quy định nhãn hàng hóa",
          "ghi nhãn hàng hóa nhập khẩu",
          "kiểm tra nhãn hàng hóa"
        ],
        "theme_id": "vietnam-label-compliance"
      },
      {
        "database": "vn",
        "label": "Vietnam AI News Distribution Engine",
        "search_channel_fit": "secondary",
        "seeds": [
          "tin tức ai",
          "công cụ ai",
          "trí tuệ nhân tạo tin tức",
          "ai cho doanh nghiệp"
        ],
        "theme_id": "ai-news-vn"
      },
      {
        "database": "vn",
        "label": "Vietnam Auto Care Private Label",
        "search_channel_fit": "secondary",
        "seeds": [
          "dung dịch vệ sinh ô tô",
          "chăm sóc xe ô tô",
          "dung dịch rửa xe",
          "phủ ceramic ô tô"
        ],
        "theme_id": "auto-care-vn"
      },
      {
        "database": "ca",
        "label": "Canada Recall Check",
        "search_channel_fit": "primary",
        "seeds": [
          "canada recalls",
          "product recall canada",
          "food recall canada",
          "vehicle recall canada",
          "recall checker canada"
        ],
        "theme_id": "canada-recall"
      },
      {
        "database": "ca",
        "label": "Canada Natural Product Number / NPN Lookup",
        "search_channel_fit": "primary",
        "seeds": [
          "npn lookup",
          "natural product number lookup",
          "natural health product database",
          "npn canada"
        ],
        "theme_id": "canada-npn-lookup"
      },
      {
        "database": "ca",
        "label": "Canada CFIA Public Data / Food Inspection Lookup",
        "search_channel_fit": "primary",
        "seeds": [
          "cfia inspection search",
          "food inspection canada",
          "cfia establishment search",
          "food recall inspection canada"
        ],
        "theme_id": "canada-cfia-lookup"
      },
      {
        "database": "ca",
        "label": "Canada ISED Radio Equipment List / Certification Lookup",
        "search_channel_fit": "primary",
        "seeds": [
          "ised rel search",
          "radio equipment list canada",
          "ic certification lookup",
          "ised certification search"
        ],
        "theme_id": "canada-ised-rel"
      },
      {
        "database": "uk",
        "label": "UK Court Listings SEO Site",
        "search_channel_fit": "primary",
        "seeds": [
          "court listings",
          "court listings today",
          "crown court listings",
          "magistrates court listings"
        ],
        "theme_id": "uk-court-listings"
      },
      {
        "database": "uk",
        "label": "UK HSE Enforcement / Prosecution Lookup",
        "search_channel_fit": "primary",
        "seeds": [
          "hse enforcement notice",
          "hse prosecutions",
          "hse enforcement database",
          "hse notices"
        ],
        "theme_id": "uk-hse-enforcement"
      },
      {
        "database": "uk",
        "label": "UK CQC Inspection / Rating Intelligence",
        "search_channel_fit": "primary",
        "seeds": [
          "cqc ratings",
          "cqc inspection reports",
          "cqc care home ratings",
          "cqc provider search"
        ],
        "theme_id": "uk-cqc-intelligence"
      },
      {
        "database": "au",
        "label": "NSW Development Application / DA Tracker",
        "search_channel_fit": "primary",
        "seeds": [
          "development application search nsw",
          "da tracker nsw",
          "development applications nsw",
          "council da tracker"
        ],
        "theme_id": "nsw-development-apps"
      }
    ]
  },
  "fresh_demand_first": {
    "database": "us",
    "seed_count": 253,
    "source_sha256": "099dc6a8994971e6cdf4fa77a72875ab3c196ebd286773ac1c73b9aa15b36680",
    "theme_count": 61,
    "themes": [
      {
        "seeds": [
          "property owner lookup",
          "property tax lookup",
          "parcel lookup",
          "deed search",
          "property lien search"
        ],
        "theme_id": "property-records"
      },
      {
        "seeds": [
          "building permit lookup",
          "permit requirements",
          "permit cost calculator",
          "contractor license lookup"
        ],
        "theme_id": "home-permits"
      },
      {
        "seeds": [
          "solar panel calculator",
          "solar savings calculator",
          "electricity cost calculator",
          "solar permit requirements"
        ],
        "theme_id": "solar-energy"
      },
      {
        "seeds": [
          "hvac load calculator",
          "hvac sizing calculator",
          "ac tonnage calculator",
          "furnace size calculator"
        ],
        "theme_id": "hvac"
      },
      {
        "seeds": [
          "roofing calculator",
          "roof pitch calculator",
          "roof replacement cost calculator",
          "shingle calculator"
        ],
        "theme_id": "roofing"
      },
      {
        "seeds": [
          "flooring calculator",
          "tile calculator",
          "flooring cost calculator",
          "carpet calculator"
        ],
        "theme_id": "flooring"
      },
      {
        "seeds": [
          "concrete calculator",
          "concrete cost calculator",
          "brick calculator",
          "mortar calculator"
        ],
        "theme_id": "concrete-masonry"
      },
      {
        "seeds": [
          "paint calculator",
          "paint coverage calculator",
          "epoxy calculator",
          "stain calculator"
        ],
        "theme_id": "paint-coatings"
      },
      {
        "seeds": [
          "mulch calculator",
          "soil calculator",
          "gravel calculator",
          "sod calculator"
        ],
        "theme_id": "landscaping"
      },
      {
        "seeds": [
          "vin lookup",
          "vehicle recall lookup",
          "license plate lookup",
          "car title check",
          "vehicle registration fee calculator"
        ],
        "theme_id": "vehicle-records"
      },
      {
        "seeds": [
          "oil change cost calculator",
          "tire size calculator",
          "car battery finder",
          "brake cost calculator"
        ],
        "theme_id": "auto-maintenance"
      },
      {
        "seeds": [
          "ev charging cost calculator",
          "ev charging time calculator",
          "ev range calculator",
          "home charger installation cost"
        ],
        "theme_id": "ev-charging"
      },
      {
        "seeds": [
          "truck route planner",
          "freight class calculator",
          "truck load calculator",
          "dot number lookup"
        ],
        "theme_id": "trucking"
      },
      {
        "seeds": [
          "shipping cost calculator",
          "dimensional weight calculator",
          "freight quote calculator",
          "container size calculator"
        ],
        "theme_id": "shipping-freight"
      },
      {
        "seeds": [
          "import duty calculator",
          "hs code lookup",
          "customs duty calculator",
          "tariff code lookup"
        ],
        "theme_id": "customs-import"
      },
      {
        "seeds": [
          "business name lookup",
          "llc cost calculator",
          "business license lookup",
          "registered agent lookup"
        ],
        "theme_id": "business-registration"
      },
      {
        "seeds": [
          "sales tax calculator",
          "sales tax lookup",
          "nexus checker",
          "resale certificate lookup"
        ],
        "theme_id": "sales-tax"
      },
      {
        "seeds": [
          "payroll calculator",
          "paycheck calculator",
          "overtime calculator",
          "employer tax calculator"
        ],
        "theme_id": "payroll"
      },
      {
        "seeds": [
          "invoice calculator",
          "markup calculator",
          "profit margin calculator",
          "job cost calculator"
        ],
        "theme_id": "contractor-finance"
      },
      {
        "seeds": [
          "loan payment calculator",
          "interest calculator",
          "debt payoff calculator",
          "amortization calculator"
        ],
        "theme_id": "loans"
      },
      {
        "seeds": [
          "mortgage calculator",
          "closing cost calculator",
          "refinance calculator",
          "mortgage affordability calculator"
        ],
        "theme_id": "mortgage"
      },
      {
        "seeds": [
          "rent calculator",
          "rental yield calculator",
          "cap rate calculator",
          "security deposit calculator"
        ],
        "theme_id": "rent-real-estate"
      },
      {
        "seeds": [
          "insurance calculator",
          "coverage calculator",
          "insurance quote comparison",
          "deductible calculator"
        ],
        "theme_id": "insurance"
      },
      {
        "seeds": [
          "retirement calculator",
          "401k calculator",
          "pension calculator",
          "roth ira calculator"
        ],
        "theme_id": "retirement"
      },
      {
        "seeds": [
          "compound interest calculator",
          "investment return calculator",
          "dividend calculator",
          "capital gains calculator"
        ],
        "theme_id": "investing-math"
      },
      {
        "seeds": [
          "amazon fee calculator",
          "etsy fee calculator",
          "ebay fee calculator",
          "shopify fee calculator"
        ],
        "theme_id": "ecommerce-fees"
      },
      {
        "seeds": [
          "profit calculator for sellers",
          "break even calculator ecommerce",
          "shipping profit calculator",
          "product margin calculator"
        ],
        "theme_id": "marketplace-sellers"
      },
      {
        "seeds": [
          "roas calculator",
          "cpc calculator",
          "cpm calculator",
          "facebook ads cost calculator"
        ],
        "theme_id": "advertising"
      },
      {
        "seeds": [
          "keyword density checker",
          "redirect checker",
          "robots txt tester",
          "sitemap checker",
          "schema validator"
        ],
        "theme_id": "seo-utilities"
      },
      {
        "seeds": [
          "page size checker",
          "website speed test",
          "core web vitals checker",
          "ttfb checker"
        ],
        "theme_id": "website-performance"
      },
      {
        "seeds": [
          "domain age checker",
          "dns lookup",
          "mx lookup",
          "whois lookup",
          "ssl checker"
        ],
        "theme_id": "domain-dns"
      },
      {
        "seeds": [
          "email verifier",
          "spf checker",
          "dmarc checker",
          "email header analyzer",
          "email deliverability checker"
        ],
        "theme_id": "email-tools"
      },
      {
        "seeds": [
          "password strength checker",
          "hash checker",
          "ip reputation lookup",
          "port checker",
          "breach checker"
        ],
        "theme_id": "cybersecurity-utilities"
      },
      {
        "seeds": [
          "json formatter",
          "regex tester",
          "timestamp converter",
          "uuid generator",
          "base64 converter"
        ],
        "theme_id": "developer-utilities"
      },
      {
        "seeds": [
          "webhook tester",
          "api response checker",
          "jwt decoder",
          "http status checker",
          "curl converter"
        ],
        "theme_id": "api-utilities"
      },
      {
        "seeds": [
          "sql formatter",
          "sql query builder",
          "database size calculator",
          "connection string builder"
        ],
        "theme_id": "database-utilities"
      },
      {
        "seeds": [
          "aws cost calculator",
          "cloud cost calculator",
          "storage cost calculator",
          "bandwidth cost calculator"
        ],
        "theme_id": "cloud-costs"
      },
      {
        "seeds": [
          "pdf size reducer",
          "pdf page counter",
          "file checksum calculator",
          "document word counter"
        ],
        "theme_id": "files-documents"
      },
      {
        "seeds": [
          "image size calculator",
          "aspect ratio calculator",
          "dpi calculator",
          "image metadata viewer"
        ],
        "theme_id": "image-utilities"
      },
      {
        "seeds": [
          "video bitrate calculator",
          "video file size calculator",
          "recording time calculator",
          "video resolution calculator"
        ],
        "theme_id": "video-utilities"
      },
      {
        "seeds": [
          "audio bitrate calculator",
          "audio file size calculator",
          "bpm finder",
          "audio duration calculator"
        ],
        "theme_id": "audio-utilities"
      },
      {
        "seeds": [
          "paper size calculator",
          "print resolution calculator",
          "dpi to pixels calculator",
          "poster size calculator"
        ],
        "theme_id": "printing"
      },
      {
        "seeds": [
          "3d print time calculator",
          "filament calculator",
          "3d printer settings calculator",
          "stl file size checker"
        ],
        "theme_id": "3d-printing"
      },
      {
        "seeds": [
          "machining calculator",
          "cutting speed calculator",
          "feed rate calculator",
          "tolerance calculator"
        ],
        "theme_id": "manufacturing"
      },
      {
        "seeds": [
          "wire size calculator",
          "voltage drop calculator",
          "amp calculator",
          "breaker size calculator"
        ],
        "theme_id": "electrical"
      },
      {
        "seeds": [
          "pipe size calculator",
          "water flow calculator",
          "pipe volume calculator",
          "water pressure calculator"
        ],
        "theme_id": "plumbing"
      },
      {
        "seeds": [
          "construction cost calculator",
          "material calculator",
          "labor cost calculator",
          "square footage calculator"
        ],
        "theme_id": "construction-estimating"
      },
      {
        "seeds": [
          "salary calculator",
          "hourly to salary calculator",
          "pto calculator",
          "severance calculator"
        ],
        "theme_id": "hr-employment"
      },
      {
        "seeds": [
          "time zone converter",
          "work hours calculator",
          "business days calculator",
          "date duration calculator"
        ],
        "theme_id": "scheduling-time"
      },
      {
        "seeds": [
          "gpa calculator",
          "grade calculator",
          "salary comparison",
          "career salary calculator"
        ],
        "theme_id": "education-career"
      },
      {
        "seeds": [
          "mileage calculator",
          "fuel cost calculator",
          "trip cost calculator",
          "travel time calculator"
        ],
        "theme_id": "travel-planning"
      },
      {
        "seeds": [
          "food cost calculator",
          "recipe cost calculator",
          "menu price calculator",
          "portion calculator"
        ],
        "theme_id": "food-business"
      },
      {
        "seeds": [
          "reorder point calculator",
          "inventory turnover calculator",
          "warehouse space calculator",
          "pallet calculator"
        ],
        "theme_id": "inventory-warehousing"
      },
      {
        "seeds": [
          "box size calculator",
          "pallet loading calculator",
          "packaging cost calculator",
          "carton calculator"
        ],
        "theme_id": "logistics-packaging"
      },
      {
        "seeds": [
          "data usage calculator",
          "internet speed calculator",
          "bandwidth calculator",
          "phone number lookup"
        ],
        "theme_id": "telecom"
      },
      {
        "seeds": [
          "youtube money calculator",
          "tiktok money calculator",
          "sponsorship rate calculator",
          "creator rate calculator"
        ],
        "theme_id": "creator-economy"
      },
      {
        "seeds": [
          "mrr calculator",
          "churn calculator",
          "ltv calculator",
          "cac calculator",
          "saas valuation calculator"
        ],
        "theme_id": "saas-metrics"
      },
      {
        "seeds": [
          "freelance rate calculator",
          "hourly rate calculator",
          "project cost calculator",
          "agency profit margin calculator"
        ],
        "theme_id": "agency-freelance"
      },
      {
        "seeds": [
          "statute of limitations lookup",
          "court record lookup",
          "filing fee calculator",
          "small claims limit lookup"
        ],
        "theme_id": "legal-admin"
      },
      {
        "seeds": [
          "license lookup",
          "certification lookup",
          "renewal requirements",
          "continuing education requirements"
        ],
        "theme_id": "licensing-certification"
      },
      {
        "seeds": [
          "osha recordable calculator",
          "safety data sheet lookup",
          "compliance checklist",
          "inspection checklist"
        ],
        "theme_id": "compliance-safety"
      }
    ]
  },
  "purpose": "Exact durable seed identity for anti-repeat. Future runs MUST compare against this snapshot and only process new/delta themes or materially changed theses.",
  "snapshot_version": 1
}
```
<!-- /SEMRUSH_EXACT_SEED_SNAPSHOT_20260921 -->

<!-- SEMRUSH_DELTA_R2_R3_TERMINAL_20260921 -->
## Delta-only continuation R2 + R3 — TERMINAL — 2026-09-21

Anti-repeat authority extension. These were queried only after dedupe against the prior 680 literal seed entries.

- R2: 12 new themes / 48 new seeds; bank SHA `e54148467ee0bab0068b1d681e946ff823e980664ee391d351a43b05a9a2f126`; RPC 48/48, 0 errors; canonical demand gate 0 PASS; terminal DROP all.
- R3: 10 new themes / 40 new seeds; bank SHA `c2443d7eb784806fbe7fdc73bd35d4d502ae20191d64d0e3a78100cf894481e1`; RPC 40/40, 0 errors; demand gate PASS: pool-spa, aquarium, generator-sizing, forestry extension.
- R3 downstream terminal: 0 PASS_CANDIDATE. Pool/aquarium/generator/forestry all DROP after current exact-product/SERP competitor review due dense exact-tool competition; generator additionally has major-brand Generac sizing tooling; small forestry residual tails do not rescue the thesis.
- Terminal verdict artifact SHA: `00eef881a05012c2e9ccdc576d3277d83374903fadf2f9007718d475d2a48a5b`.

### HARD no-repeat update

Prior canonical snapshot = 680 literal seed entries. R2 + R3 add 88 verified-new literal seed entries. Canonical coverage is now **768 literal seed entries**.

```text
same theme/thesis + any seed contained in ORIGINAL_SNAPSHOT or DELTA_R2 or DELTA_R3
→ NEVER query that seed again
→ only genuinely new seed strings / new theme identities / materially changed thesis may be queried
```

### DELTA_R2 exact seed snapshot
```json
{
  "version": 1,
  "created": "2026-09-21",
  "database": "us",
  "purpose": "Delta-only Semrush Research batch after 680-seed anti-repeat lock. All themes and seeds deduped against prior 61 fresh themes + 106 Dropbox themes.",
  "themes": [
    {
      "theme_id": "agriculture-crop-math",
      "label": "Crop / Seed / Yield Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "seed rate calculator",
        "plant population calculator",
        "crop yield calculator",
        "fertilizer rate calculator"
      ]
    },
    {
      "theme_id": "agriculture-irrigation",
      "label": "Agricultural Irrigation Planning",
      "search_channel_fit": "primary",
      "seeds": [
        "irrigation calculator",
        "drip irrigation calculator",
        "irrigation scheduling calculator",
        "evapotranspiration calculator"
      ]
    },
    {
      "theme_id": "livestock-feed-math",
      "label": "Livestock Feed / Ration Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "cattle feed calculator",
        "feed ration calculator",
        "feed conversion ratio calculator",
        "hay calculator cattle"
      ]
    },
    {
      "theme_id": "forestry-timber-math",
      "label": "Forestry / Timber Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "board foot calculator",
        "tree volume calculator",
        "timber value calculator",
        "log weight calculator"
      ]
    },
    {
      "theme_id": "marine-boating-math",
      "label": "Marine / Boating Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "boat prop calculator",
        "boat fuel consumption calculator",
        "hull speed calculator",
        "boat trailer weight calculator"
      ]
    },
    {
      "theme_id": "commercial-cleaning-estimating",
      "label": "Commercial Cleaning Estimating",
      "search_channel_fit": "primary",
      "seeds": [
        "commercial cleaning calculator",
        "janitorial bid calculator",
        "cleaning estimate calculator",
        "office cleaning cost calculator"
      ]
    },
    {
      "theme_id": "water-well-septic",
      "label": "Well / Septic Sizing and Planning",
      "search_channel_fit": "primary",
      "seeds": [
        "septic tank size calculator",
        "septic drain field size calculator",
        "well yield calculator",
        "septic system cost calculator"
      ]
    },
    {
      "theme_id": "event-venue-planning",
      "label": "Event / Venue Planning Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "event capacity calculator",
        "table seating calculator",
        "venue size calculator",
        "catering quantity calculator"
      ]
    },
    {
      "theme_id": "packaging-epr-compliance",
      "label": "US Packaging EPR Compliance",
      "search_channel_fit": "primary",
      "seeds": [
        "epr compliance packaging",
        "packaging epr calculator",
        "extended producer responsibility packaging",
        "epr fees calculator"
      ]
    },
    {
      "theme_id": "building-energy-compliance",
      "label": "Building Energy Benchmarking / Performance Compliance",
      "search_channel_fit": "primary",
      "seeds": [
        "building energy benchmarking",
        "energy benchmarking compliance",
        "building performance standards",
        "building emissions compliance"
      ]
    },
    {
      "theme_id": "food-label-compliance-us",
      "label": "US Food Label / Allergen Compliance",
      "search_channel_fit": "primary",
      "seeds": [
        "food label compliance checker",
        "allergen label checker",
        "food labeling requirements",
        "nutrition label compliance"
      ]
    },
    {
      "theme_id": "battery-passport-eu",
      "label": "EU Battery Passport Compliance",
      "search_channel_fit": "primary",
      "seeds": [
        "battery passport",
        "battery passport software",
        "eu battery passport",
        "battery passport requirements"
      ]
    }
  ]
}
```

### DELTA_R3 exact seed snapshot
```json
{
  "version": 1,
  "created": "2026-09-21",
  "database": "us",
  "purpose": "Delta-only batch r3. New seeds only; extension themes explicitly do not rerun prior seeds.",
  "themes": [
    {
      "theme_id": "forestry-timber-extension",
      "label": "Forestry/Timber expansion — new seeds only",
      "search_channel_fit": "primary",
      "delta_extension_of": "forestry-timber-math",
      "seeds": [
        "lumber calculator",
        "wood weight calculator",
        "lumber weight calculator",
        "timber calculator"
      ]
    },
    {
      "theme_id": "commercial-cleaning-extension",
      "label": "Commercial cleaning expansion — new seeds only",
      "search_channel_fit": "primary",
      "delta_extension_of": "commercial-cleaning-estimating",
      "seeds": [
        "commercial cleaning rates",
        "janitorial pricing calculator",
        "cleaning rate calculator",
        "janitorial cost per square foot"
      ]
    },
    {
      "theme_id": "payment-processing-fees",
      "label": "Payment Processor Fee Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "paypal fee calculator",
        "stripe fee calculator",
        "square fee calculator",
        "payment processing fee calculator"
      ]
    },
    {
      "theme_id": "pool-spa-calculators",
      "label": "Pool / Spa Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "pool volume calculator",
        "pool gallons calculator",
        "pool chemical calculator",
        "pool pump size calculator"
      ]
    },
    {
      "theme_id": "aquarium-calculators",
      "label": "Aquarium / Fish Tank Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "aquarium volume calculator",
        "fish tank volume calculator",
        "aquarium stocking calculator",
        "aquarium co2 calculator"
      ]
    },
    {
      "theme_id": "generator-sizing",
      "label": "Generator Sizing Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "generator size calculator",
        "generator wattage calculator",
        "backup generator calculator",
        "whole house generator size calculator"
      ]
    },
    {
      "theme_id": "welding-fabrication-math",
      "label": "Welding / Fabrication Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "welding calculator",
        "weld size calculator",
        "welding heat input calculator",
        "wire feed speed calculator"
      ]
    },
    {
      "theme_id": "woodworking-cut-planning",
      "label": "Woodworking Cut Planning / Optimization",
      "search_channel_fit": "primary",
      "seeds": [
        "cut list optimizer",
        "plywood cut calculator",
        "sheet cut optimizer",
        "wood cut list calculator"
      ]
    },
    {
      "theme_id": "water-softener-sizing",
      "label": "Water Softener Sizing / Hardness Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "water softener size calculator",
        "water softener grain calculator",
        "water hardness calculator",
        "water softener salt usage calculator"
      ]
    },
    {
      "theme_id": "fleet-tco-math",
      "label": "Fleet TCO / Cost-per-Mile Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "fleet cost calculator",
        "vehicle tco calculator",
        "cost per mile calculator fleet",
        "fleet fuel cost calculator"
      ]
    }
  ]
}
```

### R2/R3 terminal machine state
```json
{
  "created_at": "2026-09-21T06:37:34Z",
  "lane": "semrush-demand-first-delta-only",
  "r2": {
    "bank": "/var/lib/semrush-research/config/delta-bank-2026-09-21-r2.json",
    "bank_sha256": "e54148467ee0bab0068b1d681e946ff823e980664ee391d351a43b05a9a2f126",
    "themes": 12,
    "seeds": 48,
    "rpc_errors": 0,
    "demand_pass": [],
    "terminal": "DROP_ALL_AT_DEMAND_GATE",
    "reason": "0/12 projects satisfy canonical aggregate demand gate; no SERP-DD warranted."
  },
  "r3": {
    "bank": "/var/lib/semrush-research/config/delta-bank-2026-09-21-r3.json",
    "bank_sha256": "c2443d7eb784806fbe7fdc73bd35d4d502ae20191d64d0e3a78100cf894481e1",
    "themes": 10,
    "seeds": 40,
    "rpc_errors": 0,
    "demand_pass": [
      "aquarium-calculators",
      "forestry-timber-extension",
      "generator-sizing",
      "pool-spa-calculators"
    ],
    "serp_runtime_note": "Live SERP script was not forced through guardian while noxtools-main was profile-busy; fresh public web competitor evidence was used to terminalize the four numerical survivors.",
    "project_verdicts": [
      {
        "project": "pool-spa-calculators",
        "terminal": "DROP_SERP_SATURATED",
        "reason": "Dense exact pool-volume/chemical/pump calculator field plus broad calculator suites and major-brand tooling (e.g. Pentair). Low KD does not imply greenfield."
      },
      {
        "project": "aquarium-calculators",
        "terminal": "DROP_SERP_SATURATED",
        "reason": "Multiple exact aquarium volume + stocking calculators and multi-calculator suites; dedicated 2026 entrants indicate active exact-tool competition."
      },
      {
        "project": "generator-sizing",
        "terminal": "DROP_SERP_SATURATED_BRAND",
        "reason": "Many exact generator sizing/wattage calculators plus Generac official whole-home sizing/solution finder."
      },
      {
        "project": "forestry-timber-extension",
        "terminal": "DROP_SERP_SATURATED_LOW_VALUE_TAIL",
        "reason": "Board-foot/lumber-weight SERPs already contain many exact calculators; residual timber-value/beam/frame subclusters are too small to rescue standalone thesis."
      }
    ],
    "terminal": "DROP_ALL_AFTER_SERP_COMPETITOR_DD",
    "pass_candidate_count": 0
  },
  "anti_repeat": {
    "r2": "Do not rerun these 48 seeds unless the thesis materially changes.",
    "r3": "Do not rerun these 40 seeds unless the thesis materially changes.",
    "combined_new_seed_entries": 88,
    "next": "Generate only genuinely new delta themes/seeds; exact-product gate early when obvious."
  }
}
```

<!-- SEMRUSH_DELTA_R4_TERMINAL_20260921 -->
## Delta-only R4 — TERMINAL — 2026-09-21

- 12 new themes / 48 verified-new seeds; bank SHA `2ea022ec7bc62bc7a793368c225c7328e571d036fe83f29128f294c266a42852`.
- RPC 48/48, 0 errors.
- Canonical demand gate: only `brewing-fermentation-math` passed; 11/12 dropped before SERP DD.
- Brewing terminal: `DROP_SERP_SATURATED` after current exact-product review (many ABV, priming sugar, and multi-tool homebrew calculators).
- PASS_CANDIDATE: 0.
- Terminal artifact SHA `53f3cdc2bb7b56ca6d1937108c62cf5e04c73c0503354e2eb9508da5b7f3df10`.

### HARD no-repeat update
Prior authority 768 literal seed entries + R4 48 = **816 literal seed entries**. Never rerun any R4 seed on unchanged thesis.

### DELTA_R4 exact seed snapshot
```json
{
  "version": 1,
  "created": "2026-09-21",
  "database": "us",
  "purpose": "Delta-only batch R4 after 768-seed lock; all literal seeds deduped against original + R2 + R3.",
  "themes": [
    {
      "theme_id": "commercial-lease-math",
      "label": "Commercial Lease / CAM Math",
      "search_channel_fit": "primary",
      "seeds": [
        "nnn lease calculator",
        "cam charges calculator",
        "rent escalation calculator commercial lease",
        "commercial lease commission calculator"
      ]
    },
    {
      "theme_id": "construction-retainage",
      "label": "Construction Retainage / Pay App Math",
      "search_channel_fit": "primary",
      "seeds": [
        "retainage calculator",
        "construction retention calculator",
        "subcontractor retainage calculator",
        "pay application retainage calculator"
      ]
    },
    {
      "theme_id": "building-egress-occupancy",
      "label": "Occupant Load / Egress Planning",
      "search_channel_fit": "primary",
      "seeds": [
        "occupant load calculator",
        "egress width calculator",
        "exit capacity calculator",
        "means of egress calculator"
      ]
    },
    {
      "theme_id": "parking-planning-math",
      "label": "Parking Ratio / Capacity Planning",
      "search_channel_fit": "primary",
      "seeds": [
        "parking ratio calculator",
        "parking requirement calculator",
        "parking spaces calculator",
        "parking lot capacity calculator"
      ]
    },
    {
      "theme_id": "restaurant-tip-labor-math",
      "label": "Restaurant Tip / Labor Math",
      "search_channel_fit": "primary",
      "seeds": [
        "tip pool calculator",
        "tip out calculator",
        "restaurant labor cost calculator",
        "labor cost percentage calculator restaurant"
      ]
    },
    {
      "theme_id": "salon-business-math",
      "label": "Salon Pricing / Commission Math",
      "search_channel_fit": "primary",
      "seeds": [
        "salon pricing calculator",
        "salon commission calculator",
        "salon profit calculator",
        "booth rent calculator salon"
      ]
    },
    {
      "theme_id": "plumbing-commercial-extension",
      "label": "Commercial Plumbing Sizing Extension",
      "search_channel_fit": "primary",
      "delta_extension_of": "plumbing",
      "seeds": [
        "grease interceptor sizing calculator",
        "water heater recovery calculator",
        "expansion tank sizing calculator",
        "fixture unit calculator"
      ]
    },
    {
      "theme_id": "hvac-airflow-extension",
      "label": "HVAC Airflow / Duct Extension",
      "search_channel_fit": "primary",
      "delta_extension_of": "hvac",
      "seeds": [
        "duct size calculator",
        "hvac cfm calculator",
        "return air grille size calculator",
        "static pressure calculator hvac"
      ]
    },
    {
      "theme_id": "fencing-pasture-math",
      "label": "Farm Fencing / Pasture Planning",
      "search_channel_fit": "primary",
      "seeds": [
        "fence post calculator",
        "pasture stocking rate calculator",
        "grazing calculator",
        "electric fence calculator"
      ]
    },
    {
      "theme_id": "greenhouse-growing-math",
      "label": "Greenhouse / Horticulture Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "greenhouse size calculator",
        "grow light calculator",
        "plant spacing calculator",
        "greenhouse heating calculator"
      ]
    },
    {
      "theme_id": "brewing-fermentation-math",
      "label": "Brewing / Fermentation Calculators",
      "search_channel_fit": "primary",
      "seeds": [
        "abv calculator",
        "priming sugar calculator",
        "brewing water calculator",
        "specific gravity calculator beer"
      ]
    },
    {
      "theme_id": "sign-vinyl-print-math",
      "label": "Sign / Vinyl / Large-format Math",
      "search_channel_fit": "primary",
      "seeds": [
        "vinyl roll calculator",
        "banner size calculator",
        "sign pricing calculator",
        "vinyl lettering size calculator"
      ]
    }
  ]
}
```

### R4 terminal machine state
```json
{
  "created_at": "2026-09-21T06:46:38Z",
  "bank": "/var/lib/semrush-research/config/delta-bank-2026-09-21-r4.json",
  "bank_sha256": "2ea022ec7bc62bc7a793368c225c7328e571d036fe83f29128f294c266a42852",
  "themes": 12,
  "seeds": 48,
  "rpc_errors": 0,
  "demand_pass": [
    "brewing-fermentation-math"
  ],
  "demand_drop_count": 11,
  "survivor_verdicts": [
    {
      "project": "brewing-fermentation-math",
      "terminal": "DROP_SERP_SATURATED",
      "reason": "ABV/priming-sugar/homebrew calculator intent is crowded by dedicated calculators, brewing publishers, and multi-tool homebrew suites; no greenfield exact-tool gap."
    }
  ],
  "terminal": "DROP_ALL",
  "pass_candidate_count": 0,
  "anti_repeat": "All 48 R4 seeds are complete; never rerun on unchanged thesis. Only new literal seeds/new themes may be queried."
}
```

<!-- SEMRUSH_NOX_SESSION_SWITCH_20260921_SERVER1 -->
## Runtime session switch — 2026-09-21
- NoxTools login restored on `noxtools-main`.
- Semrush active server switched from **Server 6** to **Server 1** via `https://semrush.noxtools.com/server1.php`.
- Browser landed on `https://1.semrush.com.in/...`; browser-side `keywords.GetInfo` RPC returned HTTP 200 with a valid result.
- Direct unauthenticated HTTP to Server 1 still returns `Session expired, access again from Dashboard`; therefore R5 retry must use the authenticated browser session / page fetch, not the old direct-HTTP collector.
- R5 remains **6 successful / 42 pending rate-limited seeds**. The 42 pending seeds are NOT checked and must be resumed only after this session switch; all previously completed seeds remain hard-skip.
- Anti-repeat invariant remains unchanged: never rerun completed seed/preflight/universe work on unchanged theme + seed + thesis.

<!-- SEMRUSH_DELTA_R5_R6_20260921 -->
## Delta terminal update — R5 + R6 — 2026-09-21

### R5 — terminal / HARD SKIP

- bank: `/var/lib/semrush-research/config/delta-bank-2026-09-21-r5.json`
- bank SHA256: `ab13848e7355f5711693040fb0b001f5e45faf36de958e0dfb2819f0bf8e2980`
- 12 themes / 48 seeds.
- Initial Server 6 direct-RPC pass produced 6 good + 42 `-2002 Rate limit reached`; that `COMPLETE` state was stale and must not be reused.
- Corrective collection retried **only those 42 failed seeds** via authenticated browser RPC on `1.semrush.com.in`; 42/42 recovered, final errors=0. The original 6 good seeds were not queried again.
- corrected demand-universe SHA256: `bf4e126d2fcd4f02242b7b30826f594bfde289b82caeeb76579c8d5ec05adb28`.
- demand gate PASS projects: `cycling-fit-gearing`, `sewing-fabric-yardage`, `speaker-enclosure-math`.
- 7 clusters reached SERP DD: mechanical = 4 `DROP_SERP_SATURATED` + 3 `WATCH_COMPETITION`.
- terminal review: **7/7 DROP; PASS_CANDIDATE=0**.
- WATCH terminal reasons:
  - `speaker-enclosure-math-001` → `DROP_EXACT_TOOL_INCUMBENTS`;
  - `cycling-fit-gearing-002` → `DROP_LOW_SCALE_INCUMBENTS`;
  - `cycling-fit-gearing-005` → `DROP_TINY_SCALE_OFFICIAL_INCUMBENTS`.
- terminal verdict SHA256: `d69856b897dc94aab1e217eae84cb6d935fe29523e6b62a4cddb38528f85781e`.
- HARD SKIP: unchanged R5 bank/thesis → do not rerun seed collection, demand gate, or SERP DD.

### R6 — terminal / HARD SKIP

- bank: `/var/lib/semrush-research/config/delta-bank-2026-09-21-r6.json`
- bank SHA256: `941aad743821dfa6d66e2383a3ad31ee2b656c486343369737968faa01296be7`.
- 12 genuinely new themes / 46 seeds after exact dedupe against prior local banks; two proposed duplicate seeds were excluded before querying.
- collection: authenticated browser RPC on `1.semrush.com.in`; `UNIVERSE_READY`, 46/46 seed preflight + 46/46 ideas.
- universe SHA256: `7b122d3e51cfd81734330cd2f9991b82d422dcf637b9cf913ca5498583c2ec10`.
- demand gate: only `soap-making-math` passed; 1 cluster queued.
- SERP DD: 1/1 `DROP_SERP_SATURATED`.
- terminal review: **1/1 DROP; PASS_CANDIDATE=0**.
- terminal verdict SHA256: `98bc5a75d6c89898e7f3c961dc29ecee596355fe149841e3fadf88c092739b2d`.
- HARD SKIP: unchanged R6 bank/thesis → do not rerun any completed stage.

### R6 exact seed snapshot

```json
{
  "version": 1,
  "database": "us",
  "created_at": "2026-09-21T07:27:00Z",
  "scope": "fresh delta only; exact-deduped against all local prior seed banks",
  "themes": [
    {
      "theme_id": "metal-weight-calculators",
      "label": "Metal Weight Calculators",
      "search_channel_fit": "keyword-first standalone calculator/tool thesis",
      "seeds": [
        "metal weight calculator",
        "steel weight calculator",
        "steel plate weight calculator",
        "pipe weight calculator"
      ]
    },
    {
      "theme_id": "machining-feeds-speeds",
      "label": "Machining Feeds Speeds",
      "search_channel_fit": "keyword-first standalone calculator/tool thesis",
      "seeds": [
        "feeds and speeds calculator",
        "chip load calculator",
        "machining rpm calculator"
      ]
    },
    {
      "theme_id": "compressed-air-engineering",
      "label": "Compressed Air Engineering",
      "search_channel_fit": "keyword-first standalone calculator/tool thesis",
      "seeds": [
        "air compressor size calculator",
        "compressed air cfm calculator",
        "compressed air pressure drop calculator",
        "air consumption calculator"
      ]
    },
    {
      "theme_id": "pump-hydraulic-sizing",
      "label": "Pump Hydraulic Sizing",
      "search_channel_fit": "keyword-first standalone calculator/tool thesis",
      "seeds": [
        "pump head calculator",
        "pump sizing calculator",
        "npsh calculator",
        "pump flow rate calculator"
      ]
    },
    {
      "theme_id": "rv-towing-payload",
      "label": "Rv Towing Payload",
      "search_channel_fit": "keyword-first standalone calculator/tool thesis",
      "seeds": [
        "towing capacity calculator",
        "truck payload calculator",
        "tongue weight calculator",
        "rv weight calculator"
      ]
    },
    {
      "theme_id": "telescope-optics",
      "label": "Telescope Optics",
      "search_channel_fit": "keyword-first standalone calculator/tool thesis",
      "seeds": [
        "telescope magnification calculator",
        "telescope field of view calculator",
        "eyepiece calculator",
        "telescope focal length calculator"
      ]
    },
    {
      "theme_id": "scuba-dive-planning",
      "label": "Scuba Dive Planning",
      "search_channel_fit": "keyword-first standalone calculator/tool thesis",
      "seeds": [
        "nitrox calculator",
        "scuba gas calculator",
        "sac rate calculator",
        "dive planning calculator"
      ]
    },
    {
      "theme_id": "archery-arrow-tuning",
      "label": "Archery Arrow Tuning",
      "search_channel_fit": "keyword-first standalone calculator/tool thesis",
      "seeds": [
        "arrow spine calculator",
        "arrow weight calculator",
        "archery kinetic energy calculator",
        "arrow foc calculator"
      ]
    },
    {
      "theme_id": "candle-making-math",
      "label": "Candle Making Math",
      "search_channel_fit": "keyword-first standalone calculator/tool thesis",
      "seeds": [
        "candle wax calculator",
        "fragrance load calculator",
        "candle cost calculator",
        "wick size calculator"
      ]
    },
    {
      "theme_id": "soap-making-math",
      "label": "Soap Making Math",
      "search_channel_fit": "keyword-first standalone calculator/tool thesis",
      "seeds": [
        "lye calculator",
        "soap calculator",
        "soap fragrance calculator",
        "soap batch calculator"
      ]
    },
    {
      "theme_id": "epoxy-resin-math",
      "label": "Epoxy Resin Math",
      "search_channel_fit": "keyword-first standalone calculator/tool thesis",
      "seeds": [
        "resin calculator",
        "epoxy volume calculator",
        "resin mix ratio calculator"
      ]
    },
    {
      "theme_id": "water-treatment-engineering",
      "label": "Water Treatment Engineering",
      "search_channel_fit": "keyword-first standalone calculator/tool thesis",
      "seeds": [
        "chemical dosage calculator water treatment",
        "chlorine contact time calculator",
        "filter loading rate calculator",
        "water treatment flow calculator"
      ]
    }
  ]
}
```

### Current continuation contract

- R5 and R6 are terminal and must not be rerun.
- Continue only with genuinely new/delta themes after checking against all embedded seed snapshots.
- NoxTools runtime: Server 1 browser-authenticated RPC is known-good. Direct HTTP to Server 1 without browser session returns `Session expired, access again from Dashboard` and must not be treated as demand=0.
- Current overall delta result through R6: no new `PASS_CANDIDATE`.
<!-- /SEMRUSH_DELTA_R5_R6_20260921 -->

<!-- SEMRUSH_IDEA_SCANNER_REVIEW_20261005 -->
## SEO idea scanner review / terminal reconciliation — 2026-10-05

Current authority:
- This lane is `Semrush Research`, not `SeoTrends Public Daily Scanner`.
- Full Dropbox idea coverage from 2026-09-21 remains terminal: 106 themes / 427 seeds, 427/427 complete, 0 pending, 0 errors.
- HARD anti-repeat remains authoritative: do not rerun completed full/R2-R8 theme identities unless the thesis or source identity materially changes.

R7 terminal:
- run: `/var/lib/semrush-research/runs/delta-2026-09-30-r7/`
- 12 themes / 48 seeds; broker collection 48/48 complete.
- post-process: 683 dedup keyword rows, 12 projects, 0 demand-gate PASS, 0 SERP queue.
- canonical terminal state is now `COMPLETE_NO_PASS`; do not treat the old `SERP_DD_PENDING` state as live.

R8 commercial terminal:
- configured bank: 20 themes / 80 seeds.
- stale 2026-09-30 `BLOCKED_RATE_LIMIT` state was resumed on 2026-10-05 through the single-owner broker; 80/80 seed preflight and related-keyword universe completed.
- 18 projects with normalized related-keyword rows entered demand post-processing.
- result: 0 demand-gate PASS, 0 SERP queue.
- canonical terminal state: `COMPLETE_NO_PASS`.
- hosted-pool canary on the same R8 universe returned `COMPLETE_NO_PASS` end-to-end.

State-machine repair:
- queue_count > 0 => `SERP_DD_PENDING`.
- queue_count == 0 => `COMPLETE_NO_PASS`.
- `COMPLETE_NO_PASS` is terminal and participates in RESUME_NO_BACKTRACK.
- vps-control regression suite `tests/test_semrush_niche_pool.py`: 3/3 PASS after the repair.
- source updates: vps-control through commit `5544698dc444df4817423a0f162457c8ab4615d0`; runner-3 Semrush helper updates through `d0254db63614065b29341c8d6e6969b6bdfef144`.

Runtime routing:
- authenticated Semrush acquisition remains broker-only through `/run/semrush-rpc-broker/control.sock`.
- `semrush-rpc-broker.service` verified active + enabled during this review.
- legacy runtime `dropbox_idea_scan_rpc.py` direct HTTP/RPC execution is fail-closed; pure helper imports such as `aggregate` / `sha` remain available for historical rebuild compatibility.
- current production acquisition command is `live_collect.py` through the broker; stateless demand/clustering may continue through `pool_postprocess.py`.

Scheduling:
- Semrush Research / SEO idea scanner is currently delta/on-demand, not a daily scheduled scanner.
- no Semrush Research cron/systemd scheduler was found during the 2026-10-05 review.
- SeoTrends daily scheduling remains a separate lane and must not be conflated with this scanner.

Exact resume rule:
- full baseline, R7 and R8 are terminal; do not rerun them.
- next scan starts only from genuinely new/delta themes or materially changed theses after anti-repeat reconciliation.
- a zero-survivor batch is a valid successful terminal result and must not remain falsely pending.
<!-- /SEMRUSH_IDEA_SCANNER_REVIEW_20261005 -->

<!-- SEMRUSH_SINGLE_OWNER_BROKER_20260930 -->
## Authenticated runtime broker migration — TERMINAL — 2026-09-30

### Runtime authority

- Authenticated Semrush/NoxTools I/O is now single-owner through `/run/semrush-rpc-broker/control.sock` on the VPS.
- Broker implementation authority: `louisalviss/vps-control:stack/semrush_rpc_broker.py`.
- `noxtools-main` remains the persistent authenticated profile. Cookies, API key and session material remain host-side and are never returned to workers.
- Broker owns Guardian/CDP, launches the profile on demand, warm-reuses it, and tears it down after 20 seconds idle.
- Allowed keyword/SERP methods are bounded; DPA is separately allowlisted by the broker. No arbitrary browser execution is exposed.

### Job placement / source authority

- `live_collect.py`, `serp_dd_live.py`, and `r5_retry_browser.py` are broker-only callers; they must not acquire `noxtools-main` or attach CDP directly.
- Research-job source authority is `louisalviss/runner-3:jobs/semrush-research/`.
- `live_collect.py` source writeback commit: `21ef954da4155c5de63e9d27064dee70f6d6fa02`.
- `serp_dd_live.py` source writeback commit: `56208ecdd7d5702cbc514352b0057e465d10a8f3`.
- `r5_retry_browser.py` source writeback commit: `e2a9e1f5d3cd7e2ac8b3112c1c23e4e55207c651`.
- Broker/Guardian authority remains in `vps-control`; do not duplicate broker implementation into `runner-3`.
- Login/recovery may use the dedicated login lane when required; normal research paths must use the broker.

### Guardian / contention fix

- Guardian no longer treats a stale manager `CDP connected` log as indefinitely busy.
- Runtime truth is reconciled per managed profile by resolving that profile Chromium `--remote-debugging-port` and checking ESTABLISHED sockets to that exact port inside `cloak-manager`.
- Exact-profile live socket => busy; stale log with no exact-profile socket => reusable; unknown truth => fail closed.
- Current `vps-control` source commit: `e5e1c9c0862ed7212b2a625e914360ca4a6eb1b9` (`fix(guardian): reconcile stale CDP per profile`).
- Current-main Guardian regression: 41/41 tests PASS.

### Acceptance proof

- Real one-seed run: `/var/lib/semrush-research/runs/broker-accept-20260930-1349`.
- Result: `UNIVERSE_READY`, transport `semrush-rpc-broker-v1`, shard `6.semrush.com.in`, `seed_done=1`, `ideas_done=1`, approximately 3 seconds wall time.
- Idle acceptance after 25 seconds: broker `IDLE`, `noxtools-main` `stopped`, Semrush Guardian leases empty.
- SERP transport can return a successful envelope with zero usable organic rows. Such incomplete evidence is now fail-closed as `BLOCKED_INCOMPLETE_SERP`; empty SERP data must never imply weak competition or `SERP_DD_PASS`.

### Hosted-pool boundary

- Authenticated acquisition stays on VPS broker because it depends on persistent NoxTools session/profile state.
- Stateless downstream work (demand gate, clustering, scoring, result processing) may be offloaded to the GitHub hosted pool only through a narrow allowlisted worker capability with source/input/output hashes.
- `vps-code-swarm` is coding-only and is not a research execution path.

### Resume rule

- Do not reintroduce per-job direct CDP ownership for Semrush.
- Do not rerun completed broad/R5/R6 universes. Continue only with genuinely new delta themes and the canonical anti-repeat snapshots.
<!-- /SEMRUSH_SINGLE_OWNER_BROKER_20260930 -->


<!-- SEMRUSH_POOL_POSTPROCESS_20260930 -->
## Hosted pool post-processing — 2026-09-30

Runtime placement is now split by statefulness:
- authenticated Semrush/NoxTools collection and live SERP RPC remain on VPS through `semrush-rpc-broker.service`;
- deterministic demand gate + normalization + clustering run as allowlisted task `data-pipeline-stateless:niche-research-postprocess` on GitHub-hosted acc2–acc5;
- input transport is immutable Runner3 Core artifact `semrush-research/pool-input/*.json` bound by SHA256; no browser/session material leaves VPS;
- worker task is fail-closed: fixed `semrush_demand_first.py`, numeric config allowlist/ranges, 64 MiB input cap, exact artifact SHA, terminal stage must be `SERP_DD_PENDING`;
- stable pooled source hash after narrowing bundle authority: `d1288179d23ae189568bb0f7dbe99cfe740c5fbde4df81d45394f25d193ffe0a` on acc2–acc5; unrelated `stack/tests/jobs` changes no longer rotate this flow hash;
- production handoff helper source: `louisalviss/runner-3@7154436090be24e8f9cdcb1f2bc55403397f0b98/jobs/semrush-research/pool_postprocess.py`; runtime: `/var/lib/semrush-research/scripts/pool_postprocess.py`;
- helper enforces anti-repeat: same input SHA + same config + verified `SERP_DD_PENDING` returns `RESUME_NO_BACKTRACK`; interrupted completed dispatch can materialize existing router proof instead of dispatching another hosted job.

Acceptance proofs:
- direct pooled task: GitHub run `36680519987`, job `niche-pool-canary-20260930-0651`, router proof OK;
- swarm E2E: GitHub run `36681333717`, job `niche-swarm-canary-20260930.demand`, router proof OK;
- both used synthetic input SHA `e2477abd24d6c7f1b1ca1292eb65e0ce557f53174798c384e02f35aaf58e7cc0`, produced one passing synthetic project and one SERP queue item; they did not query Semrush/NoxTools.

Swarm authority: `louisalviss/github-ops-guard@37aaf90f1c717e27e5a7edd74820b41e71c7b12b` supports bounded generic task payloads through `vps-actions-task-submit`; normal ingress remains unchanged.
<!-- /SEMRUSH_POOL_POSTPROCESS_20260930 -->


<!-- SEMRUSH_DETERMINISM_20260930 -->
## Deterministic hosted post-processing — 2026-09-30

- Heavy real-dataset acceptance: `fresh-2026-09-21/universe.json` (12,298,165 bytes) completed through the hosted pool with 17 demand-gate projects and 50 SERP-DD queue entries.
- Testing found a cluster-label tie could depend on Python hash seed. `demand_first.py` now uses an explicit lexical tie-break, so identical input/config produces byte-identical `project-gates.json`, `clusters.json`, `serp-dd-queue.json`, and `keywords-normalized.csv` across different hash seeds and hosted/local execution.
- Current `data-pipeline-stateless` source hash after the determinism fix: `d1288179d23ae189568bb0f7dbe99cfe740c5fbde4df81d45394f25d193ffe0a`.
- Hosted confirmation run: `36691284542`; router proof PASS.
<!-- /SEMRUSH_DETERMINISM_20260930 -->

<!-- SEMRUSH_POOL_FANOUT_20260930 -->
## Hosted pool fan-out acceptance — 2026-09-30

- Production `vps-actions-swarm` acceptance used four real Semrush `universe.json` datasets in one wave with `max_parallel=4`; all 4 tasks returned verified router proofs.
- Production routing completed the four tasks in 34.403s wall time. `highest_headroom` intentionally routed two jobs to acc2, one to acc4, one to acc5; acc3 was not selected because its remaining included minutes were lower. This is expected balancing behavior, not a fan-out failure.
- Separate lane-isolation acceptance forced one task to each acc2–acc5 concurrently without changing production routing. All four lanes passed; wall time was 28.751s.
- Per-lane results: acc2 27.989s / 0 queue; acc3 28.626s / 0 queue; acc4 22.602s / 1 queue; acc5 28.747s / 50 queue. All four router proofs were `ok=true`.
- Therefore hosted post-processing can run multiple niche datasets concurrently and every routable worker lane has executed the niche task successfully. Do not change `highest_headroom` merely to force one job per account; distinct-lane spreading is not required for current throughput.
- Current deterministic `data-pipeline-stateless` source hash used by acc2–acc5: `d1288179d23ae189568bb0f7dbe99cfe740c5fbde4df81d45394f25d193ffe0a`.
<!-- /SEMRUSH_POOL_FANOUT_20260930 -->

<!-- SEMRUSH_POOL_FANOUT8_20260930 -->
## Pool fan-out capacity benchmark — 2026-09-30

- 8 independent `data-pipeline-stateless:niche-research-postprocess` tasks ran with `max_parallel=8` using existing Semrush universe artifacts only; no Semrush/NoxTools RPC was performed.
- Terminal: 8/8 PASS, all router proofs valid, reservations returned empty.
- Wall time: 37.81 s. Prior 4-task production swarm: 34.40 s.
- Router distribution: acc2=3, acc4=2, acc5=3, acc3=0 under `highest_headroom`.
- Doubling workload from 4 to 8 tasks added only ~3.4 s. Existing lanes can run multiple hosted jobs concurrently, so account count is not the current post-processing speed bottleneck.
- More accounts currently add quota/headroom/failure isolation. Add accounts for speed only after observed GitHub queue/concurrency limits on existing lanes or after raising swarm parallelism beyond the current `MAX_PARALLEL=8` ceiling.
<!-- /SEMRUSH_POOL_FANOUT8_20260930 -->

<!-- SEMRUSH_ACQUISITION_BENCH_20260930 -->
## Semrush acquisition benchmark — 2026-09-30

- Production-pattern benchmark used the single-owner VPS broker with batch size 4 seeds: preflight issues `keywords.GetInfo` + `ideas.GetKeywordsSummary` in parallel, then `ideas.GetKeywords` in a second pass.
- 100-seed run: 112.497 s total on `5.semrush.com.in`; 300 RPC calls; 0 errors; 0 rate-limit responses. Breakdown: session ensure 9.868 s, preflight 65.597 s / 200 RPC, ideas 37.029 s / 100 RPC.
- 500-seed run used 500 different seeds (offset after the first 100) and stopped fail-closed during preflight batch 94. It attempted 376 seeds / 752 preflight RPC calls in 223.478 s; total elapsed 234.754 s including session ensure. Observed 1 upstream connection-timeout response and 4 `-2002 Rate limit reached` responses. Provider `ExpireAt` was approximately `2026-09-30T12:02:09Z`.
- The 1000-seed benchmark was intentionally not run after the provider rate-limit. Do not hammer during `ExpireAt`; resume only after cooldown or after an explicit quota-isolation experiment.
- During the long run VPS load remained low (~1 load average on 8 CPUs), so the measured bottleneck is provider response latency/quota rather than VPS CPU/RAM.
- Broker long-run safety was fixed before the 500-seed test: warm broker requests now renew the Guardian lease fail-closed. Canonical source commit: `d31dcb7a0d0d8764285ccb97cb352a509939065d`. Renewal canary proved lease expiry advances on subsequent broker calls.
- Implication: adding GitHub pool accounts does not accelerate authenticated Semrush acquisition. Before adding multiple authenticated acquisition lanes, verify whether rate limits are isolated by NoxTools/Semrush entitlement/server/profile; shared quota would make parallel sessions hit the same ceiling faster.
<!-- /SEMRUSH_ACQUISITION_BENCH_20260930 -->

    
<!-- SEMRUSH_RESEARCH_RUNTIME_PREFLIGHT_20261005 -->
## Runtime preflight contract — 2026-10-05

This research lane must preserve the hard anti-repeat contract before touching Semrush.

Execution ordering:

```text
reconcile identity / resume state
→ if terminal or no provider work remains: return/resume from artifacts
→ if provider work is pending: mandatory shallow runtime preflight
→ broker ensure
→ Semrush acquisition
```

Do not run healthcheck or broker `ensure` merely because a historical run is loaded. Existing terminal work stays terminal. For pending work, `runtime_preflight.py` is the canonical gate. A failed gate becomes `BLOCKED_RUNTIME_PREFLIGHT`; it is not demand=0, no-data evidence, or permission to backtrack/rebuild prior stages.

The runtime implementation is owned by `SEO Runtime Tooling - Semrush via NoxTools.md`. Semrush Research owns only the resume/anti-repeat decision that determines whether provider work is actually pending.
<!-- /SEMRUSH_RESEARCH_RUNTIME_PREFLIGHT_20261005 -->

    
<!-- SEMRUSH_RESEARCH_METRICS_RECOVERY_20261005 -->
## Research execution telemetry and recovery — 2026-10-05

For every pending Semrush acquisition run, state evidence now includes `semrush_metrics`. Use those metrics when deciding whether a run consumed provider work, hit provider errors, or was blocked before quota-consuming RPC.

Interpretation rules:
- `provider_rpc_calls=0` means the run did not reach provider RPC, even if broker/preflight work occurred;
- `rate_limit_errors>0` is direct rate-limit evidence and must preserve the fail-closed blocked state;
- terminal/no-pending runs should show zero provider calls;
- latency is broker request latency for the job process and is diagnostic, not a Semrush ranking metric.

If live auth becomes unavailable:
1. keep the current research run blocked; do not mark demand/no-data conclusions;
2. run the broker-owned `semrush-noxtools-login` recovery;
3. retry the same run identity after recovery;
4. preserve previous artifacts and anti-repeat state.

The recovery implementation is owned by the runtime tooling flow. Research must not add its own direct-CDP login path.
<!-- /SEMRUSH_RESEARCH_METRICS_RECOVERY_20261005 -->


<!-- SEMRUSH_RESEARCH_ONE_SHOT_QUOTA_20261006 -->
## One-shot auth recovery and quota semantics — 2026-10-06

Research jobs inherit the runtime one-shot recovery helper. Recovery is allowed only for `SEMRUSH_LIVE_AUTH_UNAVAILABLE`; it is attempted at most once and retries broker ensure at most once. The run identity does not change.

Do not interpret any of the following as demand/no-data evidence:
- `SEMRUSH_ONE_SHOT_RECOVERY_FAILED`;
- `BLOCKED_RATE_LIMIT` / `SEMRUSH_RATE_LIMIT`;
- `BLOCKED_QUOTA_LIMIT` / `SEMRUSH_REPORT_LIMIT`;
- resource admission failures.

Provider error `-2004 Report limit reached` is a hard quota block for the current provider allowance. Preserve all completed artifacts and stop the current provider-acquisition lane immediately. Do not backtrack, rebuild terminal work, or retry repeatedly.

State telemetry:
- `runtime_recovery` proves whether self-healing was attempted and whether the single retry succeeded;
- `semrush_metrics.quota_limit_errors` counts report-quota errors;
- `semrush_metrics.rate_limit_errors` remains reserved for rate limiting such as `-2002`.
<!-- /SEMRUSH_RESEARCH_ONE_SHOT_QUOTA_20261006 -->


<!-- SEMRUSH_ERROR_CLASSIFIER_20261006 -->
## Semrush error classifier — canonical override — 2026-10-06

Use this classification before deciding recovery, quota wait, or rerun:

| Signal | Meaning | Required action |
|---|---|---|
| `SEMRUSH_LIVE_AUTH_UNAVAILABLE` | Auth/session unavailable | Broker-owned one-shot recovery only; retry same run identity once. |
| `NOX_LOGIN_FORM_MISSING` | NoxTools login DOM/form changed or was not hydrated | Diagnose login DOM inside broker; do not classify as quota. |
| `-2002 Rate limit reached` | Short-term provider rate limit | `BLOCKED_RATE_LIMIT`; stop/retry after cooldown; no auth recovery. |
| `-2004 Report limit reached` | Provider report/quota allowance exhausted | `BLOCKED_QUOTA_LIMIT`; stop provider acquisition until a lightweight probe succeeds; no auth recovery. |
| DPA `-32098 Limits exceeded` | First assume report/result-window or domain-size limit, not daily/account quota | Check `organic.PositionsTotal` and page/window size. Canonical exporter handles the observed 30,000-row DPA window and should return a truncated usable export instead of failing the whole domain. |

Hard rule for `-32098`:
- Never label it as account/day quota merely from the error text.
- If other domains in the same batch succeed, that is strong evidence against a global quota block.
- Check report size first.
- Observed case: `pokecut.com` reported `34,185` organic positions; the provider allowed the first `30,000` rows and rejected the window starting at offset `30,000`.
- Canonical result for that case: PASS/truncated with `rows_fetched=30,000`, `unfetched_rows=4,185`.
- This is a provider result-window boundary, not evidence that VPS, broker, auth, scanner, or the daily account quota is broken.

Resume rule:
- Preserve completed artifacts and run identity.
- Retry only the failed/pending unit.
- Do not rerun cached/terminal work.
- Use one lightweight probe only when checking whether `-2004`/provider quota has opened again.
<!-- /SEMRUSH_ERROR_CLASSIFIER_20261006 -->


<!-- SEMRUSH_R9_AI_RESILIENT_20261006 -->
## R9 AI-resistant niche discovery — 2026-10-06

Trigger: keyword-first Semrush niche discovery with explicit preference for solid volume, low KD, and low AI-displacement risk.

### R9 acquisition
Run: `/var/lib/semrush-research/runs/delta-2026-10-06-r9-ai-resistant/`
Seed bank: `delta-bank-2026-10-06-r9-ai-resistant.json`
- 18 genuinely new themes / 54 seeds.
- Exact theme IDs and exact seeds were deduplicated against prior Semrush Research config banks before acquisition.
- Collection terminal: `UNIVERSE_READY`, 18/18 projects, 54/54 seeds, no provider/rate/quota errors.
- GitHub authority: `louisalviss/runner-3` PR #357, squash merge `b14387cadcd41a67debfb88ccbcfbe1cfb6b0132`.

AI-resilience theme policy for this delta:
- prefer structured-input, physical-measurement, engineering/spec-dependent, current-data, or workflow utilities;
- avoid pure informational/direct-answer niches that an LLM can satisfy without a dedicated tool;
- AI resilience is a gate, not proof from low KD alone.

### R9 demand/SERP result
Only `refrigeration-service-math` passed the strict default numeric gate:
- total volume 10,400/mo;
- KD<29 volume 9,980/mo;
- median KD 6;
- 24 low-KD long-tails;
- head share 9.62%.

However, exact tool-intent SERP DD on superheat/subcooling/refrigerant calculator terms was saturated:
- tool-intent pool approximately 4,190 volume/mo;
- direct calculator SERP batch averaged 6.25 exact tools in top 10;
- terminal: DROP for greenfield bare-calculator thesis.
Low KD was therefore not treated as sufficient evidence.

Near-miss SERP triage also rejected belt/pulley and pond-volume calculator theses because exact-tool SERPs were saturated.

### Best R9 survivor: Psychrometric HVAC Toolkit
Initial theme `psychrometric-air-math`:
- aggregate volume 3,160/mo;
- KD<29 volume 2,300/mo;
- median KD 22;
- representative keyword `psychrometric calculator`: volume 1,300/mo, KD 23, CPC about $1.84;
- representative exact SERP: `SERP_DD_PASS`, 4 exact tools/top10.

R9b additive expansion:
Run: `/var/lib/semrush-research/runs/delta-2026-10-06-r9b-psychrometric/`
Seed bank: `delta-bank-2026-10-06-r9b-psychrometric.json`
- 10 additional NEW psychrometric seeds; no old seed was rerun.
- Combined original+expansion universe: 13 seeds.
- combined universe SHA256: `f7dfbd454ce6c038240fff2cbc0479897337c37c786156ff7f389b0e5a6e28ce`.

Combined toolkit metrics:
- total volume: 18,180/mo;
- canonical KD<29 volume: 4,040/mo;
- 199 deduped keywords / 59 metric-bearing;
- 16 low-KD long-tails;
- median KD: 31;
- head share: 19.8%;
- weighted CPC: about $0.80;
- high-intent volume share: 71.62%.

The full toolkit narrowly misses the strict canonical median-KD gate (31 > 30), so it is NOT a full `PASS_CANDIDATE`.

Low-KD wedge:
- `psychrometric calculator`: 1,300 vol / KD 23 / CPC ~$1.84;
- `psychrometric chart calculator`: 590 / KD 26 / CPC ~$1.96;
- `dry bulb and wet bulb calculator`: 110 / KD 16;
- `humidity ratio calculator`: 90 / KD 17;
- additional low-KD terms include sensible heat ratio, air enthalpy, dew-point-from-DB/WB, and related psychrometric calculations.

Exact 4-query wedge SERP DD:
- terminal: `SERP_DD_PASS`;
- average exact tools/top10: 4.25;
- checked SERP feature codes did not include Semrush AI Overview code 52 in this snapshot;
- absence of code 52 on these queries is only current SERP evidence, not proof that future AI/zero-click risk is zero.

Current terminal classification:
`WATCH_STRONG_CANDIDATE — Psychrometric HVAC Toolkit`

Why WATCH rather than PASS:
1. full-toolkit median KD is 31, one point above strict gate;
2. exact low-KD wedge is materially cleaner and passes SERP;
3. current competitor activity is increasing, so another bare calculator is not enough;
4. strongest product thesis is a structured-input HVAC field workflow/toolkit, not informational content.

If continued downstream, validate a differentiated field-workflow product: measured DB/WB/RH/pressure inputs → psychrometric state/process/mixing calculations → saved jobs/reports/export/diagnostic workflow. Do not rerun R9/R9b acquisition unless the thesis/source materially changes.

### Future AI-resilience gate
For future Semrush Research promotion:
- low KD + volume is necessary but insufficient;
- prefer search tasks where the user supplies real measurements, dimensions, files, current records, inventory/specs, or transaction context;
- penalize pure “what/how/formula/explain” demand if the dedicated-tool subset is weak;
- explicitly split informational demand from tool-intent demand before promotion;
- inspect exact SERPs for AI Overview/direct-answer risk and exact-tool saturation;
- a candidate survives only if a meaningful low-KD tool-intent wedge remains after those filters.
<!-- /SEMRUSH_R9_AI_RESILIENT_20261006 -->


<!-- SEMRUSH_R10_R11_AI_RESILIENT_20261007 -->
## R10/R11 AI-resistant niche continuation — 2026-10-07

Purpose: continue keyword-first niche discovery after R9, preferring lookup/compatibility/current-data and physical sizing patterns that are harder for generic AI answers to replace.

### R10
Run: `/var/lib/semrush-research/runs/delta-2026-10-06-r10-lookup/`
Seed bank: `delta-bank-2026-10-06-r10-lookup.json`
- 15 new themes / 47 seeds.
- 0 duplicate theme IDs and 0 duplicate exact seeds against prior banks.
- terminal acquisition: `UNIVERSE_READY`, 47/47 seeds, 141 provider RPC, 0 provider/rate/quota errors.

Strict demand survivors:
1. `electrical-fill-code-calculators`
   - total volume 27,300/mo
   - KD<29 volume 25,350
   - median KD 18
   - high-intent share 88.24%
   - exact SERP: `DROP_SERP_SATURATED`, ~7 exact tools/top10.
   - terminal: DROP despite excellent volume/KD.

2. `hvac-equipment-age-lookup`
   - total volume 4,060/mo
   - KD<29 volume 2,430
   - median KD 20
   - 100% high-intent by current classifier
   - deep 4-query exact SERP: `SERP_DD_PASS`, average 3.75 exact tools/top10.
   - merged with water-heater/appliance age lookup into `home-equipment-age-intelligence`:
     - total volume 10,740/mo
     - KD<29 volume 7,200
     - median KD 18
     - 56 low-KD long-tails
     - head share 4.47%
     - exact SERP result: `WATCH_COMPETITION` on both clusters, average tool density 5.5-6.0.
   - product/market check found fast-rising decoder competition and direct inspector-camera products; do not promote as current winner.

Near-miss DD:
- `garage-door-spring-sizing`: total 3,610, KD<29 3,270, median KD 1, high-intent 96.68%; exact 3-query SERP averaged 8 exact tools/top10 -> `DROP_SERP_SATURATED`.
- `attic-ventilation-sizing`, `dc-battery-wire-sizing`, other R10 near-misses remain numerically weaker and were not promoted ahead of the stronger tested candidates.

### R11 equipment error-code expansion
Run: `/var/lib/semrush-research/runs/delta-2026-10-06-r11-error-codes/`
Seed bank: `delta-bank-2026-10-06-r11-error-codes.json`
- 12 new additive seeds for furnace/boiler/heat-pump/thermostat error-code expansion.
- terminal acquisition: `UNIVERSE_READY`, 12/12 seeds, 36 provider RPC, 0 errors.

Artifact-only merge with R10 mini-split/water-heater/generator error-code groups:
`equipment-error-code-intelligence`
- total volume 13,980/mo
- KD<29 volume 9,460
- median KD 9.5
- 77 low-KD long-tails
- head share 6.29%

Exact SERP:
- main mini-split/water-heater cluster: `DROP_SERP_SATURATED`, average 7.33 exact tools/top10.
- Generac generator error-code cluster: `SERP_DD_PASS`, average 4.67 exact tools/top10.

AI-resilience/business override:
- Do NOT promote a pure error-code lookup merely because KD is low.
- Error-code questions are highly compressible into direct AI answers.
- Current manufacturer ecosystems already provide guided troubleshooting/product assistants and dealer escalation.
- Generac-specific pain and WTP are real, but the remaining clean cluster is too narrow and too AI-answerable to outrank the psychrometric structured-input thesis.
- Result: `WATCH_NARROW / NO_PROMOTION`.

### Current ranking after R9-R11
Best overall SEO niche remains:
`Psychrometric HVAC Toolkit — WATCH_STRONG_CANDIDATE`

Why it remains #1:
- meaningful total demand;
- a defensible low-KD wedge;
- exact SERP pass across the tested psychrometric wedge;
- user must provide real measured inputs and needs interactive state/process/chart outputs;
- less directly compressible to a one-shot AI answer than serial decoders or error-code explainers.

Do not rescan R9/R10/R11 banks unless the thesis/source materially changes. Future rounds should explore genuinely new structured-input/data-workflow niches and must run exact-tool saturation before promotion.
GitHub authority for R10/R11 seed banks: `louisalviss/runner-3` PR #358, squash merge `dd2c4bb78e28a885c4af84d84c80226039ce69e3`.
<!-- /SEMRUSH_R10_R11_AI_RESILIENT_20261007 -->


<!-- SEMRUSH_R12_R19_WINNER_20261007 -->\nPROJECT AUTHORITY: /Apps/remotely-save/AI/AI-MEMORY/PROJECTS/Fisch Live Trade Value Database/PROJECT.md\n
## R12-R19 continuation + current winner — 2026-10-07

Objective: solid search volume + low KD + low AI displacement + exact-SERP whitespace.

Terminal anti-repeat summary:
- R12 fitment/cross-reference: COMPLETE_NO_PASS; strongest near-misses all DROP_SERP_SATURATED.
- R13 industrial compatibility: COMPLETE_NO_PASS; chemical-material compatibility 5,970 vol / 2,790 KD<29 / median KD23, but 3-query SERP avg 6 exact tools/top10 -> DROP.
- R14 current/local records: restaurant inspections 3,410 vol / 2,480 KD<29 / median KD17, exact SERP PASS avg 4.33 tools/top10; R14b geo expansion only reached 3,590 -> WATCH_SCALE_TOO_LOW.
- R15 trade/landed cost: COMPLETE_NO_PASS.
- R15 vehicle tax/registration: COMPLETE_NO_PASS; California largest 6,320 vol but median KD43.
- R16 vehicle service data: COMPLETE_NO_PASS.
- R17 address risk: COMPLETE_NO_PASS.
- R19 field industrial: COMPLETE_NO_PASS.

### R18 winner — Fisch Live Trade Value Database
Run: `delta-2026-10-07-r18-game-economy`

Four strict survivors entered exact SERP DD:
- Grow a Garden -> DROP_SERP_SATURATED, avg 6.67 exact tools/top10.
- Blox Fruits -> DROP_SERP_SATURATED, avg 7.67.
- Steal a Brainrot -> DROP_SERP_SATURATED, avg 7.0.
- Fisch -> SERP_DD_PASS, avg 4.33.

Fisch metrics:
- total volume 12,310/mo;
- KD<29 volume 11,690/mo;
- median KD 17;
- 11 low-KD long-tails;
- head share 23.56%.
Representative queries:
- fisch values 2,900 / KD27;
- fisch value list 1,900 / KD19;
- fisch trading values 1,600 / KD22;
- fisch trade values 1,300 / KD16;
- fisch value 1,300 / KD8;
- fisch value calculator 260 / KD12.

AI resilience:
- values/demand change with patches and real trading;
- main checked SERPs did not include Semrush AI Overview feature code 52;
- fresh market data is the product, so static AI answers decay.

Current activity validation on 2026-10-07:
- Roblox official page showed about 60k active players, 4.9B+ visits, updated 2026-10-05, FischFright 3 scheduled 2026-10-17.
- Recent community posts still ask where to obtain current/fair Fisch trade values.

Competition override:
- Game.Guide is a strong incumbent with live value list, trade calculator and a large trading hub.
- Do NOT build a bare calculator.
- Best thesis = focused live value database: item-level pSEO pages + current value/demand/history + trade comparison/calculator as supporting feature.
- Game half-life is a material risk; freshness automation is mandatory.

Current classification:
`PASS_CANDIDATE — Fisch Live Trade Value Database`

For the exact objective "volume ổn + KD thấp + ít bị AI đánh", Fisch now ranks above Psychrometric HVAC Toolkit. Psychrometric remains the evergreen fallback, not current #1.

Resume rule:
- Never rerun R12-R19 banks unless thesis/source materially changes.
- Reuse existing universes first.
- Continue Fisch with competitor/data-source/build validation, OR open a genuinely new R20 family; do not reopen broad R18 acquisition.

GitHub authority: `louisalviss/runner-3` PR #361, squash merge `7c1feff4e3d4af83c2f2157bea4585144bc853de`.
<!-- SEMRUSH_MODIFIER_DISCOVERY_20261007 -->
CANDIDATE STORAGE RULE: WATCH/PASS candidates remain in this Semrush Research authority; create PROJECTS/<name>/ only after promotion to BUILD_TEST / ACTIVE VALIDATION / EXECUTION.


## Modifier-first SEO Idea Scanner — canonical update — 2026-10-07

This block supersedes older scanner resume/ranking notes where they conflict.

### Official discovery pipeline
- GitHub source authority: `louisalviss/runner-3/jobs/semrush-research/`
- runtime: `/var/lib/semrush-research/scripts/`
- one-command entrypoint: `discovery_cycle.py`
- exact-SERP anti-repeat registry: `/var/lib/semrush-research/config/discovery-tested-v1.json`

```text
auto-select unseen modifier roots
→ live_collect.py through semrush-rpc-broker only
→ modifier_mine.py
→ semantic/config anti-repeat
→ tested-SERP registry anti-repeat
→ bounded candidate queue
→ exact serp_dd_live.py
→ discovery_finalize.py
→ COMPLETE_NO_CANDIDATE / COMPLETE_NO_SURVIVOR / COMPLETE_WITH_SURVIVOR
```

Hard rules:
- never reacquire a terminal universe only to rerun discovery;
- never exact-SERP-test a candidate already present in `discovery-tested-v1.json`;
- zero candidates / zero survivors are valid terminal outcomes;
- do not promote on volume/KD alone;
- authenticated Semrush I/O stays broker-only;
- brand-specific tested candidates must not suppress a genuinely broader market candidate;
- R20-R25 are terminal and must not be reacquired.

### Implementation and acceptance
- `modifier_mine.py`, `modifier_seed_bank.py`, `discovery_stage.py`, `discovery_finalize.py`, `discovery_cycle.py` are active.
- Regression: 3/3 PASS.
- Tested registry after R25: 135 exact-SERP-tested candidates.
- R24: 6 candidates → 6 `DROP_SERP_SATURATED` → terminal no survivor.
- R25 one-command acceptance: 8 candidates → 7 `DROP_SERP_SATURATED` + 1 `WATCH_COMPETITION` (snowboard-length) → 0 `SERP_DD_PASS` → `COMPLETE_NO_SURVIVOR`.
- Next discovery identity starts at R26 or later.

Noise filters reject obvious informational/tutorial queries, malformed subject artifacts, retail-calculator product noise, weapon-related queries, and medical/YMYL calculator queries.

### Current ranking correction
Subsequent review overrides the earlier R18 promotion:
- `Fisch Trade Values` → `WATCH / NO BUILD` for current scanner recommendation because direct competition is rising, existing live databases/calculators exist, moat is weak, and the thesis depends on one game's lifecycle.
- `Psychrometric HVAC Toolkit` → current #1 `WATCH_STRONG_CANDIDATE`.
- No R20-R25 candidate surpassed Psychrometric.
- Do not force a BUILD winner by relaxing exact-SERP gates.

### Exact resume
```bash
python3 /var/lib/semrush-research/scripts/discovery_cycle.py \
  --run-dir /var/lib/semrush-research/runs/delta-YYYY-MM-DD-rNN-auto-modifier \
  --config-dir /var/lib/semrush-research/config \
  --tested-registry /var/lib/semrush-research/config/discovery-tested-v1.json \
  --queries-per-cluster 2 \
  --max-serp-candidates 8
```

Terminal runs must return resume/no-backtrack semantics instead of repeating provider work.
<!-- /SEMRUSH_MODIFIER_DISCOVERY_20261007 -->

<!-- /SEMRUSH_R12_R19_WINNER_20261007 -->


<!-- SEMRUSH_R26_R28_20261008 -->
## R26-R28 modifier discovery continuation — 2026-10-08

This block supersedes older next-run notes where they conflict.

### R26
Run: `delta-2026-10-08-r26-auto-modifier`
- 8/8 new modifier roots collected; no provider/rate/quota errors.
- 1 exact-SERP candidate: `jobs that don't require background checks`.
- Mechanical result: `BLOCKED_INCOMPLETE_SERP`.
- Lifecycle/business override: `DROP_INFORMATIONAL_EMPLOYMENT_NOISE / NO_RECHECK`.
- Reason: informational/job-search intent, not a tool niche.
- Scanner fix: employment informational-noise pattern added before future SERP DD.

### R27
Run: `delta-2026-10-08-r27-auto-modifier`
- 8 new modifier roots.
- 5 exact-SERP candidates.
- 4 `DROP_SERP_SATURATED`.
- 1 mechanical `SERP_DD_PASS`: Goodman warranty lookup.
- Goodman metrics: 12,100 monthly volume / KD26 / 4 exact tools top10.
- Business override: `DROP_OFFICIAL_AUTHORITY_NO_BUILD`.
- Exact SERP showed `goodmanmfg.com` occupying 7/10 top positions and providing the canonical warranty lookup.
- Do not promote a brand-owned lookup simply because mechanical tool density passes.

### R28
Run: `delta-2026-10-08-r28-auto-modifier`
- 8 new modifier roots.
- terminal: `COMPLETE_NO_CANDIDATE`.
- no new exact-SERP records.

### Current scanner state
- exact-SERP tested registry: 141 records.
- R20-R28 terminal; do not reacquire unchanged batches.
- Candidate Registry authority: `Semrush Candidate Registry.md`.
- Machine recovery mirror: `Semrush Tested Registry.json`.
- Current #1 remains `Psychrometric HVAC Toolkit — WATCH_STRONG_CANDIDATE`.
- Fisch remains `WATCH / NO BUILD`.
- No R26-R28 candidate is promoted to PROJECTS.
- Next discovery identity: R29+.

GitHub:
- PR #364 squash `17db1c01a62bb513249efabe278af8a15b20d89b` — R26/R27 fixes, lifecycle overrides, tested registry 141, terminal-round tracking.
- PR #365 squash `8f6ae53327519863a89386175dfe475ab322c477` — R28 recovery state.
- PR #366 squash `c93897ee9a128128d493643e555449b5f7a5ed91` — exact runtime R28 seed bank.
<!-- /SEMRUSH_R26_R28_20261008 -->


<!-- SEMRUSH_R29_20261008 -->
## R29 modifier discovery — 2026-10-08

Run: `delta-2026-10-08-r29-auto-modifier`

Exact-SERP queue:
- mixed fraction calculator — cluster volume 12,690 / median KD26.5 -> `DROP_SERP_SATURATED`;
- 50:1 gas/oil mix calculator — 2,020 / median KD13 -> `DROP_SERP_SATURATED`;
- baluster spacing calculator — 1,140 / median KD23.5 -> `DROP_SERP_SATURATED`.

Terminal:
- `COMPLETE_NO_SURVIVOR`;
- tested registry: 144 records;
- no candidate promoted;
- current #1 remains `Psychrometric HVAC Toolkit — WATCH_STRONG_CANDIDATE`;
- next discovery identity: R30+.

GitHub: PR #368, squash `d19eb5c5a94d993f44dc23360c160dbb76580a10`.
<!-- /SEMRUSH_R29_20261008 -->


<!-- SEMRUSH_R30_R31_20261008 -->
## R30-R31 terminal continuation — 2026-10-08

This block is the newest scanner resume authority and supersedes older next-run notes where they conflict.

### R30
Run: `delta-2026-10-08-r30-auto-modifier`
- final 7 unseen modifier roots in the current catalog;
- 3 exact-SERP candidates;
- total variable cost -> `DROP_SERP_SATURATED`;
- county lookup by ZIP -> `DROP_SERP_SATURATED`;
- county lookup by address -> mechanical `SERP_DD_PASS`:
  - cluster volume 3,380;
  - median KD 26;
  - avg exact tools/top10 2.5.
- lifecycle/business override for county-by-address:
  `ABSORB_AS_ADDRESS_GEO_MODULE_NO_STANDALONE_BUILD`.
- rationale: CPC 0, head-heavy demand, free official geocoding/geography data commoditizes the core lookup; retain only as a module for address/permit intelligence.
- tested registry advanced 144 -> 147.
- no project promotion.

### R31
Run: `delta-2026-10-08-r31-auto-modifier`
- generated seed bank: `themes: []`;
- terminal: `COMPLETE_CATALOG_EXHAUSTED`;
- no Semrush provider acquisition;
- tested registry remains 147.

### Current terminal state
- R20-R31 are terminal; do not reacquire unchanged batches.
- Exact-SERP tested registry: 147 records.
- Candidate lifecycle authority: `Semrush Candidate Registry.md`.
- Machine recovery mirror: `Semrush Tested Registry.json`.
- Current #1 remains `Psychrometric HVAC Toolkit — WATCH_STRONG_CANDIDATE`.
- Fisch remains `WATCH / NO BUILD`.
- No R26-R31 candidate is promoted to PROJECTS.
- Current modifier catalog is exhausted.
- Do NOT create R32 from the same catalog.
- Recommended next gate: downstream product/business validation of Psychrometric (workflow differentiation + WTP) before any BUILD_TEST promotion.
- Expand the modifier catalog only if intentionally seeking a genuinely new idea family.

GitHub:
- PR #370 squash `0b0ecd73a1317cdae70f75f1c6f30f3d34544601` — R30 + county lifecycle + catalog-exhaustion semantics.
- PR #371 squash `8fde6eca695f1130090fe84006f954f505cc9056` — exact R31 empty seed bank + catalog exhaustion state.
<!-- /SEMRUSH_R30_R31_20261008 -->

<!-- SEMRUSH_WORD_SEARCH_PROBE_20261008 -->
## Word Search Solver from Image — research override — 2026-10-08

Status: `SEO_PROBE_ONLY / NO PROJECT`.

Research conclusion:
- image/photo word-search solving has real user demand and a natural web -> mobile-camera workflow;
- however exact-match competition for image/photo/scanner solvers is rising quickly;
- the core OCR + grid reconstruction + deterministic solver is readily cloneable, so current moat is weak;
- a single word-search solver has a limited traffic ceiling; meaningful scale would require a broader Puzzle Scanner network.

If tested, the continuation gate is:
`indexed + correct-query impressions + ranking movement + real upload usage`.

Indexing alone is not sufficient.

Priority rule:
- do not prioritize this over `Psychrometric HVAC Toolkit — WATCH_STRONG_CANDIDATE`;
- do not create a PROJECTS entry unless the probe produces the full continuation signal above.
<!-- /SEMRUSH_WORD_SEARCH_PROBE_20261008 -->

<!-- SEMRUSH_PSYCHROMETRIC_PRODUCT_WTP_20261008 -->
## Psychrometric HVAC Toolkit — product/WTP validation — 2026-10-08

Purpose: execute the downstream gate after R31 catalog exhaustion: validate willingness-to-pay and field-workflow differentiation before any BUILD_TEST promotion.

### WTP evidence — PASS

Standalone psychrometric products demonstrate real paid demand:
- Pheinex Psychrometric Chart: $59.99 one-time on Apple platforms.
- Psychro Calc Pro: $9.99 one-time premium.
- Carmel HVAC Psychrometric: $6.99.
- Hands Down HDPsyChart Professional: $199/year subscription.
- IX-CHART: approximately $149-$150/year for web/subscription tiers.

Broader HVAC field/reporting workflows demonstrate materially higher WTP:
- measureQuick Premier: $49/user/month for diagnostics, reporting, cloud history, integrations and remote verification.
- Testo Smart PRO air-balancing program: $9.99/month or $89.99/year.
- FlowPoint TAB: $79-$129/user/month for field TAB workflow, reports, offline use and team collaboration.

Conclusion: professionals pay for psychrometric/field software. WTP itself is not the blocker.

### Product differentiation — FAIL for standalone build

The former differentiation thesis (interactive chart + multiple processes + saved jobs + PDF/report/export) is no longer sufficient:
- PsychroView already provides interactive psychrometric charts, multiple chained air-handling processes, ASHRAE-based calculations, PDF/PNG/DXF export and sharing.
- Psych-Chart/PsychroSim provides process chains, projects, PDF reports and company access.
- Current/new web tools already expose air mixing, cooling-coil analysis, ADP, bypass factor, sensible/latent/total loads, SHR, condensate/moisture calculations and exports.
- HVAC-calcs.app is a recent paid suite covering psychrometric process paths, mixed air, AHU design, saved projects and PDF reporting.
- measureQuick already provides hardware-agnostic connectivity across many tool brands plus diagnostics/reporting; Testo and Fieldpiece own strong instrument-connected workflows.

Competition is therefore expanding from both directions:
1. low-cost/free dedicated psychrometric utilities;
2. higher-value field/commissioning platforms with measurements, diagnostics and reports.

A bare calculator is not differentiated.
A chart/process/project/report app is also not differentiated enough.
A field workflow based only on manual psychrometric entry is unlikely to justify competing directly with instrument ecosystems.

### Current lifecycle override

Psychrometric HVAC Toolkit -> WATCH_NO_BUILD_CURRENT

Interpretation:
- SEO wedge remains useful benchmark evidence.
- Demand and WTP are real.
- Do NOT create PROJECTS/ or BUILD_TEST now.
- Reopen only if a materially new moat/distribution thesis appears, e.g. proprietary measurement data, uniquely valuable integration/workflow, or an acquisition asset with existing distribution.
- If reused later, treat psychrometrics as a module inside a broader HVAC product, not the standalone business.

### Scanner consequence

R31 already exhausted the current modifier catalog. Since the benchmark itself did not clear the product-differentiation gate, the current scan has no BUILD winner.

Do not relax gates to force one.

Next discovery work, if initiated, must use a genuinely new idea family/catalog and should target:
- utility/search surfaces with larger reachable ceilings;
- structured inputs / files / measurements / current data;
- clearer monetization than ad-only tools;
- a defensible data/workflow/distribution advantage not already commoditized by free utilities.
<!-- /SEMRUSH_PSYCHROMETRIC_PRODUCT_WTP_20261008 -->



<!-- SEMRUSH_PSYCHROMETRIC_DOWNSTREAM_DD_20261008 -->
## Psychrometric HVAC Toolkit downstream validation — 2026-10-08

Purpose: test whether the strongest remaining search candidate is strong enough to cross from research candidate into BUILD_TEST.

Historical search evidence remains attractive:
- combined toolkit demand: 18,180/month;
- KD<29 volume: 4,040/month;
- low-KD wedge exact SERP: SERP_DD_PASS, avg 4.25 exact tools/top10;
- representative low-KD queries include psychrometric calculator (1,300/KD23) and psychrometric chart calculator (590/KD26).

### Current market / product validation

Full field-diagnostics workflow:
- measureQuick reports 100,000+ technicians and compatibility with 80+ tools across 17+ brands.
- measureQuick core diagnostics are free; Premier is $49/user/month and adds System View, reporting/cloud, AI Assist, live streaming, standalone/offline mode, checklists and management workflow.
- Fieldpiece Job Link provides free live measurements, calculations and professional reports around the Fieldpiece hardware ecosystem, plus team/remote support features.
- Conclusion: the earlier proposed probe-connected field-workflow moat is already occupied by mature ecosystems.

Browser engineering workflow:
- PsychroView already provides a free no-sign-up browser chart, ASHRAE/Hyland-Wexler calculations, 13 process types, process chaining, PDF/PNG/DXF export, project cloud storage and share links.
- HVAC-calcs.app offers free single-point psychrometrics and a £4.50/month suite with process lines, charts, PDF reporting, duct/pipe tools and project features.
- PsychroStudio/PsychroFlow also provides browser psychrometric workflow and professional report/project features.
- Conclusion: browser + process-chain + project/report differentiation is no longer whitespace.

Low-cost / offline professional tool:
- Psychrometrics iOS is about $3.99 in the US with interactive charts, process modeling, saved projects and PDF export.
- Psychro Calc Pro offers a $9.99 lifetime unlock with any-two-property solver, process analysis, history and PDF reporting.
- Android competitors offer offline interactive charts/processes/reporting; AirCore explicitly targets 100% on-device/no-account/no-subscription use.
- Conclusion: offline/no-login/one-time-payment is also not a unique wedge.

Free SEO-tool layer:
- AskHVAC advertises 29 free psychrometric tools and 520+ HVAC calculators overall with no login and exports.
- Other free browser tools expose psychrometric state/chart/PDF functionality.
- Conclusion: a generic free calculator cluster has weak moat even if some keywords remain low-KD.

User/workflow pain evidence:
- HVAC community discussions show demand for simpler probe workflows and complaints around app reliability/location permissions.
- However measureQuick Classic/Standalone and Fieldpiece Quick View already address much of the just-show-measurements use case.
- This is UX pain, not sufficient greenfield business whitespace.

### WTP conclusion

There is real HVAC software WTP, but it splits into:
- high WTP (~$49/user/month) for full diagnostics + hardware integration + reporting/team/cloud ecosystems;
- low WTP (~$4-$10 one-time or ~£4.50/month) for standalone psychrometric analysis.

A new standalone psychrometric product would compete primarily in the low-WTP tier unless it builds a hardware/integration/standards moat comparable to mature incumbents.

### Terminal business verdict

`WATCH_NO_BUILD_ACQUIRE_ONLY — Psychrometric HVAC Toolkit`

Reason:
1. search demand remains attractive;
2. interactive calculation remains more AI-resistant than pure informational content;
3. but every proposed greenfield wedge is already materially covered;
4. low-end standalone WTP is weak;
5. high-end WTP is tied to ecosystems/integrations that substantially increase scope;
6. therefore it does NOT cross the BUILD_TEST promotion gate.

Reopen only if:
- an already-indexed/trafficked psychrometric/HVAC tool asset becomes available for acquisition at attractive economics;
- a materially proprietary data/hardware/integration advantage appears;
- or new search/competitor evidence creates a genuinely different wedge.

Do not create a Psychrometric PROJECTS folder under current evidence.

### Scanner conclusion after catalog exhaustion

`NO_GREENFIELD_BUILD_CANDIDATE`

- Psychrometric remains the strongest SEARCH watch, but is no longer a greenfield build recommendation.
- Fisch remains WATCH / NO BUILD.
- R20-R31 are terminal.
- exact-SERP registry: 147 records.
- current modifier catalog is exhausted.
- do not open R32 from the unchanged catalog merely to force a winner.
<!-- /SEMRUSH_PSYCHROMETRIC_DOWNSTREAM_DD_20261008 -->


<!-- SEMRUSH_R32_LICENSE_CREDENTIAL_20261008 -->
## R32 license / credential verification — terminal — 2026-10-08

New family rationale:
- structured current license / credential / registration status;
- answer quality depends on fresh authoritative records;
- potentially less AI-compressible than static informational content;
- possible B2B/API/lead monetization.

Run: `delta-2026-10-08-r32-license-credential`

Execution:
- 8 exact new seeds;
- first attempt stopped at resource admission before acquisition: `browser-slots-full`;
- first attempt had `seed_done=0` and `provider_rpc_calls=0`;
- resumed the SAME R32 identity after a legitimate browser slot became available;
- no duplicate acquisition identity was created.

Exact-SERP result:
- one mechanical survivor: `verification of license pa`;
- volume 5,400 / KD21 / CPC0;
- head share 1.0;
- avg exact tools/top10 4.0;
- Pennsylvania primary-source `pa.gov/PALS` occupied positions 1, 2 and 4 and provides the canonical public verification workflow.

Lifecycle/business override:
`DROP_OFFICIAL_AUTHORITY_HEAD_HEAVY_NO_BUILD`

Reason:
- 100% of measured demand is concentrated in one head query;
- navigational / official-authority intent dominates;
- no defensible standalone SEO/tool wedge despite the mechanical SERP pass.

Terminal:
- tested registry advanced 147 -> 148;
- Candidate Registry and Tested Registry Dropbox mirrors synced;
- no R32 candidate is promoted to PROJECTS;
- do not continue this family merely because the PA keyword mechanically passed.

GitHub:
- PR #376 squash `3e093a18f1c46d5d8572ce49cc401f68286cd84d` — R32 family seed bank.
- PR #378 squash `fa4fae91b06b0ddb4adb53a82a10b6bdc6207b77` — terminal outcome, lifecycle override, tested registry 148.

Next:
- open only a genuinely new idea family;
- keep exact-SERP anti-repeat registry authoritative;
- mechanical `SERP_DD_PASS` still requires business/authority DD before any promotion.
<!-- /SEMRUSH_R32_LICENSE_CREDENTIAL_20261008 -->


<!-- SEMRUSH_R33_MODEL_DOCUMENT_20261008 -->
## R33 model-specific document retrieval — terminal — 2026-10-08

Run: `delta-2026-10-08-r33-model-document-retrieval`

Family:
- manual lookup;
- service manual lookup;
- parts diagram lookup;
- wiring diagram lookup;
- spec sheet lookup;
- datasheet lookup;
- user manual lookup;
- repair manual lookup.

Execution:
- 8/8 seeds collected;
- universe stage: `UNIVERSE_READY`;
- provider RPC calls: 24;
- provider RPC errors: 0;
- rate/quota errors: 0;
- raw rows: 86;
- qualified rows: 1;
- mined clusters: 0;
- exact-SERP queue: 0.

Terminal:
- `COMPLETE_NO_CANDIDATE`;
- tested registry remains 148;
- Candidate Registry Dropbox sync PASS/readback verified;
- no candidate promoted to PROJECTS;
- no R33 process remains running.

Resume rule:
- R33 is terminal; do not reacquire this seed bank unchanged.
- Do not open a new round merely to repeat these document-retrieval roots.
- Next discovery, if resumed, must be a genuinely new family.
<!-- /SEMRUSH_R33_MODEL_DOCUMENT_20261008 -->

<!-- SEMRUSH_R34_AUTO_REPAIR_LABOR_TIME_20261008 -->
## R34 auto-repair labor-time — terminal — 2026-10-08 (VN)

Run: `delta-2026-10-08-r34-auto-repair-labor-time`.
Family: structured automotive repair labor time / flat-rate guide / mechanic book-time lookup. Seed bank contains 8 new roots. Historical R20-R33 exact-SERP tests are retained; this is NOT a scan of the exhausted modifier catalog.

Execution:
- First attempt hit `SEMRUSH_RESOURCE_ADMISSION_DENIED:browser-slots-full` before provider acquisition (`seed_done=0`, `provider_rpc_calls=0`); resumed **the same R34 identity**, without creating a duplicate round.
- 8/8 seeds completed;
- raw keyword rows: 189;
- qualified keyword rows: 4;
- mined clusters: 0;
- exact-SERP queue: 0;
- terminal: `COMPLETE_NO_CANDIDATE`.
- No candidate promoted to `PROJECTS/`.

Machine / Dropbox:
- exact-SERP tested registry unchanged at **148**;
- Candidate Registry regenerated and synced with Dropbox readback PASS;
- Tested Registry Dropbox mirror unchanged;
- do not reacquire this R34 seed bank unchanged.

Business DD cleanup of old mechanical SERP passes:
- `manufactured-home-resolver` → `DROP_OFFICIAL_AUTHORITY_LOW_SCALE_NO_BUILD` (title-search ~570 monthly; official-authority SERP).
- `manufacturing` → `DROP_SEMANTIC_CONTAMINATION_NO_BUILD` (mixed unrelated tolerance intent).
- `open-channel-flow-math` → `WATCH_LOW_SCALE_NO_BUILD` (Manning representative ~390 monthly, existing calculators).
- `trucking` → `WATCH_MATURE_MARKET_NO_GREENFIELD_BUILD` (truck routing ~410 monthly cluster, mature market).

GitHub persistence:
- `louisalviss/runner-3` PR #380 squash `c5459d29ff47a2061229f63c87dd1e6b1dd78852`;
- `jobs/semrush-research/config/delta-2026-10-08-r34-auto-repair-labor-time.json`;
- `jobs/semrush-research/config/candidate-lifecycle-v1.json`;
- `ops/checkpoints/semrush-r34-2026-10-08-VN.md`.

Resume authority: R34 is terminal. R35+ only if backed by a **genuinely new, independent idea family**, never to force a winner or repeat existing seeds. Exact-SERP anti-repeat remains authoritative. No current `BUILD_TEST` candidate; Psychrometric remains WATCH_NO_BUILD_CURRENT and Fisch remains WATCH_NO_BUILD.
<!-- /SEMRUSH_R34_AUTO_REPAIR_LABOR_TIME_20261008 -->

<!-- SEMRUSH_R35_SOLAR_INTERCONNECTION_QA_20261008 -->
## R35 utility interconnection QA — terminal — 2026-10-08 VN

Identity: `delta-2026-10-08-r35-solar-interconnection-qa`
Candidate family: US solar installer-side utility-interconnection document preflight/rejection QA; 6 genuinely new exact root seeds. Business-first probe, not greenfield project promotion.

Business preflight:
- Commercial buyer: US solar installer / EPC permit and interconnection coordinator. Utility-specific instructions and document mismatch cause practical rework.
- Narrow wedge considered: source-grounded utility-specific checks and cross-document consistency, NOT another solar CRM.
- Competition includes utility-native validation (PG&E), SolaDrive and GridProjeX. Source/data moat and buyer conversion for this exact wedge NOT demonstrated.
- Six-seed Semrush measurement only, no new domain, build or PROJECTS candidate.

Execution (verified):
- 6/6 seeds completed, provider RPC 18 = 6 each keywords.GetInfo / ideas.GetKeywordsSummary / ideas.GetKeywords.
- Auth PASS; provider errors 0; rate/quota errors 0; browser resource admission PASS.
- Raw keyword rows 2 (both volume 0); qualified rows 0; clusters 0; exact SERP queue 0.
- Terminal stage `COMPLETE_NO_CANDIDATE`. No need for live SERP DD.
- Exact SERP tested registry remains **148**; Candidate Registry Dropbox terminal sync PASS/readback verified; Tested Registry Dropbox mirror unchanged.

Authority/recovery:
- VPS terminal: `/var/lib/semrush-research/runs/delta-2026-10-08-r35-solar-interconnection-qa/discovery-cycle-state.json`
- GitHub `louisalviss/runner-3` PR #382 merged commit `b9fe5d6bc76327cf48e3cafc10de890ebe1c90b5`, seed bank and `ops/checkpoints/semrush-r35-2026-10-08-VN.md`.
- Source links and detailed competing product notes are in that checkpoint.
- DO NOT reacquire unchanged R35 roots and DO NOT auto-open R36 simply to force a survivor. R36+ requires independently proven new thesis and explicit preflight gate; conserve Semrush access/cost.
- Lifecycle conclusion unchanged: `NO_GREENFIELD_BUILD_CANDIDATE`; Psychrometric WATCH_NO_BUILD_CURRENT; Fisch WATCH_NO_BUILD.
<!-- /SEMRUSH_R35_SOLAR_INTERCONNECTION_QA_20261008 -->

