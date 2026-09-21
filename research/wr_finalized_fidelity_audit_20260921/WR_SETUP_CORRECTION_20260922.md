# WR setup correction — 2026-09-22

## Retraction
The 2026-09-21 attempt to infer WR setup from `Backtest 2026` manual Line-test labels (`Ok`/`Hit`) used the wrong authority scope. Those labels are not the source definition of the coded Wave Rider strategy. Conclusions that Finalized WR had no proven numeric S/R parameter, that pivot 10/10 was not provenance, or that signal-range/CHOP/angle/regime were non-authority are retracted for the coded WR engine.

## Actual coded WR authority
Historical Git/TradingView evidence proves an encrypted canonical Pine strategy existed and was compiled on TradingView:
- Pine title: `Wave Rider Strategy v2.5.13 WINDOW REPORT`
- shorttitle: `WR 2.5.13 WIN`
- normalized canonical Pine plaintext SHA256: `9156e8c49b9a5e36007620f3e17fcab26c06714a3e32a252be52437ae23d6026`
- encrypted artifact: `ops/tradingview/wave-rider-v2.5.13-window-report.pine.aes`
- source was loaded/compiled against `BINANCE:BNBUSDT.P` 5m in historical TradingView automation.
- later saved derivative: `Wave Rider Strategy v2.5.14 DETERMINISTIC` / `WR 2.5.14 DET`; its patch changes deterministic state anchoring/report initialization, not the core WR setup filters.
- no separate WR Pine `indicator()` artifact was found in reachable WR history; the canonical artifact is a Pine `strategy()`.

## Exact core rules from parity-proven verifier
Frozen/core constants:
- Left pivot bars = 10
- Right pivot bars = 10
- EMA length = 21
- EMA smoothing direction lookback = 2
- EMA-side regime = 12 consecutive closes
- EMA angle period = 4
- angle normalization ATR = 10
- minimum absolute EMA angle = 5 degrees
- CHOP length = 14; CHOP must be < 50
- signal ATR = 14
- signal candle range / ATR must be <= 1.5
- TP = 2.3R
- risk budget = 1% equity

Pivot semantics:
- Pine-compatible `ta.pivothigh/ta.pivotlow(...)[1]`
- right-most tie semantics: equal extrema may exist on the older/left side; equal extrema on newer/right side invalidate the pivot.
- last confirmed pivot high = resistance; last confirmed pivot low = support.

Long setup on signal bar:
- 12+ consecutive closes above EMA21
- close > EMA21
- normalized EMA angle is outside +5°/-5° band and is increasing vs prior bar
- CHOP < 50
- resistance exists
- signal candle range <= 1.5 * ATR14
- bullish signal candle (`close > open`)
- close > resistance AND low <= resistance (break + touch/retest through the level on the signal candle)
- session/news setup guards allow the signal

Short is symmetric:
- 12+ consecutive closes below EMA21
- close < EMA21
- normalized EMA angle is outside the ±5° band and is decreasing vs prior bar
- CHOP < 50
- support exists
- signal range <= 1.5 * ATR14
- bearish signal candle
- close < support AND high >= support
- session/news guards allow the signal

Execution:
- signal creates a stop-entry valid only on the next chart candle.
- Long planned entry = signal high + 1 tick; stop = signal low - 1 tick.
- Short planned entry = signal low - 1 tick; stop = signal high + 1 tick.
- target = 2.3R from planned entry/stop distance.
- position sizing risks 1% equity, quantized by mincontract/pointvalue in parity engine.
- pending order expires after the next candle if unfilled.
- historical broker-emulator path/tick semantics are parity guarded; TP executable price is tick-quantized.

Managed exit priority after intrabar TP/SL:
1. SESSION
2. NEWS
3. EMA

EMA managed exit:
- Long: close < EMA21 AND no longer in 12-bar-above regime AND EMA is not up over the 2-bar smoothing lookback.
- Short: close > EMA21 AND no longer in 12-bar-below regime AND EMA is up over the 2-bar smoothing lookback.

Canonical session guard in v2.5.13:
- no new setup near UTC day close (40-minute no-entry guard, with chart-boundary semantics)
- force managed exit 15 minutes before UTC day close.

Canonical embedded news sample in v2.5.13 parity source:
- 2025-11-20 13:30 UTC
- 2025-12-10 19:00 UTC
- 2025-12-16 13:30 UTC
- 2025-12-18 13:30 UTC
- exit/lock begins 15 minutes before, resume 15 minutes after.

## Authority distinction
The January `Backtest 2026` / Finalized asset-day-time spreadsheet is a manual historical/filter layer and must not be used to reverse-engineer or overwrite the coded WR setup definition above. Any comparison between those manual entries and the coded WR strategy is a fidelity study, not setup provenance.

## Status
- `WR_CODED_SETUP_AUTHORITY = PINE_V2_5_13`
- `WR_CODED_SETUP_PIVOT = 10/10`
- `WR_SEPARATE_PINE_INDICATOR_FOUND = FALSE`
- `WR_V2_5_14 = DETERMINISTIC_DERIVATIVE_SAME_CORE_SETUP`
- previous 2026-09-21 manual-S/R provenance conclusion = RETRACTED
