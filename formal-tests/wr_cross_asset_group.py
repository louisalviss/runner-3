#!/usr/bin/env python3
import importlib.util, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import websocket

p=Path(__file__).with_name('wr_cross_asset_screen.py')
spec=importlib.util.spec_from_file_location('wr_screen',p)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def fetch_one(fullsym,tf,timeout=14):
    cs=m.sid('cs_'); sk='ser_0'
    ws=websocket.create_connection(m.TV,timeout=timeout,origin='https://www.tradingview.com',header=['User-Agent: Mozilla/5.0'])
    vals={}; meta={}; errs=[]; requested_more=False; completions=0
    try:
        ws.send(m.cmd('set_auth_token',['unauthorized_user_token']))
        ws.send(m.cmd('chart_create_session',[cs,'']))
        spec0={'symbol':fullsym,'adjustment':'splits','session':'regular'}
        ws.send(m.cmd('resolve_symbol',[cs,'sym_0','='+json.dumps(spec0,separators=(',',':'))]))
        ws.send(m.cmd('create_series',[cs,sk,sk,'sym_0',str(tf),5000]))
        deadline=time.monotonic()+timeout
        done=False
        while time.monotonic()<deadline and not done:
            ws.settimeout(max(.5,min(4,deadline-time.monotonic())))
            try: raw=ws.recv()
            except Exception: break
            if not isinstance(raw,str): continue
            for payload in m.payloads(raw):
                if payload.startswith('~h~'):
                    ws.send(m.frame(payload)); continue
                try: msg=json.loads(payload)
                except Exception: continue
                method=msg.get('m'); par=msg.get('p',[])
                if method=='symbol_resolved' and len(par)>=3 and isinstance(par[2],dict):
                    x=par[2]
                    for k in ('name','full_name','description','exchange','listed_exchange','timezone','session','minmov','pricescale','pointvalue','type'):
                        if k in x: meta[k]=x[k]
                elif method=='critical_error':
                    errs.append(par)
                elif method=='timescale_update':
                    u=par[1] if len(par)>1 and isinstance(par[1],dict) else {}
                    s=u.get(sk)
                    if isinstance(s,dict):
                        for row in s.get('s',[]):
                            v=row.get('v',[])
                            if len(v)>=5:
                                try: vals[int(float(v[0]))]=v[:5]
                                except Exception: pass
                elif method=='series_completed' and len(par)>1 and par[1]==sk:
                    completions+=1
                    if tf==3 and not requested_more:
                        ws.send(m.cmd('request_more_data',[cs,sk,3000])); requested_more=True
                    else:
                        done=True
        bars=[m.Bar(ts,tf,*vals[ts][1:5]) for ts in sorted(vals)]
        return tf,bars,meta,errs,completions
    finally:
        try: ws.close()
        except Exception: pass

def fetch_symbol_fixed(fullsym,bars=5000,timeout=18):
    out={tf:[] for tf in m.TFS}; meta={}; errs=[]; completed=[]
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs=[ex.submit(fetch_one,fullsym,tf) for tf in m.TFS]
        for f in as_completed(futs):
            try:
                tf,b,md,er,n=f.result(); out[tf]=b
                if md and not meta: meta=md
                if er: errs.extend(er)
                if n: completed.append(str(tf))
            except Exception as e:
                errs.append(repr(e))
    return out,meta,errs,completed

m.fetch_symbol=fetch_symbol_fixed
g=os.environ['WR_GROUP']
if g not in m.GROUPS: raise SystemExit(f'unknown group {g}')
m.GROUPS={g:m.GROUPS[g]}
sys.argv=[sys.argv[0],'--out',f'wr_cross_asset_{g}.json']
m.main()
