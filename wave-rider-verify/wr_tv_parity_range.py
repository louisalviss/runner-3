#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, sys, time
from datetime import timedelta
from pathlib import Path
import websocket

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('base_tv_parity',HERE/'wr_tv_parity.py')
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)

def tv_fetch_range(symbol,session='regular',total=None):
    cs=base.sid('cs_')
    ws=websocket.create_connection('wss://data.tradingview.com/socket.io/websocket?from=chart',origin='https://www.tradingview.com',timeout=20,enable_multithread=True)
    def send(m,p): ws.send(base.frame(m,p))
    send('set_auth_token',['unauthorized_user_token']);send('set_locale',['en','US']);send('chart_create_session',[cs,'']);send('switch_timezone',[cs,'Etc/UTC'])
    cfg='='+json.dumps({'symbol':symbol,'adjustment':'splits','session':session},separators=(',',':'))
    send('resolve_symbol',[cs,'sym_1',cfg])
    a=int((base.START-timedelta(days=150)).timestamp()); b=int((base.END+timedelta(days=5)).timestamp())
    send('create_series',[cs,'s1','s1','sym_1',base.TF,0,f'r,{a}:{b}'])
    rows={};info=None;done=False;deadline=time.time()+150
    def take_series(container):
        if not isinstance(container,dict): return
        candidates=[]
        for key in ('s1','sds_1'):
            if isinstance(container.get(key),dict): candidates.append(container[key])
        candidates += [v for v in container.values() if isinstance(v,dict) and isinstance(v.get('s'),list)]
        for ser in candidates:
            for item in ser.get('s',[]) or []:
                v=item.get('v') if isinstance(item,dict) else None
                if not v or len(v)<5:continue
                try:
                    ts=int(float(v[0]));rows[ts]=(float(v[1]),float(v[2]),float(v[3]),float(v[4]))
                except Exception:pass
    while time.time()<deadline and not done:
        try: raw=ws.recv()
        except Exception: break
        for kind,msg in base.unpack(raw):
            if kind=='hb':
                try: ws.send(f'~m~{len(msg)}~m~{msg}')
                except Exception: pass
                continue
            m=msg.get('m');p=msg.get('p',[])
            if m=='symbol_resolved' and p and isinstance(p[-1],dict):info=p[-1]
            if m in ('timescale_update','du') and len(p)>1: take_series(p[1])
            if m in ('series_error','symbol_error','critical_error'):
                raise RuntimeError(f'{symbol} {session} {m}: {p}')
            if m=='series_completed':done=True
    try:ws.close()
    except Exception:pass
    if not rows:raise RuntimeError(f'{symbol} {session}: no range bars')
    bars=[base.Bar(ts*1000,ts*1000+base.TF_MS,*rows[ts]) for ts in sorted(rows)]
    print('RANGE',symbol,session,'bars',len(bars),'first',bars[0].ot,'last',bars[-1].ot,flush=True)
    return bars,info or {}

base.tv_fetch=tv_fetch_range
base.main()
