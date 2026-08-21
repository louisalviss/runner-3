#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
import websocket

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('tvbase', HERE/'wr_tv_parity.py')
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)

SYMBOL='OANDA:EURUSD'; SESSION='regular'; TF='5'
OUT=Path('/tmp/wr-tv-ref-probe');OUT.mkdir(parents=True,exist_ok=True)
CASES=[
    ('y2025_fake_replay', datetime(2025,1,15,0,0,tzinfo=timezone.utc)),
    ('y2024_fake_replay', datetime(2024,1,15,0,0,tzinfo=timezone.utc)),
]

def fetch_fake_replay(ref_ts:int):
    cs=base.sid('cs_')
    ws=websocket.create_connection('wss://data.tradingview.com/socket.io/websocket?from=chart',origin='https://www.tradingview.com',timeout=20,enable_multithread=True)
    def send(m,p): ws.send(base.frame(m,p))
    send('set_auth_token',['unauthorized_user_token'])
    send('set_locale',['en','US'])
    send('chart_create_session',[cs,''])
    send('switch_timezone',[cs,'Etc/UTC'])
    cfg='='+json.dumps({'symbol':SYMBOL,'adjustment':'splits','session':SESSION},separators=(',',':'))
    send('resolve_symbol',[cs,'ser_1',cfg])
    # Mirror Mathieu2301/TradingView-API Chart.setSeries exactly:
    # create_series(series_id='$prices', alias='s1', symbol='ser_1', range=['bar_count', reference, -1])
    send('create_series',[cs,'$prices','s1','ser_1',TF,['bar_count',ref_ts,-1]])
    rows={}; info=None; errors=[]; completed=0; requests=0
    deadline=time.time()+60
    def take(container):
        if not isinstance(container,dict): return
        candidates=[]
        if isinstance(container.get('$prices'),dict): candidates.append(container['$prices'])
        candidates += [v for v in container.values() if isinstance(v,dict) and isinstance(v.get('s'),list)]
        for ser in candidates:
            for item in ser.get('s',[]) or []:
                v=item.get('v') if isinstance(item,dict) else None
                if not v or len(v)<5: continue
                try: rows[int(float(v[0]))]=(float(v[1]),float(v[2]),float(v[3]),float(v[4]))
                except Exception: pass
    while time.time()<deadline:
        try: raw=ws.recv()
        except Exception: break
        for kind,msg in base.unpack(raw):
            if kind=='hb':
                try: ws.send(f'~m~{len(msg)}~m~{msg}')
                except Exception: pass
                continue
            m=msg.get('m'); p=msg.get('p',[])
            if m=='symbol_resolved' and p and isinstance(p[-1],dict): info=p[-1]
            if m in ('timescale_update','du') and len(p)>1: take(p[1])
            if m in ('series_error','symbol_error','critical_error'): errors.append({'m':m,'p':p})
            if m=='series_completed':
                completed += 1
                # Mirror chart.fetchMore(-N): request_more_data on '$prices' with negative count.
                if requests < 8:
                    send('request_more_data',[cs,'$prices',-250])
                    requests += 1
                else:
                    deadline=0; break
    try: ws.close()
    except Exception: pass
    ts=sorted(rows)
    return {
        'reference':ref_ts,'count':len(ts),'first':ts[0] if ts else None,'last':ts[-1] if ts else None,
        'first_iso':datetime.fromtimestamp(ts[0],timezone.utc).isoformat() if ts else None,
        'last_iso':datetime.fromtimestamp(ts[-1],timezone.utc).isoformat() if ts else None,
        'completed':completed,'forward_requests':requests,'errors':errors,
        'meta':{k:(info or {}).get(k) for k in ('exchange','listed_exchange','provider_id','timezone','session','subsessions','minmov','pricescale')},
        'sample':[{ 't':t,'o':rows[t][0],'h':rows[t][1],'l':rows[t][2],'c':rows[t][3]} for t in ts[:3]+ts[-3:]],
    }

def main():
    out=[]
    for label,dt in CASES:
        row=fetch_fake_replay(int(dt.timestamp())); row['label']=label; out.append(row)
        print('FAKE_REPLAY',json.dumps(row,default=str),flush=True)
    Path(OUT/'probe.json').write_text(json.dumps(out,indent=2,default=str))
    # PASS only if both cases actually start close to requested historical anchor and move forward.
    ok=True
    for r in out:
        if r['count'] < 100 or r['first'] is None or abs(r['first']-r['reference']) > 7*86400 or r['last'] <= r['first']:
            ok=False
    print('FAKE_REPLAY_HISTORY_PASS' if ok else 'FAKE_REPLAY_HISTORY_FAIL',flush=True)
    if not ok: raise SystemExit(7)

if __name__=='__main__': main()
