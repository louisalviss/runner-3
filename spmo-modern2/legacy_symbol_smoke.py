#!/usr/bin/env python3
import yfinance as yf
pairs=['FISV','PXD','ATVI','HES','SIVB','DFS','FRC','INFO','CTRA','MRO']
for t in pairs:
    try:
        d=yf.download(t,start='2019-01-01',end='2026-04-01',auto_adjust=False,progress=False,threads=False)
        print(t,'rows',len(d),'first',None if d.empty else str(d.index.min().date()),'last',None if d.empty else str(d.index.max().date()),flush=True)
    except Exception as e:
        print(t,'ERR',type(e).__name__,str(e),flush=True)
