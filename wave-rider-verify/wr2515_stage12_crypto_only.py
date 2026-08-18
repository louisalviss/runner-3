#!/usr/bin/env python3
from pathlib import Path

# TradFi symbols that appeared in the first frozen Stage2 selection pass.
# Stage1 shard integrity is still checked against all 672 current-TV symbols;
# this set is removed only from the effective crypto universe before ranking/trade attribution.
TRADFI_EXCLUDE={
 'BZUSDT','CLUSDT','DRAMUSDT','EWYUSDT','KORUUSDT','MSTRUSDT','MUUSDT',
 'SKHYNIXUSDT','SKHYUSDT','SNDKUSDT','SNXXUSDT','SOXLUSDT','SOXSUSDT',
 'SPCXUSDT','XAGUSDT'
}

p=Path('wave-rider-verify/wr2515_stage12_frozen_merge.py')
s=p.read_text()

# Preserve the original 672-symbol Stage1 integrity assertion, then apply TradFi exclusion.
anchor="    if got!=universe:raise SystemExit(f'Stage1 universe mismatch got={len(got)} expected={len(universe)} missing={sorted(universe-got)[:20]}')"
insert=anchor+"\n    TRADFI_EXCLUDE="+repr(TRADFI_EXCLUDE)
if s.count(anchor)!=1: raise SystemExit('Stage1 integrity anchor missing')
s=s.replace(anchor,insert,1)

# Stage1 selection universe becomes crypto-only after the integrity check.
old="        if x['symbol'] in universe:pass_by[int(x['checkpoint'])].add(x['symbol'])"
new="        if x['symbol'] in universe and x['symbol'] not in TRADFI_EXCLUDE:pass_by[int(x['checkpoint'])].add(x['symbol'])"
if s.count(old)!=1: raise SystemExit('pass_by anchor missing')
s=s.replace(old,new,1)

# Structural sample, raw comparator and attributed trades must be crypto-only too.
old="            if sym not in universe:continue"
new="            if sym not in universe or sym in TRADFI_EXCLUDE:continue"
if s.count(old)!=1: raise SystemExit('trade universe anchor missing')
s=s.replace(old,new,1)

s=s.replace(
    "'universe_policy':'current TradingView BINANCE USDT perpetual overlap only for this pass'",
    "'universe_policy':'current TradingView BINANCE USDT perpetual overlap; verified TradFi exclusions applied after Stage1 integrity QA and before ranking/trade attribution'",
    1,
)
s=s.replace(
    "'universe_symbols':len(universe),",
    "'universe_symbols_stage1_qa':len(universe),'crypto_universe_symbols':len(universe-TRADFI_EXCLUDE),'tradfi_excluded':sorted(TRADFI_EXCLUDE),",
    1,
)

ns={'__name__':'__main__','__file__':str(p)}
exec(compile(s,str(p),'exec'),ns,ns)
