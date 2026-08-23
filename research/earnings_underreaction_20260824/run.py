import pandas as pd
import backtest
from HistoricalEarningsData import load_earnings_data


def load_earnings_from_package():
    e = load_earnings_data().copy()
    e.columns = [str(c).strip().lower() for c in e.columns]
    required = {"symbol", "earnings_date", "surprise"}
    missing = required - set(e.columns)
    if missing:
        raise RuntimeError(f"HistoricalEarningsData missing columns: {sorted(missing)}; got={list(e.columns)}")
    e["symbol"] = e["symbol"].map(backtest.norm_ticker)
    date_text = e["earnings_date"].astype("string").str.extract(r"([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})", expand=False)
    parsed = pd.to_datetime(date_text, format="%b %d, %Y", errors="coerce")
    # Package versions may already contain parseable date values rather than the verbose web string.
    parsed = parsed.fillna(pd.to_datetime(e["earnings_date"], errors="coerce"))
    e["event_date"] = parsed
    e["surprise_pct"] = pd.to_numeric(e["surprise"].astype("string").str.replace("+", "", regex=False).str.replace("%", "", regex=False), errors="coerce")
    e = e.dropna(subset=["symbol", "event_date", "surprise_pct"]).copy()
    e = e[(e["event_date"] >= backtest.DISCOVERY[0]) & (e["event_date"] <= backtest.VALIDATION[1])]
    e = e.drop_duplicates(["symbol", "event_date"], keep="first")
    print(f"HistoricalEarningsData package rows usable 2010-2024: {len(e):,}")
    return e.sort_values(["event_date", "symbol"]).reset_index(drop=True)


backtest.load_earnings = load_earnings_from_package
backtest.main()
