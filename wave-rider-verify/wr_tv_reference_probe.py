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
REFS=[
    ('recent', datetime(2026,8,16,0,0,tzinfo=timezone.utc)),
    ('y2025', datetime(2025,1,15,0,0,tzinfo=timezone.utc)),
    ('y2024', datetime(2024,1,15,0,0,tzinfo=timezone.utc)),
]
OUT=Path('/tmp/wr-tv-ref-probe');OUT.mkdir(parents=True,exist_ok=True)

def fetch_ref(ref_ts:int):
    cs=base.sid('cs_')
    ws=websocket.create_connection('wss://data.tradingview.com/socket.io/websocket?from=chart',origin='https://www.tradingview.com',timeout=20,enable_multithread=True)
    def send(m,p):ws.send(base.frame(m,p))
    send('set_auth_token',['unauthorized_user_token']);send('set_locale',['en','US']);send('chart_create_session',[cs,'']);send('switch_timezone',[cs,'Etc/UTC'])
    cfg='='+json.dumps({'symbol':SYMBOL,'adjustment':'splits','session':SESSION},separators=(',',':'))
    send('resolve_symbol',[cs,'sym_1',cfg])
    # TradingView's chart protocol supports a historical reference timestamp:
    # range = ['bar_count', reference_unix_seconds, count].
    send('create_series',[cs,'s1','s1','sym_1',TF,['bar_count',ref_ts,COUNT]])
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
        'reference':ref_ts,'count':len(ts),'first':ts[0] if ts else None,'last':ts[-1] if ts else None,
        'first_iso':datetime.fromtimestamp(ts[0],timezone.utc).isoformat() if ts else None,
        'last_iso':datetime.fromtimestamp(ts[-1],timezone.utc).isoformat() if ts else None,
        'errors':errors,
        'meta':{k:(info or {}).get(k) for k in ('exchange','listed_exchange','provider_id','timezone','session','subsessions','minmov','pricescale')},
        'sample':[{ 't':t,'o':rows[t][0],'h':rows[t][1],'l':rows[t][2],'c':rows[t][3]} for t in ts[-3:]],
    }

def main():
    out=[]
    for label,dt in REFS:
        row=fetch_ref(int(dt.timestamp()));row['label']=label;out.append(row);print('PROBE',json.dumps(row,default=str),flush=True)
    Path(OUT/'probe.json').write_text(json.dumps(out,indent=2,default=str))
    # Historical reference succeeds only if both old anchors return bars near their requested dates.
    ok=True
    for row in out:
        if row['count']<100:ok=False
        if row['last'] is not None and abs(row['last']-row['reference'])>7*86400:ok=False
    print('REFERENCE_HISTORY_PASS' if ok else 'REFERENCE_HISTORY_FAIL',flush=True)
    if not ok:raise SystemExit(7)
if __name__=='__main__':main()
