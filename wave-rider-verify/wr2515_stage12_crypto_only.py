#!/usr/bin/env python3
from pathlib import Path
import sys

# TradFi symbols that appeared in the first frozen Stage2 selection pass.
# Classification was verified against Binance/official-equivalent launch material before this rerank.
TRADFI_EXCLUDE={
 'BZUSDT','CLUSDT','DRAMUSDT','EWYUSDT','KORUUSDT','MSTRUSDT','MUUSDT',
 'SKHYNIXUSDT','SKHYUSDT','SNDKUSDT','SNXXUSDT','SOXLUSDT','SOXSUSDT',
 'SPCXUSDT','XAGUSDT'
}

p=Path('wave-rider-verify/wr2515_stage12_frozen_merge.py')
s=p.read_text()
old="tv=json.load(open(BASE/'tv_tick_map.json'));summary=json.load(open(BASE/'summary.json'));have={x['symbol'] for x in summary};universe=set(tv)&have"
new="tv=json.load(open(BASE/'tv_tick_map.json'));summary=json.load(open(BASE/'summary.json'));have={x['symbol'] for x in summary};TRADFI_EXCLUDE="+repr(TRADFI_EXCLUDE)+";universe=(set(tv)&have)-TRADFI_EXCLUDE"
if s.count(old)!=1: raise SystemExit('universe patch anchor missing')
s=s.replace(old,new,1)
s=s.replace("'universe_policy':'current TradingView BINANCE USDT perpetual overlap only for this pass'", "'universe_policy':'current TradingView BINANCE USDT perpetual overlap, verified TradFi exclusions applied before Stage2 ranking'",1)
s=s.replace("'universe_symbols':len(universe),", "'universe_symbols':len(universe),'tradfi_excluded':sorted(TRADFI_EXCLUDE),",1)
ns={'__name__':'__main__','__file__':str(p)}
exec(compile(s,str(p),'exec'),ns,ns)
