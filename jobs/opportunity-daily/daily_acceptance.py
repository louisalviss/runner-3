#!/usr/bin/env python3
"""Conservative daily acceptance receipt. No network/provider/browser side effects."""
from __future__ import annotations
import argparse, datetime,hashlib,json,pathlib,os,sys
from zoneinfo import ZoneInfo

from reviewed_cutover import is_reviewed_prior_listing


def qualified_rows_match(day: str, source_items: list, payload: dict) -> bool:
    """Exact source identity reconciliation, including the immutable reviewed cohort."""
    if payload.get('schema') != 'opportunity-daily-v2' or payload.get('seo', {}).get('source_complete') is not True:
        return False
    new = (payload.get('flippa') or {}).get('new') or []
    candidates = (payload.get('qualification') or {}).get('candidates') or []
    if not all(isinstance(x, dict) for x in source_items + new + candidates):
        return False
    input_seo = [str(x.get('domain') or '').lower() for x in source_items]
    input_flippa = [str(x.get('identity') or '') for x in new]
    if not all(input_seo) or not all(x.startswith('flippa:') for x in input_flippa):
        return False
    expected_flippa = [x for x in input_flippa if not is_reviewed_prior_listing(x, day)]
    actual_seo = [str(x.get('identity') or '').lower() for x in candidates if x.get('source') == 'SEOTRENDS']
    actual_flippa = [str(x.get('identity') or '') for x in candidates if x.get('source') == 'FLIPPA']
    q = payload.get('qualification') or {}
    expected_suppressed = len(input_flippa) - len(expected_flippa)
    return bool(
        len(input_seo) == len(set(input_seo))
        and len(input_flippa) == len(set(input_flippa))
        and len(actual_seo) == len(set(actual_seo))
        and len(actual_flippa) == len(set(actual_flippa))
        and len(candidates) == len(actual_seo) + len(actual_flippa)
        and set(actual_seo) == set(input_seo)
        and set(actual_flippa) == set(expected_flippa)
        and q.get('archived_reviewed_suppressed', 0) == expected_suppressed
    )

SEO=pathlib.Path('/var/lib/seotrends-public/scans')
ROOT=pathlib.Path('/var/lib/acquisition-radar-scan')
OUT=pathlib.Path('/var/lib/opportunity-daily')
TZ=ZoneInfo('Asia/Ho_Chi_Minh')
# Same dedicated owner as the Flippa inventory template and detail scanner.
FLIPPA_PROFILE_ID='c97a7500-3b11-403f-ac43-2566cdcd3fa2'

def load(path):
    try:return json.loads(pathlib.Path(path).read_text(encoding='utf8'))
    except (OSError,ValueError,TypeError):return {}

def check(day,seo=SEO,root=ROOT,out=OUT):
    q=load(seo/(day+'-semrush-queue.json'))
    sem=load(seo/(day+'-semrush-results.json'))
    ter=load(seo/(day+'-terminal-verdicts.json'))
    manifest=load(out/(day+'-manifest.json'))
    payload=load(out/(day+'-research-queue.json'))
    f=load(root/('flippa-'+day.replace('-','')+'-daily-state.json'))
    pub=load(out/(day+'-dropbox-publish.json'))
    cross=payload.get('flippa_semrush') or {}
    checks={}
    checks['same_date']=all(str(x.get('date') or x.get('date_vn') or '')==day for x in (q,sem,ter,manifest,payload)) and pub.get('day')==day
    items=q.get('items') or []
    checks['source_complete']=bool(q.get('scan_terminal') is True and isinstance(q.get('added_total'),int) and q['added_total']>0 and q.get('scanned')==q['added_total'] and q.get('pending')==0 and q.get('count')==len(items) and len(items)>0)
    checks['semrush_all_pass']=sem.get('status')=='PASS' and sem.get('queue_count')==len(items) and sem.get('pass_count')==len(items) and sem.get('not_run_count')==0 and sem.get('fail_count')==0
    checks['exact_serp_complete']=ter.get('status')=='PASS' and len(ter.get('verdicts') or [])==len(items) and ter.get('semrush_status')=='PASS'
    all_pages=f.get('pages') or []
    checks['flippa_daily_source']=f.get('profile_id')==FLIPPA_PROFILE_ID and f.get('recent_done') is True and f.get('first_done') is True and len(set(f.get('recent_ids') or []))==500 and bool(all_pages) and all(x.get('status')==200 and x.get('challenge')=='NONE' for x in all_pages)
    checks['flippa_detail_stage']=payload.get('flippa_detail',{}).get('status') in ('PASS','PASS_EMPTY')
    checks['flippa_semrush_stage']=cross.get('status') in ('PASS','PASS_EMPTY')
    checks['qualified_rows_match']=qualified_rows_match(day, items, payload)
    checks['buy_build_guard']=payload.get('qualification',{}).get('approved_buy')==0 and payload.get('qualification',{}).get('approved_build')==0 and manifest.get('approved_buy')==0 and manifest.get('approved_build')==0
    report=out/(day+'-report.md')
    current=out/(day+'-current.md')
    checks['report_complete']=report.is_file() and bool(report.stat().st_size>300) and (out/(day+'-manifest.json')).is_file()
    content=current.read_bytes() if current.is_file() else b''
    checks['dropbox_verified']=pub.get('status')=='PASS' and bool(content) and hashlib.sha256(content).hexdigest()==pub.get('sha256') and ('SCOPED_REPORT_DAY: '+day).encode() in content and b'## All scoped candidate decisions' in content and b'DROPBOX_SYNC_PASS' in str(pub.get('reason','')).encode()
    # Includes actual source filename and date, not just the watch queue.
    good=all(checks.values())
    return {
        'schema':'acquisition-daily-acceptance-v1',
        'date':day,
        'checked_at':datetime.datetime.now(TZ).isoformat(),
        'status':'PASS' if good else 'PARTIAL_BLOCKED',
        'checks':checks,
        'passed_checks':sum(checks.values()),
        'total_checks':len(checks),
        'scope':'source discovery, Semrush/SERP, bounded Flippa details and Semrush, qualification, Dropbox sync only',
        'excluded':'social checks and full semantic business DD not part of current automated acceptance contract',
        'scheduler_proven_unattended':False,
        'evidence_paths':{
            'source':str(seo/(day+'-semrush-queue.json')),
            'semrush':str(seo/(day+'-semrush-results.json')),
            'serp':str(seo/(day+'-terminal-verdicts.json')),
            'flippa':str(root/('flippa-'+day.replace('-','')+'-daily-state.json')),
            'manifest':str(out/(day+'-manifest.json')),
            'report':str(report),
            'publisher':str(out/(day+'-dropbox-publish.json')),
        }
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--date',default=datetime.datetime.now(TZ).date().isoformat())
    p.add_argument('--no-write',action='store_true')
    args=p.parse_args()
    result=check(args.date)
    if not args.no_write:
        OUT.mkdir(parents=True,exist_ok=True)
        file=OUT/(args.date+'-acceptance.json')
        tmp=file.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        os.replace(tmp,file)
    print(json.dumps({'date':args.date,'status':result['status'],'passed':result['passed_checks'],'total':result['total_checks'],'failed':[k for k,v in result['checks'].items() if not v]},ensure_ascii=False))
    return 0 if result['status']=='PASS' else 3

if __name__=='__main__':sys.exit(main())
