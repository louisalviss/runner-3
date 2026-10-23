#!/usr/bin/env python3
"""Read-only source integrity and outstanding DD ledger for Acquisition Radar.
Writes dedicated audit files, never mutates provider snapshots, buying decisions,
or a live checkout. It does not infer lost Flippa listings were absent.
"""
import datetime,hashlib,json,pathlib
from collections import Counter,defaultdict
from zoneinfo import ZoneInfo

S=pathlib.Path('/var/lib/seotrends-public/scans')
R=pathlib.Path('/var/lib/acquisition-radar-scan')
O=pathlib.Path('/var/lib/opportunity-daily')
TZ=ZoneInfo('Asia/Ho_Chi_Minh')
FIRST=datetime.date(2026,10,14)

def j(p):
 try:return json.loads(p.read_text(encoding='utf8'))
 except (OSError,ValueError,TypeError):return {}

def sourcehash(p):
 try:return hashlib.sha256(p.read_bytes()).hexdigest()
 except OSError:return None

def audit():
 today=datetime.datetime.now(TZ).date();end=today
 days=[];pending=[];dd=[];missing_flippa=[]
 totals=Counter();dates=[]
 for n in range((end-FIRST).days+1):
  date=FIRST+datetime.timedelta(days=n)
  day=date.isoformat();stamp=day.replace('-','')
  qpath=S/(day+'-semrush-queue.json')
  sempath=S/(day+'-semrush-results.json')
  terpath=S/(day+'-terminal-verdicts.json')
  src=j(qpath);sem=j(sempath);ter=j(terpath)
  dr=O/(day+'-research-queue.json')
  payload=j(dr)
  qualification=payload.get('qualification') or {}
  acceptance=j(O/(day+'-acceptance.json'))
  fl=R/('flippa-'+stamp+'-daily-state.json')
  flippa=j(fl)
  candidates=src.get('items') or []
  csv=S/(day+'-candidates.csv')
  rows=(S/(day+'-candidates.jsonl'))
  count_cand=sum(1 for l in rows.open(encoding='utf-8') if l.strip()) if rows.is_file() else None
  source_ok=bool(src.get('scan_terminal') is True and src.get('scanned')==src.get('added_total') and src.get('pending')==0 and count_cand==src.get('scanned') and src.get('count')==len(candidates))
  sem_ok=bool(sem.get('status')=='PASS' and sem.get('pass_count')==len(candidates) and sem.get('queue_count')==len(candidates))
  serp_ok=bool(ter.get('status')=='PASS' and len(ter.get('verdicts') or [])==len(candidates))
  flippa_ok=bool(flippa.get('recent_done') is True and len(set(flippa.get('recent_ids') or []))==500 and flippa.get('first_done') is True)
  if not flippa_ok:missing_flippa.append(day)
  if not sem_ok:
   for item in candidates:
    domain=str(item.get('domain') or '').lower()
    pending.append({'day':day,'domain':domain,'reason':sem.get('global_blocker') or sem.get('status') or 'MISSING','seo_source_sha256':sourcehash(qpath)})
  for x in qualification.get('candidates') or []:
   if x.get('category') in ('BUILD_DD','BUY_DD','DUAL_DD'):
    ev=x.get('evidence') or {}
    dd.append({'day':day,'identity':x.get('identity'),'source':x.get('source'),'category':x.get('category'),'title':x.get('title'),'modelled_us_organic_month':ev.get('source_organic_us_monthly_estimate'),'price_asking_or_bin_usd':ev.get('price_observed_usd'),'product_intent_checked':ev.get('product_intent_exact_serp_checked'),'semantic_review_completed':ev.get('semantic_review_completed'),'approved':False})
  row={'day':day,'source_count':src.get('added_total'),'scanned':src.get('scanned'),'shortlist':len(candidates),'candidate_jsonl_rows':count_cand,'source_complete':source_ok,'semrush':sem.get('status','MISSING'),'semrush_pass_count':sem.get('pass_count') or 0,'serp':ter.get('status','MISSING'),'serp_completed_count':len(ter.get('verdicts') or []),'flippa_daily_complete':flippa_ok,'flippa_recent_count':len(flippa.get('recent_ids') or []),'daily_qualification':qualification.get('status','MISSING'),'acceptance':acceptance.get('status','MISSING'),'acceptance_checks':acceptance.get('passed_checks'),'dropbox':j(O/(day+'-dropbox-publish.json')).get('status','MISSING'),'evidence_sha256':{'queue':sourcehash(qpath),'semrush':sourcehash(sempath),'serp':sourcehash(terpath),'daily':sourcehash(dr)}}
  days.append(row)
  if isinstance(src.get('scanned'),int):totals['discovery_scanned']+=src['scanned']
  if source_ok:totals['source_days_complete']+=1
  if sem_ok and serp_ok:totals['provider_days_complete']+=1
  if flippa_ok:totals['flippa_days_complete']+=1
  if acceptance.get('status')=='PASS':totals['acceptance_pass_days']+=1
 backlog=j(O/'flippa-backlog-current.json')
 ddc=Counter(x['category'] for x in dd)
 status='PASS' if not pending and not missing_flippa and all(x['acceptance']=='PASS' for x in days) else 'UNRESOLVED_GAPS'
 summary={'scope_start':FIRST.isoformat(),'scope_end':end.isoformat(),'days_checked':len(days),'scanned':totals['discovery_scanned'],'source_days_complete':totals['source_days_complete'],'semrush_serp_pass_days':totals['provider_days_complete'],'flippa_pass_days':totals['flippa_days_complete'],'acceptance_pass_days':totals['acceptance_pass_days'],'semrush_pass_shortlists':sum(x['semrush_pass_count'] for x in days if x['semrush']=='PASS'),'unique_unprocessed_domains':len({x['domain'] for x in pending}),'unprocessed_domain_rows':len(pending),'dd_pending_items':len({x['identity'] for x in dd}),'dd_categories':dict(ddc),'flippa_missing_days':missing_flippa,'cumulative_flippa_active':backlog.get('active_count'),'cumulative_flippa_closed_historical':backlog.get('closed_historical_count'),'last_verified_flippa_recent':backlog.get('last_scoped_recent_scan'),'full_inventory_observation':backlog.get('last_full_inventory_observation'),'cannot_reconstruct_expired_flippa_recent_windows':bool(missing_flippa)}
 ledger={'schema':'acquisition-gap-ledger-v1','generated_at':datetime.datetime.now(TZ).isoformat(),'status':status,'summary':summary,'daily':days,'pending_semrush':pending,'historical_dd_candidates':dd,'limits':{'source_traffic_not_new_site_forecast':True,'seller_metrics_not_audited':True,'historical_listings_not_guaranteed_live':True,'unobserved_inventory_not_proven_empty':True,'no_social_check':True,'no_purchase_or_build_authorized':True}}
 output=O/('gap-ledger-'+end.isoformat()+'.json')
 temp=output.with_suffix('.json.tmp');temp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n');temp.replace(output)
 lines=['# Acquisition Radar — retrospective gap audit '+FIRST.isoformat()+' to '+end.isoformat(),'',
 'STATUS: '+status,'Audit generated: '+ledger['generated_at'],'',
 '## Totals',
 '- Discovery '+str(summary['scanned'])+' domains across '+str(summary['source_days_complete'])+'/'+str(summary['days_checked'])+' complete daily source snapshots.',
 '- Semrush/SERP finished: '+str(summary['semrush_pass_shortlists'])+' shortlisted domains; pending: '+str(summary['unique_unprocessed_domains'])+' distinct domains.',
 '- Flippa daily feed: '+str(summary['flippa_pass_days'])+'/'+str(summary['days_checked'])+' complete; missing capture days '+', '.join(missing_flippa)+'.',
 '- Historical DD hypotheses not yet a BUY/BUILD approval: '+str(summary['dd_pending_items'])+' ('+str(summary['dd_categories'])+').',
 '- Existing cumulative Flippa backlog '+str(summary['cumulative_flippa_active'])+' tracked + '+str(summary['cumulative_flippa_closed_historical'])+' historical closed; last recent feed '+str(summary['last_verified_flippa_recent'])+'.',
 '- Daily independent acceptance '+str(summary['acceptance_pass_days'])+'/'+str(summary['days_checked'])+' PASS; sync status recorded separately for every day.','',
 '## Daily evidence matrix','',
 '| Date | Discovery | Semrush pass | Exact SERP | Flippa | Acceptance |',
 '|---|---:|---|---|---|---|']
 for x in days:
  lines.append('| '+x['day']+' | '+str(x['scanned'])+'/'+str(x['source_count'])+' | '+str(x['semrush'])+' '+str(x['semrush_pass_count'])+'/'+str(x['shortlist'])+' | '+x['serp']+' | '+('PASS' if x['flippa_daily_complete'] else 'MISSING')+' | '+x['acceptance']+' |')
 lines += ['', '## Historical BUILD/BUY DD hypotheses (NOT APPROVED)','',
 '| Date | Candidate | Lane | Organic US modeled / month |','|---|---|---|---:|']
 for x in dd:
  lines.append('| '+x['day']+' | '+str(x['identity'])+' | '+str(x['category'])+' | '+str(x.get('modelled_us_organic_month') or 'N/A')+' |')
 lines += ['', '## Unprocessed Semrush backlog','',
 '- All '+str(len(pending))+' source domain/day records remain in the JSON pending_semrush array with immutable queue SHA-256.',
 '- Blocking provider auth and missing Flippa network must be repaired before treating these as analyzed or no opportunities.',
 '- Dates missing Flippa Recent-500 cannot be retrospectively asserted complete; historical listings may have appeared and disappeared between observations.','',
 '## Safety and work remaining','',
 '- Keep immutable SeoTrends source/shortlists. Do not rerun public delta discovery for an old date.',
 '- After legitimate NoxTools authentication, resume existing Semrush queues with bounded provider use; run exact SERP only on completed exports and regenerate dated qualification without auto BUY/BUILD.',
 '- Restore the original Flippa proxy/session provenance and scan current inventory; do not silently substitute a different profile/direct network.',
 '- This is an evidence ledger, not a business success report, and excludes social research by user direction.','']
 markdown=O/('gap-ledger-'+end.isoformat()+'.md')
 temp=markdown.with_suffix('.md.tmp');temp.write_text('\n'.join(lines));temp.replace(markdown)
 print(json.dumps({'status':status,'summary':summary,'json':str(output),'markdown':str(markdown),'markdown_sha256':sourcehash(markdown)},ensure_ascii=False))
 return ledger
if __name__=='__main__':audit()
