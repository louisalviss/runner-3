#!/usr/bin/env python3
import time, urllib.parse
import trinity_backtest as tb

OKX = 'https://www.okx.com/api/v5/market/history-candles'
MAP = {
    'SOLUSDT': 'SOL-USDT-SWAP',
    'ETHUSDT': 'ETH-USDT-SWAP',
    'XRPUSDT': 'XRP-USDT-SWAP',
}


def fetch_okx(symbol, start_ms, end_ms):
    inst = MAP[symbol]
    out = []
    cursor = end_ms
    while cursor > start_ms:
        q = urllib.parse.urlencode({
            'instId': inst,
            'bar': '3m',
            'after': cursor,
            'limit': 300,
        })
        data = tb.get_json(OKX + '?' + q)
        if not isinstance(data, dict) or data.get('code') != '0':
            raise RuntimeError(f'OKX error for {inst}: {data}')
        rows = data.get('data') or []
        if not rows:
            break
        times = []
        for x in rows:
            t = int(x[0])
            if start_ms <= t < end_ms:
                out.append(tb.Bar(t, float(x[1]), float(x[2]), float(x[3]), float(x[4])))
            times.append(t)
        earliest = min(times)
        if earliest >= cursor:
            raise RuntimeError(f'OKX pagination stalled for {inst}: {earliest} >= {cursor}')
        cursor = earliest
        if earliest <= start_ms:
            break
        time.sleep(0.12)
    bars = [v for _, v in sorted({b.t: b for b in out}.items())]
    expected = (end_ms - start_ms) // tb.INTERVAL_MS
    if len(bars) < expected * 0.95:
        raise RuntimeError(f'{symbol}: incomplete OKX data {len(bars)}/{expected} bars')
    return bars


tb.fetch_3m = fetch_okx
tb.REPORT_DAYS = 30
tb.WARMUP_DAYS = 14

if __name__ == '__main__':
    tb.main()
