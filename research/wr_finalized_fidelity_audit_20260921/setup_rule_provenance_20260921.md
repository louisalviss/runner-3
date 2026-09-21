# Finalized WR setup-rule provenance audit — 2026-09-21

## Authority hierarchy

1. Finalized WR Google Doc: `Wave rider` — `1huCShzPmSiY8MVJ033OuBtuwENLU1og5anK6d1spw04`.
2. Historical workbook: `Backtest 2026` — `1QWSf1LOoBCjcXvg0k-f8CNMJ5MTYFAjTLj9_solFI6g`.
3. User clarification on 2026-09-21:
   - `Ok` = the S/R line was completed/valid at the breakout.
   - `Hit` = the S/R line was not completed, breakout was taken anyway, then the trade stopped.
4. Upstream but distinct Bob optimization doc: `Bob volman` — `16sBpIGioFzA8jXO5V1DbGEBgp2Bf2_L9F8bczFspkoY`, created 2025-12-30 19:50Z. It summarizes a separate ~427-trade Bob dataset and MUST NOT be silently promoted into the Finalized WR rule.

## Proven facts for Finalized WR manual execution

- M5.
- EMA21 is used for trend / barrier context.
- Setup authority text is exactly `Wave Rider / Bob Volman Price Action`.
- Entry is at signal-candle close / next candle open.
- Signal direction follows signal-candle direction.
- Long SL = signal-candle low; short SL = signal-candle high.
- Final TP = +2.3R fixed; SL = -1R fixed; no early TP; no time exit in the Finalized version.
- S/R lines: red resistance / green support; entry requires candle close through the applicable S/R line.
- User clarification: an unfinished/forming S/R line must not be treated as a valid breakout line.

## What is NOT historically proven

No recovered WR source, Drive doc, Dropbox source, or prior conversation provides a canonical LuxAlgo setting or numeric pivot Left/Right parameter for Finalized WR M5.

Therefore all of the following are NON-AUTHORITY hypotheses unless new provenance is found:
- LuxAlgo as a mandatory WR indicator.
- pivot 10/10 as the original WR M5 rule.
- pivot 9/9 as the original WR M5 rule.
- any fixed same-bar retest requirement.
- v2.5.13 `signal_range <= 1.5 ATR`, CHOP, 12-bar regime, or angle gates as mandatory Finalized WR setup conditions.

## Line-test label provenance

Clean historical line-test labels:
- 25 `Ok` positives.
- 3 explicit/original `Hit` negatives: SUI 2025-11-07 05:15, XRP 2026-01-01 21:05, ETH 2026-01-03 21:35.
- 2 legacy labels were originally numeric `1`: XRP 2023-10-20 12:55 and XRP 2023-08-27 21:45. They remained `1` through 2026-04-22 00:15Z and were normalized to `Hit` later, between revisions 3498 and 3506. They are held out from training.

## Numeric pivot grid result

A full Pine-compatible rightmost-tie grid was run on Binance USD-M futures M5 over:
- LeftBars 4..12
- RightBars 4..12
- pivot availability delay 0 and +1 bar
- labels: 25 Ok / 3 original Hit / 2 legacy-1 holdout

Artifact:
`sr_left_right_grid_20260921.json`

Result:
- No Left/Right pair perfectly separates 25/25 Ok from 0/3 Hit.
- RightBars 7/8 can exclude all 3 Hit but loses at least one Ok.
- RightBars 9 can retain 25/25 Ok but admits 1/3 Hit (XRP 2026-01-01 21:05).
- The two other original Hit cases (SUI 2025-11-07 and ETH 2026-01-03) show a clear retrospective-line/repaint-style conflict: the line visible after future pivot confirmation differs from the line available at entry.
- XRP 2026-01-01 21:05 is a one-tick boundary case under smaller RightBars on Binance USD-M: close 1.8582 vs local resistance 1.8583.

## Additional falsified hypothesis

A causal `proper break = close beyond the most recent local N-bar high/low` rule was tested for N=1..20.
It rejects all three original Hit cases, but only preserves 12–17 of 25 Ok depending on N. Therefore Finalized WR S/R is not reducible to a simple recent-high/recent-low breakout.

## Canonical status

- `FINALIZED_WR_MANUAL_RULE = RECOVERED_AT_HUMAN_RULE_LEVEL`
- `FINALIZED_WR_SCHEDULE_EXECUTION = RECOVERED`
- `FINALIZED_WR_ENTRY_ORACLE_48 = RECOVERED`
- `FINALIZED_WR_NUMERIC_SR_PARAMETER = NOT_PROVEN`
- `FINALIZED_WR_AUTOMATED_SETUP_DETECTOR = NOT_EXACT`
- `V2513_IS_EXACT_FINALIZED_WR = FALSE`

Do not claim an exact machine replica until the discretionary Wave Rider/Bob PA setup and completed-line selection can be encoded from authoritative historical evidence or a newly labeled visual oracle.
