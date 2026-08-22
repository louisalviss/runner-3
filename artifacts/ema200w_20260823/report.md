# 200-week MA US-stock backtest — causal / point-in-time filtered

Price coverage: 2000-01-07 to 2025-01-03
Weekly rows: 984,281; symbols: 1,017; listing segments: 1,089
Events after point-in-time S&P 500 membership filter: 82,038

Method: previous completed week's 200W MA is the causal touch level. A touch-limit entry requires the current week's adjusted high/low to actually trade through that level. Delisted/ended series are retained; when a requested horizon extends past a genuine pre-dataset-end series termination, the final observed adjusted close is used as the exit instead of silently dropping the trade. Active names whose horizon extends beyond 2024-12-31 are censored.

Matched control: same signal week, point-in-time S&P 500 members, similar 52-week drawdown (±5pp, widened to ±10pp only when needed), excluding stocks simultaneously touching the same MA. This asks whether the MA level adds information beyond simply being in a comparable drawdown.

## 52-week result

| Strategy | N | Median | Win | Median max DD | Matched excess mean | Beat matched | SPY excess mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| EMA_touch_limit_fresh26 | 4339 | 12.0% | 64.3% | -17.0% | 1.3% | 52.7% | -2.0% |
| EMA_reject_close | 8862 | 9.6% | 62.9% | -15.0% | 1.1% | 49.2% | -2.1% |
| EMA_fresh26_rising_reject | 2253 | 11.1% | 64.0% | -16.8% | 0.8% | 52.4% | -2.6% |
| EMA_touch_limit | 17084 | 10.2% | 63.0% | -15.4% | 0.8% | 49.4% | 4.6% |
| EMA_confirm_next_close | 9200 | 9.6% | 63.1% | -14.4% | 0.8% | 48.9% | -2.2% |
| EMA_touch_limit_rising | 11730 | 10.1% | 62.6% | -16.2% | 0.7% | 49.8% | 6.5% |
| SMA_touch_limit | 15210 | 9.8% | 62.7% | -16.0% | 0.7% | 48.7% | 8.2% |
| SMA_reject_close | 7850 | 8.8% | 62.0% | -15.6% | 0.6% | 48.5% | -2.4% |
| SMA_fresh26_rising_reject | 1761 | 9.6% | 61.5% | -17.6% | 0.0% | 50.5% | -3.4% |

## Era stability — 52 weeks

| Strategy | Era | N | Median | Win | Matched excess mean | Beat matched |
|---|---|---:|---:|---:|---:|---:|
| EMA_confirm_next_close | 2004-2009 | 2644 | -0.6% | 49.1% | -0.9% | 45.8% |
| EMA_confirm_next_close | 2010-2019 | 4116 | 12.3% | 67.8% | 0.1% | 49.3% |
| EMA_confirm_next_close | 2015-2024 | 4434 | 11.7% | 65.6% | 1.7% | 49.8% |
| EMA_confirm_next_close | 2020-2024 | 2380 | 15.3% | 70.5% | 3.8% | 51.9% |
| EMA_confirm_next_close | pre2015 | 4706 | 8.1% | 60.8% | -0.1% | 48.1% |
| EMA_fresh26_rising_reject | 2004-2009 | 575 | -8.0% | 38.1% | -4.4% | 45.9% |
| EMA_fresh26_rising_reject | 2010-2019 | 1059 | 17.7% | 73.7% | 2.5% | 55.4% |
| EMA_fresh26_rising_reject | 2015-2024 | 1229 | 15.1% | 71.0% | 2.6% | 54.0% |
| EMA_fresh26_rising_reject | 2020-2024 | 619 | 15.9% | 71.7% | 2.8% | 53.3% |
| EMA_fresh26_rising_reject | pre2015 | 1024 | 5.4% | 55.8% | -1.3% | 50.6% |
| EMA_reject_close | 2004-2009 | 2632 | -0.2% | 49.7% | -0.8% | 46.1% |
| EMA_reject_close | 2010-2019 | 3957 | 12.3% | 67.3% | 0.4% | 49.3% |
| EMA_reject_close | 2015-2024 | 4225 | 12.1% | 65.7% | 2.3% | 50.7% |
| EMA_reject_close | 2020-2024 | 2218 | 15.9% | 70.9% | 4.6% | 53.0% |
| EMA_reject_close | pre2015 | 4582 | 7.7% | 60.5% | -0.1% | 48.0% |
| EMA_touch_limit | 2004-2009 | 5105 | 0.1% | 50.1% | -1.1% | 47.1% |
| EMA_touch_limit | 2010-2019 | 7549 | 12.4% | 66.7% | 0.4% | 49.9% |
| EMA_touch_limit | 2015-2024 | 8175 | 12.6% | 65.8% | 1.9% | 50.2% |
| EMA_touch_limit | 2020-2024 | 4333 | 17.6% | 71.7% | 3.6% | 51.5% |
| EMA_touch_limit | pre2015 | 8812 | 8.0% | 60.4% | -0.3% | 48.8% |
| EMA_touch_limit_fresh26 | 2004-2009 | 1139 | -6.4% | 41.3% | -1.5% | 48.0% |
| EMA_touch_limit_fresh26 | 2010-2019 | 1941 | 17.5% | 72.4% | 3.0% | 56.4% |
| EMA_touch_limit_fresh26 | 2015-2024 | 2384 | 16.2% | 71.2% | 2.2% | 53.6% |
| EMA_touch_limit_fresh26 | 2020-2024 | 1259 | 17.9% | 72.7% | 1.3% | 51.2% |
| EMA_touch_limit_fresh26 | pre2015 | 1955 | 5.6% | 55.9% | 0.3% | 51.6% |
| EMA_touch_limit_rising | 2004-2009 | 3353 | -3.1% | 46.0% | -0.9% | 47.5% |
| EMA_touch_limit_rising | 2010-2019 | 5256 | 14.0% | 68.4% | 1.0% | 51.3% |
| EMA_touch_limit_rising | 2015-2024 | 5902 | 12.8% | 66.3% | 1.4% | 50.1% |
| EMA_touch_limit_rising | 2020-2024 | 3121 | 16.5% | 70.8% | 1.9% | 49.8% |
| EMA_touch_limit_rising | pre2015 | 5828 | 7.3% | 59.0% | 0.0% | 49.6% |
| SMA_fresh26_rising_reject | 2004-2009 | 469 | -10.2% | 33.0% | -1.8% | 45.8% |
| SMA_fresh26_rising_reject | 2010-2019 | 777 | 16.8% | 72.7% | 1.4% | 53.8% |
| SMA_fresh26_rising_reject | 2015-2024 | 1004 | 13.9% | 70.6% | 0.6% | 51.1% |
| SMA_fresh26_rising_reject | 2020-2024 | 515 | 14.1% | 70.5% | -0.3% | 49.9% |
| SMA_fresh26_rising_reject | pre2015 | 757 | 0.0% | 49.4% | -0.7% | 49.8% |
| SMA_reject_close | 2004-2009 | 2364 | -2.1% | 46.9% | 0.6% | 47.1% |
| SMA_reject_close | 2010-2019 | 3512 | 12.4% | 67.2% | -0.3% | 48.2% |
| SMA_reject_close | 2015-2024 | 3662 | 11.4% | 65.8% | 0.6% | 49.1% |
| SMA_reject_close | 2020-2024 | 1929 | 13.9% | 70.5% | 2.3% | 51.0% |
| SMA_reject_close | pre2015 | 4143 | 6.3% | 58.4% | 0.6% | 48.1% |
| SMA_touch_limit | 2004-2009 | 4601 | -1.5% | 48.1% | -0.5% | 47.0% |
| SMA_touch_limit | 2010-2019 | 6634 | 12.6% | 67.0% | 0.3% | 48.8% |
| SMA_touch_limit | 2015-2024 | 7250 | 12.8% | 66.7% | 1.2% | 49.4% |
| SMA_touch_limit | 2020-2024 | 3876 | 16.5% | 72.6% | 2.6% | 50.6% |
| SMA_touch_limit | pre2015 | 7861 | 7.1% | 58.9% | 0.2% | 48.0% |

## Caveats

- FINSABER identifies the price file as S&P 500 prices including delisted names; membership is independently filtered with the fja05680 point-in-time S&P 500 history.
- The price archive ends 2024-12-31, so 2025-2026 are not part of this historical test.
- Adjusted OHLC is reconstructed by scaling raw OHLC with adjusted_close/close. This keeps split/dividend scaling internally consistent.
- Final observed price on early-ended series is a practical delisting proxy, not CRSP delisting-return quality. Therefore this is materially cleaner than current-survivor backtests but not institutional-grade CRSP validation.
- Multiple variants are exploratory. Do not select the best-looking row as a production rule without a frozen follow-up test.