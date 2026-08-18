# Wave Rider Cross-Asset Screen — 2026-08-17

Status: **SCREENING CHECKPOINT ONLY — NOT PRODUCTION / NOT OOS VALIDATION**

## Purpose
Extend the current Wave Rider v2.5.13 research beyond crypto into US stocks, major FX, metals and US indices without changing the core signal/lifecycle rules.

This checkpoint does **not** modify the canonical production/reference engine. Wave Rider v2.5.13 remains canonical.

## Frozen screen design

- Calendar window: `2026-07-27 00:00 UTC` → `2026-08-15 00:00 UTC` exclusive (through 2026-08-14).
- Timeframes: 3m, 5m, 10m.
- 3m and 5m fetched independently from TradingView public regular-session chart data.
- 10m is causally aggregated from consecutive 5m bars because anonymous TradingView did not return native 10m in this harness.
- Wave Rider logic replicated: causal S/R pivot 10/10 + `[1]`, EMA21, 12-close regime, EMA-angle/ATR10, CHOP14 < 50, signal candle range <= 1.5 ATR, signal breakout/wick geometry, one-next-candle pending entry, ±1 tick entry/SL, TP 2.3R, EMA/session lifecycle exits, conservative same-bar ambiguity.
- Gross R only. Spread, commission and slippage are not deducted.
- Same short fixed calendar window is used for every group.
- Bootstrap CI is block-based and is descriptive for this screen; pooled cross-symbol trades are not fully independent observations.

## Universe

### US stocks
Public, Wave-Rider-independent 37-name large/liquid benchmark basket. The private 73-symbol `HAS_TRADE_BEFORE` registry was deliberately **not** copied into the public runner and was not replayed backward, because its own guardrail prohibits leaking symbols discovered later into earlier timestamps.

### Forex
EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD via `FX_IDC`.

### Metals
XAUUSD, XAGUSD via OANDA chart feed.

### Indices
NAS100USD, SPX500USD, US30USD via OANDA chart feed.

## Aggregate results

| Asset class | TF | Trades | Avg R | PF | 95% block-bootstrap CI AvgR | Positive cells | Screen state |
|---|---:|---:|---:|---:|---:|---:|---|
| US stocks | 3m | 176 | +0.132 | 1.221 | [-0.065, +0.364] | 20/37 | UNPROVEN |
| US stocks | 5m | 92 | +0.017 | 1.026 | [-0.231, +0.295] | 14/33 | UNPROVEN |
| US stocks | 10m | 43 | +0.096 | 1.164 | [-0.241, +0.536] | 12/29 | UNPROVEN |
| Forex | 3m | 66 | **-0.458** | 0.407 | **[-0.715, -0.190]** | 1/7 | **SCREEN_NEGATIVE** |
| Forex | 5m | 44 | **+0.257** | 1.494 | [-0.069, +0.591] | 4/6 | UNPROVEN / candidate |
| Forex | 10m | 25 | -0.317 | 0.592 | [-0.713, +0.079] | 2/7 | UNPROVEN |
| Metals | 3m | 25 | -0.241 | 0.656 | [-0.569, +0.142] | 0/2 | UNPROVEN |
| Metals | 5m | 22 | **+0.350** | 1.592 | [-0.250, +0.950] | **2/2** | UNPROVEN / candidate |
| Metals | 10m | 8 | +0.237 | 1.380 | [-1.000, +1.475] | 1/2 | UNPROVEN |
| US indices | 3m | 36 | **-0.670** | 0.233 | **[-0.960, -0.267]** | **0/3** | **SCREEN_NEGATIVE** |
| US indices | 5m | 19 | -0.305 | 0.613 | [-0.831, +0.042] | 1/3 | UNPROVEN |
| US indices | 10m | 31 | -0.132 | 0.810 | [-0.661, +0.211] | 1/3 | UNPROVEN |

## Cell-level hints — hypothesis only

### Forex 5m
- USDJPY 5m: N=8, AvgR ≈ +0.906, CI ≈ [-0.136, +1.972].
- EURUSD 5m: N=9, AvgR ≈ +0.496, CI ≈ [-0.097, +1.457].
- These are far too small to promote.

### Metals
- XAUUSD 5m: N=13, AvgR ≈ +0.269, CI ≈ [-0.492, +1.031].
- XAGUSD 5m: N=9, AvgR ≈ +0.467, CI ≈ [-0.633, +1.567].
- XAGUSD 10m: N=5, AvgR ≈ +0.980, CI ≈ [+0.320, +2.300], but N=5 is explicitly insufficient and this was noticed post-hoc.

### US stocks
The broad basket has weak positive point estimates but no timeframe CI clears zero. Small-N leaders such as HD 3m, GE 3m and LOW 3m are **not** accepted as stock winners because they were identified after looking at the same short screen.

### US indices
- 3m is the clearest negative result in the cross-asset pilot: all three index cells negative, pooled AvgR ≈ -0.670 and CI fully below zero.
- SPX500 10m also looked poor (N=7, AvgR ≈ -0.935), but remains a tiny cell.

## Interpretation

1. The crypto finding that Wave Rider is conditional on instrument × timeframe is reinforced rather than contradicted.
2. There is no evidence here for a universal cross-asset Wave Rider edge.
3. **Forex 3m and US-index 3m should not be promoted; this screen provides evidence against them.**
4. **Forex 5m and metals 5m are the only non-crypto broad candidates worth carrying forward**, but neither is validated because their CIs still include zero and costs are excluded.
5. US stocks as a broad class are currently **unproven**. The 3m point estimate is positive but weak relative to uncertainty.
6. The current short screen is not comparable in evidential strength to the long crypto formal basket (BNB5/TRX5). It is a hypothesis-generation checkpoint only.

## Important invalidated old evidence
The prior workflow named `wave-cme-hist-temp` used `NASDAQ:CME`, which is CME Group stock, not CME futures. Its old result must never be cited as evidence for CME index/metal/FX futures.

## Data limitations

- Anonymous TradingView intraday history is shallow compared with the long crypto archive used in formal research.
- Current test window is short and reused for hypothesis discovery.
- No transaction costs are applied. FX/CFD spread and slippage can materially reduce small positive point estimates.
- OANDA/FX_IDC chart feeds are proxies; actual CFD/futures broker execution can differ.
- Current public stock basket has current-universe selection/survivorship limitations.
- Cross-symbol trades share macro regimes, so pooled trade counts overstate independent information.

## Frozen next-test protocol

Do **not** tune the core Wave Rider logic from this screen.

Carry forward only these hypotheses:
1. Forex 5m broad family.
2. Metals 5m broad family.
3. US-stock 3m broad family as weak/secondary only.
4. US indices 3m = negative-control / avoid hypothesis unless genuinely new untouched evidence reverses it.

Next evidence must come from new untouched data or a longer independent historical source. Predeclare the next window before opening results. Add realistic spread/commission/slippage sensitivity. Keep asset-class results separate. Do not select USDJPY5, EURUSD5, XAG5/XAG10 or small-N stock winners from this screen and then call the same period OOS.

## Decision state 2026-08-17

- Crypto: remains the strongest formal research branch; BNB5/TRX5 lead historical candidates.
- Forex: 5m candidate; 3m negative in this screen.
- Metals: 5m candidate; not validated.
- US indices: current evidence poor, especially 3m.
- US stocks: broad class unproven; no production winner selected.
- Wave Rider v2.5.13: unchanged canonical/reference engine.
