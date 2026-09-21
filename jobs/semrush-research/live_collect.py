#!/opt/chatgpt-bridge/venv/bin/python
from __future__ import annotations
import argparse, hashlib, json, pathlib, subprocess, time, urllib.request
from playwright.sync_api import sync_playwright

MANAGER='http://127.0.0.1:8080'
GUARDIAN='/usr/local/bin/vps-resource-guardian'
PROFILE_ID='5f65f5cd-c8fa-4238-bd14-441760eda81d'
SERVER_TMPL='https://semrush.noxtools.com/server{}.php'

def ts(): return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def sh(cmd,timeout=60): return subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
def http(method,path,payload=None,timeout=60):
    data=json.dumps(payload or {}).encode() if method!='GET' else None
    req=urllib.request.Request(MANAGER+path,data=data,method=method,headers={'Content-Type':'application/json'} if data else {})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read(); return json.loads(raw) if raw else {}
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def atomic(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True); q=path.with_suffix(path.suffix+'.tmp')
    q.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); q.replace(path)
def journal(path,event):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as f: f.write(json.dumps({'at':ts(),**event},ensure_ascii=False,separators=(',',':'))+'\n')
def acquire():
    sh([GUARDIAN,'sweep','--apply'],60)
    p=sh([GUARDIAN,'acquire','--owner','semrush-research-live','--profile',PROFILE_ID,'--priority','interactive','--ttl','1800','--allow-recent-idle-reuse'],30)
    d=json.loads(p.stdout or '{}')
    if p.returncode or not d.get('granted') or not d.get('token'): raise RuntimeError('GUARDIAN_DENIED:'+str(d.get('reason') or p.stderr)[:160])
    return str(d['token'])
def release(tok):
    if tok: sh([GUARDIAN,'release','--token',tok],20)
def launch():
    try:http('POST',f'/api/profiles/{PROFILE_ID}/launch',{},90)
    except Exception:pass
    for _ in range(60):
        try:
            if str(http('GET',f'/api/profiles/{PROFILE_ID}',timeout=10).get('status') or '').lower()=='running': return
        except Exception:pass
        time.sleep(.5)
    raise RuntimeError('PROFILE_LAUNCH_TIMEOUT')
def body(page):
    try:return ' '.join((page.locator('body').inner_text(timeout=4000) or '').split())
    except Exception:return ''
def challenge(page):
    s=(page.title()+' '+body(page)).lower()
    return any(x in s for x in ('just a moment','performing security verification','verify you are human','captcha','security verification'))
def load_bank(path):
    d=json.loads(path.read_text(encoding='utf-8')); out=[]
    for t in d.get('themes',[]):
        tid=str(t.get('theme_id') or '').strip()
        for seed in t.get('seeds') or []:
            seed=' '.join(str(seed).split()).strip()
            if tid and seed: out.append((tid,seed))
    return d,out

def pick_server(page):
    evidence=[]
    for n in range(1,7):
        try:
            page.goto(SERVER_TMPL.format(n),wait_until='domcontentloaded',timeout=45000); page.wait_for_timeout(900)
            ok=bool(page.evaluate('()=>!!window?.sm2?.user?.api_key')) and not challenge(page)
            evidence.append({'server':n,'ok':ok,'title':page.title()[:80]})
            if ok:return n,evidence
        except Exception as e:evidence.append({'server':n,'ok':False,'error':type(e).__name__})
    return None,evidence

def rpc(page,method,args):
    return page.evaluate("""async ({method,args})=>{
      const k=window?.sm2?.user?.api_key; if(!k)return {status:0,result:null,error:{message:'API_KEY_MISSING'}};
      const q={jsonrpc:'2.0',id:1,method,params:{request_id:crypto.randomUUID(),apikey:k,args}};
      const r=await fetch('/kwogw/v2/webapi',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'include',body:JSON.stringify(q)});
      const text=await r.text(); let j=null; try{j=JSON.parse(text)}catch(e){}
      return {status:r.status,result:j?.result??null,error:j?.error??(j?null:{message:'NON_JSON',sample:text.slice(0,160)})};
    }""",{'method':method,'args':args})
def base_args(seed,db): return {'phrase':seed,'device':0,'currency':'USD','database':db,'location':0,'date':''}
def idea_rows(result):
    if isinstance(result,list): return result
    if not isinstance(result,dict): return []
    for k in ('keywords','items','rows','data','results'):
        if isinstance(result.get(k),list): return result[k]
    return []
def get_ideas(page,seed,db,page_size=100):
    base=base_args(seed,db)
    variants=[
      {**base,'display':{'page':1,'pageSize':page_size,'order':{'field':'volume','direction':'desc'}}},
      {**base,'page':1,'pageSize':page_size},
      {**base,'offset':0,'limit':page_size},
    ]
    errs=[]
    for i,args in enumerate(variants,1):
        z=rpc(page,'ideas.GetKeywords',args)
        if z.get('error') is None:return {'rows':idea_rows(z.get('result')),'variant':i,'error':None}
        errs.append(z.get('error'))
    return {'rows':[],'variant':None,'error':errs}

def main():
    ap=argparse.ArgumentParser(description='Live Semrush Research collector via authenticated NoxTools session.')
    ap.add_argument('--seed-bank',required=True); ap.add_argument('--run-dir',required=True); ap.add_argument('--database',default='us')
    ap.add_argument('--max-seeds',type=int,default=0); ap.add_argument('--force',action='store_true')
    a=ap.parse_args(); bank=pathlib.Path(a.seed_bank); out=pathlib.Path(a.run_dir); out.mkdir(parents=True,exist_ok=True)
    statep=out/'collection-state.json'; jp=out/'main-points.jsonl'; rawp=out/'seed-preflight.jsonl'; universep=out/'universe.json'
    bank_sha=sha(bank); _,seeds=load_bank(bank)
    if a.max_seeds>0:seeds=seeds[:a.max_seeds]
    state={'version':1,'bank_sha256':bank_sha,'database':a.database,'stage':'LIVE_AUTH_PENDING','seed_total':len(seeds),'seed_done':0,'server':None,'updated_at':ts()}
    if statep.exists() and not a.force:
        prev=json.loads(statep.read_text())
        if prev.get('bank_sha256')==bank_sha and prev.get('database')==a.database:
            state=prev
            if state.get('stage') in ('UNIVERSE_READY','BLOCKED_RPC_SCHEMA'):
                print(json.dumps({'status':'RESUME_NO_BACKTRACK','state':state},ensure_ascii=False)); return 0
    atomic(statep,state); journal(jp,{'event':'RUN_START','bank_sha256':bank_sha,'seed_total':len(seeds),'database':a.database})
    tok=''
    try:
        tok=acquire(); launch()
        with sync_playwright() as pw:
            br=pw.chromium.connect_over_cdp(f'{MANAGER}/api/profiles/{PROFILE_ID}/cdp',timeout=30000); ctx=br.contexts[0]; page=ctx.pages[-1] if ctx.pages else ctx.new_page()
            server,ev=pick_server(page)
            if server is None:
                state.update(stage='BLOCKED_LIVE_AUTH_CF',blocker='Cloudflare verification on all Semrush NoxTools servers',server_probe=ev,updated_at=ts())
                atomic(statep,state); journal(jp,{'event':'BLOCKED','stage':state['stage'],'server_probe':ev})
                print(json.dumps({'status':'BLOCKED','reason':'LIVE_AUTH_CF','state':state},ensure_ascii=False)); return 3
            state.update(stage='SEED_PREFLIGHT_RUNNING',server=server,updated_at=ts()); atomic(statep,state); journal(jp,{'event':'LIVE_AUTH_PASS','server':server})
            done={}
            if rawp.exists() and not a.force:
                for line in rawp.read_text(encoding='utf-8').splitlines():
                    try:r=json.loads(line); done[(r['theme_id'],r['seed'])]=r
                    except Exception:pass
            with rawp.open('a',encoding='utf-8') as rf:
                for theme,seed in seeds:
                    if (theme,seed) in done:continue
                    info=rpc(page,'keywords.GetInfo',base_args(seed,a.database)); summ=rpc(page,'ideas.GetKeywordsSummary',base_args(seed,a.database))
                    rec={'theme_id':theme,'seed':seed,'info':info.get('result'),'summary':summ.get('result'),'errors':{'info':info.get('error'),'summary':summ.get('error')}}
                    rf.write(json.dumps(rec,ensure_ascii=False,separators=(',',':'))+'\n'); rf.flush(); done[(theme,seed)]=rec
                    state.update(seed_done=len(done),last_seed=seed,updated_at=ts()); atomic(statep,state)
            journal(jp,{'event':'SEED_PREFLIGHT_COMPLETE','seed_done':len(done)})
            projects={theme:{'database':a.database,'seeds':{}} for theme in sorted(set(t for t,_ in seeds))}; schema_error=None
            for theme,seed in seeds:
                ex=get_ideas(page,seed,a.database)
                projects[theme]['seeds'][seed]={'summary':done.get((theme,seed),{}).get('summary'),'info':done.get((theme,seed),{}).get('info'),'ideas':ex['rows'],'rpc_variant':ex.get('variant')}
                if ex.get('error') and schema_error is None:schema_error={'seed':seed,'errors':ex['error']}
            atomic(universep,{'created_at':ts(),'source':'Semrush Keyword RPC via NoxTools','database':a.database,'seed_bank_sha256':bank_sha,'projects':projects})
            if schema_error:
                state.update(stage='BLOCKED_RPC_SCHEMA',blocker='ideas.GetKeywords returned errors; request-shape validation required',schema_probe=schema_error,updated_at=ts())
                atomic(statep,state); journal(jp,{'event':'BLOCKED','stage':'BLOCKED_RPC_SCHEMA','schema_probe':schema_error})
                print(json.dumps({'status':'BLOCKED','reason':'RPC_SCHEMA','state':state},ensure_ascii=False)); return 4
            state.update(stage='UNIVERSE_READY',universe=str(universep),updated_at=ts()); atomic(statep,state); journal(jp,{'event':'UNIVERSE_READY','project_count':len(projects)})
            print(json.dumps({'status':'PASS','stage':'UNIVERSE_READY','projects':len(projects),'seeds':len(seeds),'universe':str(universep)},ensure_ascii=False)); return 0
    except Exception as e:
        state.update(stage='FAILED',error=type(e).__name__+':'+str(e)[:240],updated_at=ts()); atomic(statep,state); journal(jp,{'event':'FAILED','error':state['error']})
        print(json.dumps({'status':'FAIL','state':state},ensure_ascii=False)); return 1
    finally:release(tok)
if __name__=='__main__':raise SystemExit(main())
