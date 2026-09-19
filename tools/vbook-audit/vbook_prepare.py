import json,requests,zipfile,io,os,shutil,concurrent.futures
META_FILE=os.environ.get('VBOOK_META_FILE','/tmp/vbook171_meta.json')
rows=json.load(open(META_FILE,encoding='utf-8'))
base='/tmp/vbook-audit/roots'; shutil.rmtree('/tmp/vbook-audit',ignore_errors=True); os.makedirs(base,exist_ok=True)
def one(t):
 i,r=t; d=f'{base}/{i}'; os.makedirs(d,exist_ok=True)
 try:
  b=requests.get(r['path'],timeout=30).content; z=zipfile.ZipFile(io.BytesIO(b)); z.extractall(d)
  p=json.load(open(d+'/plugin.json'))
  return {'i':i,'name':r['name'],'type':r.get('type'),'source':r.get('source'),'path':r['path'],'manifest':p,'ok':True}
 except Exception as e: return {'i':i,'name':r['name'],'type':r.get('type'),'source':r.get('source'),'path':r['path'],'ok':False,'err':repr(e)}
ids_env=os.environ.get('VBOOK_IDS','').strip()
selected=set(int(x) for x in ids_env.split(',') if x.strip()) if ids_env else set(range(len(rows)))
out=[{'i':i,'name':r.get('name'),'type':r.get('type'),'source':r.get('source'),'path':r.get('path'),'ok':False,'skipped':True} for i,r in enumerate(rows)]
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
 for res in ex.map(one,[(i,rows[i]) for i in sorted(selected)]): out[res['i']]=res
json.dump(out,open('/tmp/vbook-audit/meta.json','w'),ensure_ascii=False,indent=2)
print('prepared',sum(x['ok'] for x in out),'/',len(out))
