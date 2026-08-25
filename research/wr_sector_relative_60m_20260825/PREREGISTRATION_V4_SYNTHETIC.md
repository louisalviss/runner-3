# Wave Rider Sector-Relative Alignment — V4 Synthetic Sector Benchmark

Date: 2026-08-25 (Asia/Ho_Chi_Minh)
Status: PREREGISTERED / RESULTS UNSEEN

V1/V2 were infrastructure-blocked before PnL because the Dukascopy ETF universe does not provide the exact Communication Services benchmark. V3 attempted direct literal XLC/XLRE resolution but had not produced any PnL before this V4 was frozen. No WR sector-relative PnL has been observed.

## Research question

Does causal relative strength versus a leave-one-out same-sector peer basket, combined with sector participation versus SPY, identify a positive executable subset of frozen WR v2.5.13 US-stock 60m trades?

## Frozen parent

- parent executable run: `32677300335`
- WR v2.5.13 frozen
- 60m US regular session
- actual BID/ASK R outcomes unchanged
- no WR rule/TP/SL/timeframe changes

## Fixed sector membership

- Technology: AAPL ADBE ADI ADSK AMAT AMD AVGO CDNS CSCO CTSH FTNT INTC INTU LRCX MCHP MPWR MRVL MSFT MU NVDA PANW PLTR QCOM SNPS TXN WDAY WDC ZS
- Communication Services: CMCSA EA GOOG GOOGL META NFLX TMUS TTWO
- Consumer Discretionary: AMZN MAR ORLY ROST SBUX TSLA
- Consumer Staples: COST KHC MDLZ PEP WMT
- Energy: BKR FANG
- Health Care: ALNY AMGN DXCM GILD IDXX ISRG REGN VRTX
- Industrials: ADP CPRT CSX HON ODFL PAYX PCAR
- Utilities: AEP EXC

Singleton groups Financials=PYPL and Real Estate=CSGP are structurally ineligible because a leave-one-out peer basket cannot be formed. They are excluded before any PnL view. Primary eligible universe = 66 stocks.

## Synthetic sector construction

Data: paired Dukascopy M5 BID/ASK -> timestamp midpoint -> 60m completed bars.

Within each sector, synchronize member closes and SPY on exact 60m timestamps.

For every completed bar:
- member return = close / previous close - 1
- full-sector return = equal-weight arithmetic mean of all member returns
- full-sector index = cumulative product of (1 + full-sector return), initialized at 1

For target stock `i`:
- leave-one-out sector return = equal-weight arithmetic mean of returns of every other member in the same sector
- LOO sector index = cumulative product of (1 + LOO sector return), initialized at 1
- stock index = stock close / first synchronized stock close
- SPY index = SPY close / first synchronized SPY close

Ratios:
- `RS_stock_sector = stock_index / LOO_sector_index`
- `RS_sector_market = full_sector_index / SPY_index`

Each ratio uses recursive `EMA(50)` with `adjust=False, min_periods=50`; slope is current EMA minus immediately previous synchronized-bar EMA.

At WR signal close `t`, context is read only from exact completed `bar_open = t - 60m`. No nearest/future fallback.

LONG aligned iff both ratios > EMA50 and both EMA slopes > 0.
SHORT aligned iff both ratios < EMA50 and both EMA slopes < 0.

## Primary evaluation

2024-2026 only. 2022-2023 diagnostic.

A = all causally scoreable frozen parent trades from the 66 structurally eligible stocks.
B = sector-aligned subset.

## Frozen promotion gates

PASS only if ALL:
1. causal scoring coverage >=95% of eligible OOS parent trades
2. B n >=150
3. B retention 10%-70%
4. B mean R/trade >0
5. B PF >1.05
6. B mean R >= A mean R +0.10R
7. B total R >0
8. B positive in >=2 of 2024/2025/2026
9. >=50% of symbols with >=5 B trades positive cumulative R
10. day-block bootstrap 95% lower bound B mean R >0
11. day-block bootstrap 95% lower bound B-A mean delta >0

No sector membership, basket weighting, EMA length, slope rule, threshold, timeframe, direction, or ticker filtering may be changed after results. FAIL closes V4.