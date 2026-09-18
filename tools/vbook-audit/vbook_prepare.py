import json,requests,zipfile,io,os,shutil,concurrent.futures
rows=json.load(open('/tmp/vbook171_meta.json'))
base='/tmp/vbook-audit/roots'; shutil.rmtree('/tmp/vbook-audit',ignore_errors=True); os.makedirs(base,exist_ok=True)
def one(t):
 i,r=t; d=f'{base}/{i}'; os.makedirs(d,exist_ok=True)
 try:
  b=requests.get(r['path'],timeout=30).content; z=zipfile.ZipFile(io.BytesIO(b)); z.extractall(d)
  p=json.load(open(d+'/plugin.json'))
  return {'i':i,'name':r['name'],'type':r.get('type'),'source':r.get('source'),'path':r['path'],'manifest':p,'ok':True}
 except Exception as e: return {'i':i,'name':r['name'],'type':r.get('type'),'source':r.get('source'),'path':r['path'],'ok':False,'err':repr(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex: out=list(ex.map(one,enumerate(rows)))
json.dump(out,open('/tmp/vbook-audit/meta.json','w'),ensure_ascii=False,indent=2)
print('prepared',sum(x['ok'] for x in out),'/',len(out))
