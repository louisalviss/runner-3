# WR 10m Timing Matched A/B — Final Result

Date: 2026-08-25 (Asia/Ho_Chi_Minh)
Status: COMPLETE / FAIL
Preregistration: `4891b76fc1072dead7a5759b3fca7f330145bc8a`
Run: `32779153302`
Final artifact: `9539737745`
Artifact digest: `sha256:4cf5b9842c31fcbcb96ce62c6dba42891e3d6c48f73a872c4c70a817966bd3db`

## Primary holdout

- Symbols: 63/63
- Matched opportunities: 4,023/4,023
- A PF: 1.3937737824
- A mean return: +64.078865 bps/opportunity
- B executed opportunities: 0
- B execution rate: 0.0%
- B missed rate: 100.0%
- B mean return: 0 bps/opportunity
- B - A mean delta: -64.078865 bps/opportunity

The frozen canonical WR 2.5.13 10m long timing condition did produce WR setups/fill events in the broad market history, but none matched and filled inside the preregistered 60-minute window after any of the 4,023 primary external-alpha opportunities.

## Statistical check

Paired day-block bootstrap (2,000 resamples, 956 days):
- mean delta: -64.078865 bps/opportunity
- 2.5%: -97.049779 bps
- median: -63.891079 bps
- 97.5%: -32.788236 bps

The full 95% bootstrap interval is negative.

## Frozen gate result

- matched opportunities = 4,023: PASS
- B mean >= A + 10 bps: FAIL
- B executed PF >= A PF + 0.05: FAIL
- median entry improvement > 0: FAIL
- execution rate >= 20%: FAIL
- pre-2026 B mean >= A: FAIL
- B beats A in >=2 of 2024/2025/2026: FAIL
- bootstrap 95% lower bound > 0: FAIL
- symbol breadth / median delta gate: FAIL

`PASS_WR_TIMING_INCREMENTAL = false`

## Interpretation

This preregistered WR 10m / 60-minute timing overlay is decisively rejected for the validated RSI E2 + SuperTrend external alpha.

Per preregistration:
- do not tune WR parameters, timing window, timeframe, ticker/sector list, or external-alpha parameters as a rescue inside this lineage;
- keep the independently validated RSI E2 + SuperTrend external alpha unchanged;
- WR standalone alpha remains CLOSED;
- WR is NOT promoted as an incremental timing/execution layer from this test.

This result does not invalidate the parent external alpha. It only shows that this specific frozen WR timing mechanism has essentially zero overlap with the external-alpha opportunity clock under the preregistered causal execution rules.
