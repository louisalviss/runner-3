import json,os,re,base64,requests,time,html,sys
META=json.load(open('/tmp/vbook-audit/meta.json'))
END='http://127.0.0.1:28080/test'; IP='http://10.0.2.2:18807'
S=requests.Session()
def main_script(i,fn):
 p=f'/tmp/vbook-audit/roots/{i}/src/{fn}'
 try:return open(p,encoding='utf-8').read()
 except:return None
def sig(script):
 m=re.search(r'function\s+execute\s*\(([^)]*)\)',script or '')
 return [x.strip() for x in m.group(1).split(',') if x.strip()] if m else None
def call(i,fn,inputs,timeout=40):
 sc=main_script(i,fn)
 if sc is None:return {'ok':False,'kind':'missing_script'}
 payload={'language':'javascript','script':sc,'ip':IP,'root':str(i),'input':[str(x) for x in inputs]}
 hdr={'data':base64.b64encode(json.dumps(payload,ensure_ascii=False).encode()).decode()}
 t=time.time(); last=None
 for attempt in range(1):
  try:
   rr=S.get(END,headers=hdr,timeout=timeout); outer=rr.json(); sec=round(time.time()-t,2); break
  except Exception as e:
   last=e; time.sleep(0.4)
 else:
  return {'ok':False,'kind':'transport','err':repr(last),'sec':round(time.time()-t,2)}
 if outer.get('status')!=0:return {'ok':False,'kind':'engine','err':outer.get('exception') or outer.get('log') or str(outer)[:1000],'sec':sec}
 try: inner=json.loads(outer.get('result') or '{}')
 except Exception as e:return {'ok':False,'kind':'bad_result','err':repr(e),'raw':str(outer.get('result'))[:500],'sec':sec}
 return {'ok':inner.get('code')==0,'kind':'result','inner':inner,'log':outer.get('log',''),'sec':sec}
def nonempty_list(x): return isinstance(x,list) and len(x)>0
def text_len(x):
 if not isinstance(x,str): return 0
 t=re.sub(r'<[^>]+>',' ',html.unescape(x)); t=re.sub(r'\s+',' ',t).strip(); return len(t)
def audit(i):
 r=META[i]; typ=r.get('type'); out={'i':i,'name':r['name'],'type':typ,'source':r.get('source'),'stages':{}}
 sc=main_script(i,'search.js'); sg=sig(sc)
 if not sg: out['class']='NO_SEARCH_OR_ENCRYPTED'; return out
 qs=['tiên','truyện','a'] if typ=='novel' else ['修仙','仙','的']
 sr=None
 for q in qs:
  inputs=[]
  for a in sg:
   al=a.lower(); inputs.append(q if any(k in al for k in ['key','query','search','name','word']) else ('1' if 'page' in al else ''))
  x=call(i,'search.js',inputs); out['stages']['search']={'q':q,'ok':x.get('ok'),'kind':x.get('kind'),'sec':x.get('sec'),'err':str(x.get('err',''))[:300]}
  data=(x.get('inner') or {}).get('data')
  if x.get('ok') and nonempty_list(data): sr=(x,data[0]); break
 if not sr: out['class']='SEARCH_FAIL_OR_EMPTY'; return out
 item=sr[1]; link=item.get('link') if isinstance(item,dict) else None; host=item.get('host','') if isinstance(item,dict) else ''
 if not link: out['class']='SEARCH_NO_LINK'; return out
 # detail
 x=call(i,'detail.js',[link]); d=(x.get('inner') or {}).get('data'); out['stages']['detail']={'ok':x.get('ok'),'kind':x.get('kind'),'sec':x.get('sec'),'err':str(x.get('err',''))[:300]}
 if not x.get('ok') or not isinstance(d,dict): out['class']='DETAIL_FAIL'; return out
 # toc
 x=call(i,'toc.js',[link]); td=(x.get('inner') or {}).get('data'); out['stages']['toc']={'ok':x.get('ok'),'kind':x.get('kind'),'sec':x.get('sec'),'err':str(x.get('err',''))[:300],'n':len(td) if isinstance(td,list) else None}
 if not x.get('ok') or not nonempty_list(td): out['class']='TOC_FAIL_OR_EMPTY'; return out
 # choose up to 4 unlocked chapters
 cands=[]
 for ch in td:
  if isinstance(ch,dict) and ch.get('link') and not ch.get('lock',False) and not ch.get('pay',False): cands.append(ch)
  if len(cands)>=4: break
 if not cands:
  cands=[ch for ch in td[:4] if isinstance(ch,dict) and ch.get('link')]
 if not cands: out['class']='TOC_NO_LINK'; return out
 chap_results=[]
 for ch in cands:
  x=call(i,'chap.js',[ch['link']]); cd=(x.get('inner') or {}).get('data'); L=text_len(cd)
  chap_results.append({'ok':x.get('ok'),'kind':x.get('kind'),'sec':x.get('sec'),'len':L,'err':str(x.get('err',''))[:220]})
  if x.get('ok') and L>=120:
   out['stages']['chap']=chap_results; out['class']='PASS_E2E'; out['sample']={'book':item.get('name'),'chapter':ch.get('name'),'content_len':L}; return out
 out['stages']['chap']=chap_results; out['class']='CHAP_FAIL_OR_SHORT'; return out

def indices():
 if len(sys.argv)>1: return [int(x) for x in sys.argv[1].split(',')]
 out=[]
 for r in META:
  if r.get('type') not in ('novel','chinese_novel'):continue
  if sig(main_script(r['i'],'search.js')): out.append(r['i'])
 return out
if __name__=='__main__':
 ids=indices(); print('AUDIT',len(ids),ids[:20],flush=True)
 results=[]
 for n,i in enumerate(ids,1):
  t=time.time(); a=audit(i); results.append(a)
  open('/tmp/vbook-audit/plain-results.json','w').write(json.dumps(results,ensure_ascii=False,indent=2))
  print(f"{n}/{len(ids)} i={i} {a['name']} => {a['class']} {time.time()-t:.1f}s",flush=True)
