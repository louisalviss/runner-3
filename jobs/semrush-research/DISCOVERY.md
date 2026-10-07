# Semrush Modifier-First Discovery

Canonical discovery flow:

1. `modifier_seed_bank.py` selects unseen generic utility roots from the curated catalog.
2. `live_collect.py` acquires the root universe through the single-owner Semrush broker.
3. `discovery_stage.py` runs `modifier_mine.py`, applies config/theme anti-repeat plus the exact-SERP tested registry, and emits a bounded `serp-dd-queue.json`.
4. `serp_dd_live.py` performs exact SERP DD only for shortlisted candidates.
5. `discovery_finalize.py` appends tested candidates to the registry and emits the survivor summary.

Hard rules:
- Never reacquire a terminal universe only to rerun discovery.
- Never exact-SERP-test a candidate already present in the tested registry.
- A zero-candidate or zero-survivor result is a valid terminal result.
- Do not promote a niche on volume/KD alone; exact SERP must survive.
- Authenticated Semrush I/O remains broker-only.

Canonical one-command entrypoint:

```bash
python3 discovery_cycle.py --run-dir <run> --config-dir <config> --tested-registry <registry>
```

The cycle auto-generates an unseen modifier seed bank when `--seed-bank` is omitted, resumes partial acquisition in the same run identity, skips provider work when `universe.json` already exists, runs bounded exact SERP DD, finalizes the tested registry, and returns `RESUME_NO_BACKTRACK` for terminal runs.


## Acceptance state — 2026-10-07

- Runtime regression: 3/3 PASS.
- R24 one-path acceptance: 8 root modifiers acquired; discovery shortlisted 6; exact SERP returned 6/6 `DROP_SERP_SATURATED`; registry advanced to 127.
- R25 one-command acceptance through `discovery_cycle.py`: terminal `COMPLETE_NO_SURVIVOR`; 8 candidates tested; 7 `DROP_SERP_SATURATED`, 1 `WATCH_COMPETITION`; registry advanced to 135.
- R25 strongest watch only: snowboard-length cluster, not promoted.
- Current overall leader remains `Psychrometric HVAC Toolkit — WATCH_STRONG_CANDIDATE`.
- Next run identity should start at R26 or later. R20-R25 are terminal and must not be reacquired.
- Modifier miner now filters duplicate themes, exact-SERP-tested candidates, obvious informational noise, retail-calculator noise, weapon-related queries, and medical/YMYL calculator noise.


## Candidate lifecycle + durable anti-repeat — 2026-10-07

Terminal close now includes candidate registry reconciliation:

1. `discovery_finalize.py` updates `discovery-tested-v1.json`.
2. `candidate_registry_sync.py` renders the human candidate lifecycle projection from the tested registry + `config/candidate-lifecycle-v1.json`.
3. It syncs `Semrush Candidate Registry.md` and the machine mirror `Semrush Tested Registry.json` to Dropbox.
4. `SERP_DD_PASS` remains evidence only; it does not auto-promote a candidate into `PROJECTS/`.
5. Only `BUILD_TEST / ACTIVE VALIDATION / EXECUTION` candidates become project folders.

The sync also runs on `RESUME_NO_BACKTRACK` and zero-candidate terminal paths. If Dropbox reconciliation fails after SERP finalization, the cycle returns BLOCKED at sync; the next invocation reuses terminal artifacts and retries sync without reacquiring or re-running SERP work.

R25 resume acceptance verified twice: first run reconciled the registries, second run returned both Dropbox targets as `unchanged=true`.


## R26-R28 terminal continuation — 2026-10-08

- R26: 8 new modifier roots; 1 exact-SERP candidate, `jobs that don't require background checks`. Mechanical outcome `BLOCKED_INCOMPLETE_SERP`; business/lifecycle override `DROP_INFORMATIONAL_EMPLOYMENT_NOISE`. Employment informational-noise filter added.
- R27: 8 new modifier roots; 5 exact-SERP candidates. Four were `DROP_SERP_SATURATED`; Goodman warranty lookup mechanically passed with ~12.1K volume / KD26 / 4 exact tools top10, but the official Goodman domain occupied 7/10 results. Lifecycle override: `DROP_OFFICIAL_AUTHORITY_NO_BUILD`.
- R28: terminal `COMPLETE_NO_CANDIDATE`; no new SERP records.
- Exact-SERP tested registry after R27/R28: 141 records.
- Current #1 remains `Psychrometric HVAC Toolkit — WATCH_STRONG_CANDIDATE`.
- No R26-R28 result is promoted to PROJECTS.
- Next discovery identity: R29+.
- R28 seed bank in GitHub has been verified against the recovered runtime original and now matches the exact generated seed identities/timestamp.


## R29 terminal continuation — 2026-10-08

- R29 exact-SERP queue: 3 candidates.
- mixed fraction calculator: 12,690 cluster volume / median KD26.5 -> `DROP_SERP_SATURATED`.
- 50:1 gas/oil mix calculator: 2,020 cluster volume / median KD13 -> `DROP_SERP_SATURATED`.
- baluster spacing calculator: 1,140 cluster volume / median KD23.5 -> `DROP_SERP_SATURATED`.
- Terminal: `COMPLETE_NO_SURVIVOR`.
- Tested registry advanced 141 -> 144.
- Current #1 remains `Psychrometric HVAC Toolkit — WATCH_STRONG_CANDIDATE`.
- Next discovery identity: R30+.


## Catalog exhaustion behavior

When `modifier_seed_bank.py` has no unseen catalog roots left, `discovery_cycle.py` now terminates as `COMPLETE_CATALOG_EXHAUSTED` before `live_collect.py`. It still reconciles Candidate Registry state, but performs zero new provider acquisition. This makes calling the next round safe after the finite modifier catalog is exhausted.


## R30 terminal continuation — 2026-10-08

- R30 used the final 7 unseen roots in the current modifier catalog.
- Exact-SERP queue: 3 candidates.
- total variable cost -> `DROP_SERP_SATURATED`.
- county lookup by ZIP -> `DROP_SERP_SATURATED`.
- county lookup by address -> mechanical `SERP_DD_PASS` (3,380 cluster volume / median KD26 / 2.5 exact tools top10).
- Business override for county-by-address: `ABSORB_AS_ADDRESS_GEO_MODULE_NO_STANDALONE_BUILD` because economics are weak and the core mapping is commoditized by free official geocoding/geography data.
- Tested registry advanced 144 -> 147.
- Current #1 remains `Psychrometric HVAC Toolkit — WATCH_STRONG_CANDIDATE`.
- No R30 candidate is promoted to PROJECTS.
- After R30, the current modifier root catalog has no unseen entries; the next probe should terminate as `COMPLETE_CATALOG_EXHAUSTED` without provider acquisition.


## R31 catalog exhaustion — 2026-10-08

- Auto-seed bank generated with `themes: []`.
- `discovery_cycle.py` terminated as `COMPLETE_CATALOG_EXHAUSTED`.
- No Semrush provider acquisition was performed.
- Candidate Registry remained at 147 exact-SERP tested records and now reports that there is no next discovery run until the modifier catalog is expanded.
- Current #1 remains `Psychrometric HVAC Toolkit — WATCH_STRONG_CANDIDATE`.
- Recommended next gate is downstream product/business validation of Psychrometric; do not reopen R20-R31 or expand generic modifiers merely to force a winner.


## R31 catalog exhaustion probe — 2026-10-08

- Generated seed bank contains zero themes.
- `discovery_cycle.py` terminated as `COMPLETE_CATALOG_EXHAUSTED`.
- No Semrush provider acquisition was performed.
- Exact-SERP tested registry remains 147 records.
- Candidate Registry now reports terminal through R31 and modifier catalog exhausted.
- Do not open R32 until the modifier catalog itself is materially expanded.
- Current #1 remains `Psychrometric HVAC Toolkit — WATCH_STRONG_CANDIDATE`.


## Psychrometric downstream business gate — 2026-10-08

Search evidence remains attractive (18,180 combined toolkit demand; 4,040 KD<29; low-KD wedge SERP pass), but downstream product/business validation does not support greenfield BUILD_TEST.

Observed market coverage:
- full field diagnostics: measureQuick + Fieldpiece Job Link;
- browser process/chart/report workflows: PsychroView, HVAC-calcs, PsychroStudio;
- low-cost/offline standalone tools: multiple one-time-purchase/mobile competitors;
- free SEO-tool layer: broad HVAC calculator networks already cover psychrometric utilities.

WTP splits sharply between full ecosystems (~$49/user/month) and low-price standalone psychrometric tools (~$4-$10 one-time or low single-digit monthly pricing). A new standalone tool would compete in the low-WTP tier without a proprietary hardware/data/integration advantage.

Lifecycle override:
`Psychrometric HVAC Toolkit -> WATCH_NO_BUILD_ACQUIRE_ONLY`.

Scanner conclusion after R31 catalog exhaustion:
`NO_GREENFIELD_BUILD_CANDIDATE`.

Do not create a Psychrometric PROJECTS folder. Reopen only for an attractive already-ranked acquisition, material proprietary integration/data advantage, or a genuinely new market wedge.
