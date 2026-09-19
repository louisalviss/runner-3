#!/usr/bin/env python3
import argparse, concurrent.futures, io, json, re, urllib.request, zipfile
from pathlib import Path

def fetch(url,timeout=30):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 VBookRegistryAudit/1.0'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()

def one(t):
    i,row=t; out={'i':i,'name':row.get('name'),'path':row.get('path'),'source':row.get('source'),'type':row.get('type'),'registry_version':row.get('version')}
    try:
        b=fetch(row['path'])
        out['zip_bytes']=len(b)
        z=zipfile.ZipFile(io.BytesIO(b))
        names=set(z.namelist())
        if 'plugin.json' not in names: raise ValueError('plugin.json missing')
        manifest=json.loads(z.read('plugin.json').decode('utf-8-sig'))
        md=manifest.get('metadata') or {}
        scripts=manifest.get('script') or {}
        out['manifest']={'name':md.get('name'),'version':md.get('version'),'source':md.get('source'),'type':md.get('type'),'scripts':scripts}
        errs=[]; warns=[]
        if str(row.get('version'))!=str(md.get('version')): errs.append(f"version registry={row.get('version')} manifest={md.get('version')}")
        if row.get('source') and md.get('source') and row.get('source').rstrip('/')!=str(md.get('source')).rstrip('/'): warns.append('source mismatch')
        if row.get('type') and md.get('type') and row.get('type')!=md.get('type'): errs.append(f"type registry={row.get('type')} manifest={md.get('type')}")
        for key,fn in scripts.items():
            if fn and f'src/{fn}' not in names and fn not in names: errs.append(f'missing script {key}:{fn}')
        typ=row.get('type') or md.get('type')
        if typ in ('novel','chinese_novel'):
            for req in ('search','detail','toc','chap'):
                if not scripts.get(req): warns.append(f'novel missing {req} declaration')
        out['errors']=errs; out['warnings']=warns; out['class']='PASS_PACKAGE' if not errs else 'FAIL_PACKAGE'
    except Exception as e:
        out['errors']=[repr(e)]; out['warnings']=[]; out['class']='FAIL_PACKAGE'
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--meta',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    rows=json.loads(Path(a.meta).read_text(encoding='utf-8'))
    global_err=[]
    for fld in ('name','path'):
        seen={}
        for i,r in enumerate(rows):
            v=r.get(fld)
            if not v: global_err.append(f'row {i} missing {fld}'); continue
            if v in seen: global_err.append(f'duplicate {fld}: {v} at {seen[v]},{i}')
            seen[v]=i
    # Exact source duplicates are suspicious but legacy registries can intentionally carry variants;
    # report them as warnings rather than making the whole historical registry un-auditable.
    srcs={}; global_warn=[]
    for i,r in enumerate(rows):
        s=str(r.get('source') or '').rstrip('/').lower()
        if not s: continue
        if s in srcs: global_warn.append(f'duplicate source: {s} at {srcs[s]},{i}')
        else: srcs[s]=i
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        results=list(ex.map(one,enumerate(rows)))
    bad=[r for r in results if r['class']!='PASS_PACKAGE']
    report={'total':len(rows),'pass_package':len(rows)-len(bad),'fail_package':len(bad),'global_errors':global_err,'global_warnings':global_warn,'results':results}
    Path(a.out).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('total','pass_package','fail_package','global_errors','global_warnings')},ensure_ascii=False,indent=2))
    raise SystemExit(2 if bad or global_err else 0)
if __name__=='__main__':main()
