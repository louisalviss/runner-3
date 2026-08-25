# Wave Rider Full BTC+ETH Crypto Regime Stack — Preregistration

Date: 2026-08-25 (Asia/Ho_Chi_Minh)
Status: PREREGISTERED / RESULTS UNSEEN

## Research question

On the frozen corrected Crypto Stage1 canonical WR opportunity set, does a causal broad crypto-regime stack identify a robust positive-expectancy subset?

This is a new structural/context lineage. It is NOT a retry of the failed asset/BTC RS50 gate.

## Frozen parent

- corrected Stage1 source run: `32618199814`
- source artifact: `wr-crypto-stage1-close-final-corrected`
- artifact digest: `sha256:6212a95887ad09f544ae5e401b76d241afe0bfc3bdae1219f14be42639a2adfe`
- canonical parent trades: 359
- expected baseline at 6bps: `-91.2313R`
- timeframe: 5m
- WR rules/exits/stops and parent membership are frozen; no WR recomputation or parameter change.

## Source

Historical Binance USD-M futures klines from `data.binance.vision`, 5m bars, using only completed bars available at the WR signal close.

Frozen Stage1 symbol universe is inferred from the parent artifact. BTCUSDT and ETHUSDT are regime benchmarks; all other parent-universe symbols with causal data are eligible for breadth/correlation.

## Six frozen regime components

Each trade receives six binary components at the completed signal bar. LONG and SHORT use symmetric directional definitions where applicable.

1. **BTC trend**
   - LONG: BTC close > EMA200 and EMA200 slope > 0.
   - SHORT: BTC close < EMA200 and EMA200 slope < 0.

2. **ETH trend**
   - LONG: ETH close > EMA200 and EMA200 slope > 0.
   - SHORT: ETH close < EMA200 and EMA200 slope < 0.

3. **BTC+ETH 24h joint participation**
   - LONG: both BTC and ETH 24h close-to-close returns > 0.
   - SHORT: both BTC and ETH 24h returns < 0.

4. **Alt breadth**
   - Per available non-BTC/non-ETH parent-universe symbol: bullish iff close > EMA50 and EMA50 slope > 0; bearish iff close < EMA50 and EMA50 slope < 0.
   - LONG favorable iff bullish fraction >= 55%.
   - SHORT favorable iff bearish fraction >= 55%.
   - At least 15 alt symbols must be causally available at the timestamp.

5. **BTC volatility regime**
   - Compute BTC 24h realized volatility from 5m log returns.
   - Compare to causal rolling 30-day distribution of the same 24h realized-vol measure.
   - Favorable iff current RV is between the rolling 20th and 80th percentiles, inclusive.
   - This component is direction-neutral and excludes extreme compression/panic regimes.

6. **Cross-sectional BTC correlation**
   - For each available alt symbol, compute 24h Pearson correlation of 5m log returns versus BTC using only completed bars.
   - Favorable iff median alt/BTC correlation >= 0.35.
   - At least 10 valid alt correlations are required.

## Frozen composite

`REGIME_SCORE = sum(components 1..6)`

Primary B subset: `REGIME_SCORE >= 5`.

No alternate score threshold, EMA length, return horizon, breadth threshold, volatility percentile band, correlation threshold, or symbol whitelist after results.

## Scoreability / infrastructure gate

A trade is scoreable only when all six components are defined causally.

Formal alpha interpretation requires >=95% of parent trades to be scoreable. Below this is `INFRASTRUCTURE_BLOCKED`, but economic diagnostics are still reported and may justify closing the lineage if clearly adverse.

## Frozen promotion gate

`PASS_FULL_CRYPTO_REGIME_WR = true` only if ALL:
1. scoreable coverage >=95%
2. retained B n >=80
3. retention between 15% and 70%
4. B mean R/trade at 6bps >0
5. B PF at 6bps >1.05
6. B mean >= A mean +0.10R/trade
7. B total R at 6bps >0
8. B total R positive in BOTH 2025 and 2026
9. >=50% of symbols with >=5 B trades have positive cumulative B R
10. day-block bootstrap 95% lower bound for B mean R >0
11. day-block bootstrap 95% lower bound for B-A mean delta >0

## Guardrails

- No parameter sweep.
- No post-hoc LONG-only/SHORT-only rescue.
- No ticker whitelist.
- No removal of losing years.
- No changing component count or score threshold.
- No alternate BTC/ETH benchmark after PnL is observed.
- If a source/instrument is unavailable, fix infrastructure only before seeing PnL; otherwise record the block.

If this preregistered lineage fails economically, the current major WR crypto regime rescue queue is considered exhausted unless a genuinely independent external hypothesis is introduced later.