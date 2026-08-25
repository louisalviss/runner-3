# Super RSI Backtest Flow

Status: ACTIVE / CANONICAL BACKTEST FLOW  
Strategy: Super RSI  
Short code: `SUPER_RSI`

## Purpose

This flow is the reproducible backtest harness for Super RSI. It is independent from Wave Rider.

Canonical frozen strategy:

`RSI10 + SMA(RSI,10) + second bullish crossover while RSI < 50 -> LONG -> SuperTrend(10,2.5) bearish flip -> EXIT`

The canonical production-research profile is:

`profiles/canonical-us-equities-60m-v1.json`

## Architecture

1. **Profile**
   - freezes asset class, universe, dates, session, timeframe, strategy parameters, execution model and pass gates;
   - profile files are research lineage boundaries;
   - changing a material parameter requires a new profile and new preregistration.

2. **Per-symbol executable engine**
   - fetches paired Dukascopy BID/ASK source bars;
   - builds midpoint chart bars;
   - computes Super RSI signal causally;
   - executes long entry at next chart-bar ASK open;
   - exits at next chart-bar BID open after SuperTrend bearish flip;
   - emits per-symbol summary + raw trades.

3. **Evaluator**
   - merges all shards;
   - computes actual and midpoint PF/expectancy;
   - symbol breadth;
   - yearly stability;
   - spread diagnostics;
   - frozen gate results;
   - emits machine-readable + human-readable artifacts.

4. **Artifacts**
   - `report.json`
   - `trades.jsonl`
   - `symbol_summary.csv`
   - `yearly_summary.csv`
   - `SUMMARY.md`

## Canonical US 60m profile

Primary evidence setup:
- US equities
- 60m regular-session chart
- source quotes: paired Dukascopy M5 BID/ASK
- chart: midpoint
- next-chart-bar market execution
- long entry: ASK open
- long exit: BID open
- warmup: 2021-12-01
- report: 2022-01-01 through 2026-08-24 inclusive
- universe: 68 liquid US stocks
- primary gate excludes the five names previously seen in earlier ablation:
  `AAPL AMZN MSFT NVDA TSLA`

This profile should reproduce the already validated external-alpha lineage within normal feed reproducibility tolerance:
- primary trades ~4,023
- actual PF ~1.394
- mean ~+64.08 bps/trade
- positive symbols 49/63
- median per-symbol PF ~1.285

A material mismatch means the flow is not parity-safe and must be fixed before new research.

## How to run

GitHub Actions workflow:

`.github/workflows/super-rsi-backtest.yml`

Manual run:
- open Actions
- select **Super RSI Backtest**
- choose the profile path
- run workflow

Bootstrap branch pushes run only when the head commit contains:
`[super-rsi-run]`

## Adding another timeframe or asset class

Do **not** edit the canonical profile.

Create a new profile, e.g.:
- `research-us-equities-240m-v1.json`
- `research-bist-240m-v1.json`
- `research-crypto-240m-v1.json`

Any new profile must explicitly freeze:
- universe
- session/calendar
- source data
- chart timeframe
- signal parameters
- execution assumptions
- dates/splits
- pass/fail gates

If the asset class requires a different market session or execution model, modify the engine only through a separate lineage and prove parity on the canonical profile first.

## Anti-overfitting rules

Do not use this flow to retrospectively rescue the canonical sample by:
- tuning RSI length;
- tuning RSI signal SMA;
- changing RSI threshold 50;
- changing second-cross count;
- tuning SuperTrend ATR/factor;
- selecting winning tickers/sectors from observed PnL;
- selecting a new timeframe because its backtest looked better;
- importing Wave Rider filters;
- changing gates after results.

Material changes are:
`NEW PROFILE / NEW PREREGISTRATION / NEW HOLDOUT`.

## Storage roles

- GitHub: code, profiles, workflows, run lineage.
- GitHub Actions artifacts: raw run outputs.
- Dropbox canonical project: durable research summaries/checkpoints.
- D1 is not required for deterministic backtest output; add it only if run indexing/checkpoint querying becomes operationally useful.

## Current next research module

After canonical parity is proven:

`Super RSI -> portfolio construction -> full friction -> robustness/factor decomposition -> untouched forward -> paper trade`

Portfolio construction is deliberately separate from the per-symbol alpha engine so allocation assumptions cannot silently alter signal validation.
