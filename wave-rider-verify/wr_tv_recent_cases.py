#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
import websocket

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('base_tv_parity',HERE/'wr_tv_parity.py')
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)
base.START=datetime(2026,8,9,17,0,tzinfo=timezone.utc)   # 10 Aug 00:00 VN
base.END=datetime(2026,8,15,17,0,tzinfo=timezone.utc)    # 16 Aug 00:00 VN exclusive
TARGET=5500
OUT=HERE/'output'/'tv-recent-cases';OUT.mkdir(parents=True,exist_ok=True)

def fetch(symbol,session='regular'):
    cs=base.sid('cs_');ws=websocket.create_connection('wss://data.tradingview.com/socket.io/websocket?from=chart',origin='https://www.tradingview.com',timeout=20,enable_multithread=True)
    def send(m,p):ws.send(base.frame(m,p))
    send('set_auth_token',['unauthorized_user_token']);send('set_locale',['en','US']);send('chart_create_session',[cs,'']);send('switch_timezone',[cs,'Etc/UTC'])
    cfg='='+json.dumps({'symbol':symbol,'adjustment':'splits','session':session},separators=(',',':'));send('resolve_symbol',[cs,'sym_1',cfg]);send('create_series',[cs,'s1','s1','sym_1',base.TF,5000,''])
    rows={};info=None;requested=False;deadline=time.time()+60
    def take(c):
        if not isinstance(c,dict):return
        vals=[]
        for k in ('s1','sds_1'):
            if isinstance(c.get(k),dict):vals.append(c[k])
        vals += [v for v in c.values() if isinstance(v,dict) and isinstance(v.get('s'),list)]
        for ser in vals:
            for it in ser.get('s',[]) or []:
                v=it.get('v') if isinstance(it,dict) else None
                if not v or len(v)<5:continue
                try:rows[int(float(v[0]))]=(float(v[1]),float(v[2]),float(v[3]),float(v[4]))
                except Exception:pass
    while time.time()<deadline:
        try:raw=ws.recv()
        except Exception:break
        for kind,msg in base.unpack(raw):
            if kind=='hb':
                try:ws.send(f'~m~{len(msg)}~m~{msg}')
                except Exception:pass
                continue
            m=msg.get('m');p=msg.get('p',[])
            if m=='symbol_resolved' and p and isinstance(p[-1],dict):info=p[-1]
            if m in ('timescale_update','du') and len(p)>1:take(p[1])
            if m=='series_completed':
                if not requested:send('request_more_data',[cs,'s1',500]);requested=True
                else:deadline=0;break
    try:ws.close()
    except Exception:pass
    bars=[base.Bar(ts*1000,ts*1000+base.TF_MS,*rows[ts]) for ts in sorted(rows)]
    return bars,info or {}

def main():
    ref=base.load_ref();specs=[('OANDA:EURUSD','regular'),('OANDA:USDJPY','regular'),('OANDA:XAUUSD','regular'),('ICMARKETS:US500','regular'),('NASDAQ:AAPL','regular'),('NASDAQ:AAPL','extended')]
    ans=[]
    for sym,sess in specs:
        bars,info=fetch(sym,sess)
        # 10-day state warmup is available for 24h instruments; stocks get all returned bars before window.
        hs=base.START-timedelta(days=10)
        tr,m=base.run_case(ref,bars,info,hs,'start',True)
        ans.append({'symbol':sym,'series_session':sess,'n':m.get('n'),'R':m.get('R'),'tick':m.get('tick'),'session':m.get('session'),'timezone':m.get('timezone'),'exits':m.get('exits'),'bars_used':m.get('bars'),'history_first_utc':datetime.fromtimestamp(bars[0].ot/1000,tz=timezone.utc).isoformat() if bars else None})
        print('CASE',ans[-1],flush=True)
    (OUT/'cases.json').write_text(json.dumps(ans,indent=2,default=str))
if __name__=='__main__':main()
