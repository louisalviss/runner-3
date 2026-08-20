from pathlib import Path

p=Path('/tmp/zonec_hist.py')
s=p.read_text()
repl={
 "STATE=int(datetime(2024,12,1,tzinfo=timezone.utc).timestamp()*1000)":"STATE=int(datetime(2021,9,1,tzinfo=timezone.utc).timestamp()*1000)",
 "START=int(datetime(2025,1,1,tzinfo=timezone.utc).timestamp()*1000)":"START=int(datetime(2021,10,1,tzinfo=timezone.utc).timestamp()*1000)",
 "END=int(datetime(2026,8,15,tzinfo=timezone.utc).timestamp()*1000)":"END=int(datetime(2024,1,1,tzinfo=timezone.utc).timestamp()*1000)",
 "RUN_END=int(datetime(2026,8,18,tzinfo=timezone.utc).timestamp()*1000)":"RUN_END=int(datetime(2024,1,1,tzinfo=timezone.utc).timestamp()*1000)",
 "months=[(2024,12)]+[(2025,m) for m in range(1,13)]+[(2026,m) for m in range(1,8)]":"months=[(2021,m) for m in range(9,13)]+[(2022,m) for m in range(1,13)]+[(2023,m) for m in range(1,13)]",
}
for a,b in repl.items():
    if s.count(a)!=1: raise SystemExit(f'date patch anchor missing: {a}')
    s=s.replace(a,b,1)
old="""    for d in range(1,19):
        fn=f'{sym}-{source_tf}m-2026-08-{d:02d}.zip'
        u=f'https://data.binance.vision/data/futures/um/daily/klines/{sym}/{source_tf}m/{fn}'
        try:b.extend(readzip(getzip(u)))
        except Exception as e:print('FETCH_ERR',sym,fn,repr(e),flush=True)
"""
if s.count(old)!=1: raise SystemExit('daily-tail patch anchor missing')
s=s.replace(old,'',1)
old='        allowed,sexit=sf(x.ct+1,chart_ms)\n'
new="        allowed,sexit=sf(x.ct+1,chart_ms)\n        vn_hour=((x.ct+1)//3600000+7)%24\n        if vn_hour not in (23,0): allowed=False\n"
if s.count(old)!=1: raise SystemExit('zone patch anchor missing')
s=s.replace(old,new,1)
p.write_text(s)
exec(compile(s,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})
