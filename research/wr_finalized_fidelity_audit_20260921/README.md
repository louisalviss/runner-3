# Finalized WR Fidelity Audit — 2026-09-21

Purpose: determine whether fresh OOS run 35561572293 is evidence about Louis's legacy Finalized WR ruleset from source 314, rather than merely about the automated WR v2.5.13 structural engine.

## Provenance
- OOS run: 35561572293, 34/34 jobs PASS.
- OOS final report SHA256: bbd4e0233a2d9a2de19647bc2db4cca98603df2236e1694cad7b0156a0698966.
- OOS artifact: wr-tvol-oos-final, ID 10622606719, digest sha256:a8345ff2244cfa2d975a5317a7febb1630d3e78e51f703d4aca4aa250c7d44b2.
- Finalized WR source: Google Doc source 314 (`Wave rider`, source_document_id 1huCShzPmSiY8MVJ033OuBtuwENLU1og5anK6d1spw04).

## Mechanical replay
All 64 OOS trade rows were reconstructed from Binance M5 and replayed against the exact automated v2.5.13-derived predicates and execution geometry used by the OOS harness.

Result: 64/64 mechanical PASS, 0 implementation failures.

This validates the OOS harness against its own automated engine. It does NOT establish equivalence between that engine and the manual `Wave Rider / Bob Volman Price Action` setup language in source 314.

## Pre-existing Finalized WR scope corrections
Source 314 predates the OOS result and specifies:
- assets: SOL, ETH, XRP only;
- T/cluster days: T-2, T-1, T0, T+2, T+3;
- VN entry blocks on cluster days: 00:00–11:59, 14:00–17:59, 21:00–23:59;
- 12:00–13:59 and 18:00–20:59 OFF;
- M5, EMA21, Wave Rider / Bob Volman Price Action;
- fixed TP +2.3R and SL -1R, no time exit.

OOS run 35561572293 used a broad crypto universe and generic crypto session admission rather than those exact asset/time constraints.

Observed scope deltas:
- original OOS: 64 trades, -17.8R gross;
- 10/64 trades were in Finalized-WR OFF hours (18:00–20:59 VN): 1 TP / 9 SL, total -6.7R;
- applying only the pre-existing Finalized WR time blocks leaves 54 trades, -11.1R gross;
- applying the pre-existing asset filter SOL/ETH/XRP plus valid Finalized-WR time blocks leaves 13 trades, -9.7R gross.

The 13-trade figure is still NOT an exact Finalized WR test because setup equivalence is unresolved.

## Original oracle recovery status
Historical conversation provenance identifies an uploaded workbook named `Backtest 2026.xlsx`.
The only result directly verified from that workbook in the original 2025-12-30 audit was a 67-trade / +48.5R (~0.72R/trade) baseline after a specific historical filtering/simulation step. Later summaries leading to the claimed 48-trade / +46.4R Finalized WR result were not independently recomputed from a preserved 48-row ledger in the recovered evidence.

The original `Backtest 2026.xlsx` bytes / exact 48-trade oracle have not been recovered from current Dropbox, Drive, Library, or the separate Bob-Louis portable state. Bob-Louis is a distinct 2026 lineage and must not be used as a substitute oracle.

## Authority decision
- `RUN_35561572293 = VALID_V2513_OOS / SCOPE_MISMATCH_FOR_FINALIZED_WR`
- `V2513_OOS_MECHANICAL_FIDELITY = 64/64 PASS`
- `LOUIS_FINALIZED_WR_EXACT_REPLICATION = NOT_YET_REPRODUCED`
- `ORIGINAL_48_TRADE_ORACLE = NOT_RECOVERED`
- `SOURCE314_46_4R_48_TRADES = HISTORICAL_CLAIM / NOT_CURRENTLY_INDEPENDENTLY_REPRODUCIBLE`

Therefore run 35561572293 may be cited against the tested v2.5.13 + T + causal-volume formulation, but must NOT be cited as a rejection of Louis's legacy Finalized WR ruleset.
