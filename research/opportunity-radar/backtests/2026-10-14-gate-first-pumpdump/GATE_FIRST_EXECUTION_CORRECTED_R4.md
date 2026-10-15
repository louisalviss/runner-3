# Gate-first actual-decision replay: correction for executable Entry Zone

Checkpoint 2026-10-15. SHADOW audit only, no real orders, no Gate or Paper mutation.

## Historical evidence and scope

The connected Opportunity Radar Google Sheet has 159 revision identifiers (2026-08-09 to 2026-10-15); six exports were sampled before revision export was rate-limited HTTP 429. This is NOT a 159-revision exhaustive replay. Current Sheet has 43 curated Candidates across engines/asset types. The separate price-universe archive contains 3,035 US symbols and 41,244 symbol-sessions, but does not save a complete contemporaneous catalyst/Score/MQ/RR/Entry decision for each. Unknown must not be called Gate FAIL. Only three original paper BUY_SIGNAL events are documented from Gate-first Defense Deep Bottleneck, none certified P/D + Gate.

Google revisions:
- 260 at 2026-09-10 10:14 UTC: LMT Score84 MQ4, estimated R/R 2.40 at $524.46, ENTRY_READY, signal NONE; NOC Score85.6 MQ4, R/R 2.09 at $515.57, ENTRY_READY but signal NONE because $0.57 above strict $515 signal-zone maximum. On next US session NOC low was $516 and DID NOT touch $515.
- 261 at 11:02 UTC Sep10: LMT transitioned to advisory BUY_SIGNAL at 17:52 Asia/Ho_Chi_Minh.
- 291 at 2026-09-15 03:47 UTC: LHX Score85.8 MQ4, R/R ~2.13 at $248.93, ENTRY_READY and BUY_SIGNAL.
- 293 at 2026-09-16 02:15 UTC: LHX same score/MQ, R/R ~2.02 at $249.66, a second BUY_SIGNAL.
- 335 Oct09 shows later EXPIRED/NOT_READY, never backdate that to signal timestamps.

## CRITICAL: next NYSE OPEN outside original Entry Zone on ALL THREE

Original signal times preceded the next regular 09:30 NYSE open and expiry was after that session's 16:00 close. Yahoo historical daily OHLC:

| Historical advisory | Source US session | Entry Zone | Following NYSE open | Session low | Upper limit reached? |
|---|---|---|---:|---:|---|
| LMT Sep10 | Sep09 | $515–525 | $526.01 Sep10 | $524.09 | YES |
| LHX Sep15 | Sep14 | $245–250 | $251.90 Sep15 | $247.87 | YES |
| LHX Sep16 | Sep15 | $245–250 | $250.07 Sep16 | $248.14 | YES |

Unconditional next-open MARKET buy violates the archived Execution Zone in all three. The intraday lows do touch the limit cap; a resting limit $525/$250/$250 could theoretically execute within the expiry session, but there was NO actual order/fill logged, and daily OHLC does not establish order time, queue, spread, slippage, intraday trigger recomputation or guaranteed liquidity.

Assumed hypothetical limit fill exactly at upper Entry cap if price range touched it; 50bps roundtrip costs; exit at trading-session close 5/20, returns net. Include optimistic original paper close-reference-if-touched as a different scenario.

| Advisory | 5D next-open MARKET (not Gate-valid) | 5D limit cap | 20D limit cap | 20D original reference-if-touched |
|---|---:|---:|---:|---:|
| LMT Sep10 | +1.637% | +1.833% | -5.410% | -5.313% |
| LHX Sep15 | -2.473% | -1.728% | -5.200% | -4.790% |
| LHX Sep16 | -4.571% | -4.544% | -6.612% | -6.484% |
| Event mean, N3 (2 issuers) | -1.802% | -1.480% | -5.741% | -5.529% |

Under conditional limit-fill reference, 20D 0/3 profitable, mean -5.741%. No statistical confidence with N3, only two distinct companies and same LHX appears twice. Existing Paper_Trades has two virtual LHX tickets open simultaneously, each nominal $100 on a $1,000 paper capital base: this is nominal 20% same-symbol exposure. Review issuer-level dedup and 10% per-idea cap; not evidence real orders breached a cap.

## Dropbox ORSNAP decision-hash audit

Five ORSNAP decision objects were read directly from Dropbox and SHA256 recomputed over canonical sorted compact JSON. LHX Sep14, NOC Sep11 and NOC Sep14 (3/5) MATCH. LMT Sep11 and LMT Sep14 (2/5) DO NOT MATCH the declared decision_sha256. Quarantine those two as independent immutable evidence until hash serialization/payload discrepancy is understood. Digest mismatch does not prove intentional tampering. LMT Sep10 BUY evidence exists independently in contemporaneous Google revision 261 and Google Paper_Trades.

## Verdict

Gate-first: 3 documented paper advisory BUY, zero proved real broker fills. Entry-zone-corrected limit-reference 20D outcomes all negative. P/D+same-Gate: zero verified original BUY, does not imply 1,139 price events were Gate FAIL. Full economic historical 3,035 issuer Gate backtest remains unreconstructable from price-only snapshots. Main Gate has strict primary priority and P/D adds only secondary candidate discovery.

Files: gate_first_actual_decisions_and_limit_replay_v1.json; gate_first_limit_fills_3.csv; asof_execution_gate_limit_fill_3.json; dropbox_snapshot_hash_audit_5.json. No production or paper modifications.

Next: recover all 159 historical Sheet versions in rate-safe fashion, store versioned decision transitions and avoid issuing non-executable market-open fills. For future broad backtests, persist complete PIT economic Gate inputs for every candidate after Hard Persist so UNKNOWN is not mistaken for FAIL.
