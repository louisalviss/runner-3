# D1 recommendation_runs — one-person, two-step guarded migration (2026-10-24)


## Source D1 still active + incomplete target date-coverage guard staged — 2026-10-31

**Fresh, zero-new-D1-query SOURCE evidence:** Existing [D1 Account Usage Watch #41161104801](https://github.com/louisalviss/runner-3/actions/runs/41161104801) 2026-10-31 02:41:12Z shows `runner3-content-intelligence` **1,012 rowsWritten / 471 writeQueries** for the UTC calendar date. Later [#41177032866](https://github.com/louisalviss/runner-3/actions/runs/41177032866) at **2026-10-31 06:32:30Z** shows **10,900 rowsWritten / 5,257 writeQueries**, source account-wide total **11,384 rowsWritten**. Therefore source production is still **actively writing on Oct31** (does not attribute table/individual writer). On Oct30 existing [#41142795907](https://github.com/louisalviss/runner-3/actions/runs/41142795907) 23:10Z source content DB had **53,160 rowsWritten and 4,026,039 rowsRead**; account-wide 54,948 rowsWritten. Do NOT run another big full-table audit when nearing daily read limits; these are already paid/read historical GitHub log receipts, not new Cloudflare API calls.

**Target metric report ambiguity FIX staged only:** Historical [TARGET read-only #40929887617](https://github.com/louisalviss/runner-3/actions/runs/40929887617) had **zero writeQueries only in returned groups**, but returned 2/4 UTC days for Content D1 and 1/4 for Core D1. Older `scripts/cloudflare_target_d1_recent_write_metrics_readonly.py` wrote `write_activity_detected=false` for an incomplete window, which could be misread as 'proved zero writes on all four days'. Existing audit branch `audit/d1-feature-drift-side-readonly-20261029` now also holds strictly bounded additive, read-only **report-semantics** updates in commits `e30e7fc41f91025f0c82dbd468870881ff530b15` and `af19cb62954ed4f12a92cbc9f9e9b9a4f75da1fa`:
- Explicit `calendar_window_coverage_complete` and `missing_days_utc` per database, and `all_target_databases_date_coverage_complete` overall.
- `write_activity_detected = true` when a returned group has positive writes; **null/unknown** when all returned groups show 0 but some dates are missing; **false** only when every requested date has a returned zero group. No day is silently zero-filled.
- Reject duplicate/out-of-range/negative metrics from the reader. Preserve original TWO GraphQL requests, 4-day UTC range, output redaction, `writer_quiescence_proven=false`, `cutover_ready=false`, zero D1 SQL/writes, zero Worker deployments and R2 calls.
- Alongside existing branch feature drift diagnostics, the exact branch files were replayed in an isolated, auto-cleaned Python directory with all `urllib.request.urlopen` calls blocked: **23/23 synthetic tests PASS, 0 failures, 0 errors, ZERO_CLOUDFLARE_REQUESTS** (13 feature parity + 10 target metric cases). This is not a GitHub PR/CI or a real Cloudflare acceptance run. Existing source/target production behavior unchanged.

**Additional readiness gate confirmed:** As of this turn GitHub Secret *names only* from `gh secret list` show `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW` and `CLOUDFLARE_TARGET_D1_WRITE_TOKEN` present but **`CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` absent**; contents of all Secrets remain unread. Existing `cloudflare-d1-recommendation-runs-guarded-insert.yml` has **no runs** returned. Its explicit `target_writers_quiesced=YES`, `row_safe_recovery=YES` and a live exact bookmark are not established. **DO NOT select YES or dispatch real INSERT.** Existing source Core deploy workflow list has no deploy newer than [#40784421607](https://github.com/louisalviss/runner-3/actions/runs/40784421607), but non-GitHub deployment cannot be ruled out.

**Decisions:** TARGET Worker binding census #40377262061 already established six Workers with none binding target Content D1 on its observation date; do not repeat it. Remaining blockers are **complete SOURCE/TARGET writer-owner coverage, explicit time-bounded source write-fence with in-flight drain, target external-writer exclusion, deletion-safe keyed reconciliation, and independently tested row-safe target rollback/escrow**. Further live auditing cannot substitute for these. **D1 HOLD / R2 COST_HOLD**. Branch unmerged; PR creation was blocked earlier, do not claim CI success or bypass tool safety by another route.



## Live target D1 query-write analytics — two actual read-only runs (2026-10-29 UTC)

**Latest user-triggered read-only run** [#40929887617](https://github.com/louisalviss/runner-3/actions/runs/40929887617), 2026-10-29 18:20:34Z, main HEAD `086788b7af6fcedb9001520a5e1e7dd0a045a9e4`: GitHub job `recent-write-metrics` **SUCCESS**, all 6 offline tests PASS, GraphQL step PASS, sanitized artifact ID `12921128485` uploaded. ZIP SHA256 `feba0c052c9d3ae0638f9da3729958eeff1c366b9d6c6bfc467bcbc753b763d8` was independently checked against the GitHub API artifact digest after download. Internal JSON:
- `calendar_window_utc`: **2026-10-26 through 2026-10-29** (four calendar dates inclusive).
- TARGET `runner3-content-intelligence`: returned **two groups only**, 2026-10-26 `write_queries=0`, 2026-10-29 `write_queries=0`. **2026-10-27 and 2026-10-28 NOT RETURNED** (missing, **NOT zero**); `write_queries_in_returned_groups=0`, `write_activity_detected=false`.
- TARGET `runner3-core`: returned **one group only**, 2026-10-26 `write_queries=0`. **2026-10-27, -28, -29 NOT RETURNED** (missing, **NOT zero**); `write_queries_in_returned_groups=0`, `write_activity_detected=false`.
- Explicit sanitized artifact flags: `analytics_api_available=true`, `live_writer_identity_verified=false`, `writer_quiescence_proven=false`, `queries_reflect_ongoing_inflight_requests=false`, `data_row_parity_verified=false`, `cutover_ready=false`, `d1_sql_requests=0`, `d1_writes=0`, `r2_requests=0`, `worker_deploys=0`.

**Prior independent existing run** [#40866816956](https://github.com/louisalviss/runner-3/actions/runs/40866816956) also completed SUCCESS; artifact ID `12893547943` downloaded and ZIP SHA256 `d0875094630142bee18a829d325d704f401aa28ef1d1175e31f422be94d5cd2d` checked. For the *same* 2026-10-26..29 UTC window it returned only **2026-10-26** at `write_queries=0` for EACH of the two target databases. The newer source returned an additional 2026-10-29 ZERO group for `content-intelligence`, but **no complete four-day coverage in either run**. Do not fill gaps with zero or extrapolate that the target had no historical writes.

**Inference:** Returned-group write query counts were zero. This is useful bounded negative evidence, **not** evidence of complete temporal coverage, non-Worker writer absence, in-flight drain or quiescence. The earlier complete target Worker binding census [#40377262061](https://github.com/louisalviss/runner-3/actions/runs/40377262061) remains valid for its observation timestamp only (6 Workers, only `volamidle-rogue` D1 binding; no target Content DB bindings). No new full-table D1 scan, no migration write, Worker deploy, R2 requests or stop/fence. Next step: independent approval/design for owner-scoped writer/in-flight fence, deletion lineage, target-only preservation, safe bookmark recovery/rollback, then consistent keyed reconciliations. **D1 migration HOLD; R2 COST_HOLD**.



## Target non-Worker write activity gate — existing read-only workflow, offline tests PASS (2026-10-30)

**Avoid duplicate work:** Read-back of this checkpoint reconfirmed that target Worker-to-D1 binding attestation was already completed in [#40377262061](https://github.com/louisalviss/runner-3/actions/runs/40377262061) on 2026-10-27. Six mutually consistent target Workers, zero cron schedules, only `volamidle-rogue` binds `volamidle-rogue-data`; remaining five have no D1 bindings. Thus **NO target deployed Worker then had a D1 binding to `runner3-content-intelligence`**. Do not rescan target Worker inventory just for the same fact, and do not extrapolate this to all non-Worker writers or Oct30 freshness.

**Existing next gate found, NOT dispatched:** [`.github/workflows/cloudflare-target-d1-recent-write-metrics-readonly.yml`](https://github.com/louisalviss/runner-3/actions/workflows/cloudflare-target-d1-recent-write-metrics-readonly.yml) is an existing **manual** `workflow_dispatch` read-only analysis workflow. Its script `scripts/cloudflare_target_d1_recent_write_metrics_readonly.py` sends **2** bounded Cloudflare GraphQL analytics queries for `runner3-content-intelligence` and `runner3-core` in the TARGET account, covering four UTC calendar days, no SQL/rows, Worker deploy or R2 access. Its outputs are aggregate `writeQueries` per day; HTTP/API errors are redacted; its contract explicitly marks `writer_quiescence_proven=false` and `live_writer_identity_verified=false`. Zero observed write queries (if obtained) cannot prove there are no delayed, external, future, or in-flight writes; positive counts only prove account/database activity, not owner, changed row count or D1 table.

**Independent tests:** The exact existing script/test source on `main` was loaded, replayed into an auto-cleaned isolated temporary Python directory with `urllib.request.urlopen` blocked, and `unittest` run via connected SentinelX: **6/6 synthetic tests PASS, 0 failures, 0 errors, NO_NETWORK**. No Cloudflare API call, new action run, new PR, R2 request, production write, writer disable or cost escalation. The recent-run inventory checked in the current task did not establish a completed current target metric receipt; **do not assert no target writes**.

**Next optional user-controlled observation:** Only when an explicitly permitted read-only Cloudflare query is desired, manually dispatch the *existing* TARGET D1 Historical Write Metrics workflow on `main`, then validate its job success and sanitized artifact; do not rerun full `content_features` scan or reinterpret query metrics as quiescence. Pending: confirm other external API clients, future deployments, in-flight requests, rollback escrow, deletion lineage and final source write fence with separate approval. Cutover remains **D1 HOLD** and **R2 COST_HOLD**.


## Live source D1 write evidence + deployed writer code attestation — 2026-10-30

**Live source account usage evidence (not table-level attribution).** Source-only hourly [D1 Account Usage Watch #40798918028](https://github.com/louisalviss/runner-3/actions/runs/40798918028), [#40836747987](https://github.com/louisalviss/runner-3/actions/runs/40836747987), and [#40902211395](https://github.com/louisalviss/runner-3/actions/runs/40902211395) all passed on 2026-10-29. Their logs carry monotonically increasing UTC-day cumulative `runner3-content-intelligence` `rowsWritten` totals **935** (01:11:52Z), **19,797** (07:38:41Z), and **36,541** (15:30:18Z), respectively. Source account-wide totals at those observations were **1,019**, **20,354**, **37,969**. So SOURCE database *definitively saw billed row-write operations*, but the watch aggregates do NOT identify table, request, mutation type, count of distinct changed PKs, or writer. This alone does NOT prove whether `content_features` vs `user_content_events` or other tables caused run #40907537967's feature instability. **No new Cloudflare API requests were made** to obtain this evidence: existing GitHub run logs only.

**Latest inspected source Worker deployment receipt:** [Runner3 Core Production Deploy #40784421607](https://github.com/louisalviss/runner-3/actions/runs/40784421607) (2026-10-28 23:02 UTC / 2026-10-29 06:02 VN), source commit `bbe0e1646a8161fdc133febdc885cf6aeffc4731`. The **deploy step succeeded**: `Uploaded runner3-core`; `Deployed runner3-core triggers`; production workers.dev address and schedule `17 * * * *`; `Current Version ID: 1465c17c-b712-4c79-8b46-4067a249b959`; live Wrangler binding listing includes `env.CONTENT_DB (runner3-content-intelligence)`. Overall workflow **FAILURE** arose only **AFTER** deploy in Reader smoke check (`AssertionError: missing creator`), so do NOT interpret overall action FAILURE as a failed/rolled-back deploy. It is still necessary to separately verify current live deployed version if another external deploy route is suspected.

**Source-code-to-deploy attestation:** GitHub exact blob SHA readback at deployed commit `bbe0e164` and current `main` matched for all five relevant files: `src/content-feature-enrichment.js`, `src/rss-reader-learning.js`, `src/content-intelligence.js`, `reader-media-entry.js`, and `src/domain-db.js`. Therefore the following writer behavior is supported by the code that was actually checked out and deployed at that run, not solely contemporary source:
- `replaceAutoSemanticFeatures` inserts, updates **and deletes** rows in `content_features` when generated features vary; cannot assume append-only CDC.
- `content-intelligence.js` supports authenticated feature/item and interest-upsert write routes.
- RSS Reader library GET/learning routes can cause `ensureContentItem`→`replaceAutoSemanticFeatures`, including background `waitUntil`; pausing only GitHub RSS ingestion cannot guarantee quiescence.
- `src/domain-db.js` `contentEnv` routes to `CONTENT_DB`.

**No second source of truth or new production writer.** Still no evidence of target writer quiescence, in-flight drain, deletion/tombstone lineage or exact rollback; maintain D1 migration HOLD and R2 COST_HOLD. The diagnostic change is still on branch `audit/d1-feature-drift-side-readonly-20261029`, synthetic tests 13/13 PASS; PR creation was blocked, PR/CI/merge NOT confirmed. Do not dispatch repeated costly scans to infer account side while source writes remain active. Cloudflare [Sessions documentation](https://developers.cloudflare.com/d1/best-practices/read-replication/) explicitly provides sequential (monotonic) consistency, not a frozen multi-request snapshot, and is Worker-binding-only (not REST). [D1 Export documentation](https://developers.cloudflare.com/d1/best-practices/import-export-data/) says export blocks other database requests; not an authorized workaround.

**Next executable gate:** Independently establish the currently deployed Worker routing/version and target writer runtime coverage; propose a temporary, explicitly approved application-level write-fence that covers all source + target write paths (POST + GET-triggered learning + background `waitUntil`, scheduled/queue workers and externally authenticated callers), verify in-flight drain and a safe rollback bookmark/recovery test before a final fixed-snapshot keyed reconciliation. No production write, Worker deploy, writer stop or R2 operation authorized in this task.



## D1 content_features writer inventory + offline drift diagnostic — 2026-10-29

**Why the read-only scan failed:** [run #40907537967](https://github.com/louisalviss/runner-3/actions/runs/40907537967) stopped at `FEATURE_SNAPSHOTS_UNSTABLE` while comparing two sequential keyed+payload HMAC captures; account side and changed keys were unobservable from that run. No raw rows or hashes exported; no D1 mutation.

**Source-code writer census (potential writers, NOT live per-writer mutation proof):**

1. `cloudflare/runner3-core/src/content-intelligence.js`:
   - POST `/content-intelligence/items` performs `content_items` upsert and calls `replaceAutoSemanticFeatures` per item; POST `/content-intelligence/features` upserts `content_features`.
   - POST `/content-intelligence/interests/ingest` upserts the item and any supplied explicit features (no auto-rebuild in that endpoint). Legacy `/interests/save` calls auto-enrichment as well.
2. `cloudflare/runner3-core/src/content-feature-enrichment.js` `replaceAutoSemanticFeatures`: when generated features differ, **DELETE** stale rows in `AUTO_MODELS=` [`reader-bridge-v2`, `semantic-bridge-v3`, `semantic-bridge-v4`] for that item, then INSERT/UPDATE current generated feature keys. Therefore neither `updated_at`-only catch-up nor additive-only replay covers all mutations.
3. `cloudflare/runner3-core/src/rss-reader-learning.js`: `ensureContentItem` calls auto-enrichment. `reconcileLibraryLearning` invokes it when library articles are read/selected; POST deep-read/follow-up and reader state/preferences also invoke it. `reader-media-entry.js` routes library-v2 GET through an async `reconcileLibraryLearning` `waitUntil`, and reader learning POST handlers through `contentEnv`. This can mutate source Content D1 during apparently read-oriented UI activity.
4. `scripts/content_intelligence_client.py` `ingest-manifest` POSTs item batches plus feature batches. `.github/workflows/rss-reader.yml` invokes it on both today/yesterday manifests, **but its trigger is push/manual, not schedule**. Last observed `rss-reader.yml` run in 2026-10-29 review was 2026-10-09. It is a potential writer, **not established as the active feature writer** on 2026-10-29.
5. VPS `/opt/content-intelligence-bridge/content_intelligence_dropbox_bridge.py` process was observed running; its hotpath POSTs `/content-intelligence/interests/ingest` for eligible Interest saves. Its local state as read had `last_error=HTTP 500`, old `last_ok_at=2026-09-30`; therefore successful current writes are **not established**. Other external callers/target-account writers have not been exhaustively inventoried.
6. Repository `cloudflare/runner3-core/wrangler.jsonc` binds `CONTENT_DB` to SOURCE `runner3-content-intelligence` D1 ID `9cbec4ec-c930-459d-9499-9c66166c9241`. `src/domain-db.js` `contentEnv` selects `CONTENT_DB`. This is source-code routing evidence, not a current deployed-config digest.

**Diagnostic implementation (not merged):** Branch [`audit/d1-feature-drift-side-readonly-20261029`](https://github.com/louisalviss/runner-3/tree/audit/d1-feature-drift-side-readonly-20261029) holds commits `ed5774695ae2cb6d70cad069d2bdfc6bfadcb946` and `e18859587e8e30e882fccfeb5ca10a19a0b7460c`: on a read-only unstable snapshot it identifies SOURCE vs TARGET and returns aggregate `keys_added`, `keys_removed`, `shared_payload_changed`, with no raw PKs/values/fingerprints and **no extra Cloudflare queries**. Synthetic tests executed independently via SentinelX one-off Python `unittest` with urllib disabled/blocked, auto-cleaned temporary directory: **13 tests, 0 failures, 0 errors, NO_NETWORK**. This is an **offline test only**, not a GitHub PR CI or a live Cloudflare scan. PR creation was rejected by tool safety gate and [PR #507](https://github.com/louisalviss/runner-3/pull/507) was NOT found when checked; **do not claim merged/production-ready** or work around denial. Existing main script unchanged.

**Safe next gate:** Before any rescan or write freeze, resolve source **and target** writer ownership and runtime coverage (including GET-triggered `waitUntil`, authenticated POST API, scheduled/queue callers, replay jobs and third-party clients). Design a time-bounded application-level write fence with in-flight drain and verified rollback / Time Travel bookmark recovery; get separate production approval before enabling it. Do **not** disable browser interactions, global timers, Cloudflare Workers or target writes on code evidence alone. The quiescent final scan must include deletes/tombstones and target-only preservation, followed by replay/cutover only with distinct authorization. R2 `COST_HOLD` remains independent. Cloudflare D1 Sessions bookmarks do not supply an atomic frozen snapshot across many source and target queries.

**Current status:** production D1 writes by this audit **0**; R2 by this audit **0**; migration/cutover **HOLD**; unresolved `content_features` keyed parity **HOLD**.


## Live content_features stability gate — run #40907537967 (2026-10-29)

[Manual read-only workflow #40907537967](https://github.com/louisalviss/runner-3/actions/runs/40907537967) used HEAD `cc9c43a426a634e92251ba0397a3572430f552c8`. `recommendation-runs` completed **SUCCESS**; the opt-in `content-features` job was actually **RUN**, unlike #40905131992 where it had been skipped. Feature job **FAIL (exit 3)** with canonical script message **`D1_CONTENT_FEATURES_AUDIT_HOLD FEATURE_SNAPSHOTS_UNSTABLE NO_WRITES`**; the feature artifact was not emitted. The two bounded sequential snapshots `src1/src2` or `dst1/dst2` disagreed in keyed/HMAC payload state. The fail-closed routine does not disclose which account(s) drifted or whether keys vs payload changed. **Do not report missing/conflicting feature counts.** This is not the previous 8-minute timeout or missing manual input; the audit detected instability under the separate 12-minute budget.

Other completed same-run read-only results:
- `user_content_events`: SOURCE **6,925** (5,017 common matching plus 1,908 SOURCE-only), TARGET **5,017**, **0 TARGET-only**. SOURCE has grown +4 since #40905131992.
- `content_items`: **2,853** common PKs, 2,768 shared payload matches, **85** payload conflicts.
- No production D1 mutations, R2 requests, worker deploy, feature data export, restoration or cutover in this run.

**Decision:** Keep **`content_features` = NOT AUDITED TO COMPLETION / HOLD**, D1 migration/cutover **HOLD**, R2 `COST_HOLD`, SOURCE authoritative, and preserve all preexisting TARGET rows. No repeated full-table scans on an actively changing dataset just to chase a transient stable interval; first establish owner-controlled SOURCE/TARGET writer inventory, a defensible temporary quiescence/fence or snapshot solution, deletion lineage, full row-safe rollback/recovery rehearsal and bounded delta catch-up. The other tables' prior parity results do not override this independent gate. Resume only with an approved read-only stability/consistency plan that retains strict caps and does not incur unapproved metered costs.



## Latest run #40905131992 — base PASS, optional features job SKIPPED (2026-10-29)

[Actual manually triggered read-only workflow #40905131992](https://github.com/louisalviss/runner-3/actions/runs/40905131992) ran on `main` after [PR #506](https://github.com/louisalviss/runner-3/pull/506). The original `recommendation-runs` job **completed SUCCESS** with no failed steps. The distinct `content-features` job **completed SKIPPED** (not timeout, not an observed schema/cost failure). There is **no `d1-content-features-keyed-readonly` aggregate artifact**, and **no completed live keyed feature comparison**. The dependent job uses `if: ${{ inputs.audit_content_features }}` and its required predecessor succeeded, so the most likely issue is that this input evaluated false/unset at dispatch; exact GUI selection is not independently observed. Keep feature parity unproven.

Same run's audit logs provide updated SOURCE/TARGET event semantic multiset: SOURCE **6,921**, TARGET **5,017**, matching occurrences **5,017**, SOURCE-only **1,904**, TARGET-only **0**. This is +15 source-only events versus prior #40880438525 (6,906/5,017, 1,889 missing). `content_items` recheck: 2,853 shared primary keys, 2,768 matching payloads, **85 shared metadata conflicts**. Upstream `content_features` aggregate preflight still reports a capped source count, not exact keyed parity. No data D1 write, Worker deploy, R2 migration, feature replay or cutover was authorized.

**Next action (only needed user UI step):** In the EXISTING [manual workflow](https://github.com/louisalviss/runner-3/actions/workflows/cloudflare-d1-first-live-row-parity.yml) choose `Run workflow` → `main` → check **Include bounded content_features keyed HMAC audit (read-only)** (`audit_content_features=true`) → launch. Verify the resulting `content-features` job is **RUNNING then SUCCESS** (not SKIPPED), and read the aggregate artifact. Preserve all production D1, source writers, target-only data, rollback and R2 **HOLD**. No new transport or bypass of earlier chat-tool invocation safety gate.

## Content Intelligence D1 upstream feature timeout recovery — 2026-10-29 (LATEST; no production writes)

**Evidence:** [Existing read-only workflow #40880438525](https://github.com/louisalviss/runner-3/actions/runs/40880438525) was manually dispatched on `main` after [PR #505](https://github.com/louisalviss/runner-3/pull/505) merged. The single original `recommendation-runs` job was **cancelled** while running the new `content_features` production read-only audit: its old overall `timeout-minutes: 8` was exhausted after lengthy earlier serial audits. The feature-specific **10/10 offline synthetic tests PASS** but **NO complete feature parity receipt exists** from this run. Do not label feature keyed parity PASS.

Completed earlier read-only steps in that run included:
- `content_items`: 2,853 common PKs; 2,768 exact shared rows, 85 shared metadata payload differences, no newly approved merge rule.
- `user_content_events`: 5,017 semantic occurrence matches; SOURCE 6,906, TARGET 5,017, SOURCE-only **1,889**, TARGET-only **0**. These are database-ID-independent HMAC occurrence counts, not permission to insert; source grew three events since prior 6,903/1,886 audit.
- `content_features`: old schema/count receipt remains lower-bounded SOURCE >=19,000 versus target 14,328; current exact shared/missing/changed feature key counts **unknown**.
- No INSERT, UPDATE, DELETE, Worker deployment, rollback, R2 operation or cutover was performed.

**Engineering fix:** [PR #506](https://github.com/louisalviss/runner-3/pull/506) merged into `main` at `d3dc1279b7aab656a8361eb1b795dff38331db28`; its offline CI PASS. Keep **same** manually dispatched workflow and default-OFF `audit_content_features` flag. Legacy `recommendation-runs` now has a 10-minute budget. An optional dependent `content-features` job has its **own 12-minute budget**, consumes the sanitized `d1-upstream-three-bounded-counts-readonly` receipt from the **same workflow run** via artifact download (no repeat preflight scan), executes the same two-pass bounded HMAC-keyed read-only script, and emits only aggregate counts if fully successful. Existing `content_features` SQL/row-cost/privacy caps remain unchanged.

**New-run status:** A post-merge attempt to trigger the existing manual audit was refused by the chat-side tool safety gate **before SentinelX/VPS execution**. This is *not* a D1/schema/credential failure and does *not* prove a new workflow was dispatched. The latest verified production run remains #40880438525 (cancelled); no post-fix feature results have been observed. Do not work around the refusal by alternate transports.

**NEXT GATE:** An authorized operator must run the *existing* [Cloudflare D1 First Live Row Parity (Read Only) workflow](https://github.com/louisalviss/runner-3/actions/workflows/cloudflare-d1-first-live-row-parity.yml) with branch `main` and `audit_content_features=true`, within the established cost budget. Read the terminal run status **and** `d1-content-features-keyed-readonly` aggregate artifact before deciding any reconciliation. If scan caps, drift or credentials fail, keep HOLD and investigate separately. Even a complete audit PASS does **not** authorize replay, profile recompute, target writes or cutover. Keep SOURCE authoritative, preserve target-only rows, and require a tested exact row-safe rollback, writer quiescence/fence, deletion lineage and independently approved migration plan. R2 remains independent `COST_HOLD`.


## Prior live source/target user_content_events semantic multiset — 2026-10-29 (historical, no writes)

[Existing D1 read-only row-parity workflow #40877737399](https://github.com/louisalviss/runner-3/actions/runs/40877737399) completed **PASS** after [PR #503](https://github.com/louisalviss/runner-3/pull/503). Source and target D1 `runner3-content-intelligence` were each scanned twice with a strict primary-key cursor (100-row pages, hard 9,000-row cap per account). Rows were compared as an **occurrence multiset** using session-random HMACs over all semantic columns **except** the database-local `id`; no integer IDs were joined across accounts and no raw event contents, PK values or HMACs were exported.

| Observation | Count |
| --- | ---: |
| SOURCE event occurrences | **6,903** |
| TARGET event occurrences | **5,017** |
| Semantically matching occurrences across both | **5,017** |
| Source-only semantic occurrences | **1,886** |
| Target-only semantic occurrences | **0** |
| Exact duplicate semantic occurrences (both individually) | **0** |

Each account's two sequential reads were stable within this run. Cloudflare source increased by six occurrences compared to the older count (6,897 → 6,903), so this is **not** proof of writer quiescence or atomic cross-account snapshot. An occurrence match does not demonstrate that the accounts' auto-increment IDs are the same, does not establish real-world event identity beyond full stored field equality, and is not permission to replay any event.

**Migration implication:** The 5,017 target events are preserved. 1,886 source-only semantic occurrences are *potential* catch-up candidates, subject to preserving existing target data, checking exact referenced `content_items.item_id`, establishing safe idempotent event provenance/deduplication and local ID remapping (and any other dependent foreign keys), bounded quiescence and tested row-safe recovery. Never directly copy source `id` values into the independently auto-incrementing target. A one-pass replay while source is active can miss later events; require delta catch-up and fresh verification at approved cutover.

Prior [content_items row payload check #40876217743](https://github.com/louisalviss/runner-3/actions/runs/40876217743) showed 4,674 source, 2,853 target, 1,821 source-only, zero target-only, 85 shared metadata conflicts; the source had already grown since initial count. `content_features` remains SOURCE **≥19,000** versus TARGET 14,328 (only bounded aggregate counts; not keyed/payload parity). The production profile tables must not be recomputed before their base tables are complete. R2 cost gate, production D1 apply, Worker deploy, and cutover stay **HOLD** until recovery and writer quiescence are proven. No D1 write, R2 request, restore, worker deploy or cutover in the audit.


## Latest live content_items payload reconciliation — 2026-10-29 (HOLD, no production write)

[Bounded two-pass read-only HMAC payload check #40876217743](https://github.com/louisalviss/runner-3/actions/runs/40876217743) after [PR #500](https://github.com/louisalviss/runner-3/pull/500) and test-only [PR #501](https://github.com/louisalviss/runner-3/pull/501) **PASS**. Existing row-parity workflow reused the source read secret and NEW scoped target audit token. PK-cursor pages of at most 100 rows, fixed 5k cap per account, source+target double read and count-to-key receipts verified stability in this run; no row/PK values, HMACs, URLs, titles or arbitrary metadata were saved in logs or artifacts. **Zero D1 writes, zero R2 requests, no Worker deploy.**

| Field | Current source | Current target |
| --- | ---: | ---: |
| `content_items` rows | **4,674** | **2,853** |
| PKs shared | **2,853** | **2,853** |
| Shared PKs with whole typed row identical | **2,768** | **2,768** |
| Shared PKs with some payload differences | **85** | **85** |
| Source-only PKs | **1,821** | — |
| Target-only PKs | — | **0** |

Within the 2,853 shared PKs, differing column counts: `last_seen_at=85`, `metadata_json=82`, `published_at=2`. The following columns have **0 observed differences**: `canonical_url`, `title`, `content_hash`, `source_type`, `source_name`, `source_key`, `raw_ref`, `language`, `captured_at`, `first_seen_at`. The 85 conflicts overlap across columns, so sums exceed 85. **These are only snapshot-level counts, not approved field merge rules.** Observe SOURCE `content_items` increased by 5 PKs since prior [#40873720661](https://github.com/louisalviss/runner-3/actions/runs/40873720661) (4,669 → 4,674), confirming source can change. Two passes within one run were stable, but account reads are not atomic and no continuous writer quiescence is proven.

**Decision for proposed migration (not authorization to execute):**
1. Reconcile base dependencies with bounded row+key evidence: `content_features` (SOURCE >=19,000, exact count unknown) and `user_content_events` (DB-local AUTOINCREMENT `id` not cross-account global identity); never copy child rows without a source/target identity mapping, matching item parents and tombstone/deletion policy.
2. For `content_items`, explicitly classify the **1,821 missing target PKs** as additive-only candidates, and **85 shared-PK metadata conflicts** as separate merge-policy decisions. Preserve all existing target PKs. Never assume last_seen_at, metadata_json or published_at should be overwritten without field ownership and writer quiescence proof.
3. Before any production D1 apply, establish secure, **usable** pre-apply recovery bookmark, independently tested rollback, bounded target writer quiescence and separate explicit approval. The public source-only HMAC receipt and empty SQLite DDL replay do not replace those conditions.
4. R2 migration remains under independent cost HOLD. Source remains production authority. Never set `target_writers_quiesced=YES`, `row_safe_recovery=YES` or `cutover_ready=true` on this evidence.

Current status: `CONTENT_ITEMS_BOUNDED_PAYLOAD_PARITY_HOLD_NOT_CUTOVER` with `rollback_ready=false`, `target_writer_quiescence_verified=false`, `d1_write_requests=0`, `cutover_ready=false`.


## Upstream materialized-profile base tables: bounded counts + content_items PK-only HMAC census — 2026-10-29 (latest, migration HOLD)

[Workflow #40873720661](https://github.com/louisalviss/runner-3/actions/runs/40873720661), after [PR #497](https://github.com/louisalviss/runner-3/pull/497) and [PR #498](https://github.com/louisalviss/runner-3/pull/498), completed all synthetic tests, three-table count/schema preflight, and additional **content_items PK-only** HMAC source/target comparison. It used SOURCE read credential and verified NEW TARGET Audit Secret only; no D1 WRITE credential passed. No raw item IDs, per-key HMACs, raw application payloads, or secrets were exported or logged. **No D1, Worker, R2 or restore mutations.**

**Three upstream tables in `runner3-content-intelligence`** are required by canonical `profileProjectionCte` and `recomputeInterestProfile` before derived interest profiles can be safely rebuilt:

| Table | SOURCE bounded count | TARGET bounded count | Source minus target aggregate | Count interpretation |
| --- | ---: | ---: | ---: | --- |
| `content_items` | **4,669** | **2,853** | **+1,816** | Exact count below fixed 6,000 cap on each account |
| `content_features` | **≥19,000** | **14,328** | **≥4,672** | SOURCE hit 19,000 fixed cap; never claim exact count or exact delta |
| `user_content_events` | **6,897** | **5,017** | **+1,880** | Exact count below fixed 9,000 cap on each account |

Schema columns and declared PKs matched live between accounts for all three tables. The bounded `COUNT` reads are not keyed row/payload or deletion parity and are **not atomic snapshots**. We did **not** increase caps after the initial [HTTP-independent safety stop #40872610472](https://github.com/louisalviss/runner-3/actions/runs/40872610472) identified `COUNT_CAP_REACHED_content_features`. PR #497 instead reports capped counts as *lower bounds* and retains fixed aggregate read-budget 40,000 rows per account.

**New content_items key identity result** (exact source+target counts consistent with same-run preflight):
- SOURCE PK count 4,669; TARGET PK count 2,853.
- Shared `item_id` PKs **2,853**, SOURCE-only **1,816**, TARGET-only **0**.
- The `item_id` set was fetched once/account using fixed `SELECT item_id FROM content_items ORDER BY item_id LIMIT 5001`, checked against bounded counts, then compared with a fresh in-memory HMAC session key. The HMAC secret, raw item IDs and HMAC values were never serialized. **This is a single sequential account snapshot: no stability re-read, no cross-account atomicity.**
- This proves only current **key presence** and that the target PK set was a subset of source at that read. **No payload comparisons** were done on the shared 2,853 rows; do not infer they are identical. **Do not automatically insert all 1,816 keys** until source/target content payload ownership, tombstones and source/target write quiescence plus recovery are independently established. Target-only absence at one snapshot does not authorize deletion logic elsewhere.

**Next safe priorities, with no production write permission:**
1. Verify complete, bounded *payload* parity of `content_items` common keys using ephemeral HMAC and explicit cost/privacy budget; preserve target-only records and deletions if any appear later.
2. For `content_features`, use a separately budgeted PK-cursor/paginated comparison **without raising the established 19k count cap implicitly**. Current actual source row count is unknown. Index/metadata should be checked before a larger read.
3. `user_content_events.id` is `INTEGER PRIMARY KEY AUTOINCREMENT` **scoped to each database**. Do NOT treat equal numeric ID across source/target as proof of identical semantic events; inspect original event identity/deduplication lineage and deletion policy before HMAC keyed parity or replication.
4. Maintain `DERIVED_PROFILE_RECOMPUTE_BLOCKED_UPSTREAM_PARITY_AND_RECOVERY` as established by [PR #492](https://github.com/louisalviss/runner-3/pull/492); no direct profile `weight` overwrite, no deletion of one target-only interest-profile key. Fresh recovery bookmark remains uninstalled and writer quiescence unproven. R2 cost HOLD, production INSERT and cutover HOLD.


## FIXED: derived interest profiles require upstream parity before recomputation — 2026-10-29

[PR #492](https://github.com/louisalviss/runner-3/pull/492) added a **fail-closed, no-write derived-profile reconciliation gate** to the **existing** manually dispatched `cloudflare-d1-first-live-row-parity.yml`; eight new offline synthetic tests PASS. [Real Cloudflare read-only workflow #40870331372](https://github.com/louisalviss/runner-3/actions/runs/40870331372) PASS, including the gate receipt `d1-derived-profile-reconciliation-hold`, with zero D1 writes, R2 requests or Worker deployments.

Live HMAC-keyed source/target summaries (no source values, keys, or hashes exported):
- `runner3-content-intelligence.interest_profile`: SOURCE **28**, TARGET **26**; **25** shared PKs, **4** identical payloads and **21** shared payload conflicts. **Three** source-only keys and **one target-only key**. Across the 21 shared conflicts, `weight` changed in 21 and `updated_at` in 21; evidence/positive/negative/confidence counts match. **Preserve the target-only record** pending lineage / deletion review. Never delete or overwrite automatically.
- `runner3-content-intelligence.interest_family_profile`: SOURCE **13**, TARGET **13**; all 13 PKs shared, **1** identical payload and **12** shared payload conflicts. `weight` and `updated_at` each changed in 12; one shared record additionally differs in `evidence_count`, `positive_count` and `confidence` (negative count differences: zero).
- The production source `cloudflare/runner3-core/src/content-personalization.js` builds `profileProjectionCte` from `content_features` and `user_content_events` and calls `recomputeInterestProfile` to INSERT/UPDATE/DELETE in both derived profile tables. The profile tables are **MATERIALIZED DERIVED OUTPUTS**, **not** authoritative direct source-of-truth tables. Copying `weight` across accounts or blindly calling recomputation on a database with incomplete underlying content/events could corrupt scores or delete legitimate target-only state.

**Correct safe sequence:** (1) reconcile/uphold source authority for `content_items`, `content_features` and `user_content_events` including deletion/tombstone and target-only lineage; (2) independently establish target writer quiescence and preservation policy for the target-only profile PK; (3) capture fresh pre-apply bookmark and demonstrate authorized row-safe rollback; (4) only after separate production approval run `recomputeInterestProfile` using the canonical Worker logic; (5) recompare both profile tables, dependent `content_scores` and overall D1 keyed row parity. `workflow_state` source-only and other control-plane tables must also be resolved before enabling the runtime.

**Live gate result:** `DERIVED_PROFILE_RECOMPUTE_BLOCKED_UPSTREAM_PARITY_AND_RECOVERY` with `upstream_row_parity_verified=false`, `writer_quiescence_verified=false`, `recovery_bookmark_installed=false`, `direct_copy_authorized=false`, `recompute_authorized=false`, `production_target_changes=0`, `cutover_ready=false`. This PR **fixes the migration decision/guard**, NOT production D1 data. The earlier read-only `recommendation_runs` 47-vs-35 dry-run still requires its separate guards. Keep all Cloudflare D1 writes/restores and R2 migration on HOLD.


## Live two interest profile tables keyed-parity & column attribution — 2026-10-29 (NEW, HOLD)

[Two-profile first bounded live HMAC comparison #40868655035](https://github.com/louisalviss/runner-3/actions/runs/40868655035) and follow-up [column-level aggregate #40869143828](https://github.com/louisalviss/runner-3/actions/runs/40869143828), implemented in the **existing** read-only row-parity workflow through [PR #489](https://github.com/louisalviss/runner-3/pull/489) and [PR #490](https://github.com/louisalviss/runner-3/pull/490), all PASS operationally. Both runs used independently scoped source and target read credentials; validated exact source/target column metadata and declared PKs, read each table twice with a strict 100-row cap, and compared one-time in-memory HMACs for identity, complete typed payloads and non-PK column values. Sensitive row content, PKs, per-row HMACs, session secrets and profile names/values were never exported. D1 writes, R2 and Worker deploys = 0.

**Detailed sanitized evidence (data equality did NOT pass):**

| D1 table | Source | Target | Identical key+payload | Source-only PK | Target-only PK | Shared-PK payload mismatch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `runner3-content-intelligence.interest_family_profile` | 13 | 13 | 1 | 0 | 0 | 12 |
| `runner3-content-intelligence.interest_profile` | 28 | 26 | 4 | 3 | 1 | 21 |

**Column-level counts among 13 shared family keys**: `weight` 12, `updated_at` 12, `evidence_count` 1, `positive_count` 1, `confidence` 1, `negative_count` 0. The counts are per-column: affected keys may overlap, and do not reveal values or change direction.

**Column-level counts among 25 shared interest keys**: `weight` 21, `updated_at` 21; `evidence_count`, `positive_count`, `negative_count` and `confidence` **0**. The remaining four shared keys have identical payloads. There are **three source-only and one target-only** profile keys, so a blind source overwrite could discard target-only state. The source/target changes may reflect derived score and timestamp drift, but the root cause or authoritative latest state is **NOT verified**. Timestamp columns are not reliable substitute for sequence/deletion lineage and do not justify merging.

**Action gate:** Do not auto-copy or overwrite profile tables. Determine authoritative owner and the recomputation model for `weight` and `updated_at`, compare source/target upstream `content_items`, `user_content_events`, `content_features`, `content_scores` and derived-profile lineage with bounded PK snapshots and a tombstone policy. An explicit resolution policy is needed for one target-only interest key and all shared-PK payload differences before any writer quiescence/cutover. The extant [recommendation_runs 47/35 read-only dry-run #40867548676](https://github.com/louisalviss/runner-3/actions/runs/40867548676) remains only one separate additive-table result (12 source-only, no conflicts).

**Migration status:** D1 row/content parity **HOLD**; source production remains authoritative; current snapshots are not atomic across accounts, not proof of absence of external writers. `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` remains absent at last verified metadata check, and real tested rollback remains unavailable. No production D1 writes/restores, no Worker changes, no R2 migration, no cutover.


## Refreshed 2026-10-29 recommendation_runs source/target bounded dry-run (latest; NOT authorized to write)

[Workflow #40867548676](https://github.com/louisalviss/runner-3/actions/runs/40867548676) completed PASS on the existing `cloudflare-d1-recommendation-runs-additive-dryrun.yml` read-only workflow. Re-read and compared small `runner3-content-intelligence.recommendation_runs` on both Cloudflare accounts twice, then simulated additive INSERT and row-safe reverse entirely in ephemeral local SQLite. Observed **47 source rows, 35 target rows, 35 existing matching rows, 12 missing target rows, 0 payload conflicts, 0 unexplained target-only rows**. Source and target each stable within the two reads; schema metadata equal. The local 12-row additive insertion and subsequent 12-row deletion simulation both PASS; scratch baseline restored exactly to the original 35 rows. This is one table only, not atomic cross-account snapshot or full-account row parity.

As of 2026-10-29, the GitHub guarded production D1 INSERT workflow had **no prior runs** returned by run listing. Repo Secret metadata still lists `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW` but **does not list `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK`**. Neither `target_writers_quiesced` nor `row_safe_recovery` is established, so **do not dispatch the real write job**, and do not set either safety confirmation to YES. No D1 write/restore, R2 request or Worker deploy occurred in this repeat dry-run. The target's production Time Travel API working is **not** a usable installed rollback bookmark.

Evidence scope: current only for `recommendation_runs`, source production unchanged and remains authoritative. Next needed gates are secure authorized fresh bookmark/rollback verification, independent live writer ownership/quiescence, and safe bounded keyed row reconciliation of additional DBs/tables. R2 migration remains HOLD. Do not infer global data parity or production migration readiness from this PASS.


## Current target write analytics and Time Travel — 2026-10-29 (latest, no writes, HOLD)

**Read-only evidence only; NOT proof of writer quiescence or rollback readiness.**

- [Target D1 GraphQL write-query analytics #40866816956](https://github.com/louisalviss/runner-3/actions/runs/40866816956) PASS, under [PR #486](https://github.com/louisalviss/runner-3/pull/486). Audited `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW` fetched read-only `d1AnalyticsAdaptiveGroups` for two pinned target D1s, `runner3-content-intelligence` and `runner3-core`, requested **2026-10-26 to 2026-10-29 UTC**. The GraphQL API returned **only 2026-10-26**, with `writeQueries=0` for each D1. **Dates 2026-10-27, 28 and 29 had no returned group**. Missing groups are NOT evidence of zero writes, no background clients or source-to-target quiescence. The workflow recorded `writer_quiescence_proven=false`, `d1_sql_requests=0`, `d1_writes=0`, `r2_requests=0`, `cutover_ready=false`. No write token was passed to the workflow. No per-client attribution is possible from these aggregate metrics.
- [Fresh target Time Travel eligibility #40866983692](https://github.com/louisalviss/runner-3/actions/runs/40866983692) PASS at **2026-10-29T11:39:01Z** for `runner3-content-intelligence`. Read-only GET confirmed correct target identity and production backend; current bookmark endpoint works. Raw bookmark was **not exported or preserved**; `bookmark_preserved_for_actual_restore=false`, `pre_apply_fresh_bookmark_verified=false`, `target_writers_quiesced=false`, `safe_restore_approved=false`, `cutover_ready=false`. Production restore is a whole-database, potentially destructive operation; none was attempted.
- GitHub Actions Secret `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` is **still absent** in the authenticated repo secret-name listing on 2026-10-29. The original VPS courier private-key decrypt/install action had been caller-side blocked. **Do not circumvent or reroute to extract the courier key or bookmark**. The prior encrypted 1-day evidence artifact is not proof of installed escrow. New escrow must be handled via separately authorized, secure process and a tested row-safe recovery plan, immediately before any approved target write.
- Earlier [39/39 DDL empty isolated SQLite rehearsal #40388871787](https://github.com/louisalviss/runner-3/actions/runs/40388871787) PASS structurally; [15 source missing-table data presence #40389799662](https://github.com/louisalviss/runner-3/actions/runs/40389799662) found **12 nonempty, 3 empty**. This does not mean data in any common-named DB matches. Authentication, magic-link and migration bookkeeping tables must have explicit retention/security handling, not automatic copying. Do not run unbounded `COUNT(*)` across all tables without a cost limit and review; D1 bills by rows read.
- **Remaining decisive gates**: explicitly identify/control non-Worker target D1 writers, prove bounded quiescence at time of cutover; secure an immediately pre-apply bookmark and tested rollback route without private-key policy bypass; reconcile all needed D1 keyed content, tombstones and preserved target-only stores; separately release R2 cost gate and cutover with user approval. No D1 schema apply, INSERT/DELETE, restore, Worker deployment, R2 migration, source deletion or cutover occurred in these audits.
- **Do not set either `target_writers_quiesced=YES` or `row_safe_recovery=YES` on the guarded INSERT workflow. Preserve all production services and keep migration on HOLD.**


## Live 15-table content-presence and FK-dependency checks — 2026-10-27 (latest, HOLD)

Two authenticated, bounded **read-only** workflows passed; both were synthetic-tested and run manually from `main`, with sanitized artifacts and no production writes.

1. [Source-only 15-table existence run #40389799662](https://github.com/louisalviss/runner-3/actions/runs/40389799662), from [PR #483](https://github.com/louisalviss/runner-3/pull/483). It made exactly 15 bounded `SELECT 1 AS present FROM "<allowlisted_table>" LIMIT 1` queries on SOURCE, not `COUNT(*)`, and returned only empty/nonempty flags with **no application row content**. 12/15 missing-on-target source tables were nonempty; 3 were empty.
2. [Isolated 39-DDL replay with FK dependencies #40390362550](https://github.com/louisalviss/runner-3/actions/runs/40390362550), from [PR #484](https://github.com/louisalviss/runner-3/pull/484). The already PASS full source-pinned 39/39 additive CREATE-only rehearsal now additionally fails closed if any source FK parent table is absent and summarizes table-level FK edges. Nine independent synthetic tests PASS. Still **zero D1 writes**.

**Source tables confirmed empty (no rows in source at time of query):**
- `runner3-content-intelligence.checkpoints` (composite PK)
- `runner3-core.artifact_library_pin_attempts` (one-column PK)
- `runner3-core.ebook_reader_trace_v113` (composite PK)

**Source tables confirmed nonempty (at least one row; exact row count and content are NOT known):**
- `runner3-content-intelligence`: `link_interest_events`, `workflow_state`.
- `runner3-core`: `artifact_library_auth`, `artifact_library_magic_links`, `checkpoints`, `d1_migrations`, `delivery_permalinks`, `events`, `r2_receipts`, `typed_kv`, `vps_mailbox_jobs`, `workflow_state`.

**Foreign keys in reconstructed `runner3-content-intelligence` source schema (all three are on tables ALREADY present at target):**
- `content_features` → `content_items`, `ON DELETE CASCADE`.
- `content_scores` → `content_items`, `ON DELETE CASCADE`.
- `user_content_events` → `content_items`, `ON DELETE CASCADE`.

`runner3-core` has zero declared FKs. **None of the 15 source-only missing tables is the parent or child of those three source-declared FKs**. This removes a DDL topological blocker in *empty scratch SQLite* but does not validate uniqueness, dependent triggers on populated targets, application referential consistency, or row copying order.

### Required migration treatment — policy, not automatic permission

- **Schema-only candidates:** three source-empty tables can be considered for CREATE-only staging, provided a fresh source check, target-empty/absence identity check and tested recovery are performed immediately before any actual DDL. Do not equate a source-empty snapshot with permanently empty tables.
- **Data-backed candidates:** 12 source-nonempty tables require bounded keyed row reconciliation, source/target create-definition/constraint verification, append-only or explicit conflict policy, and handling of changes while copying.
- **High-risk authentication/session state:** `artifact_library_auth`, `artifact_library_magic_links` must not be blindly migrated as live credentials or session links; require deliberate invalidate/reissue/preserve policy and leakage safeguards. `artifact_library_pin_attempts` is empty only at this snapshot.
- **Operational state and history:** `d1_migrations`, `workflow_state`, `vps_mailbox_jobs` require single-owner replay/idempotency and source authority decisions. Never automatically replay jobs or copy migration history.
- **R2-related metadata:** `r2_receipts` is nonempty and may encode external R2 references; remains separately subject to `CLOUDFLARE-R2-COST-001 HOLD` and its explicit operation-cost budget.
- **Triggers and remaining objects:** One missing trigger is verified locally as CREATE-only but **has never fired on a populated target**; 23 missing indexes have not been checked for unique-key conflicts against populated target rows.

GitHub Actions Secret metadata rechecked after these runs: `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW` and `CLOUDFLARE_TARGET_D1_WRITE_TOKEN` present; **`CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` still absent**. No validated immediately-pre-apply recovery/restore capability. External writer quiescence, full source/target keyed row/content/delete parity and authorization are missing. **DO NOT schedule or run live DDL, row INSERT, restore, Worker cutover or R2 operations; production migration remains HOLD.**


## All 39 source-pinned missing CREATE DDL — isolated empty SQLite rehearsal PASS (2026-10-27)

[Dispatch-only isolated replay #40388871787](https://github.com/louisalviss/runner-3/actions/runs/40388871787) on merged [PR #481](https://github.com/louisalviss/runner-3/pull/481) **PASS**. Uses the verified NEW Cloudflare target read-only Audit Secret plus independent source read-only token. Re-ran the existing source-pinned exact-six DDL capture and independently checked the 33 source-fingerprint-pinned CREATE candidates from versioned repository input. Both current target database identities and their schema metadata were checked via Cloudflare API without row content or any schema/data write. Candidate raw SQL existed **only in transient GitHub Action memory**; no raw CREATE SQL was stored in the artifact or log.

The workflow constructed the existing TARGET schema in empty, ephemeral in-memory SQLite, then applied source CREATE-only candidates in isolation and compared every resulting schema object name/CREATE definition against the LIVE SOURCE schema. It also checked no silent IF NOT EXISTS no-ops, no changes to preexisting target catalog objects, SQLite `integrity_check=ok` and FK schema metadata. Eight independent synthetic tests passed (including destructive statement and no-op rejection).

| D1 | Target existing objects | Source-pinned CREATE objects rehearsed | Simulated final schema objects |
| --- | ---: | ---: | ---: |
| `runner3-core` | 1 | 21 | 22 |
| `runner3-content-intelligence` | 9 | 18 | 27 |
| **Total** | **10** | **39** | **49** |

The reconstructed Content Intelligence schema contains **three foreign key constraints**, Core zero, as reported by local SQLite `foreign_key_list`. This counts constraint definitions, NOT live target FK compliance, target table size, source/target row count, or row-safety of schema migration. No real row content was loaded; uniqueness, FK enforcement on production rows, trigger execution/side-effects, migration ordering on data, table-by-table PK/row/delete/tombstone parity and retention of auth/migration state remain **UNPROVEN**. SQLite simulation confirms structural compatibility in empty scratch only, not actual apply safety.

**DO NOT auto-apply the 39 CREATE statements.** This result does not release `target_writers_quiesced`, `row_safe_recovery`, or the separate D1 WRITE approval. `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` secret still absent at last metadata check and previous private-key secret-install path blocked (do not reroute). External writers and full D1 rows are not reconciled; R2 cost gate remains HOLD; no Cloudflare writes, restore calls, Worker deploys, R2 operations or cutover occurred.


## Live source-only table PK census — 2026-10-27 (latest, still HOLD)

[Manual read-only PK workflow #40384940380](https://github.com/louisalviss/runner-3/actions/runs/40384940380) PASS after [PR #479](https://github.com/louisalviss/runner-3/pull/479), using the source-account read-only API credential and exact allowlisted `PRAGMA table_xinfo` for all 15 previously identified source-only tables. Independent six offline synthetic tests passed. There were **zero table row reads, zero D1 writes, zero R2 or target requests**. No raw column values/names, UUIDs, token values, or DDL definitions were serialized.

**Result: 15/15 source-only tables have a declared primary key**. 12 tables single-column PK; exactly three tables have two-column composite PKs:
- `runner3-content-intelligence.checkpoints` (8 total columns, two-column PK)
- `runner3-core.checkpoints` (8 total columns, two-column PK)
- `runner3-core.ebook_reader_trace_v113` (7 total columns, two-column PK)

The remaining 12 tables have a one-column PK: `link_interest_events`, `workflow_state` (in both DBs), `artifact_library_auth`, `artifact_library_magic_links`, `artifact_library_pin_attempts`, `d1_migrations`, `delivery_permalinks`, `events`, `r2_receipts`, `typed_kv`, `vps_mailbox_jobs`.

**Interpretation:** The PK design permits future deterministic key-based reconciliation in principle, subject to verifying index/constraint semantics, row payloads, deletion policy and auth/migration-state ownership. It **does not** prove one row is safe to copy, or that the target schema can be applied; target still lacks 15 tables, 23 indexes and 1 trigger. Avoid automatically copying auth secrets, magic links or migration bookkeeping merely because a PK exists.

GitHub secret `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` remains absent at last check. No approved independently tested escrow / row-safe recovery. External writer quiescence is unproven. Source production and R2 HOLD remain unchanged. **Never attest YES to the guarded D1 production INSERT workflow on this evidence.**


## Live 39-object schema gap decomposition — 2026-10-27 (latest, READ-ONLY)

[Source/target D1 schema diff #40384015167](https://github.com/louisalviss/runner-3/actions/runs/40384015167) completed **PASS** after [PR #477](https://github.com/louisalviss/runner-3/pull/477) (8 offline unit tests PASS independently, 0 D1 writes, 0 R2 requests). Source and target both have 9 D1; 8 names shared, 6 shared schema-identical. Source-only `clm-copilot-calibration` and target-only `louis-context-index` remain preserved pending independent owner/retention review.

The **39 source-only schema objects** are classified using live `sqlite_master` metadata (SQL definitions were compared but **not published**):

| Target database with incomplete schema | Missing tables | Missing indexes | Missing triggers | Missing views | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| `runner3-content-intelligence` | 3 | 14 | 1 | 0 | 18 |
| `runner3-core` | 12 | 9 | 0 | 0 | 21 |
| **Total** | **15** | **23** | **1** | **0** | **39** |

Tables missing on target, **names only**:
- `runner3-content-intelligence`: `checkpoints`, `link_interest_events`, `workflow_state`.
- `runner3-core`: `artifact_library_auth`, `artifact_library_magic_links`, `artifact_library_pin_attempts`, `checkpoints`, `d1_migrations`, `delivery_permalinks`, `ebook_reader_trace_v113`, `events`, `r2_receipts`, `typed_kv`, `vps_mailbox_jobs`, `workflow_state`.

**Safety and implementation order:** This is a schema-only census. No table counts, PK-based row digests, deletions, FK dependencies, trigger semantics, schema application or data reconciliation were established by this run. Some table names imply authentication or migration bookkeeping; name-based classification alone cannot establish retention or copy authorization. Verify **source-exact DDL plus table PK/constraints and indexes**, separately review credential-related and migration-history tables, validate dependencies in isolated SQLite, then construct additive-only DDL and independent keyed row reconciliation. A trigger must not be enabled before examining how it affects copied or preexisting rows. Do not automatically recreate all 39 objects from names.

Target Worker read-only binding census #40377262061 proves no *deployed target Worker* binds `runner3-content-intelligence`, but does not eliminate external token/API clients. On VPS, an additional read-only configuration scan on 2026-10-27 checked six relevant services, resolved two service EnvironmentFiles (without printing values), and found source Worker/account references but no literal target account UUID, target D1 UUID, or target Worker address. This is **negative static evidence only**: dynamically loaded settings and other clients remain possible writers. Do not set `target_writers_quiesced=YES` from these findings.

**Production readiness remains HOLD**: `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` GitHub Secret absent when last checked; authorized usable escrow + tested recovery unproven; full-account row/delete/tombstone parity missing; R2 cost HOLD. No D1 writes or Worker deployments, no source/target deletion or cutover.


## Target live D1 Worker binding attribution — 2026-10-27 (latest; migration HOLD)

**New result: complete read-only Worker-to-D1 attribution for the target account**. [Workflow #40377262061](https://github.com/louisalviss/runner-3/actions/runs/40377262061), after [PR #475](https://github.com/louisalviss/runner-3/pull/475) merged on main. The workflow uses scoped `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW`; both Worker lists show 6 matching Workers, all settings/schedules read successfully, target has 9 matching historical D1 identities. Zero cron schedules. It matches physical D1 binding IDs only in memory against the same **live target** D1 UUID map and publishes target D1 **names only**, no UUID or raw binding/secret.

- `volamidle-rogue`: binding `DB` matches live target D1 `volamidle-rogue-data`.
- The remaining 5 deployed Workers have **no D1 bindings**.
- `worker_d1_binding_attribution_complete=true`; `recommendation_runs_db_worker_binding_absent_verified=true`, referring **only to this account's currently deployed Worker bindings**. No target Worker binds directly to `runner3-content-intelligence`.
- **`target_nonworker_writers_excluded=false`, `writer_quiescence_proven=false`, `cutover_ready=false`**. API tokens and other external clients, source scripts, runners, remote jobs, and future Worker deploys have not all been proven idle; the Worker finding is not an authorization to attest quiescence or run INSERT.
- GitHub Secret metadata rechecked: `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW` and independent `CLOUDFLARE_TARGET_D1_WRITE_TOKEN` are present, but **`CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` remains absent**. No escrow recovery test, rollback readiness, real restore test or production D1 writes. Earlier encrypted bookmark may expire and must not be treated as installed.
- Earlier 39 source-only schema objects missing on target across `runner3-core` and `runner3-content-intelligence` remain an **unresolved historical gap**, not a statement of newly measured parity. Preserve source-only and target-only D1 objects. R2 remains cost-gated HOLD.
- Next safe work: investigate **non-Worker writers** without stopping source production; independently establish a verifiable bounded target quiescence procedure, solve authorized restoration bookmark escrow without bypassing prior caller-side private-key block, and build a full row/schema reconciliation plan. No automatic production write.


## New verified target Workers census — 2026-10-27 (supersedes earlier HTTP 403 findings)

**Worker audit token unblocked.** Operator created a **separate** GitHub Actions Secret `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW`, verified present in repository secret metadata 2026-10-26T17:08:50Z. Prior legacy `CLOUDFLARE_TARGET_AUDIT_TOKEN` was unchanged. Do not confuse either audit Secret with independent Write-only migration Secret `CLOUDFLARE_TARGET_D1_WRITE_TOKEN`.

[Manual read-only validation #40366950155](https://github.com/louisalviss/runner-3/actions/runs/40366950155) used the **NEW** Secret explicitly; target 9 D1 identity verification PASS and both Worker-list endpoints returned 6 matching workers (**Workers API HTTP 403 resolved**). All 6 settings and cron reads PASS, zero cron schedules reported. Redacted Worker binding summary:

- `balatro-clef-api`: Workers AI binding `AI`; zero cron.
- `khotruyen-worker`: no bindings; zero cron.
- `runner3-x-fast-direct`: no bindings; zero cron.
- `runner5-restore-proxy`: no bindings; zero cron.
- `volamidle-rogue`: one D1 binding `DB`; zero cron.
- `wave-rider-scanner`: no bindings; zero cron.

**IMPORTANT: NOT target writer quiescence proof.** The inventory deliberately redacts physical D1 binding UUIDs and does not prove whether the sole D1 Worker binding points to `runner3-content-intelligence`. Non-Worker clients and external calls have not been completely excluded. No Worker disabled or redeployed.

The canonical manual D1+Workers metadata inventory workflow has been remapped to `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW`. The legacy audit Secret is retained for other existing workflows unless separately reviewed. No INSERT/DELETE/RESTORE, R2 action or cutover authorized.

## Consolidated account-wide audit — 2026-10-26 evening (historical snapshot)

**Outcome: SAFE_READ_ONLY_AUDIT_COMPLETE / ACCOUNT_MIGRATION_HOLD.** User requested end-to-end execution in one pass, not a sequence of repeated dry-runs. Safe, authorized diagnostic workflows were run together. No Cloudflare D1 INSERT/DELETE/RESTORE, Worker deploy, Worker disable, R2 operation or source cutover was performed.

### Fresh authenticated evidence (main)

- [Cross-account 9-D1 schema comparison #40324195505](https://github.com/louisalviss/runner-3/actions/runs/40324195505): 9 D1 databases source and 9 target; 8 shared names. **6/8 shared databases have identical sqlite_master object names/types and CREATE SQL**, but **NO row/key/content/deletion parity proof**:
  - `clm-copilot-v1`: 4/4 object parity PASS.
  - `louis-task-context`: 4/4 PASS.
  - `personal-library`: 26/26 PASS.
  - `runner3-opportunity-radar`: 21/21 PASS.
  - `runner3-rss`: 31/31 PASS.
  - `volamidle-rogue-data`: 4/4 PASS.
  - `runner3-content-intelligence`: 27 source / 9 target; **18 source-only schema objects absent on target**, no target-only objects or changes to common CREATE SQL.
  - `runner3-core`: 22 source / 1 target; **21 source-only objects absent on target**, no target-only objects or changes to common CREATE SQL.
  - Total missing source-side schema objects in the two shared D1s: **39**. This is schema inventory, **not** 39 rows or safe-to-apply DDL.
  - Source-only named DB: `clm-copilot-calibration`; target-only named DB: `louis-context-index`. Do not conflate or silently drop either.
- [Source nine-schema encrypted audit #40322914590](https://github.com/louisalviss/runner-3/actions/runs/40322914590): PASS; source metadata encrypted artifact, no plaintext DDL/row export.
- [Target nine-schema encrypted audit #40322929050](https://github.com/louisalviss/runner-3/actions/runs/40322929050): PASS; target metadata encrypted artifact.
- [Target Worker read-only inventory #40323345810](https://github.com/louisalviss/runner-3/actions/runs/40323345810), with sanitized diagnostic from PR #470: 9 target D1 UUIDs match their historical identities; legacy /workers/scripts gives 0, **independent /workers/workers returns HTTP 403**. Thus `target_workers_zero_verified=false`, binding/cron/Worker permissions unverified. **Workers Metadata Read-Only / Workers Scripts Read** permission for account `louisalviss3` is required for a reliable census; do not substitute source/global credentials.
- [Target bookmark encryption #40322947069](https://github.com/louisalviss/runner-3/actions/runs/40322947069): PASS. The one-day **ciphertext-only** artifact expires 2026-10-27T12:29:52Z. A successful encrypted artifact **does not mean recoverable private key escrow was tested or the GitHub Secret installed**. Previous private-key decryption/install path was caller-side blocked: no circumvention.
- [Target Time Travel GET #40321609830](https://github.com/louisalviss/runner-3/actions/runs/40321609830): PASS, not rollback-ready.
- [Reversible read-only D1 table rehearsal #40321583016](https://github.com/louisalviss/runner-3/actions/runs/40321583016): source 47, target 35, 12 source-only rows, matching 35, 0 conflicts; insert and row-safe reverse rehearsal in ephemeral SQLite restored 35/35, never applied to Cloudflare. This is **one table only**, not full-account row parity, source writer quiescence, or production rollback proof.
- GitHub Actions secret metadata as of 2026-10-26: `CLOUDFLARE_TARGET_D1_WRITE_TOKEN` present, `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` absent.
- Source Worker config in `cloudflare/runner3-core/wrangler.jsonc` still binds `CONTENT_DB` to source D1, not target. VPS `library-index-d1-sync.service` uses source Worker URL. This narrows obvious writers but **does not prove target has no other writers**.
- R2 migration operation gate `ops/cloudflare-account-rehome/r2-migration-operation-gate.json` remains `HOLD`, `permit_r2_migration=false`. No R2 requests made in these D1 audits.

### Consolidated remaining external dependencies — do not start target D1 writes

1. Owner must grant appropriate **target-account Workers Metadata Read-Only or Workers Scripts Read** to an authorized *read-only* Workers inventory identity. Current target D1 audit token gets HTTP 403 from the independently documented Worker list endpoint. Do not assume a zero-worker count from incomplete API results. Re-run one full census after authorization to identify Worker bindings/crons/traffic and independently establish a bounded quiescence plan.
2. A currently **unblocked, authorized private escrow** must preserve an immediately-pre-write Time Travel bookmark in `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` and independently verify usable restoration. An encrypted, expiring artifact alone is insufficient. No retry via alternate wrappers to evade the prior caller-side block.
3. Construct/review **source-exact and additive-only** DDL for the 39 missing objects, validate every dependency/constraint/uniqueness against populated target and source, preserve target-only data and source production. No bulk target DDL apply until backups/rollback, quiescence, actual row parity and approvals are ready.
4. Independently reconcile full keyed row payloads, source-only and target-only keys plus delete/tombstones on all databases. The schema-matched six are **not** data-matched merely from identical CREATE statements.
5. R2 remains `CLOUDFLARE-R2-COST-001 HOLD` until the residual PUT cost issue, bounded request budget and explicit release are resolved. Never treat user request to execute general migration as a verified cost-gate release.
6. Only then stage Workers privately, test bindings/schedules, perform separately approved bounded cutover and preserve source until checks pass. The guarded 12-row D1 INSERT workflow still requires same actor/SHA recent Dry-Run, exact phrase and honestly verified YES recovery/quiescence; do not fabricate these flags.

**No more re-running identical 47/35/12 dry-runs without a new prerequisite being fulfilled.** The next decisive operations are permissioned target Worker metadata census and an authorized recovery-secret installation, not a token-creation loop.

## Current evidence — 2026-10-26 (supersedes historical token claims below)

**Decision: HOLD.** No live D1 INSERT/DELETE/RESTORE, no R2 operation, no production cutover has been authorized or executed by this migration workflow.

- The independent target-account D1 write-credential GitHub Actions Secret `CLOUDFLARE_TARGET_D1_WRITE_TOKEN` **exists** (GitHub secret metadata reconfirmed 2026-10-26). Earlier text below referring to it as missing is *historical*. Target D1 metadata access via this token previously returned HTTP 200, but effective **D1 Edit has not been independently exercised**. Never test with an unapproved write.
- `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` **does not exist** in current GitHub repository Actions Secrets. The 2026-10-25 encrypted bookmark artifact #12585997327 has expired; do not reuse a stale bookmark. [Encrypted escrow workflow #40160515174](https://github.com/louisalviss/runner-3/actions/runs/40160515174) passed, but private-key decryption / secret installation on VPS was blocked before execution by caller-side safety. Do not route around that block.
- Fresh same-main-commit **read-only** [Dry-Run #40321583016](https://github.com/louisalviss/runner-3/actions/runs/40321583016), 2026-10-26: source 47, target 35, existing 35 matched, 12 missing, no conflicts. Scratch in-memory 12-row insertion and reversal **both PASS**, restoring all 35 target baseline rows. Explicit output: `rollback_readiness_proven=false`, `writer_quiescence_proven=false`, `real_target_delete_requests=0`.
- Fresh [Time Travel eligibility #40321609830](https://github.com/louisalviss/runner-3/actions/runs/40321609830), 2026-10-26: correct target production D1, bookmark API GET succeeds; **no fresh bookmark escrow installed**, no rollback ready.
- Target [D1 + Workers inventory #40319460558](https://github.com/louisalviss/runner-3/actions/runs/40319460558), 2026-10-26: target D1 count 9; Workers scripts endpoint showed 0, but alternate Workers endpoint unavailable; **`target_workers_zero_verified=false`**, Workers/cron/settings coverage incomplete. Historical source records identified six Workers on target; do not interpret this limited API result as proof that none are deployed.
- [Dependency audit #40171237293](https://github.com/louisalviss/runner-3/actions/runs/40171237293): 9 schema tables, 3 tables with FKs, **zero inbound and zero outbound foreign-key relationships for `recommendation_runs`**, no triggers/views dependent on it, verified by rebuilding DDL in isolated SQLite memory. This is schema-only evidence, not production rollback proof.
- Static writer-route review 2026-10-26: `cloudflare/runner3-core/wrangler.jsonc` binds `CONTENT_DB` to source D1 UUID `9cbec4ec-c930-459d-9499-9c66166c9241`, not target `82613659-8d08-455f-b6e7-f8f6e4312e22`. VPS `library-index-d1-sync.service` explicitly points at source Worker `runner3-core.ducduy2411.workers.dev`. Examined `ai-scan-hub`, `ai-context-index`, `content-intelligence-dropbox-bridge` configs and script literals without finding target account/database IDs. These **limited static checks do not establish target writer quiescence**; environment-indirect, deployed Worker/cron and other remote writers remain unverified.
- R2 remains separate `CLOUDFLARE-R2-COST-001` **HOLD**. Do not invoke R2 operations during D1 inspection.

### Remaining gates and immediate next safe action

1. Establish **complete authorized read-only target Worker + cron + binding census**; current `CLOUDFLARE_TARGET_AUDIT_TOKEN` cannot independently prove that target Workers are absent. Identify all possible target D1 writers including deployed Workers, scheduled/event consumers and non-GitHub clients. Do not pause production source services on name alone.
2. Independently demonstrate and approve target writer pause/quiescence, including in-flight activity, only once all writer identities are known. Keep source production authoritative.
3. Obtain and securely preserve a **new immediately-pre-apply Time Travel bookmark**; prior encrypted artifact is expired and current GitHub bookmark Secret is missing. Do not bypass any credential/private-key caller-side policy block. Confirm a genuinely executable row-safe rollback plan in addition to the successful in-memory reversal rehearsal.
4. Only after the above: run a **fresh read-only Dry-Run** on the same current `main` SHA with same GitHub actor and within 30 minutes of separately explicit approval. Require 47/35/12 parity reverified at that time, exact bookmark equality, manual writer pause and row-recovery attestations. No automatic `YES` or approval phrase.

**No automatic migration and no silent security-gate relaxation.**

**Code only. NO live target insert authorized, no R2 calls, no source changes, no production cutover.**

## Why the two-person gate was removed

The repository `louisalviss/runner-3` has one operator. GitHub's **Prevent self-review** necessarily blocks a single operator from approving their own deployment. Requiring a second account is not a suitable operating model here. The previous named write environment `cloudflare-target-d1-writes` was absent in the public GitHub environment census (only `github-pages` existed, HTTP 404 for the write environment).

The workflow now has **no GitHub environment** and **no independent reviewer**, but preserves a two-stage operator-mediated transaction: *separate successful manual read-only dry-run* → *separate explicit manual target-only INSERT*. It never runs on push, PR or schedule.

## Step A: manually run read-only preflight

[Cloudflare D1 Recommendation Runs Additive Dry-Run (Read Only)](https://github.com/louisalviss/runner-3/actions/workflows/cloudflare-d1-recommendation-runs-additive-dryrun.yml) → **Run workflow → main**.

This workflow uses only separate existing source/target read-only Cloudflare credentials, captures both D1 tables twice, checks exact column/PK metadata and typed payloads, rejects conflicts and races, and rehearses missing source-only keys in scratch SQLite. It sends **no D1 INSERT**. It returns aggregate counts and status only. It must have **conclusion=success**.

Record its numeric GitHub Actions **run ID**, visible in its URL: `.../actions/runs/<ID>`. Do not reuse #40091169404: it was performed on an older commit and is no longer recent. The new preflight must be on the *identical `main` commit* as the later manual write job, created within the previous **30 minutes**.

## Step B: separately approve target-only write (NOT YET ENABLED)

[Cloudflare D1 Target Recommendation Runs ADDITIVE WRITE (Solo Two-Step Approval)](https://github.com/louisalviss/runner-3/actions/workflows/cloudflare-d1-recommendation-runs-guarded-insert.yml) → **Run workflow → main**.

The workflow has required manual inputs: `dryrun_run_id`, exact typed `APPROVE_TARGET_ONLY_RECOMMENDATION_RUNS_12_INSERTS` phrase and separate confirmations `target_writers_quiesced=YES`, `row_safe_recovery=YES`. Both confirmations default to **NO**. Never select YES without real evidence.

A standalone first GitHub job, `recent-dryrun-gate`, has **no Cloudflare credentials** and retrieves the exact previous GitHub run using only `GET /repos/louisalviss/runner-3/actions/runs/{id}` and the GitHub Actions read-only token. It requires:

- Exact previous workflow path/name and `workflow_dispatch` event, `status=completed`, `conclusion=success`, first attempt only.
- Identical initiating/triggering GitHub actor as the write job, identical `main` commit SHA, branch, current repository and event.
- Valid created/finished times and <=30 minutes old. Any stale/different/replayed/failed run **fails closed**.
- The target write job cannot begin unless this first job passes. The writer repeats proof validation before any Cloudflare mutation.

**IMPORTANT:** Two GitHub Actions runs by the same person are not independent approval. This deliberately trades independent review for a simpler solo operation without removing data integrity, rollback and source-of-truth gates.

## Atomicity hardening (2026-10-25)

The previous guarded executor issued twelve independent D1 API INSERT requests, risking a **partially written** target table if a later request failed. It has been replaced with **one SQLite SQL statement**:

`INSERT INTO "recommendation_runs" (...) VALUES (?,?,...),(?,?,...), ...`

Exactly **12 tuples, 8 allowlisted columns**, at most **96 positional bound string parameters**, no raw values embedded in SQL, no semicolon, no multi-statement batch, no DELETE, UPDATE, UPSERT or REPLACE. The writer accepts only this pinned SQL shape; rejects an unexpected number of tuples, duplicate IDs, additional statements, SQL injection, oversize SQL, or wrong D1 account. It requires the D1 API to report exactly 12 changed rows.

Since this is a **single ordinary SQLite INSERT statement**, any uniqueness/constraint error aborts the whole statement rather than committing earlier VALUES tuples. Synthetic integration tests use an isolated real SQLite engine to verify all-or-nothing behavior. A network error after POST still leaves **ambiguous 0-or-12 commit status**, requiring read-only reconciliation before any further action. Even an atomic successful commit does not replace a reviewed row-safe recovery strategy if copied data is later found incorrect.

The old per-row intermediate readback has been replaced by a **complete post-statement target readback** verifying all existing target rows remain untouched and all twelve inserted rows exactly match their sources or the SQLite REAL-affinity equivalent. The final source-to-target recheck remains mandatory and fails closed if production source writes occurred during the window. Raw keys, payloads and bookmark stay out of logs and artifacts.

Cloudflare documents the D1 REST `/query` API with `sql` and `params` string arrays: https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/ . Its D1 SQL backend is SQLite: https://developers.cloudflare.com/d1/sql-api/sql-statements/ .

## Additional non-negotiable prerequisites before any real INSERT

- Three distinct tokens: source read-only `CLOUDFLARE_API_TOKEN`, target read-only `CLOUDFLARE_TARGET_AUDIT_TOKEN`, and separately provisioned target-account D1 Write token `CLOUDFLARE_TARGET_D1_WRITE_TOKEN`. The write token must be permission-scope restricted to the target account/database as supported. Never repurpose an audit token.
- Private, securely preserved **fresh target Time Travel bookmark** set as GitHub repository secret `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK`. Its exact value must match the target's *current* bookmark immediately before any INSERT. The old audit stored only a bookmark hash and is **not a rollback point**.
- **Target writers truly paused** and a **tested row-safe recovery plan**. Time Travel restore overwrites the **entire target D1 database**, including unrelated concurrent changes. No automatic restore is permitted.
- Read-only real preflight still shows exactly 12 source-only `recommendation_runs` rows, 35 matching existing target rows, no target-only keys, no differing typed payloads, same schema. If the delta changes, block and review; do not blindly replay 12.
- Ordinary parameter-bound `INSERT` only on the hardcoded D1 target UUID. The one atomic INSERT of 12 rows must be read back in full; previously present target rows must be preserved, and source/target re-read afterward. Network failure makes the commit outcome **unknown (zero or twelve rows)**; never auto-delete or retry, reconcile with a read-only audit. If SQLite REAL affinity changes typed representation, the writer explicitly records strict parity as **HOLD**, not a false 1:1 claim.

**Historical state at initial runbook creation (2026-10-24):** No separately approved target write credentials, private bookmark, paused writers or recovery rehearsals had been verified. See the 2026-10-26 section above for superseding credential and in-memory rehearsal evidence. **Do NOT dispatch Step B now**. Complete these gates first. R2 `COST_HOLD rev28`, source production and all other D1/Workers parity checks remain in force.

## Evidence

- [First live row audit #40089305352](https://github.com/louisalviss/runner-3/actions/runs/40089305352): 47 source, 35 target, 35 exact matching pairs, 12 source-only.
- [Authenticated additive dry-run #40091169404](https://github.com/louisalviss/runner-3/actions/runs/40091169404): scratch-only 12-row INSERT+readback passed, no target writes.
- [Target Time Travel capability #40092563094](https://github.com/louisalviss/runner-3/actions/runs/40092563094): production backend and bookmark API confirmed, raw bookmark **not preserved**.

**State:** `target_d1_writes=0`; `r2_requests=0`; `source_authoritative=true`; `row_rollback_ready=false`; `full_cutover_ready=false`.
