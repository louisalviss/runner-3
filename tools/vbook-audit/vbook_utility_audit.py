#!/usr/bin/env python3
import importlib.util,json,os,sys,re
BATCH=os.environ.get('VBOOK_BATCH','/tmp/vbook_batch_plain.py')
sp=importlib.util.spec_from_file_location('vbook_batch',BATCH); b=importlib.util.module_from_spec(sp); sp.loader.exec_module(b)
META=b.META

def manifest(i):
    try:return json.load(open(f'/tmp/vbook-audit/roots/{i}/plugin.json',encoding='utf-8'))
    except:return {}
def fn(i,key):
    x=(manifest(i).get('script') or {}).get(key); return x if x and b.main_script(i,x) else None
def call(i,key,vals):
    f=fn(i,key)
    if not f:return {'ok':False,'kind':'missing_'+key}
    return b.call(i,f,vals,60)
def data(x):return (x.get('inner') or {}).get('data')
def sig(i,key):
    f=fn(i,key); return b.sig(b.main_script(i,f)) if f else []
def choose_id(seq,want=None):
    if not isinstance(seq,list):return ''
    if want:
        for z in seq:
            if isinstance(z,dict):
                v=str(z.get('id') or z.get('value') or z.get('code') or '')
                if v.lower()==want.lower() or v.lower().startswith(want.lower()+'-'):return v
            elif str(z).lower()==want.lower():return str(z)
    for z in seq:
        if isinstance(z,dict):
            v=z.get('id') or z.get('value') or z.get('code') or z.get('name')
            if v:return str(v)
        elif z:return str(z)
    return ''
def args_for(names,typ,voice='',src='vi',dst='en'):
    vals=[]
    for pos,n in enumerate(names or []):
        a=n.lower()
        if any(k in a for k in ('text','content','input','sentence')) or pos==0: vals.append('Xin chào từ VBook')
        elif 'voice' in a: vals.append(voice)
        elif any(k in a for k in ('source','from','src')): vals.append(src)
        elif any(k in a for k in ('target','to','dest','dst')): vals.append(dst)
        elif 'lang' in a: vals.append(dst if typ=='translate' else src)
        else: vals.append('')
    return vals

def one(i):
    r=META[i]; typ=r.get('type') or ((manifest(i).get('metadata') or {}).get('type'))
    out={'i':i,'name':r.get('name'),'type':typ,'source':r.get('source')}
    if typ not in ('tts','translate'):
        out['class']='SKIP_NON_UTILITY'; return out
    if typ=='tts':
        vx=call(i,'voice',[]); voices=data(vx); vid=choose_id(voices,'vi-VN')
        out['voice']={'ok':vx.get('ok'),'kind':vx.get('kind'),'n':len(voices) if isinstance(voices,list) else None,'selected':vid,'err':str(vx.get('err',''))[:220]}
        if not vx.get('ok') or not vid:out['class']='FAIL_UTILITY_VOICE';return out
        names=sig(i,'tts') or []; tx=call(i,'tts',args_for(names,'tts',voice=vid)); td=data(tx)
        L=len(td) if isinstance(td,str) else 0
        out['tts']={'ok':tx.get('ok'),'kind':tx.get('kind'),'len':L,'err':str(tx.get('err',''))[:220]}
        out['class']='PASS_UTILITY' if tx.get('ok') and L>=64 else 'FAIL_UTILITY_TTS';return out
    lx=call(i,'language',[]); langs=data(lx); src=choose_id(langs,'vi') or 'vi'; dst=choose_id(langs,'en') or 'en'
    out['language']={'ok':lx.get('ok'),'kind':lx.get('kind'),'n':len(langs) if isinstance(langs,list) else None,'src':src,'dst':dst,'err':str(lx.get('err',''))[:220]}
    if not lx.get('ok'):out['class']='FAIL_UTILITY_LANGUAGE';return out
    names=sig(i,'translate') or []; tx=call(i,'translate',args_for(names,'translate',src=src,dst=dst)); td=data(tx)
    L=len(td) if isinstance(td,str) else (len(json.dumps(td,ensure_ascii=False)) if td is not None else 0)
    out['translate']={'ok':tx.get('ok'),'kind':tx.get('kind'),'len':L,'sample':str(td)[:120] if td is not None else None,'err':str(tx.get('err',''))[:220]}
    out['class']='PASS_UTILITY' if tx.get('ok') and L>0 else 'FAIL_UTILITY_TRANSLATE';return out

def main():
    ids=[int(x) for x in sys.argv[1].split(',') if x] if len(sys.argv)>1 else list(range(len(META)))
    out=[]
    for i in ids:
        try:r=one(i)
        except Exception as e:r={'i':i,'name':META[i].get('name'),'class':'HARNESS_ERROR','err':repr(e)}
        out.append(r); print(json.dumps(r,ensure_ascii=False),flush=True)
    os.makedirs('out',exist_ok=True); json.dump(out,open('out/utility-audit.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
    bad=[r for r in out if str(r.get('class','')).startswith('FAIL_') or r.get('class')=='HARNESS_ERROR']
    return 3 if bad else 0
if __name__=='__main__':raise SystemExit(main())
