#!/opt/chatgpt-bridge/venv/bin/python
import sys, json, re, time, random, os, argparse
from datetime import datetime, timezone
sys.path.insert(0,"/opt/browser-stack/bin")
from raw_cdp_skill import RawCDPSkill

PROFILE="c97a7500-3b11-403f-ac43-2566cdcd3fa2"
ROOT="/var/lib/acquisition-radar-scan"
PRIOR=f"{ROOT}/flippa-prior-current.json"
STATE=f"{ROOT}/flippa-20261013-state.json"
OUT=f"{ROOT}/flippa-20261013-current.json"

JS=r"""els=>els.map(li=>{
 const txt=(e)=>(e?.innerText||e?.textContent||'').trim();
 const ps=[...li.querySelectorAll('p')];
 const metric=(label)=>{
   const p=ps.find(x=>txt(x)===label);
   if(!p) return '';
   const par=p.parentElement;
   const vals=[...par.querySelectorAll('p')].map(txt).filter(Boolean);
   return vals.length>1?vals[1]:'';
 };
 const href=(li.querySelector('h4 a[href*="flippa.com/"]')||li.querySelector('a.GTM-search-result-card'))?.href||'';
 const desc=ps.find(x=>String(x.className||'').includes('tw-line-clamp-3'));
 const h4=li.querySelector('h4 a');
 return {
   id:String(li.id||'').replace('listing-',''),
   title:txt(desc), heading:txt(h4), href,
   revenue:metric('Monthly Revenue'), profit:metric('Monthly Profit'),
   price:metric('Asking price'), type:metric('Type'), age:metric('Age'),
   vet:(txt(li).includes('Data Verified')?1:0), text:txt(li).slice(0,3500)
 };
})"""

def money(s):
    if not s: return None
    s=s.replace(",","").replace("USD","").replace("$","").strip()
    s=re.sub(r"^([+-])\s+(?=\d)", r"\1", s)
    m=re.search(r"(-?\d+(?:\.\d+)?)\s*([KMB]?)",s,re.I)
    if not m: return None
    v=float(m.group(1)); mult={"":1,"K":1_000,"M":1_000_000,"B":1_000_000_000}.get(m.group(2).upper(),1)
    x=v*mult
    return int(round(x)) if abs(x-round(x))<1e-9 else round(x,2)

def listing_price(raw):
    p=money(raw.get("price"))
    if p is not None: return p
    t=str(raw.get("text") or "")
    m=re.search(r"(?:^|\n)Auction\s*\n+\s*(USD\s*\$[\d,.]+(?:\s*[KMB])?)",t,re.I)
    if m: return money(m.group(1))
    m=re.search(r"(?:^|\n)Asking price\s*\n+\s*(USD\s*\$[\d,.]+(?:\s*[KMB])?)",t,re.I)
    return money(m.group(1)) if m else None

def norm(raw, first=False):
    return {
      "id":str(raw.get("id") or ""), "title":str(raw.get("title") or ""),
      "p":listing_price(raw), "pr":money(raw.get("profit")),
      "rev":money(raw.get("revenue")), "pt":str(raw.get("type") or ""),
      "age":str(raw.get("age") or ""), "vet":int(raw.get("vet") or 0),
      "href":str(raw.get("href") or ""), "fa":1 if first else 0,
      "heading":str(raw.get("heading") or ""), "raw_text":str(raw.get("text") or "")
    }

def keyrow(r):
    return [r.get("title") or "",r.get("p"),r.get("pr"),r.get("rev"),r.get("pt") or "",r.get("age") or "",r.get("vet") or 0,r.get("href") or ""]

def atomic(path,obj):
    tmp=path+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(obj,f,ensure_ascii=False)
    os.replace(tmp,path)

def load_state():
    if os.path.exists(STATE):
        with open(STATE,encoding="utf-8") as f:return json.load(f)
    return {
      "schema":"flippa-stage-state-v1","started_at":datetime.now(timezone.utc).isoformat(),
      "status":"RUNNING","first_done":False,"recent_done":False,"main_done":False,
      "first_ids":[],"recent_ids":[],"main":{},"pages":[],"next_main_page":1,
      "reported_total":None,"total_pages":None,"main_observations":0,"errors":[]
    }

def check_stop(st,ch,page,lane,state):
    if st in (403,429) or ch!="NONE":
        state["status"]="PAUSED"
        state["errors"].append({"lane":lane,"page":page,"status":st,"challenge":ch,"at":datetime.now(timezone.utc).isoformat()})
        atomic(STATE,state)
        raise RuntimeError(f"STOP_{lane.upper()} status={st} challenge={ch} page={page}")

def fetch_cards(p,s,url,wait=1400):
    resp=p.goto(url,wait_until="domcontentloaded",timeout=60000); p.wait_for_timeout(wait)
    st=resp.status if resp else 0; ch=s.challenge()
    raws=p.locator("li[id^='listing-']").evaluate_all(JS)
    return st,ch,raws

def do_bootstrap(state):
    with RawCDPSkill(PROFILE,owner="flippa-stage-bootstrap-20261013",keep_running=False,new_page=True,close_page_on_exit=True,priority="auth") as s:
        p=s.page
        if not state["first_done"]:
            for page_no in (1,2):
                u=f"https://flippa.com/buy/first-access?page_size=100&page={page_no}" if page_no>1 else "https://flippa.com/buy/first-access?page_size=100"
                st,ch,raws=fetch_cards(p,s,u,1800)
                check_stop(st,ch,page_no,"first_access",state)
                for x in raws:
                    r=norm(x,True)
                    if r["id"]: state["first_ids"].append(r["id"])
                state["first_ids"]=list(dict.fromkeys(state["first_ids"]))
                state["pages"].append({"lane":"first_access","page":page_no,"status":st,"count":len(raws),"challenge":ch})
                atomic(STATE,state)
                if len(raws)<100: break
                time.sleep(random.uniform(12,18))
            state["first_done"]=True; atomic(STATE,state)
        if not state["recent_done"]:
            for page_no in range(1,6):
                u=f"https://flippa.com/search?page_size=100&sort_alias=most_recent&page={page_no}"
                st,ch,raws=fetch_cards(p,s,u)
                check_stop(st,ch,page_no,"recent",state)
                for x in raws:
                    r=norm(x,False)
                    if r["id"]:
                        state["recent_ids"].append(r["id"])
                        state.setdefault("recent_rows",{})[r["id"]]=r
                state["recent_ids"]=list(dict.fromkeys(state["recent_ids"]))
                state["pages"].append({"lane":"recent","page":page_no,"status":st,"count":len(raws),"challenge":ch})
                atomic(STATE,state)
                if page_no<5: time.sleep(random.uniform(12,18))
            state["recent_done"]=True; atomic(STATE,state)
    print(json.dumps({"stage":"bootstrap","first_access_count":len(state["first_ids"]),"recent_count":len(state["recent_ids"]),"next_main_page":state["next_main_page"]}))

def do_main(state,max_pages):
    if state.get("main_done"):
        print(json.dumps({"stage":"main","already_done":True,"unique":len(state["main"])})); return
    start=int(state.get("next_main_page") or 1)
    done=0
    with RawCDPSkill(PROFILE,owner="flippa-stage-main-20261013",keep_running=False,new_page=True,close_page_on_exit=True,priority="auth") as s:
        p=s.page
        for page_no in range(start,start+max_pages):
            u=f"https://flippa.com/search?page_size=100&page={page_no}"
            resp=p.goto(u,wait_until="domcontentloaded",timeout=60000); p.wait_for_timeout(1400)
            st=resp.status if resp else 0; ch=s.challenge()
            body=p.locator("body").inner_text(timeout=10000)
            raws=p.locator("li[id^='listing-']").evaluate_all(JS)
            if page_no==1 and state.get("reported_total") is None:
                m=re.search(r"Showing\s+\d+[–-]\d+\s+of\s+([\d,]+)",body)
                if m:
                    state["reported_total"]=int(m.group(1).replace(",",""))
                    state["total_pages"]=(state["reported_total"]+99)//100
            check_stop(st,ch,page_no,"main",state)
            if len(raws)==0 and page_no>1 and len(state["main"])>0 and st==200 and ch=="NONE":
                state["pages"].append({"lane":"main","page":page_no,"status":st,"count":0,"challenge":ch,"terminal":True})
                state["main_done"]=True; state["terminal_page"]=page_no
                atomic(STATE,state)
                break
            for x in raws:
                r=norm(x,False)
                if r["id"]:
                    if r["id"] in state["first_ids"]: r["fa"]=1
                    state["main"][r["id"]]=r
            state["main_observations"]=int(state.get("main_observations") or 0)+len(raws)
            state["pages"].append({"lane":"main","page":page_no,"status":st,"count":len(raws),"challenge":ch})
            state["next_main_page"]=page_no+1
            if state.get("total_pages") is not None and page_no>=state["total_pages"]:
                state["main_done"]=True; state["terminal_page"]=page_no
            atomic(STATE,state)
            done+=1
            if state["main_done"]: break
            time.sleep(random.uniform(12,18))
    print(json.dumps({"stage":"main","pages_this_stage":done,"next_main_page":state["next_main_page"],"main_done":state["main_done"],"unique":len(state["main"]),"observations":state["main_observations"],"reported_total":state.get("reported_total"),"total_pages":state.get("total_pages")}))

def finalize(state):
    if not state.get("main_done"): raise SystemExit("main_not_done")
    with open(PRIOR,encoding="utf-8") as f: prior=json.load(f)
    prior_main=prior["main"]
    main=state["main"]
    prior_ids=set(prior_main); cur_ids=set(main)
    def ik(x):
        try:return int(x)
        except:return 0
    new_ids=sorted(cur_ids-prior_ids,key=ik)
    missing_ids=sorted(prior_ids-cur_ids,key=ik)
    changed_ids=[i for i in sorted(cur_ids & prior_ids,key=ik) if keyrow(main[i]) != prior_main[i]]
    recent_unique=list(dict.fromkeys(state["recent_ids"]))
    recent_new=[i for i in recent_unique if i not in prior_ids]
    first_unique=list(dict.fromkeys(state["first_ids"]))
    gap=(state.get("reported_total")-len(main)) if state.get("reported_total") is not None else None
    meta={
      "started_at":state["started_at"],"completed_at":datetime.now(timezone.utc).isoformat(),"status":"PASS",
      "pages":state["pages"],"reported_total":state.get("reported_total"),"unique_total":len(main),
      "unique_gap":gap,"observed_card_count":state.get("main_observations",0),
      "terminal_page":state.get("terminal_page")
    }
    out={
      "schema":"flippa-delta-ledger-v5-20261013","observed_at":datetime.now().astimezone().isoformat(),
      "prior_observed_at":prior.get("observed_at"),"reported_total":state.get("reported_total"),
      "total":len(main),"coverage_unique_gap":gap,"observed_card_count":state.get("main_observations",0),
      "new_count":len(new_ids),"changed_count":len(changed_ids),"missing_count":len(missing_ids),
      "recent_500_count":len(recent_unique),"recent_new_count":len(recent_new),"first_access_count":len(first_unique),
      "main":list(main.values()),"new_ids":new_ids,"changed_ids":changed_ids,"missing_ids":missing_ids,
      "recent_new_ids":recent_new,"first_access_ids":first_unique,"meta":meta
    }
    atomic(OUT,out)
    state["status"]="PASS"; state["final_out"]=OUT; atomic(STATE,state)
    print(json.dumps({k:out[k] for k in ["schema","observed_at","reported_total","total","coverage_unique_gap","observed_card_count","new_count","changed_count","missing_count","recent_500_count","recent_new_count","first_access_count"]}))

ap=argparse.ArgumentParser()
ap.add_argument("stage",choices=["bootstrap","main","finalize","status"])
ap.add_argument("--pages",type=int,default=20)
args=ap.parse_args()
state=load_state()
if args.stage=="bootstrap": do_bootstrap(state)
elif args.stage=="main": do_main(state,args.pages)
elif args.stage=="finalize": finalize(state)
else:
    print(json.dumps({k:state.get(k) for k in ["status","first_done","recent_done","main_done","next_main_page","reported_total","total_pages","main_observations"]} | {"unique":len(state.get("main",{})),"first_access_count":len(state.get("first_ids",[])),"recent_count":len(state.get("recent_ids",[]))}))
