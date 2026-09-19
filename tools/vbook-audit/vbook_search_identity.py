import importlib.util, json, os, re, sys, unicodedata, html
from urllib.parse import urljoin, urlsplit, urlunsplit

BATCH=os.environ.get('VBOOK_BATCH','/tmp/vbook_batch_plain.py')
sp=importlib.util.spec_from_file_location('vbook_batch', BATCH)
b=importlib.util.module_from_spec(sp); sp.loader.exec_module(b)
META=b.META


def manifest(i):
    try:
        return json.load(open(f'/tmp/vbook-audit/roots/{i}/plugin.json', encoding='utf-8'))
    except Exception:
        return {}


def script_name(i, key):
    fn=(manifest(i).get('script') or {}).get(key)
    return fn if fn and b.main_script(i, fn) else None


def listdata(x):
    d=(x.get('inner') or {}).get('data')
    if isinstance(d, list): return d
    if isinstance(d, dict):
        for k in ('items','list','books','data','docs','chapters'):
            if isinstance(d.get(k), list): return d[k]
    return []


def linkof(x):
    if not isinstance(x, dict): return ''
    return x.get('link') or x.get('url') or x.get('href') or ''


def ab_url(u, host=''):
    if not u: return ''
    if re.match(r'^https?://', str(u), re.I): return str(u)
    base=host or ''
    if base and not base.endswith('/'): base += '/'
    return urljoin(base, str(u))


def norm_url(u):
    if not u: return ''
    try:
        s=urlsplit(u)
        path=re.sub(r'/+$','',s.path) or '/'
        return urlunsplit((s.scheme.lower(),s.netloc.lower(),path,'',''))
    except Exception:
        return str(u).rstrip('/')


def nfc(s): return unicodedata.normalize('NFC', str(s or '')).strip()
def nfd(s): return unicodedata.normalize('NFD', str(s or '')).strip()


def no_accent(s):
    s=nfd(s).replace('đ','d').replace('Đ','D')
    return ''.join(c for c in s if unicodedata.category(c)!='Mn').strip()


def fold_title(s):
    return re.sub(r'\s+',' ',no_accent(s).lower()).strip()


def invoke_search(i, q):
    fn=script_name(i,'search')
    if not fn: return {'ok':False,'kind':'missing_search'}, []
    sg=b.sig(b.main_script(i,fn)) or []
    vals=[]
    for pos,a in enumerate(sg):
        al=a.lower()
        if any(k in al for k in ('key','query','search','name','word')) or pos==0:
            vals.append(q)
        elif 'page' in al:
            vals.append('1')
        else:
            vals.append('')
    x=b.call(i,fn,vals,40)
    return x,listdata(x)


def invoke_url(i,key,url,timeout=40):
    fn=script_name(i,key)
    if not fn:return {'ok':False,'kind':'missing_'+key}
    sg=b.sig(b.main_script(i,fn)) or []
    vals=[url if pos==0 else '' for pos,_ in enumerate(sg)]
    return b.call(i,fn,vals,timeout)


def text_len(v):
    if not isinstance(v,str): return 0
    t=re.sub(r'<[^>]+>',' ',html.unescape(v))
    return len(re.sub(r'\s+',' ',t).strip())


def match_target(items,target_url,target_title,source):
    tu=norm_url(target_url)
    tt=fold_title(target_title)
    title_hits=[]
    for z in items:
        if not isinstance(z,dict): continue
        zu=norm_url(ab_url(linkof(z), z.get('host') or source))
        zn=fold_title(z.get('name') or z.get('title') or '')
        if tu and zu==tu: return z,'url'
        if tt and zn==tt: title_hits.append(z)
    if len(title_hits)==1:return title_hits[0],'title'
    return None,None


def first_chapter(td):
    if not isinstance(td,list):return None
    for z in td:
        if isinstance(z,dict) and z.get('type')!='section' and (z.get('link') or z.get('url')) and not z.get('lock',False) and not z.get('pay',False):
            return z
    for z in td:
        if isinstance(z,dict) and z.get('type')!='section' and (z.get('link') or z.get('url')):
            return z
    return None


def chain_from_result(i,item,source):
    link=ab_url(linkof(item), item.get('host') or source)
    out={'link':link}
    dx=invoke_url(i,'detail',link); dd=(dx.get('inner') or {}).get('data')
    out['detail']={'ok':dx.get('ok'),'kind':dx.get('kind'),'name':dd.get('name') if isinstance(dd,dict) else None,'err':str(dx.get('err',''))[:220]}
    if not dx.get('ok') or not isinstance(dd,dict): return False,out

    toc_input=link
    pfn=script_name(i,'page')
    if pfn:
        px=invoke_url(i,'page',link); pd=listdata(px)
        out['page']={'ok':px.get('ok'),'n':len(pd),'err':str(px.get('err',''))[:180]}
        if px.get('ok') and pd:
            z=pd[0]
            if isinstance(z,str):toc_input=ab_url(z,source)
            elif isinstance(z,dict) and linkof(z):toc_input=ab_url(linkof(z),z.get('host') or source)

    tx=invoke_url(i,'toc',toc_input); td=(tx.get('inner') or {}).get('data')
    out['toc']={'ok':tx.get('ok'),'kind':tx.get('kind'),'n':len(td) if isinstance(td,list) else None,'err':str(tx.get('err',''))[:220]}
    if not tx.get('ok') or not isinstance(td,list) or not td:return False,out
    ch=first_chapter(td)
    if not ch:return False,out
    cu=ab_url(ch.get('link') or ch.get('url'), ch.get('host') or source)
    cx=invoke_url(i,'chap',cu); cd=(cx.get('inner') or {}).get('data'); L=text_len(cd)
    out['chap']={'ok':cx.get('ok'),'kind':cx.get('kind'),'name':ch.get('name') or ch.get('title'),'len':L,'err':str(cx.get('err',''))[:220]}
    return bool(cx.get('ok') and L>=120),out


def audit_one(row):
    i=int(row['i']); source=META[i].get('source') or row.get('source') or ''
    typ=(META[i].get('type') or ((manifest(i).get('metadata') or {}).get('type')) or row.get('type'))
    out={'i':i,'name':META[i].get('name') or row.get('name'),'source':source,'type':typ}
    if typ not in ('novel','chinese_novel'):
        out['class']='SKIP_NON_TEXT_NOVEL'; return out
    if not script_name(i,'search'):
        out['class']='FAIL_NO_SEARCH'; return out
    sample=row.get('sample_item') or {}
    target_url=sample.get('url') or sample.get('raw_link') or ''
    if not target_url:
        out['class']='FAIL_NO_REAL_ITEM'; return out

    dx=invoke_url(i,'detail',target_url); dd=(dx.get('inner') or {}).get('data')
    title=nfc((dd.get('name') if isinstance(dd,dict) else '') or sample.get('name') or '')
    if not title:
        out['class']='FAIL_NO_CANONICAL_TITLE'; return out
    out['target']={'title':title,'url':target_url}

    variants=[('nfc',title,True)]
    qnfd=nfd(title)
    if qnfd!=title:variants.append(('nfd',qnfd,True))
    qascii=no_accent(title)
    if qascii and qascii!=title:
        variants.append(('no_accent',qascii,False))

    results={}; matched_nfc=None
    required_fail=[]
    for key,q,required in variants:
        x,items=invoke_search(i,q)
        m,by=match_target(items,target_url,title,source)
        results[key]={'query':q,'ok':x.get('ok'),'kind':x.get('kind'),'n':len(items),'matched':bool(m),'matched_by':by,'sample':(items[0].get('name') if items and isinstance(items[0],dict) else None),'err':str(x.get('err',''))[:220]}
        if key=='nfc' and m is not None:matched_nfc=m
        if required and (not x.get('ok') or m is None):required_fail.append(key)
    out['search']=results
    if required_fail:
        out['class']='FAIL_SEARCH_IDENTITY_'+('_'.join(k.upper() for k in required_fail));return out
    if matched_nfc is None:
        out['class']='FAIL_SEARCH_IDENTITY_NFC';return out
    good,chain=chain_from_result(i,matched_nfc,source);out['chain']=chain
    if not good:
        out['class']='FAIL_SEARCH_CHAIN';return out
    out['no_accent_supported']=bool((results.get('no_accent') or {}).get('matched')) if 'no_accent' in results else None
    out['class']='PASS_SEARCH_IDENTITY'
    return out


def main():
    e2e_path=os.environ.get('VBOOK_E2E_RESULTS','out/e2e-benchmark.json')
    ids=set(int(x) for x in sys.argv[1].split(',')) if len(sys.argv)>1 and sys.argv[1] else None
    rows=json.load(open(e2e_path,encoding='utf-8'))
    out=[]
    for row in rows:
        if ids is not None and int(row.get('i',-1)) not in ids:continue
        try:r=audit_one(row)
        except Exception as e:r={'i':row.get('i'),'name':row.get('name'),'class':'HARNESS_ERROR','err':repr(e)}
        out.append(r);print(json.dumps(r,ensure_ascii=False),flush=True)
    dest=os.environ.get('VBOOK_SEARCH_IDENTITY_OUT','out/search-identity.json')
    os.makedirs(os.path.dirname(dest) or '.',exist_ok=True)
    json.dump(out,open(dest,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    bad=[r for r in out if str(r.get('class','')).startswith('FAIL_') or r.get('class')=='HARNESS_ERROR']
    return 2 if bad else 0

if __name__=='__main__':
    raise SystemExit(main())
