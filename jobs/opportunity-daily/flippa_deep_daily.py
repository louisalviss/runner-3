#!/usr/bin/env python3
"""Bounded Flippa listing detail acquisition; shared authenticated profile, no bypass."""
from __future__ import annotations
import argparse,json,pathlib,re,random,time,sys,os
ROOT=pathlib.Path('/var/lib/acquisition-radar-scan')
PROFILE="c97a7500-3b11-403f-ac43-2566cdcd3fa2"
ID=re.compile(r'^[0-9]{6,12}$')
MAX=3

def extract(id,title,body,status,challenge):
    def match(pattern):
        m=re.search(pattern,body,re.I|re.S)
        return m.group(1).strip() if m else None
    return {
      'id':id,'status':status,'challenge':challenge,'title':title,
      'reserve':match(r'Reserve:\s*USD \$([\d,]+(?:\.\d+)?)'),
      'bin':match(r'Buy It Now for USD \$([\d,]+(?:\.\d+)?)'),
      'asking':match(r'Asking Price[^\n]*\s*\n+\s*USD \$([\d,]+(?:\.\d+)?)'),
      'pageviews':match(r'Page Views\s*([\d,]+)\s*p/mo'),
      'subs':match(r'Total Active Subscribers\s*([\d,]+)'),
      'churn':match(r'Overall Churn\s*([\d.]+%)'),
      'body':body[:12000],
    }

def candidates_for_daily(flippa,limit=MAX):
    rows=[x for x in flippa.get('new') or [] if str(x.get('id') or '') and ID.fullmatch(str(x['id'])) and str(x.get('verdict') or '') not in ('DROP','DROP_TRAFFIC_WEAK','DROP_BUY_CAP')]
    # Focus the limited authenticated detail budget on plausible deals first.
    # Unverified build-reference cards must not displace higher-scoring watch candidates.
    rows.sort(key=lambda x:(0 if str(x.get('verdict') or '').startswith(('WATCH','BUY','SEO_BUY')) else 1, -float(x.get('score') or 0)))
    return list(dict.fromkeys(str(x['id']) for x in rows))[:min(MAX,limit)]

def existing_complete(path,ids):
    try:
        content=json.loads(path.read_text(encoding='utf8'))
        byid={str(x.get('id')):x for x in content if isinstance(x,dict)}
        return bool(ids) and all(i in byid and byid[i].get('status')==200 and byid[i].get('challenge')=='NONE' for i in ids)
    except (OSError,ValueError,TypeError):return False

def capture(ids,day,out=ROOT):
    ids=list(dict.fromkeys(str(x) for x in ids))[:MAX]
    if not all(ID.fullmatch(x) for x in ids):return {'status':'BLOCKED','reason':'INVALID_IDS','items':0}
    root=pathlib.Path(out);root.mkdir(parents=True,exist_ok=True)
    file=root/('flippa-deep-'+day.replace('-','')+'.json')
    state=root/('flippa-deep-'+day.replace('-','')+'-state.json')
    if not ids:
        return {'status':'PASS_EMPTY','items':0,'source':'NO_ELIGIBLE_CARDS'}
    if existing_complete(file,ids):
        return {'status':'PASS','items':len(ids),'source':'VALID_CACHED_DEEP'}
    import_repair=False
    if state.is_file():
        try:prior=json.loads(state.read_text(encoding='utf8'))
        except ValueError:prior={}
        if prior.get('status') in ('BLOCKED','PARTIAL') and prior.get('date')==day:
            # One explicit recovery is allowed for a local missing dependency only;
            # never retry an auth/challenge/rate-limit failure in the same day.
            import_repair=(os.environ.get('ACQ_FLIPPA_ENV_FIX_ONCE')=='1' and prior.get('reason')=='ModuleNotFoundError' and not prior.get('repair_attempted'))
            if not import_repair:
                return {'status':prior['status'],'items':prior.get('items',0),'reason':'ONE_ATTEMPT_PER_DAY'}
            stamped={**prior,'repair_attempted':True}
            tmp=state.with_suffix('.tmp');tmp.write_text(json.dumps(stamped,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,state)
    try:
        existing=json.loads(file.read_text(encoding='utf8')) if file.is_file() else []
        if not isinstance(existing,list):existing=[]
    except (ValueError,OSError):existing=[]
    done={str(x.get('id')):x for x in existing if isinstance(x,dict) and x.get('status')==200 and x.get('challenge')=='NONE'}
    remaining=[i for i in ids if i not in done]
    rows=list(done.values())
    status='PASS'; reason=''
    try:
        sys.path.insert(0,'/opt/browser-stack/bin')
        from raw_cdp_skill import RawCDPSkill
        with RawCDPSkill(PROFILE,owner='flippa-daily-deep-'+day,keep_running=False,new_page=True,close_page_on_exit=True,priority='auth') as skill:
            page=skill.page
            for count,listingid in enumerate(remaining):
                response=page.goto('https://flippa.com/'+listingid,wait_until='domcontentloaded',timeout=60000)
                page.wait_for_timeout(1600)
                http=response.status if response else 0
                challenge=skill.challenge()
                if http in (403,429) or challenge!='NONE':
                    status='BLOCKED';reason='HTTP_OR_HUMAN_CHALLENGE'
                    break
                title=page.title()
                body=page.locator('body').inner_text(timeout=15000)
                rows.append(extract(listingid,title,body,http,challenge))
                if count<len(remaining)-1:time.sleep(random.uniform(12,18))
    except Exception as e:
        status='BLOCKED';reason=type(e).__name__
    if status=='PASS' and sum(x.get('status')==200 and x.get('challenge')=='NONE' and str(x.get('id')) in ids for x in rows)!=len(ids):
        status='PARTIAL';reason='INCOMPLETE_DETAILS'
    # Always preserve earlier verified rows on challenge: no truncation.
    if rows:
        tmp=file.with_suffix('.json.tmp');tmp.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf8');os.replace(tmp,file)
    result={'date':day,'status':status,'requested':len(ids),'items':len(rows),'reason':reason,'source':'SHARED_FLIPPA_CDP','repair_attempted':import_repair}
    tmp=state.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,state)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--date',required=True)
    p.add_argument('--ids',nargs='*',default=[])
    args=p.parse_args()
    print(json.dumps(capture(args.ids,args.date),ensure_ascii=False))
