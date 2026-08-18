#!/usr/bin/env python3
import time, urllib.parse
import trinity_backtest as tb

BYBIT = 'https://api.bybit.com/v5/market/kline'

def fetch_bybit(symbol, start_ms, end_ms):
    out = []
    cur_end = end_ms - 1
    while cur_end >= start_ms:
        q = urllib.parse.urlencode({
            'category': 'linear', 'symbol': symbol, 'interval': '3',
            'start': start_ms, 'end': cur_end, 'limit': 1000,
        })
        data = tb.get_json(BYBIT + '?' + q)
        if not isinstance(data, dict) or data.get('retCode') != 0:
            raise RuntimeError(f'Bybit error: {data}')
        rows = data.get('result', {}).get('list', [])
        if not rows:
            break
        times = []
        for x in rows:
            t = int(x[0])
            if start_ms <= t < end_ms:
                out.append(tb.Bar(t, float(x[1]), float(x[2]), float(x[3]), float(x[4])))
                times.append(t)
        if not times:
            break
        earliest = min(times)
        if earliest <= start_ms:
            break
        cur_end = earliest - 1
        time.sleep(0.02)
    bars = [v for _, v in sorted({b.t: b for b in out}.items())]
    expected = (end_ms - start_ms) // tb.INTERVAL_MS
    if len(bars) < expected * 0.95:
        raise RuntimeError(f'{symbol}: incomplete Bybit data {len(bars)}/{expected} bars')
    return bars

# Replace only the market-data transport; preserve the strategy/backtest implementation.
tb.fetch_3m = fetch_bybit
if __name__ == '__main__':
    tb.main()
