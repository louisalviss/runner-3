import json
import requests

S=requests.Session(); S.headers.update({'User-Agent':'louis-research-provenance-gate/1.0'})
BASE='https://www.dolthub.com/api/v1alpha1/post-no-preference/earnings'
HF='https://datasets-server.huggingface.co/first-rows?dataset=siddharthmb%2Fstocks-earnings-eps_estimate&config=default&split=train'

def dq(q):
    r=S.get(BASE,params={'q':q},timeout=120)
    print('DOLT_HTTP',r.status_code,'QUERY',q)
    print('DOLT_BODY',r.text[:20000])
    r.raise_for_status(); return r.json()


def main():
    # Direct authority metadata/schema/sample.
    dq('SHOW TABLES')
    dq('DESCRIBE eps_estimate')
    meta=dq('SELECT MIN(date) AS min_date, MAX(date) AS max_date, COUNT(*) AS n, COUNT(DISTINCT act_symbol) AS symbols FROM eps_estimate')
    sample=dq("SELECT act_symbol,date,period,period_end_date,consensus,recent,count,high,low,year_ago FROM eps_estimate WHERE act_symbol='AAPL' AND date='2017-10-26' ORDER BY period")
    latest=dq("SELECT act_symbol,date,period,period_end_date,consensus,recent,count,high,low,year_ago FROM eps_estimate WHERE act_symbol='AAPL' ORDER BY date DESC,period LIMIT 12")
    logs=dq('SELECT commit_hash,committer,email,date,message FROM dolt_log LIMIT 20')

    # Compare an exact historical key against HF mirror first-rows.
    h=S.get(HF,timeout=60); print('HF_HTTP',h.status_code); h.raise_for_status(); hj=h.json()
    hrows=[x.get('row',{}) for x in hj.get('rows',[])]
    ha=[x for x in hrows if x.get('act_symbol')=='AAPL' and x.get('date')=='2017-10-26']
    drows=sample.get('rows',[])
    norm=lambda x:{k:(None if x.get(k) is None else str(x.get(k))) for k in ['act_symbol','date','period','period_end_date','consensus','recent','count','high','low','year_ago']}
    hs=sorted([norm(x) for x in ha],key=lambda x:x['period'] or '')
    ds=sorted([norm(x) for x in drows],key=lambda x:x['period'] or '')
    print('MIRROR_COMPARE_HF',json.dumps(hs,sort_keys=True))
    print('MIRROR_COMPARE_DOLT',json.dumps(ds,sort_keys=True))
    print('MIRROR_EXACT_MATCH',hs==ds and len(ds)>0)
    print('DOLT_META',json.dumps(meta,default=str))
    print('DOLT_LATEST_AAPL',json.dumps(latest,default=str)[:15000])
    print('DOLT_LOG_HEAD',json.dumps(logs,default=str)[:15000])
    print('PROVENANCE_GATE_DONE')

if __name__=='__main__': main()
