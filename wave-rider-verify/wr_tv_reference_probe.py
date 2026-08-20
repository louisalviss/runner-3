#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
import websocket

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('tvbase', HERE/'wr_tv_parity.py')
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)

SYMBOL='OANDA:EURUSD'; SESSION='regular'; TF='5'; COUNT=600
CASES=[
    ('recent_back', datetime(2026,8,16,0,0,tzinfo=timezone.utc), COUNT),
    ('y2025_back', datetime(2025,1,15,0,0,tzinfo=timezone.utc), COUNT),
    ('y2025_forward', datetime(2025,1,15,0,0,tzinfo=timezone.utc), -COUNT),
    ('y2024_forward', datetime(2024,1,15,0,0,tzinfo=timezone.utc), -COUNT),
]
OUT=Path('/tmp/wr-tv-ref-probe');OUT.mkdir(parents=True,exist_ok=True)

def fetch_ref(ref_ts:int, count:int):
    cs=base.sid('cs_')
    ws=websocket.create_connection('wss://data.tradingview.com/socket.io/websocket?from=chart',origin='https://www.tradingview.com',timeout=20,enable_multithread=True)
    def send(m,p):ws.send(base.frame(m,p))
    send('set_auth_token',['unauthorized_user_token']);send('set_locale',['en','US']);send('chart_create_session',[cs,'']);send('switch_timezone',[cs,'Etc/UTC'])
    cfg='='+json.dumps({'symbol':SYMBOL,'adjustment':'splits','session':SESSION},separators=(',',':'))
    send('resolve_symbol',[cs,'sym_1',cfg])
    send('create_series',[cs,'s1','s1','sym_1',TF,['bar_count',ref_ts,count]])
    rows={};info=None;errors=[];deadline=time.time()+45
    def take(container):
        if not isinstance(container,dict):return
        for ser in container.values():
            if not isinstance(ser,dict):continue
            for item in ser.get('s',[]) or []:
                v=item.get('v') if isinstance(item,dict) else None
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
            if m in ('series_error','symbol_error','critical_error'):errors.append({'m':m,'p':p})
            if m=='series_completed':deadline=0;break
    try:ws.close()
    except Exception:pass
    ts=sorted(rows)
    return {
        'reference':ref_ts,'requested_count':count,'count':len(ts),'first':ts[0] if ts else None,'last':ts[-1] if ts else None,
        'first_iso':datetime.fromtimestamp(ts[0],timezone.utc).isoformat() if ts else None,
        'last_iso':datetime.fromtimestamp(ts[-1],timezone.utc).isoformat() if ts else None,
        'errors':errors,
        'meta':{k:(info or {}).get(k) for k in ('exchange','listed_exchange','provider_id','timezone','session','subsessions','minmov','pricescale')},
        'sample':[{ 't':t,'o':rows[t][0],'h':rows[t][1],'l':rows[t][2],'c':rows[t][3]} for t in ts[:2]+ts[-2:]],
    }

def main():
    out=[]
    for label,dt,count in CASES:
        row=fetch_ref(int(dt.timestamp()),count);row['label']=label;out.append(row);print('PROBE',json.dumps(row,default=str),flush=True)
    Path(OUT/'probe.json').write_text(json.dumps(out,indent=2,default=str))
    forward=[r for r in out if r['label'].endswith('_forward')]
    ok=all(r['count']>=100 and r['first'] is not None and abs(r['first']-r['reference'])<7*86400 for r in forward)
    print('FORWARD_HISTORY_PASS' if ok else 'FORWARD_HISTORY_FAIL',flush=True)
    if not ok:raise SystemExit(7)
if __name__=='__main__':main()
