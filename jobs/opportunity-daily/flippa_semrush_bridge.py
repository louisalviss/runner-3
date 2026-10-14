#!/usr/bin/env python3
"""Bounded independent Semrush organic check for selected verified Flippa listing domains.
Never guesses missing domains, circumvents login, or mutates SeoTrends source scans.
"""
from __future__ import annotations
import json,re,pathlib,subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=pathlib.Path('/var/lib/acquisition-radar-scan')
EXPORTER=pathlib.Path('/opt/dhs-control/executors/semrush_dpa_export.py')
PYTHON='/opt/chatgpt-bridge/venv/bin/python'
TLD=r'(?:com|net|org|io|co|app|ai|site|us|info|pro|dev|me|xyz)'
DOM=re.compile(r'(?<![\w.])((?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+'+TLD+r')(?![\w.-])',re.I)
BLOCK_MARKERS=('SEMRUSH_LIVE_AUTH_UNAVAILABLE','NOX_LOGIN_CHALLENGE','NOX_LOGIN_FORM_MISSING','SEMRUSH_HUMAN_HANDOFF_ACTIVE','SEMRUSH_RATE_LIMIT','NOX_CREDENTIALS_INVALID')

def domain_from_verified_listing(row, deep):
    if row.get('verified_detail') is not True:return None
    doc=deep.get(str(row.get('id') or '')) or {}
    if doc.get('status')!=200 or doc.get('challenge')!='NONE':return None
    title=str(doc.get('title') or '').split('|',1)[0][:180]
    matches=list(dict.fromkeys(x.lower() for x in DOM.findall(title)))
    filtered=[x for x in matches if x not in ('flippa.com','www.flippa.com','youtube.com','apple.com')]
    return filtered[0] if len(filtered)==1 else None

def valid_cached(path,domain):
    try:
        j=json.loads(path.read_text(encoding='utf8'))
        return str(j.get('domain') or '').lower()==domain and isinstance(j.get('rows'),list)
    except (OSError,ValueError):return False

def summary_metrics(path):
    j=json.loads(path.read_text(encoding='utf8'))
    rows=j.get('rows') or []
    return {
        'organic_keyword_rows':len(rows),
        'reported_positions':j.get('total_reported'),
        'estimated_us_organic_visits':round(sum(float(x.get('traffic') or 0) for x in rows),2),
        'leading_keywords':[str(x.get('phrase') or '')[:110] for x in rows[:5]],
        'truncated':bool(j.get('truncated')),
        'modeled_not_first_party':True,
    }

def inspect(day,flippa,deep_path=None,output_root=ROOT,max_domains=2,exporter=None,timeout=150):
    root=pathlib.Path(output_root);root.mkdir(parents=True,exist_ok=True)
    deepraw=[]
    if deep_path and pathlib.Path(deep_path).is_file():
        try:deepraw=json.loads(pathlib.Path(deep_path).read_text(encoding='utf8'))
        except (ValueError,OSError):deepraw=[]
    deep={str(x.get('id') or ''):x for x in deepraw if isinstance(x,dict)}
    selected=[];seen=set()
    for x in flippa.get('new') or []:
        if x.get('verdict') in ('DROP','DROP_TRAFFIC_WEAK','DROP_BUY_CAP'):continue
        dom=domain_from_verified_listing(x,deep)
        if not dom or dom in seen:continue
        selected.append((x,dom));seen.add(dom)
        if len(selected)>=max_domains:break
    directory=root/('flippa-sem-'+day.replace('-',''))
    directory.mkdir(parents=True,exist_ok=True)
    results=[];blocked=False
    for row,domain in selected:
        out=directory/(domain+'.json')
        item={'id':row['id'],'listing_identity':row['identity'],'domain':domain,'provider':'Semrush','db':'us'}
        if valid_cached(out,domain):
            item.update({'status':'PASS','source':'cached-existing-export','metrics':summary_metrics(out)})
        elif blocked:
            item.update({'status':'NOT_RUN','reason':'UPSTREAM_BLOCKED'})
        else:
            proc=None
            try:
                cmd=[str(PYTHON),str(exporter or EXPORTER),'--domain',domain,'--db','us','--output',str(out)]
                proc=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout,check=False)
                event={}
                for line in reversed(proc.stdout.splitlines()):
                    try:
                        v=json.loads(line)
                        if isinstance(v,dict):event=v;break
                    except ValueError:pass
                reason=str(event.get('reason') or 'EXPORTER_FAILED')[:260]
                if proc.returncode==0 and event.get('status')=='PASS' and valid_cached(out,domain):
                    item.update({'status':'PASS','source':'fresh-export','metrics':summary_metrics(out)})
                else:
                    item.update({'status':'BLOCKED' if any(x in reason for x in BLOCK_MARKERS) else 'FAIL','reason':reason})
                    if item['status']=='BLOCKED':blocked=True
            except subprocess.TimeoutExpired:
                item.update({'status':'BLOCKED','reason':'PROVIDER_TIMEOUT'})
                blocked=True
            except OSError as e:
                item.update({'status':'BLOCKED','reason':type(e).__name__})
                blocked=True
        results.append(item)
    counts={state:sum(x['status']==state for x in results) for state in ('PASS','FAIL','BLOCKED','NOT_RUN')}
    payload={'date':day,'status':('PASS_EMPTY' if not results else 'PASS' if counts['PASS']==len(results) else 'BLOCKED' if counts['BLOCKED'] or counts['NOT_RUN'] else 'PARTIAL'),'source':'FLIPPA_VERIFIED_DETAILS','scope':'bounded_one_or_two_domain_organic_check','limit':max_domains,'eligible':len(selected),'counts':counts,'items':results,'no_traffic_transfer_claim':True,'no_automatic_buy_or_build':True}
    path=root/('flippa-semDD-'+day.replace('-','')+'.json')
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
    return payload
