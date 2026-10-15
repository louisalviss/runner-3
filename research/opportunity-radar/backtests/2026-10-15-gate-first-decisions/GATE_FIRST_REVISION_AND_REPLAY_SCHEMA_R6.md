# Gate-first R6 — revision transitions, strict entry near misses, replay schema audit
2026-10-15, NON-TRADING SHADOW RESEARCH. Supplements R4 limit-fill and R5 candidate census. No rules, historical signals or paper trades changed.

## Archived Gate-first chronology
Connected native Opportunity Radar Google Sheet: 159 revision metadata IDs Aug09 to Oct15. 10 DISTINCT selected revision bodies re-exported and classified across Aug09, Aug23, Aug24, Aug28, Sep05, Sep10 twice, Sep15, Sep16 and Oct09. THIS IS NOT AN EXHAUSTIVE REPLAY OF 159 VERSION BODIES OR 3,035 economic Gate decisions. 5 sampled bodies include all candidate rows; other 5 include high-score/ready/BUY original decision rows plus original notes.

- Aug23 and Aug24: 36 Candidate rows, 35 distinct issuers, 5 Score>=80, zero archived BUY/ENTRY_READY.
- Aug28: 42 Candidate rows, 41 distinct issuers, 6 Score>=80, zero BUY/ENTRY_READY.
- Sep05: NOC Score85.6/MQ4/RR~2.25 at $514.98, LMT Score84/MQ4/RR~2.33 at $525.28, both ENTRY_READY with NO historical BUY execution signal; NOT actual orders.
- Sep10 R260: NOC Score85.6/MQ4/RR~2.09 ENTRY_READY but Execution NONE because source close $515.57 was $0.57 ABOVE STRICT $515 signal cap. LMT Score84/MQ4/RR~2.40 ENTRY_READY but Execution NONE because canonical methodology v3.5 had not been installed and read back; fail-closed.
- Sep10 R261: LMT original BUY_SIGNAL at Sep10 17:52 +07 after canonical v3.5 active/readback; contingent on current price/risk/venue/zone. No broker fill proven.
- Sep15 R291 and Sep16 R293: two LHX BUY_SIGNAL events, same issuer, overlap and identical conditional $245-250 Entry Zone.
- Oct09 R335: 44 Candidate rows but 43 distinct issuers because NVDA appears TWICE, same Aug18 discovery and NOT_READY with score 76.3. This same duplicate appears in Aug23/24/28 samples. Current Oct15 Candidate list has 43 unique issuers, and no unique issuer was removed relative to Oct09. Deduplicate by issuer/idea and original signal IDs; never count a duplicate row as a separate traded name.

See gatefirst_revision_sampled_10_summary.csv and gatefirst_highscore_revision_states_10.csv for source revision IDs/timestamps and recorded R/R/Entry/Execution notes.

## Entry-ready near miss, not trade
Sep05 revision source was after Sep04 US market close; Sep07 US market was closed for Labor Day and next market session was Sep08. Yahoo regular-session daily OHLC:
- NOC Sep08 opening $516.00 and low $515.06 > strict $515 cap. No fill, missed by $0.06.
- LMT Sep08 opening $532.00 and low $531.37 > strict $525 cap. No fill, missed by $6.37.
- NOC Sep10 from R260 opened $517.05 and low $516.00 > $515 cap. No fill, missed by $1.00; original Execution NONE.
These three observations are NO TRADES: no hypothetical PnL is assigned. See entry_ready_no_buy_near_miss_3.csv.

## Separate replay engine incompatible with original saved ORSNAP schema
Compared current read-only cloned louisalviss/opportunity-radar replay/engine.py and five REAL immutable decision objects on connected Dropbox. Its validate_snapshot() requires a numeric decision.reference_price but ALL FIVE actual ORSNAP files instead contain decision.actionable_reference_price and string-form entry_zone. ALL 5/5 fail native engine validation with ValueError: decision missing reference_price. This explains why a naive attempt to reuse this engine against original source files will not give a valid historical trading backtest, even though the engine's own synthetic unit tests pass.

SHA256 of sorted compact UTF-8 JSON over original decision dict matched 3/5 stored decision_sha256 references; both LMT files did not match. Keep these two as QUARANTINED, not proof of malice and not a reason to erase independent Google Sheet original LMT BUY.
The 3 hash-valid ORSNAP decision dicts contain NO original MQ field and all three have execution_signal=NONE. The historical LHX snapshot observed Sep14 (source Sep11) has Score85.8, RR2.65, ENTRY_READY, but Execution NONE. A hypothetical permissive adapter that converts ready/Score/RR into a trade without checking original Execution BUY would produce ONE NONEXISTENT BUY. DO NOT normalise or repair original hash, MQ, zone or actual signal state just to force a backtest pass.

Fail-closed future adapter needs original hash/provenance, explicit price and numerical zone conversion, MQ independent evidence (unknown if absent), original execution signal and expiry (must BUY), original as-of financial economics and canonical rules/venue, and identity dedup. R/R at a now-obsolete mark must not be evaluated as if the next market-open outside zone were a permitted buy. No production scanner/Entry engine was changed.

## Verified historical result and unresolved full-universe problem
Canonical merged PR416 R4 shows all three original following-day MARKET opens above Entry caps; only conditional limit touch based on daily lows, no broker fills. Conditional limit 20D reference mean -5.741% (N3 advisories from only LMT and LHX), 0/3 wins, and NO independent proven alpha.
This does not imply 3,035 market price tickers had completed Score/MQ/valuation Gate decisions. Missing original point-in-time economic underwriting means UNKNOWN, never FAIL or backfilled BUY. Gate-first first, Pump/Dump plus SAME Gate secondary, zero verified historical original P/D-origin BUY. Live and paper execution unchanged.

Data: gatefirst_revision_sampled_10_summary.csv; gatefirst_highscore_revision_states_10.csv; entry_ready_no_buy_near_miss_3.csv; replay_schema_compatibility_5.json. R4 and R5 in main remain authoritative for Entry and 43 current Candidates respectively.


## Optional non-trading classifier implementation (follow-up)

To prevent ENTRY_READY/Score from being promoted to fictional BUY, the separate
louisalviss/opportunity-radar research PR #24 adds replay/archived_buy_intent.py
and tests, with **no changes to replay/engine.py or the active scanner**.
All existing 51 repository tests plus eight new tests passed, total 59/59.
Re-tested on the five original archived Dropbox objects: exactly two
QUARANTINE_HASH, three NO_ORIGINAL_BUY, zero claimed fills. The output and
source pointers are in failclosed_adapter_original5_QA.json. This remains an
intent classifier and does not solve missing PIT economic source data nor
normalize a mismatched original snapshot into a valid BUY.
