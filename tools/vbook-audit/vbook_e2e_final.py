import importlib.util,json,sys,time,os,re,subprocess,html
sp=importlib.util.spec_from_file_location('b','/tmp/vbook_batch_plain.py')
b=importlib.util.module_from_spec(sp); sp.loader.exec_module(b)
META=b.META

def manifest(i):
    try:return json.load(open(f'/tmp/vbook-audit/roots/{i}/plugin.json'))
    except:return {}
def smap(i): return manifest(i).get('script') or {}
def script(i,k):
    fn=smap(i).get(k)
    return fn if fn and b.main_script(i,fn) else None
def sig(i,fn): return b.sig(b.main_script(i,fn)) if fn else None

def invoke(i,fn,seed='',timeout=15):
    sg=sig(i,fn)
    if sg is None:return {'ok':False,'kind':'nosig'}
    vals=[]
    for n,a in enumerate(sg):
        al=a.lower()
        if 'page' in al or 'start' in al: vals.append('1')
        elif n==0: vals.append(str(seed))
        else: vals.append('')
    return b.call(i,fn,vals,timeout)

def data(x): return (x.get('inner') or {}).get('data')
def listdata(x):
    d=data(x)
    if isinstance(d,list): return d
    if isinstance(d,dict):
        for k in ('items','list','books','data','docs','chapters'):
            if isinstance(d.get(k),list): return d[k]
    return []
def linkof(x):
    if not isinstance(x,dict): return ''
    return x.get('link') or x.get('url') or ''
def looks_item(x): return bool(isinstance(x,dict) and linkof(x) and (x.get('name') or x.get('title')))
def textlen(v):
    if isinstance(v,str):
        t=re.sub(r'<[^>]+>',' ',html.unescape(v)); return len(re.sub(r'\s+',' ',t).strip())
    return 0

def discover(i):
    tr=[]; home=script(i,'home')
    if home:
        x=invoke(i,home,''); aa=listdata(x); tr.append(['home',x.get('ok'),x.get('kind'),len(aa)])
        for z in aa:
            if looks_item(z): return z,tr
        for z in aa[:10]:
            if not isinstance(z,dict): continue
            fn=z.get('script'); seed=z.get('input','')
            if fn and b.main_script(i,fn) and sig(i,fn) is not None:
                y=invoke(i,fn,seed); yy=listdata(y); tr.append([fn,y.get('ok'),y.get('kind'),len(yy)])
                for q in yy:
                    if looks_item(q): return q,tr
    sr=script(i,'search')
    if sr:
        typ=META[i].get('type')
        qs=['a','truyện','tình'] if typ in ('novel','video','comic','audio') else ['的','仙','爱']
        for q in qs:
            x=invoke(i,sr,q); aa=listdata(x); tr.append(['search:'+q,x.get('ok'),x.get('kind'),len(aa)])
            for z in aa:
                if looks_item(z): return z,tr
    return None,tr

def usable_chapters(td):
    if not isinstance(td,list): return []
    out=[]
    for z in td:
        if not isinstance(z,dict): continue
        if z.get('type')=='section': continue
        u=linkof(z)
        if u and not z.get('lock',False) and not z.get('pay',False): out.append((z,u))
    if not out:
        for z in td:
            if isinstance(z,dict) and z.get('type')!='section' and linkof(z): out.append((z,linkof(z)))
    return out[:5]

def validate_content(i,typ,chap_x):
    d=data(chap_x)
    if typ in ('novel','chinese_novel'):
        return chap_x.get('ok') and textlen(d)>=120, {'len':textlen(d),'shape':type(d).__name__}
    if typ=='video':
        if not chap_x.get('ok') or not isinstance(d,list) or not d:return False,{'n':len(d) if isinstance(d,list) else 0}
        track=script(i,'track'); first=d[0] if isinstance(d[0],dict) else {}
        seed=first.get('data') or first.get('url') or first.get('link') or ''
        if track and seed:
            tx=invoke(i,track,seed); td=data(tx)
            good=tx.get('ok') and isinstance(td,dict) and bool(td.get('data'))
            return good, {'servers':len(d),'track_ok':tx.get('ok'),'track_type':td.get('type') if isinstance(td,dict) else None,'stream':str(td.get('data',''))[:120] if isinstance(td,dict) else ''}
        return bool(seed), {'servers':len(d),'track':False,'seed':str(seed)[:120]}
    if typ=='comic':
        if isinstance(d,list): return chap_x.get('ok') and len(d)>0, {'images':len(d)}
        return chap_x.get('ok') and textlen(d)>20, {'len':textlen(d)}
    if typ=='audio':
        if isinstance(d,list): return chap_x.get('ok') and len(d)>0, {'tracks':len(d)}
        if isinstance(d,dict): return chap_x.get('ok') and bool(d), {'keys':list(d)[:8]}
        return chap_x.get('ok') and bool(d), {'shape':type(d).__name__}
    return chap_x.get('ok') and bool(d), {'shape':type(d).__name__}

def audit(i):
    r=META[i]; typ=r.get('type'); out={'i':i,'name':r.get('name'),'type':typ,'source':r.get('source')}
    item,tr=discover(i); out['discover']=tr
    if not item: out['class']='NO_ITEM'; return out
    url=linkof(item); out['sample_item']={'name':item.get('name') or item.get('title'),'url':url}
    det=script(i,'detail')
    if not det: out['class']='NO_DETAIL'; return out
    x=invoke(i,det,url); dd=data(x); out['detail']={'ok':x.get('ok'),'kind':x.get('kind'),'shape':type(dd).__name__,'err':str(x.get('err',''))[:180]}
    if not x.get('ok') or not isinstance(dd,dict): out['class']='DETAIL_FAIL'; return out
    toc=script(i,'toc')
    if not toc: out['class']='NO_TOC'; return out
    x=invoke(i,toc,url); td=data(x); out['toc']={'ok':x.get('ok'),'kind':x.get('kind'),'n':len(td) if isinstance(td,list) else None,'err':str(x.get('err',''))[:180]}
    cands=usable_chapters(td)
    if not x.get('ok') or not cands: out['class']='TOC_FAIL'; return out
    chfn=script(i,'chap')
    if not chfn: out['class']='NO_CHAP'; return out
    tries=[]
    for ch,u in cands:
        cx=invoke(i,chfn,u); good,info=validate_content(i,typ,cx)
        tries.append({'name':ch.get('name') or ch.get('title'),'url':u,'ok':cx.get('ok'),'kind':cx.get('kind'),'info':info,'err':str(cx.get('err',''))[:160]})
        if good:
            out['chap']=tries; out['class']='PASS_E2E'; return out
    out['chap']=tries; out['class']='CHAP_FAIL'; return out

def reset_engine():
    adb='/opt/android-sdk-local/platform-tools/adb'
    subprocess.run([adb,'-s','emulator-5554','shell','am','force-stop','com.vbook.app'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
    time.sleep(1)
    subprocess.run([adb,'-s','emulator-5554','shell','am','startservice','-n','com.vbook.app/.test.ExtensionTestService'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
    time.sleep(2)

if __name__=='__main__':
    ids=[int(x) for x in sys.argv[1].split(',')]
    out=[]
    for i in ids:
        t=time.time()
        try: row=audit(i)
        except Exception as e: row={'i':i,'name':META[i].get('name'),'class':'HARNESS_ERROR','err':repr(e)}
        row['wall']=round(time.time()-t,2); out.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
        with open('/tmp/vbook-audit/e2e-final.json','w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,indent=2)
        if row['class'] in ('HARNESS_ERROR',):
            try: reset_engine()
            except: pass
