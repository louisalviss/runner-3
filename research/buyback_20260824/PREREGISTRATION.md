# Buyback Capital Allocation — Preregistered Validation

Status: FROZEN BEFORE RETURN OUTCOMES
Date: 2026-08-24 Asia/Ho_Chi_Minh

## Hypothesis
A company that uses a meaningful amount of capital to repurchase common stock in a reported quarter **and actually shrinks diluted share count YoY** has positive subsequent matched excess return.

This is a capital-allocation hypothesis, not a price-pattern, analyst-revision, 13F, or insider-purchase variant.

## Authority and causal clock
- Official SEC XBRL `companyconcept` filing-version rows.
- Buyback concept: `us-gaap/PaymentsForRepurchaseOfCommonStock`, unit USD.
- Share concept: `us-gaap/WeightedAverageNumberOfDilutedSharesOutstanding`, unit shares.
- SEC Frames may be used only for coverage/discovery, never historical signal values.
- Causal time = `filed` date of the original `10-Q` accession.
- Exact `10-Q` only; exclude amended forms.
- Quarter-like duration 60–120 days.
- Require filing lag 0–120 days after period end.
- No later accession/restatement may replace the value known at the original filing date.

## Historical CIK ↔ ticker mapping
Use official SEC Insider Transactions quarterly data only as a historical issuer-CIK/ticker mapping source. Map each buyback filing to the nearest issuer ticker observation at or before the filing date within 365 days. If unavailable, nearest after filing within 90 days is permitted only for identity mapping; the ticker must be a PIT S&P 500 member at the mapped trading week. Ambiguous CIK/ticker mappings are dropped.

## Frozen signal: `BuybackYield1_Shrink1`
At each eligible 10-Q filing:
1. `repurchase_q` = as-filed quarter-like `PaymentsForRepurchaseOfCommonStock` value for that accession/period; must be >0.
2. `diluted_shares_q` = as-filed quarter-like diluted weighted-average shares for the same accession/period.
3. `market_cap_proxy` = previous completed weekly adjusted close before filing × `diluted_shares_q`.
4. `buyback_yield_q = repurchase_q / market_cap_proxy`.
5. Find the same issuer's closest comparable quarter-like diluted-share observation with period end 330–400 days earlier, using only the accession that had been filed by its own historical filing date.
6. `share_shrink_yoy = diluted_shares_q / diluted_shares_yrago - 1`.
7. Signal iff:
   - `buyback_yield_q >= 0.01`, and
   - `share_shrink_yoy <= -0.01`.

No magnitude sweep, acceleration multiple, ranking percentile, sector whitelist, technical filter, market regime, valuation filter, or ML.

## Entry and outcomes
- Map SEC filing date to first completed weekly bar strictly after filing date.
- Enter following week's adjusted open.
- Primary horizon: 26 weeks.
- Secondary diagnostics: 13 and 52 weeks only.

## Universe
- PIT S&P 500 membership.
- Including-delisted weekly price dataset already used by the validated research framework.
- Missing SEC standardized facts = no signal; no imputation.

## Controls
For each signal, controls are same-week PIT S&P 500 members:
- not the signal ticker,
- no buyback signal in the recent 4 weekly bars,
- valid pre-signal 52-week return,
- matched on pre-signal 52-week return within ±15 percentage points;
- widen once to ±25 percentage points if fewer than 5 controls;
- require at least 3 controls.
Matched excess = signal forward return minus median control forward return.

## Splits
- Discovery: 2010-2016.
- Validation: 2017-2024.
- All SEC/companyconcept facts filed after 2024-12-31 must be hard-excluded before signal construction.
- 2025-2026 outcomes remain untouched unless the frozen validation gate passes.

## PASS26 gate — ALL required
1. matched N >= 300
2. median matched excess > +1.0%
3. beat matched >= 52.5%
4. week-cluster bootstrap 95% CI lower bound for mean matched excess > 0

If validation fails, close the lineage. Do not rescue by changing 1% thresholds, horizon, period type, ticker whitelist, price filters, sector filters, or model selection based on observed outcomes.
