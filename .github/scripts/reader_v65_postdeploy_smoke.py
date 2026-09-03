#!/usr/bin/env python3
import json, sys, urllib.error, urllib.parse, urllib.request

CORE=(sys.argv[1] if len(sys.argv)>1 else 'https://runner3-core.ducduy2411.workers.dev').rstrip('/')
KEY='core/ebook/skeleton-crew/final/Skeleton-Crew-Stephen-King-VI-v2.epub'

def get(path):
    req=urllib.request.Request(CORE+path,headers={'User-Agent':'runner3-reader-v65-smoke/1.0','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=25) as r:
        return r.status,{k.lower():v for k,v in r.headers.items()},r.read().decode('utf-8','replace')

def require(cond,label):
    if not cond: raise SystemExit('READER_V65_SMOKE_FAIL:'+label)

status,h,library=get('/artifact-library')
require(status==200,'library-http')
for marker in ['data-r3-library-v56="1"','r3InstallMainManageV65','r3HydrateServerProgressV65','R3_LIBRARY_FAST_CLIENT_CACHE_V65']:
    require(marker in library,'library-marker:'+marker)

# Prime the derived R2 index once after deploy. R2 remains source of truth; this
# forced request intentionally scans canonical EPUBs and writes the fast index.
status,h,body=get('/artifact-library/api/list?refresh=1')
require(status==200,'library-index-prime-http')
try: prime=json.loads(body)
except Exception as error: raise SystemExit('READER_V65_SMOKE_FAIL:library-index-prime-json:'+str(error))
require(prime.get('ok') is True,'library-index-prime-ok')
require(prime.get('source')=='rebuild','library-index-prime-source')
require(isinstance(prime.get('objects'),list),'library-index-prime-objects')

# The immediately following normal request must hit the small derived index and
# must not need another bucket-wide R2 list scan.
status,h,body=get('/artifact-library/api/list')
require(status==200,'library-index-hit-http')
try: indexed=json.loads(body)
except Exception as error: raise SystemExit('READER_V65_SMOKE_FAIL:library-index-hit-json:'+str(error))
require(indexed.get('ok') is True,'library-index-hit-ok')
require(indexed.get('source')=='index','library-index-hit-source')
require(len(indexed.get('objects') or [])==len(prime.get('objects') or []),'library-index-hit-count')

status,h,version=get('/artifact-library/api/client-version')
require(status==200,'version-http')
require('"reader_client_version":"v65"' in version,'version-v65')
require(h.get('x-r3-reader-client-version')=='v65','version-header')

encoded=urllib.parse.quote(KEY,safe='')
status,h,reader=get('/artifact-library/read?key='+encoded)
require(status==200,'reader-http')
require(h.get('x-r3-reader-runtime')=='v35-continuity-single-owner','reader-runtime')
require(h.get('x-r3-reader-patch-proof')=='v34+v35:ahead-prefetch+range-follow+single-audio-owner','reader-proof')
for marker in [
    '__r3SafariBootGeometryV61','__r3PaginatedVerticalClampV62',"r3ClampPaginatedVerticalV62('cold-boot-guard')",
    'function r3StructuralPercentV64','r3MergeRemoteProgressV65','r3InstallLiveManageV65',
    'data-r3-audio-continuity-v35="1"','data-r3-audio-continuity-v34="1"','data-r3-audio-core-owner-v33="1"',
]:
    require(marker in reader,'reader-marker:'+marker)

for path in ['/artifact-library/api/progress','/artifact-library/api/manage']:
    req=urllib.request.Request(CORE+path,method='GET' if path.endswith('progress') else 'POST',headers={'User-Agent':'runner3-reader-v65-smoke/1.0'})
    try:
        urllib.request.urlopen(req,timeout=20)
        raise SystemExit('READER_V65_SMOKE_FAIL:protected-route-open:'+path)
    except urllib.error.HTTPError as e:
        require(e.code in (401,405), 'protected-route-status:'+path+':'+str(e.code))

print('READER_V65_SERVER_SMOKE=PASS')
print('LIBRARY_FAST_INDEX_PRIME=PASS count=%s rebuild_ms=%s' % (len(prime.get('objects') or []),prime.get('elapsed_ms')))
print('LIBRARY_FAST_INDEX_HIT=PASS elapsed_ms=%s' % indexed.get('elapsed_ms'))
print('SAFARI_COLD_BOOT_VERTICAL_GUARD=PASS')
print('SAFARI_DEVICE_ACCEPTANCE=REQUIRED')
