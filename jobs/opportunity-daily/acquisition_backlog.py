#!/usr/bin/env python3
"""Cumulative, evidence-dated Flippa backlog. No browser, provider or bid actions.

Historical priority is a research decision, NOT live listing availability.
Recent-500 absence must never become SOLD/ENDED. Explicit direct-status
evidence is needed before a closure.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re

ROOT = pathlib.Path('/var/lib/acquisition-radar-scan')
OUT = pathlib.Path('/var/lib/opportunity-daily')
BASELINE = ROOT / 'FLIPPA-INVENTORY-CURRENT-20261006.json'
BASELINE_DAY = '2026-10-06'
HISTORIC_AUDITS = [
    ROOT / 'flippa-candidate-audit-20261007.json',
    ROOT / 'flippa-missed-dd-20261007.json',
    ROOT / 'flippa-recovered-deep-20261007.json',
    ROOT / 'flippa-20261010-dd.json',
]
# Stable, explicit legacy decisions from the source-owned 06–13 Oct reviews.
# Priority is DD queue ordering, never a financial quality score.
SEEDS = [
    ('12661644','N8Nitro','FORENSIC_DD',1,'MRR versus lifetime deals, churn, processor and 63% price-cut', '2026-10-07'),
    ('14215867','Inbox Verifyer','BUY_DD',2,'Processor revenue continuity, relisting and reserve', '2026-10-07'),
    ('14277870','Vehicle Tax Calculator','ASSET_DD',3,'Reserve near $10k budget, GSC/GA stability and monetization', '2026-10-07'),
    ('13880956','Supernatural Word Search','ASSET_DD',4,'App store transfers, AdMob payouts and Facebook account rights', '2026-10-07'),
    ('13650492','MolSketch','ASSET_DD',5,'GA cohorts, code/IP ownership, rebuild cost and repeat users', '2026-10-07'),
    ('14414582','deltaexecotr.com','BUY_DD',6,'Reserve $7k historical; AdSense payout and organic landing pages', '2026-10-09'),
    ('14405223','BitLife Blog','TRAFFIC_DD',7,'High GA pageviews versus low earnings, GSC/geo and copyright exposure', '2026-10-10'),
    ('14434539','Dutch Bros Menu','SEO_DD',8,'Brand dependence, GSC and verified reserve', '2026-10-13'),
    ('14455942','Paul the Handyman','DUAL_DD',9,'Seller processor proof, organic enquiries and attainable price', '2026-10-15'),
    ('14440150','Wheel of Life','TRAFFIC_DD',10,'Claimed organic traffic, 17k-email list quality, reserve', '2026-10-13'),
    ('14421384','Celebrity Look Alike','ASSET_DD',11,'Verify claimed 66k visitors, API rights, marginal costs', '2026-10-13'),
    ('14438910','CGPA.app','REFERENCE',20,'Google Search clicks versus almost no revenue; SEO benchmark', '2026-10-13'),
    ('14411540','ElderlyGuides','BUILD_REFERENCE',21,'Historical reserve $12.4k exceeds $10k buy cap', '2026-10-09'),
    ('14253902','3x Motorcycle Facebook Pages','WATCH',25,'Facebook payout, reach decline, transferability', '2026-10-07'),
    ('13829251','Lightloop','WATCH',26,'Historical 28% churn and 4% refunds', '2026-10-07'),
    ('13933953','Allemailly','WATCH',27,'Subscriber versus lifetime-payer semantics', '2026-10-07'),
    ('14166015','ChatDix','WATCH',28,'Processor, buyer transfer and churn', '2026-10-07'),
    ('14185993','VidFarm','FORENSIC_WATCH',29,'Stripe refunds and cohort churn', '2026-10-07'),
    ('12894251','IndexPro','FORENSIC_WATCH',30,'Third-party indexing API, user versus subscriber counts', '2026-10-07'),
    ('14275755','Image Resizer in Pixel','WATCH',31,'Paid subscribers versus free utility semantics', '2026-10-07'),
    ('14339990','Timer.fit','ASSET_WATCH',32,'Direct organic traffic and domain history', '2026-10-07'),
    ('14306087','Unlocky','WATCH',33,'Small-N customers, creator concentration and source', '2026-10-07'),
    ('14376339','AI Blogging Tool','FORENSIC_WATCH',34,'Lifetime-plan buyers are not MRR; 16 payers', '2026-10-07'),
    ('14393965','ScorePredict','ASSET_WATCH',35,'Store install proof, active users and CAC', '2026-10-07'),
    ('14451431','Phantom Bot','WATCH',36,'Fewer than 20 subscriber accounts', '2026-10-13'),
    ('14456372','HsuperTools','WATCH',37,'Weak profit; independently demonstrate organic advantage', '2026-10-13'),
    ('14459287','Popeyemenus.com','WATCH',38,'Weak profit and Google traffic unverifiable', '2026-10-13'),
    ('14178878','Confidential 8-year SaaS','FORENSIC_WATCH',39,'NDA-gated details; verify actual reserve and processor', '2026-10-07'),
    ('12754215','True Phone Security AntiSpy','FORENSIC_WATCH',40,'Store and processor history versus large headline profits', '2026-10-07'),
    ('13944814','World Of Puzzle','FORENSIC_WATCH',41,'Card earnings anomaly and unknown reserve', '2026-10-07'),
    ('14108706','App Studio','WATCH',42,'Starting bid already $10k, reserve may exceed cap', '2026-10-07'),
    ('14338967','alodata','WATCH',43,'Supplier margins and customer repeats', '2026-10-07'),
    ('14398271','Snapelement','ASSET_WATCH',44,'Plugin/data rights and almost no earnings', '2026-10-07'),
    ('14396240','CodeHelm','ASSET_WATCH',45,'Code provenance and demand unproven', '2026-10-07'),
    ('14398351','CementQuote','BUILD_REFERENCE',46,'Vertical quoting idea, no demand proof', '2026-10-07'),
    ('14392251','Pebble','BUILD_REFERENCE',47,'Analytics code idea, pre-revenue', '2026-10-07'),
    ('14384323','Detail Quote Pro','BUILD_REFERENCE',48,'Low observed traction; rebuild versus cheap code', '2026-10-07'),
    ('14390778','CaseAI','ASSET_WATCH',49,'Deployability and Meta/Stripe transfer', '2026-10-07'),
    ('14494999','Contractor Stack','REFERENCE',50,'Utility directory concept, no verified gap', '2026-10-17'),
    ('14503209','Sleepwellspace','REFERENCE',51,'Content benchmark, no verified conversions', '2026-10-17'),
    ('14488029','SeoBigExplore','REFERENCE',52,'Unverified outsourced SEO traffic claim', '2026-10-16'),
    ('14494456','CabinetPro','REFERENCE',53,'Local SEO lead generation benchmark', '2026-10-16'),
    ('14459714','HVAC Planner','REFERENCE',54,'Industry calculator and directory concept', '2026-10-14'),
]
# Only direct-confirmed CLOSED evidence from the authenticated 07 Oct audit.
CLOSED = {
    '14265493':('Mixup Recipes','SOLD'),
    '14240344':('donporque.com','SOLD'),
    '13905600':('Seoaunty','SOLD'),
    '13472579':('TradeSave+','ENDED'),
    '12224172':('SubscriptionForce','NOT_LIVE'),
}
CATEGORIES = {'DUAL_DD':'DUAL_DD','BUY_DD':'BUY_DD','BUILD_DD':'BUILD_DD',
              'REFERENCE_ONLY':'REFERENCE'}

def load(path, default=None):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default

def valid_day(value):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None

def budget_card(raw):
    # List cards show start/current auction prices, not necessarily the reserve.
    if isinstance(raw, dict):
        return {'card_price_usd':raw.get('p'),'card_profit_usd_month':raw.get('pr'),
                'card_revenue_usd_month':raw.get('rev')}
    if isinstance(raw, list):
        return {'card_price_usd':raw[1] if len(raw)>1 else None,
                'card_profit_usd_month':raw[2] if len(raw)>2 else None,
                'card_revenue_usd_month':raw[3] if len(raw)>3 else None}
    return {}

def historical_audits(day):
    all_rows={}
    for path in HISTORIC_AUDITS:
        if not path.is_file():
            continue
        raw=load(path,{})
        data=raw.get('results',[]) if isinstance(raw,dict) else raw if isinstance(raw,list) else []
        for item in data:
            if not isinstance(item,dict):
                continue
            ident=str(item.get('id') or '')
            obs=str(item.get('observed_at') or '')[:10]
            if not ident.isdigit() or not valid_day(obs) or obs>day:
                continue
            prior=all_rows.get(ident)
            if not prior or obs>=prior['observed_on']:
                all_rows[ident]={'observed_on':obs,'status':str(item.get('state') or 'UNVERIFIED'),
                    'source':path.name,
                    'price_type':'asking' if item.get('asking_price') is not None else
                                 'reserve' if item.get('reserve') is not None else 'unknown',
                    'observed_ask_usd':item.get('asking_price'),
                    'observed_reserve_usd':item.get('reserve')}
    return all_rows

def build_backlog(day, root=ROOT, report_root=OUT, current_candidates=None):
    """Pure, deterministic snapshot based on source observations no later than day."""
    root=pathlib.Path(root);report_root=pathlib.Path(report_root)
    if not valid_day(day):
        raise ValueError('invalid day')
    baseline=load(root/'FLIPPA-INVENTORY-CURRENT-20261006.json',{})
    base_rows=baseline.get('main') or {} if BASELINE_DAY<=day else {}
    if not isinstance(base_rows,dict):base_rows={}
    snapshots=[]
    for path in root.glob('flippa-*-state.json'):
        match=re.search(r'flippa-(\d{8})(?:-(?:pm|daily))?-state\.json$',path.name)
        if match and match.group(1)<=day.replace('-',''):
            snapshots.append((match.group(1),path))
    snapshots.sort(reverse=True)
    recent_day=None;recent_ids=set();historical_cards={}
    for date,path in snapshots:
        d=load(path,{})
        if d.get('recent_done') is True and len(set(d.get('recent_ids') or []))>=400:
            observed=date[:4]+'-'+date[4:6]+'-'+date[6:]
            if recent_day is None:
                recent_day=observed
                recent_ids=set(map(str,d.get('recent_ids') or []))
            # Most recent observed card from *any* dated Recent-500 snapshot,
            # not just today's rolling feed. Absence carries the last evidence.
            for ident,card in (d.get('recent_rows') or {}).items():
                if str(ident) not in historical_cards and isinstance(card,dict):
                    historical_cards[str(ident)]=(observed,card)
    rows={}
    for ident,name,category,rank,gate,source_day in SEEDS:
        if source_day>day:
            continue
        rows[ident]={'id':ident,'identity':'flippa:'+ident,'name':name,'research_lane':category,
                     'priority':rank,'source_decision_as_of':source_day,'next_dd_gate':gate,
                     'origin':'CURATED_HISTORICAL_REVIEW','status':'DD_PENDING' if 'DD' in category else 'WATCH_OR_REFERENCE',
                     'approved_buy':False,'approved_build':False}
    # Preserve Flippa DD entries from every stored daily result as well.
    # Do not overwrite an existing stronger historical priority with a newer card.
    history=[(p.name[:10],load(p,{})) for p in sorted(report_root.glob('????-??-??-research-queue.json')) if p.name[:10]<=day]
    # Carry current DD candidates immediately on first daily scan (before the
    # dated research-queue file is written). No delayed second-run dependency.
    if current_candidates is not None:
        history.append((day,{'qualification':{'candidates':current_candidates}}))
    for source_day,data in history:
        candidates=(data.get('qualification') or {}).get('candidates') or []
        for item in candidates:
            if item.get('source')!='FLIPPA' or item.get('category') not in CATEGORIES:
                continue
            ident=str(item.get('identity') or '').removeprefix('flippa:')
            if not ident.isdigit() or ident in CLOSED:continue
            if ident not in rows:
                rows[ident]={'id':ident,'identity':'flippa:'+ident,
                            'name':str(item.get('title') or ident)[:140],
                            'research_lane':item['category'],'priority':70,
                            'source_decision_as_of':source_day,
                            'next_dd_gate':'; '.join((item.get('missing') or [])[:2])[:220],
                            'origin':'HISTORICAL_DAILY_DD','status':'DD_PENDING' if 'DD' in item['category'] else 'WATCH_OR_REFERENCE',
                            'approved_buy':False,'approved_build':False}
    audit=historical_audits(day) if root==ROOT else {}
    active=[]
    for ident,item in rows.items():
        latest=historical_cards.get(ident)
        original=base_rows.get(ident)
        if latest:
            last_observed,card=latest
            item['last_card_observation_on']=last_observed
            item['last_card_source']='RECENT_500_HISTORICAL'
            item['card']=budget_card(card)
            item['url']=str(card.get('href') or ('https://flippa.com/'+ident))
        elif original:
            item['last_card_observation_on']=BASELINE_DAY
            item['last_card_source']='FULL_BASELINE'
            item['card']=budget_card(original)
            item['url']=str(original[7] if len(original)>7 else 'https://flippa.com/'+ident)
        else:
            item['last_card_observation_on']=None
            item['last_card_source']='NOT_FOUND_IN_SCOPED_SNAPSHOTS'
            item['card']={}
            item['url']='https://flippa.com/'+ident
        # Absent from a rolling feed means UNKNOWN, never SOLD.
        item['recent_500_presence']='SEEN' if ident in recent_ids else 'NOT_SEEN'
        item['current_listing_status']='CURRENT_AVAILABILITY_UNVERIFIED'
        # Historical price/visibility is never live availability proof.
        item['direct_listing_evidence']=audit.get(ident)
        active.append(item)
    active.sort(key=lambda x:(x['priority'],x['source_decision_as_of'],x['id']))
    closed=[{'id':ident,'name':name,'last_direct_status':status,
             'last_direct_confirmation_as_of':'2026-10-07','status':'CLOSED_HISTORICAL'}
            for ident,(name,status) in sorted(CLOSED.items())
            if day>='2026-10-07']
    return {'schema':'acquisition-flippa-cumulative-backlog-v1','as_of':day,
            'last_scoped_recent_scan':recent_day,'last_full_inventory_observation':BASELINE_DAY,
            'active_count':len(active),'closed_historical_count':len(closed),
            'approved_buy':0,'approved_build':0,
            'active':active,'closed_historical':closed,
            'policy':{'no_dropping_on_recent_absence':True,'price_is_listing_claim':True,
                      'no_buy_approval_from_carried_data':True,
                      'not_in_recent_not_sold':True,
                      'cumulative_not_new_daily_results':True,
                      'last_full_listing_scan_not_today':True}}

def summarize(backlog, max_rows=18):
    lines=['## Cumulative Flippa BUY/DD/WATCH backlog (carried forward)','',
        '- Active research entries: '+str(backlog.get('active_count',0))+
        '; historical confirmed closed: '+str(backlog.get('closed_historical_count',0))+
        '; BUY approved: 0; BUILD approved: 0.',
        '- Last full Flippa inventory: '+str(backlog.get('last_full_inventory_observation'))+
        '; recent-window snapshot: '+str(backlog.get('last_scoped_recent_scan'))+
        '. Missing from Recent-500 is **not** SOLD/ENDED.',
        '- These are historical research statuses, **not** current listing availability or verified financials.','',
        '| Priority | Listing | Research lane | Last card observation | Recent-500 | Next DD gate |',
        '|---:|---|---|---|---|---|']
    for row in (backlog.get('active') or [])[:max_rows]:
        gate=str(row.get('next_dd_gate') or '').replace('|','/')[:105]
        title=str(row['name']).replace('|','/')[:55]
        lines.append('| '+str(row['priority'])+' | ['+title+']('+row['url']+') | '+
                     row['research_lane']+' | '+str(row['last_card_observation_on'] or 'not observed')+
                     ' | '+row['recent_500_presence']+' | '+gate+' |')
    rem=max(0,len(backlog.get('active') or [])-max_rows)
    if rem: lines.append('\n- '+str(rem)+' other carried entries remain in the structured backlog; not silently deleted.')
    return '\n'.join(lines)+'\n'
