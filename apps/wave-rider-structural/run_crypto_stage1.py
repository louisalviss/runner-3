#!/usr/bin/env python3
from __future__ import annotations
import math, statistics, sys
from decimal import Decimal

import crypto_stage1_close_ab as m


def robust_infer_tick(bars):
    vals=[]
    for b in bars[:5000]:
        vals += [b.o,b.h,b.l,b.c]
    if not vals:
        return None
    ds=[Decimal(str(x)) for x in vals]
    max_dec=max(max(0,-d.as_tuple().exponent) for d in ds)
    max_dec=min(max_dec,12)
    scale=10**max_dec
    ints=sorted(set(int((d*scale).to_integral_value()) for d in ds))
    g=0
    for a,b in zip(ints,ints[1:]):
        if b>a:
            g=math.gcd(g,b-a)
            if g==1:
                break
    tick=(g/scale) if g else (10**(-max_dec))
    med=statistics.median(float(x) for x in vals if float(x)>0)
    if tick<=0 or med<=0:
        raise RuntimeError(f'invalid inferred tick tick={tick} median_price={med}')
    if tick/med > 0.01:
        raise RuntimeError(f'implausibly coarse inferred tick tick={tick} median_price={med} ratio={tick/med}')
    return float(tick)


def robust_info(tick):
    d=Decimal(str(tick)).normalize()
    decimals=max(0,-d.as_tuple().exponent)
    pricescale=10**decimals
    minmov=int((d*pricescale).to_integral_value())
    if minmov<=0:
        raise RuntimeError(f'invalid tick encoding tick={tick}')
    return {
        'timezone':'Etc/UTC',
        'exchange_timezone':'Etc/UTC',
        'session':'0000-0000:1234567',
        'subsessions':[{'id':'regular','session':'0000-0000:1234567'}],
        'minmov':minmov,
        'pricescale':pricescale,
        '_tick':float(tick),
    }


m.infer_tick=robust_infer_tick
m.info=robust_info

if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else 'shard'
    m.shard() if mode=='shard' else m.merge()
