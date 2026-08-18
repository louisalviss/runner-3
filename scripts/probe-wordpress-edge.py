import http.client, json, os, ssl, statistics, time
from urllib.parse import urlparse

url=os.environ.get('SITE_URL','https://runner3-factory-smoke-2.wasmer.app/')
out=os.environ.get('EDGE_HTTP_OUT','/tmp/edge-http-probe.json')
p=urlparse(url)
host=p.hostname
path=p.path or '/'
ctx=ssl.create_default_context()

def once(target_path='/', keep=None):
    conn=keep or http.client.HTTPSConnection(host,443,context=ctx,timeout=20)
    t0=time.perf_counter()
    conn.request('GET',target_path,headers={'User-Agent':'EdgeHTTPProbe/1.1','Accept':'text/html,application/xhtml+xml'})
    res=conn.getresponse()
    ttfb=(time.perf_counter()-t0)*1000
    body=res.read()
    headers={k.lower():v for k,v in res.getheaders()}
    row={
        'status':res.status,'ttfbMs':round(ttfb,3),'bytes':len(body),
        'cacheControl':headers.get('cache-control'),'contentLength':headers.get('content-length'),
        'transferEncoding':headers.get('transfer-encoding'),'setCookie':headers.get('set-cookie') is not None,
        'vary':headers.get('vary'),'age':headers.get('age'),'originStamp':headers.get('x-edge-origin-stamp'),
        'edgeMarker':headers.get('x-runner3-edge-cache'),
        'cacheSignals':{k:v for k,v in headers.items() if ('cache' in k or k in ('age','via') or k.startswith('x-wasmer') or k.startswith('x-edge'))}
    }
    if keep is None: conn.close()
    return row

independent=[]
for _ in range(7):
    independent.append(once(path)); time.sleep(.55)

conn=http.client.HTTPSConnection(host,443,context=ctx,timeout=20)
persistent=[]
for _ in range(8):
    persistent.append(once(path,conn)); time.sleep(.2)
conn.close()

login=once('/wp-login.php')
rest=once('/wp-json/')
h=independent[0]
cc=h.get('cacheControl') or ''
try: clen=int(h.get('contentLength') or 0)
except: clen=0
eligible=('public' in cc.lower() and ('s-maxage=' in cc.lower() or 'max-age=' in cc.lower()) and clen>0 and not h['setCookie'] and h.get('vary')!='*')
stamps=[r.get('originStamp') for r in independent if r.get('originStamp')]
stamp_reused=len(stamps)>=2 and len(set(stamps)) < len(stamps)
ages=[]
for r in independent:
    try: ages.append(int(r.get('age') or 0))
    except: pass
explicit_hit=(any(a>0 for a in ages) or any('hit' in str(v).lower() for r in independent for v in (r.get('cacheSignals') or {}).values()))
warm=[r['ttfbMs'] for r in persistent[1:] if isinstance(r.get('ttfbMs'),(int,float))]
warm_median=statistics.median(warm) if warm else None
first=persistent[0]['ttfbMs'] if persistent else None
performance_hit=bool(warm_median is not None and first is not None and warm_median <= min(150,first*.75))
edge_reuse=eligible and (stamp_reused or explicit_hit or performance_hit)
admin_safe='public' not in (login.get('cacheControl') or '').lower()
rest_safe='public' not in (rest.get('cacheControl') or '').lower()
result={
    'status':'passed' if edge_reuse and admin_safe and rest_safe else 'failed',
    'site':url,'eligible':eligible,'edgeReuseVerified':edge_reuse,
    'proof':{'originStampReused':stamp_reused,'explicitHit':explicit_hit,'performanceHit':performance_hit},
    'persistent':{'firstTtfbMs':first,'warmMedianTtfbMs':warm_median,'runs':persistent},
    'independent':independent,'loginSafe':admin_safe,'restSafe':rest_safe,'login':login,'rest':rest,
    'checkedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
}
open(out,'w').write(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['status']=='passed' else 1)
