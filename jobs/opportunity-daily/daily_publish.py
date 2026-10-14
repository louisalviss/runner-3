#!/usr/bin/env python3
"""Publish verified daily state to Dropbox CURRENT + History, source-safe and idempotent."""
from __future__ import annotations
import datetime,json,pathlib,hashlib,subprocess
from zoneinfo import ZoneInfo

OUT=pathlib.Path('/var/lib/opportunity-daily')
PUBLISHER='/usr/local/bin/acquisition-radar-publish'

def render_current(value:dict,report:str)->str:
    # LAST_SCAN is kept from the report's generated_at for idempotent replays.
    day=value['date_vn']
    dt=datetime.datetime.fromisoformat(value['generated_at'])
    ts=dt.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M +07:00')
    q=value.get('qualification') or {}
    seo=value.get('seo') or {}
    source_pass=seo.get('provider_status')=='PASS' and seo.get('terminal_status')=='PASS'
    state='DAILY_CHECK_PASS_NO_BUY_NO_BUILD' if value.get('overall')!='PARTIAL_BLOCKED' and source_pass else 'DAILY_PARTIAL_BLOCKED_NEEDS_REVIEW'
    prefix=[
        '# Acquisition Idea Radar — CURRENT','',
        'STATUS: '+state,
        'LAST_SCAN: '+ts,
        'SCOPED_REPORT_DAY: '+day,
        'SOURCE_OWNERS: SeoTrends and Flippa independent scanners',
        'SEOTRENDS_SEMRUSH: '+str(seo.get('provider_status')),
        'SEOTRENDS_EXACT_SERP: '+str(seo.get('terminal_status')),
        'FLIPPA_SOURCE: '+str(value.get('flippa',{}).get('status')),
        'BUILD_BUY_QUALIFICATION: '+str(q.get('status')),
        'APPROVED_BUY: 0',
        'APPROVED_BUILD: 0',
        'CANONICAL_FLOW: ../../FLOWS/Acquisition - Idea Radar.md',
        'PREVIOUS_DAILY_REPORTS: History/ (never overwrite archive)',
        'CAVEAT: historical PASS records must not substitute for a blocked current date',
        '',
        '## Current daily evidence','',
        report.strip(),'',
        '## Automated check boundary','',
        '- Semrush organic traffic is a third-party modeled estimate, not Google Analytics.',
        '- Flippa card figures and listing prices are seller-side claims, not audited.',
        '- No domain is bought, bid on or built by this workflow.',
        '- Missing social, source login, semantic DD or GSC evidence is not counted as PASS.',
        '- Older reports remain separately archived. Recovery must preserve original daily source snapshots.',
        '',
    ]
    # Keep all candidate decisions in CURRENT; earlier full reports remain in History.
    candidates=(value.get('qualification') or {}).get('candidates') or []
    if candidates:
        prefix += ['## All scoped candidate decisions', '', '| Candidate | Source | BUY | BUILD | Decision |', '|---|---|---|---|---|']
        for x in candidates:
            title=str(x.get('title') or x.get('identity') or '')[:80].replace('|','/')
            buy=str((x.get('buy') or {}).get('state') or '-')
            build=str((x.get('build') or {}).get('state') or '-')
            prefix.append('| '+title+' | '+str(x.get('source') or '-')+' | '+buy+' | '+build+' | '+str(x.get('category') or '-')+' |')
        prefix += ['', '### Full source evidence and DD boundaries', '',
                   '- Machine-readable candidate evidence: /var/lib/opportunity-daily/'+day+'-research-queue.json',
                   '- Semantic business DD (if present): '+str((value.get('qualification') or {}).get('source_semantic_path') or 'NOT_RUN'),
                   '- Historical checkpoints: History/ (including detailed 2026-10-14-buildbuy-v2-current.md)',
                   '']
    return '\n'.join(prefix)

def publish(day:str,value:dict,report:str,out=OUT,runner=None):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    markdown=render_current(value,report)
    digest=hashlib.sha256(markdown.encode('utf8')).hexdigest()
    marker=out/(day+'-dropbox-publish.json')
    state=out/(day+'-current.md')
    old={}
    if marker.is_file():
        try:old=json.loads(marker.read_text())
        except (ValueError,OSError):pass
    if old.get('sha256')==digest and old.get('status')=='PASS':
        return {'status':'ALREADY_PUBLISHED','sha256':digest,'path':str(state)}
    temp=state.with_suffix('.md.tmp')
    temp.write_text(markdown,encoding='utf8');temp.replace(state)
    label='daily-'+day.replace('-','')+'-'+digest[:14]
    cmd=[str(runner or PUBLISHER),str(state),label]
    try:
        proc=subprocess.run(cmd,text=True,capture_output=True,timeout=130,check=False)
        status='PASS' if proc.returncode==0 and 'DROPBOX_SYNC_PASS' in proc.stdout else 'PENDING_RETRY'
        reason=(proc.stderr or proc.stdout or '')[-450:]
    except (subprocess.TimeoutExpired,OSError) as e:
        status='PENDING_RETRY'
        reason=type(e).__name__
    meta={'day':day,'sha256':digest,'status':status,'label':label,'report_path':str(state),'reason':reason}
    m=marker.with_suffix('.json.tmp');m.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n');m.replace(marker)
    return meta
