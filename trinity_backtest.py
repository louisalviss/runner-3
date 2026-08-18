#!/usr/bin/env python3
import json, math, time, urllib.parse, urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = 'https://fapi.binance.com/fapi/v1/klines'
INTERVAL_MS = 3 * 60 * 1000
REPORT_DIR = Path('reports/trinity-atr-supertrend')
SYMBOLS = ['SOLUSDT', 'ETHUSDT', 'XRPUSDT']
ATR_LEN = 10
MULT = 1.0
REPORT_DAYS = 90
WARMUP_DAYS = 14
COST_PER_SIDE = 0.0005  # explicit modeling assumption, 5 bps per side

@dataclass
class Bar:
    t: int
    o: float
    h: float
    l: float
    c: float


def get_json(url, tries=5):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'runner-3-trinity-audit/1.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            last = e
            time.sleep(min(2 ** i, 8))
    raise RuntimeError(f'GET failed after {tries} tries: {url}: {last}')


def fetch_3m(symbol, start_ms, end_ms):
    out = []
    cur = start_ms
    while cur < end_ms:
        q = urllib.parse.urlencode({
            'symbol': symbol, 'interval': '3m', 'startTime': cur,
            'endTime': end_ms - 1, 'limit': 1500,
        })
        data = get_json(BASE + '?' + q)
        if not isinstance(data, list) or not data:
            break
        for x in data:
            t = int(x[0])
            if t >= end_ms:
                continue
            out.append(Bar(t, float(x[1]), float(x[2]), float(x[3]), float(x[4])))
        nxt = int(data[-1][0]) + INTERVAL_MS
        if nxt <= cur:
            break
        cur = nxt
        time.sleep(0.03)
    by_t = {b.t: b for b in out}
    bars = [by_t[t] for t in sorted(by_t)]
    expected = (end_ms - start_ms) // INTERVAL_MS
    if len(bars) < expected * 0.95:
        raise RuntimeError(f'{symbol}: incomplete data {len(bars)}/{expected} bars')
    return bars


def aggregate(bars, minutes):
    bucket_ms = minutes * 60 * 1000
    res = []
    cur_key = None
    acc = None
    for b in bars:
        k = (b.t // bucket_ms) * bucket_ms
        if k != cur_key:
            if acc is not None:
                res.append(acc)
            cur_key = k
            acc = Bar(k, b.o, b.h, b.l, b.c)
        else:
            acc.h = max(acc.h, b.h)
            acc.l = min(acc.l, b.l)
            acc.c = b.c
    if acc is not None:
        res.append(acc)
    return res


def rma_atr(bars, length):
    tr = [math.nan] * len(bars)
    for i, b in enumerate(bars):
        if i == 0:
            tr[i] = b.h - b.l
        else:
            pc = bars[i-1].c
            tr[i] = max(b.h - b.l, abs(b.h - pc), abs(b.l - pc))
    atr = [math.nan] * len(bars)
    if len(bars) < length:
        return atr
    seed = sum(tr[:length]) / length
    atr[length-1] = seed
    for i in range(length, len(bars)):
        atr[i] = (atr[i-1] * (length - 1) + tr[i]) / length
    return atr


def supertrend_custom(bars, length=10, mult=1.0):
    atr = rma_atr(bars, length)
    up = [math.nan] * len(bars)
    dn = [math.nan] * len(bars)
    st = [math.nan] * len(bars)
    direction = [1] * len(bars)
    for i, b in enumerate(bars):
        if math.isnan(atr[i]):
            continue
        raw_up = (b.h + b.l) / 2 - mult * atr[i]
        raw_dn = (b.h + b.l) / 2 + mult * atr[i]
        if i > 0 and not math.isnan(up[i-1]):
            up[i] = max(raw_up, up[i-1]) if bars[i-1].c > up[i-1] else raw_up
            dn[i] = min(raw_dn, dn[i-1]) if bars[i-1].c < dn[i-1] else raw_dn
            prev_dir = direction[i-1]
            if b.c > dn[i-1]:
                direction[i] = -1
            elif b.c < up[i-1]:
                direction[i] = 1
            else:
                direction[i] = prev_dir
        else:
            up[i] = raw_up
            dn[i] = raw_dn
            direction[i] = 1
        st[i] = up[i] if direction[i] == -1 else dn[i]
    return {'atr': atr, 'st': st, 'dir': direction}


def series_map(bars, vals_by_bucket, bucket_minutes, mode):
    bucket_ms = bucket_minutes * 60 * 1000
    keys = sorted(vals_by_bucket)
    idx = {k: i for i, k in enumerate(keys)}
    out = []
    for b in bars:
        k = (b.t // bucket_ms) * bucket_ms
        j = idx.get(k)
        if j is None:
            out.append(math.nan)
            continue
        use_j = j if mode == 'leak' else j - 1
        out.append(vals_by_bucket[keys[use_j]] if use_j >= 0 else math.nan)
    return out


def prepare(bars, mode):
    st1 = supertrend_custom(bars, ATR_LEN, MULT)
    h60 = aggregate(bars, 60)
    h240 = aggregate(bars, 240)
    s60 = supertrend_custom(h60, ATR_LEN, MULT)
    s240 = supertrend_custom(h240, ATR_LEN, MULT)
    d60 = {b.t: s60['dir'][i] for i, b in enumerate(h60)}
    d240 = {b.t: s240['dir'][i] for i, b in enumerate(h240)}
    a60 = {b.t: s60['atr'][i] for i, b in enumerate(h60)}
    return {
        'dir1': st1['dir'],
        'dir2': series_map(bars, d60, 60, mode),
        'dir3': series_map(bars, d240, 240, mode),
        'atr_risk': series_map(bars, a60, 60, mode),
    }


def signal_at(i, s):
    if i <= 0:
        return 0
    d1, p1 = s['dir1'][i], s['dir1'][i-1]
    d2, d3 = s['dir2'][i], s['dir3'][i]
    if any(isinstance(x, float) and math.isnan(x) for x in (d2, d3)):
        return 0
    if d1 == -1 and p1 == 1 and d2 == -1 and d3 == -1:
        return 1
    if d1 == 1 and p1 == -1 and d2 == 1 and d3 == 1:
        return -1
    return 0


def summarize(trades):
    wins = sum(1 for t in trades if t['gross_r'] > 0)
    losses = sum(1 for t in trades if t['gross_r'] < 0)
    gross_profit = sum(max(t['gross_r'], 0) for t in trades)
    gross_loss = -sum(min(t['gross_r'], 0) for t in trades)
    net_profit = sum(max(t['net_r'], 0) for t in trades)
    net_loss = -sum(min(t['net_r'], 0) for t in trades)
    eq = 0.0
    peak = 0.0
    maxdd = 0.0
    for t in trades:
        eq += t['net_r']
        peak = max(peak, eq)
        maxdd = max(maxdd, peak - eq)
    return {
        'trades': len(trades),
        'wins': wins,
        'losses': losses,
        'win_rate_pct': round(100 * wins / len(trades), 2) if trades else None,
        'gross_pf': round(gross_profit / gross_loss, 3) if gross_loss else None,
        'gross_net_r': round(sum(t['gross_r'] for t in trades), 3),
        'net_pf_after_cost': round(net_profit / net_loss, 3) if net_loss else None,
        'net_r_after_cost': round(sum(t['net_r'] for t in trades), 3),
        'max_drawdown_r_after_cost': round(maxdd, 3),
    }


def simulate(bars, s, report_start_ms, clean=False):
    trades = []
    pos = 0
    entry = stop = take = risk = None
    entry_t = None
    pending = 0
    pending_risk = None

    for i, b in enumerate(bars):
        if clean and pos == 0 and pending and pending_risk and not math.isnan(pending_risk):
            pos = pending
            entry = b.o
            risk = pending_risk
            stop = entry - risk if pos == 1 else entry + risk
            take = entry + risk if pos == 1 else entry - risk
            entry_t = b.t
            pending = 0
            pending_risk = None

        if pos != 0:
            outcome = 0
            exit_px = None
            if pos == 1:
                if b.l <= stop:
                    outcome, exit_px = -1, stop
                elif b.h >= take:
                    outcome, exit_px = 1, take
            else:
                if b.h >= stop:
                    outcome, exit_px = -1, stop
                elif b.l <= take:
                    outcome, exit_px = 1, take
            if outcome:
                gross_r = float(outcome)
                cost_r = COST_PER_SIDE * (entry + exit_px) / risk if risk and risk > 0 else 0.0
                net_r = gross_r - cost_r
                if entry_t is not None and entry_t >= report_start_ms:
                    trades.append({'entry_t': entry_t, 'exit_t': b.t, 'side': pos,
                                   'entry': entry, 'exit': exit_px, 'risk': risk,
                                   'gross_r': gross_r, 'net_r': net_r})
                pos = 0
                entry = stop = take = risk = entry_t = None

        sig = signal_at(i, s)
        ar = s['atr_risk'][i]
        if clean:
            if pos == 0 and pending == 0 and sig and not (isinstance(ar, float) and math.isnan(ar)):
                pending = sig
                pending_risk = ar
        else:
            if pos == 0 and sig and not (isinstance(ar, float) and math.isnan(ar)):
                pos = sig
                entry = b.c
                risk = ar
                stop = entry - risk if pos == 1 else entry + risk
                take = entry + risk if pos == 1 else entry - risk
                entry_t = b.t
                outcome = 0
                exit_px = None
                if pos == 1:
                    if b.l <= stop:
                        outcome, exit_px = -1, stop
                    elif b.h >= take:
                        outcome, exit_px = 1, take
                else:
                    if b.h >= stop:
                        outcome, exit_px = -1, stop
                    elif b.l <= take:
                        outcome, exit_px = 1, take
                if outcome:
                    gross_r = float(outcome)
                    cost_r = COST_PER_SIDE * (entry + exit_px) / risk if risk and risk > 0 else 0.0
                    net_r = gross_r - cost_r
                    if entry_t >= report_start_ms:
                        trades.append({'entry_t': entry_t, 'exit_t': b.t, 'side': pos,
                                       'entry': entry, 'exit': exit_px, 'risk': risk,
                                       'gross_r': gross_r, 'net_r': net_r})
                    pos = 0
                    entry = stop = take = risk = entry_t = None
    return trades


def fixed_pine():
    return r'''//@version=5
strategy("Trinity ATR ST - confirmed HTF audit", overlay=true, pyramiding=0,
     process_orders_on_close=false, commission_type=strategy.commission.percent, commission_value=0.05)

atrLen1 = input.int(10, "ST1 ATR Length", minval=1)
mult1   = input.float(1.0, "ST1 Multiplier", minval=0.1, step=0.1)
tf2     = input.timeframe("60", "ST2 timeframe")
tf3     = input.timeframe("240", "ST3 timeframe")
atrLen2 = input.int(10, "ST2 ATR Length", minval=1)
mult2   = input.float(1.0, "ST2 Multiplier", minval=0.1, step=0.1)
atrLen3 = input.int(10, "ST3 ATR Length", minval=1)
mult3   = input.float(1.0, "ST3 Multiplier", minval=0.1, step=0.1)
slMult  = input.float(1.0, "SL x ATR", minval=0.1, step=0.1)
tpMult  = input.float(1.0, "TP x ATR", minval=0.1, step=0.1)

f_supertrend(_high, _low, _close, _len, _mult) =>
    atr = ta.atr(_len)
    hl2 = (_high + _low) / 2
    up = hl2 - _mult * atr
    dn = hl2 + _mult * atr
    up := _close[1] > up[1] ? math.max(up, up[1]) : up
    dn := _close[1] < dn[1] ? math.min(dn, dn[1]) : dn
    var int dir = 1
    dir := _close > dn[1] ? -1 : _close < up[1] ? 1 : nz(dir[1], 1)
    st = dir == -1 ? up : dn
    [st, dir]

f_supertrend_prev(_len, _mult) =>
    [s, d] = f_supertrend(high, low, close, _len, _mult)
    [s[1], d[1]]

[st1, dir1] = f_supertrend(high, low, close, atrLen1, mult1)
[st2, dir2] = request.security(syminfo.tickerid, tf2, f_supertrend_prev(atrLen2, mult2), lookahead=barmerge.lookahead_on)
[st3, dir3] = request.security(syminfo.tickerid, tf3, f_supertrend_prev(atrLen3, mult3), lookahead=barmerge.lookahead_on)
atrHTF = request.security(syminfo.tickerid, tf2, ta.atr(atrLen2)[1], lookahead=barmerge.lookahead_on)

longSignal  = dir1 == -1 and dir1[1] == 1 and dir2 == -1 and dir3 == -1
shortSignal = dir1 == 1 and dir1[1] == -1 and dir2 == 1 and dir3 == 1

var float riskATR = na
if strategy.position_size == 0
    if longSignal
        riskATR := atrHTF
        strategy.entry("L", strategy.long)
    else if shortSignal
        riskATR := atrHTF
        strategy.entry("S", strategy.short)

if strategy.position_size > 0 and not na(riskATR)
    strategy.exit("LX", "L", stop=strategy.position_avg_price - riskATR * slMult,
         limit=strategy.position_avg_price + riskATR * tpMult)
if strategy.position_size < 0 and not na(riskATR)
    strategy.exit("SX", "S", stop=strategy.position_avg_price + riskATR * slMult,
         limit=strategy.position_avg_price - riskATR * tpMult)
if strategy.position_size == 0 and strategy.position_size[1] != 0
    riskATR := na

plot(st1, "ST1", color=dir1 == -1 ? color.aqua : color.fuchsia)
plot(st2, "ST2 confirmed", color=dir2 == -1 ? color.blue : color.purple)
plot(st3, "ST3 confirmed", color=dir3 == -1 ? color.lime : color.red)
'''


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    end_dt = now.replace(minute=0, second=0, microsecond=0)
    end_hour = (end_dt.hour // 4) * 4
    end_dt = end_dt.replace(hour=end_hour)
    report_start_dt = end_dt - timedelta(days=REPORT_DAYS)
    fetch_start_dt = report_start_dt - timedelta(days=WARMUP_DAYS)
    start_ms = int(fetch_start_dt.timestamp()*1000)
    report_start_ms = int(report_start_dt.timestamp()*1000)
    end_ms = int(end_dt.timestamp()*1000)

    result = {
        'generated_utc': now.isoformat(),
        'data_source': 'Binance USDT-M Futures public /fapi/v1/klines',
        'interval': '3m',
        'report_days': REPORT_DAYS,
        'report_start_utc': report_start_dt.isoformat(),
        'report_end_utc': end_dt.isoformat(),
        'defaults_replicated': {'ST1':'3m','ST2':'60m','ST3':'240m','ATR_length':10,'multiplier':1.0,'SL_ATR':1.0,'TP_ATR':1.0,'entry_mode':'triple'},
        'cost_assumption': {'per_side_fraction': COST_PER_SIDE, 'round_trip_bps_approx': COST_PER_SIDE*2*10000},
        'symbols': {}
    }

    for symbol in SYMBOLS:
        try:
            bars = fetch_3m(symbol, start_ms, end_ms)
            leak = prepare(bars, 'leak')
            conf = prepare(bars, 'confirmed')
            t_orig = simulate(bars, leak, report_start_ms, clean=False)
            t_fix_only = simulate(bars, conf, report_start_ms, clean=False)
            t_clean = simulate(bars, conf, report_start_ms, clean=True)
            result['symbols'][symbol] = {
                'bars': len([b for b in bars if b.t >= report_start_ms]),
                'original_emulation': summarize(t_orig),
                'confirmed_htf_samebar_emulation': summarize(t_fix_only),
                'clean_confirmed_nextbar': summarize(t_clean),
            }
        except Exception as e:
            result['symbols'][symbol] = {'error': str(e)}

    (REPORT_DIR / 'backtest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (REPORT_DIR / 'fixed_nonrepaint_strategy.pine').write_text(fixed_pine(), encoding='utf-8')

    lines = []
    lines.append('# Trinity ATR SuperTrend audit backtest')
    lines.append('')
    lines.append(f"Window: {result['report_start_utc']} -> {result['report_end_utc']} (90 days, 3m)")
    lines.append('Defaults: ST1 3m, ST2 60m, ST3 240m, ATR 10, multiplier 1, triple alignment, SL=TP=1x 60m ATR.')
    lines.append('Cost model: 5 bps per side. Clean model enters on next 3m bar open and uses only previously confirmed HTF bars.')
    lines.append('')
    lines.append('| Symbol | Variant | Trades | Win % | Gross PF | Gross R | Net PF | Net R | MaxDD R |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|---:|')
    labels = [
        ('original_emulation','Original lookahead + same-bar'),
        ('confirmed_htf_samebar_emulation','Confirmed HTF, same-bar'),
        ('clean_confirmed_nextbar','Confirmed HTF + next-bar'),
    ]
    for symbol, sr in result['symbols'].items():
        if 'error' in sr:
            lines.append(f'| {symbol} | ERROR: {sr["error"]} | | | | | | | |')
            continue
        for k, label in labels:
            x = sr[k]
            lines.append(f"| {symbol} | {label} | {x['trades']} | {x['win_rate_pct']} | {x['gross_pf']} | {x['gross_net_r']} | {x['net_pf_after_cost']} | {x['net_r_after_cost']} | {x['max_drawdown_r_after_cost']} |")
    lines.append('')
    lines.append('Notes: The published Pastebin file is an indicator, not a TradingView strategy. Therefore its claimed Strategy Tester metrics are not reproducible from that file alone. Max drawdown percent also cannot be uniquely reproduced because position sizing is absent.')
    (REPORT_DIR / 'backtest.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))

if __name__ == '__main__':
    main()
