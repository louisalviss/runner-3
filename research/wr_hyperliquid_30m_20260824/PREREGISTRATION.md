# WR US Stocks 30m — Hyperliquid HIP-3 Validation Preregistration

Date: 2026-08-24

## Frozen candidate
- Strategy: WR 2.5.13 frozen base.
- Timeframe: 30m only.
- Parent universe: 68 US stocks with valid 30m baseline evidence from run 32657035483.
- No RS, no Market-State/regime filter, no alpha parameter changes.
- No symbol or venue selection by realized WR PnL.

## Venue discovery and overlap
- Discover live HIP-3 dexes through Hyperliquid `perpDexs`.
- Read each dex through `metaAndAssetCtxs`.
- Exact ticker overlap only against the frozen 68-symbol WR set.
- Delisted markets and markets without a usable midpoint are excluded.
- If the same ticker exists on multiple HIP-3 dexes, select the market with the highest current `dayNtlVlm`; tie-break by tighter current top-of-book spread. This selection is execution/liquidity based and occurs before WR PnL is inspected.

## Historical replay
- Source: Hyperliquid `candleSnapshot`, interval 30m, ending at the frozen WR endpoint 2026-08-21 UTC.
- Use the recent API-supported lookback window; report exact first/last candle per market and never claim 2022-2026 history if the venue API cannot provide it.
- Signals/strategy logic use the frozen WR 2.5.13 engine and regular US stock session contract (America/New_York 09:30-16:00).
- Tick assumption remains frozen at $0.01 to preserve the candidate definition.

## Execution economics
Historical L2 is not assumed available. Therefore do not label the result "historical actual execution" unless historical book data is actually obtained.

Report separate layers:
1. Gross WR result on Hyperliquid 30m candles.
2. Tier-0 taker-fee-only proxy. WR stop entries and exits are assumed taker.
3. Tier-0 taker fee + current live L2 round-trip crossing/depth proxy at $1k notional.
4. Same as (3) plus historical funding applied at funding timestamps while each replay trade is open, when funding history is available.
5. Current L2 $10k round-trip crossing/depth as a capacity diagnostic, not as the primary small-trade gate.

Fee model:
- Validator-operated baseline taker fee reference: 4.5 bps per fill.
- HIP-3 growth mode applies a 0.1 protocol multiplier.
- Estimated all-in tier-0 taker fee per fill = 4.5 bps × growth multiplier × (1 + deployer fee scale), using the live dex/asset metadata available from the API.
- Report the raw fee metadata and flag this as a model if the API does not expose an authoritative user-specific effective fee.

## Primary gate
Hyperliquid is a viable execution venue for WR 30m only if, on the exact live-overlap set:
- replay has enough trades to be informative (report count; do not force a pass threshold if history is short),
- fee + $1k live-L2 proxy net R is positive,
- PF under that proxy is > 1,
- breadth is not narrowly concentrated in a few symbols,
- and the result is not created by ignoring materially adverse funding.

If the overlap/history is too small, verdict must remain INSUFFICIENT EVIDENCE rather than PASS.
If fee + spread/depth proxy is negative, reject Hyperliquid as the current execution solution for this candidate rather than tuning WR after seeing the result.
