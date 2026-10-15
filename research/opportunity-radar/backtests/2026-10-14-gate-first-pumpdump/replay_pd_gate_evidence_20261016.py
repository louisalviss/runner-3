#!/usr/bin/env python3
"""Read-only P/D historical evidence join. NO investment Gate is derived."""
import csv, json, datetime, collections
from pathlib import Path
B=Path(__file__).resolve().parent
def csvrows(name):
    with (B/name).open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def jsonrows(name):
    return json.loads((B/name).read_text(encoding='utf-8'))
def snap(k,rows,key_cols):
    return {tuple(v[c] for c in key_cols):v for v in rows}
pd_all=csvrows('all_pumpdump_events.csv')
cohort=jsonrows('eligible_326.json')
fin=snap(None,jsonrows('asof_financial_fields_326.json'),['session','symbol'])
filings=snap(None,csvrows('asof_sec_edgar_index_326.csv'),['session','ticker'])
sec=snap(None,jsonrows('asof_filing_primary_text_index_89.json'),['source_session','symbol'])
quality=snap(None,csvrows('asof_fundamental_quality_AB_326.csv'),['date','symbol'])
headlines=snap(None,csvrows('research_triage_326.csv'),['session','symbol'])
reverse=snap(None,csvrows('rr2_reverse_screen_326.csv'),['source_session','ticker'])
deals={v['ticker']:v for v in csvrows('verified_deal_rr4.csv')}
# Original 6-K sources (the R3 primary documents were checked to predate
# packet creation); these six signs were recovered later, not newly published.
recovered_6k=jsonrows('asof_primary_recovered_financial_ab_r3.json')
recovered_positive={(x['date'],x['symbol']) for x in recovered_6k['updated_from_missing_to_positive']}
# 12 manually observed original historic Candidates, already in previous Drive revisions.
# Gate score values were last updated BEFORE their later P/D events: NEVER call
# this a P/D-session gate calculation.
dossiers={'BLLN':(70.3,3,'0.0x'),'RIOT':(72.8,5,'RR_NOT_CERTIFIED'),
'SNDK':(71.3,4,'1.5x'),'AMAT':(71.8,3,'1.6x'),
'CBRS':(61.5,2,'1.5x'),'KRMN':(70.3,4,'RR_NOT_CERTIFIED'),
'MRNA':(74.0,3,'RR_BELOW_2_REPORTED'),'MRVL':(80.7,4,'1.7x'),
'RUM':(70.5,4,'RR_NOT_CERTIFIED'),'DKS':(70.8,3,'RR_NOT_CERTIFIED'),
'HPQ':(31.3,3,'RR_BELOW_1_REPORTED'),'P':(81.8,4,'1.3x')}
# Manually inspected original SEC source narrative, not a certified
# price-event causal connection or a subjective pass of economic Gate.
primary={
('2026-09-15','ENVA'):('WITHDRAWN_MERGER_APPLICATION','Approval request for Grasshopper Bancorp acquisition withdrawn; no demonstrated positive equity upside'),
('2026-09-17','GNRC'):('COMMERCIAL_CONTRACT_AND_EQUITY_WARRANT','Amazon supply expected gross deliveries; independently demonstrated after-tax equity value not known'),
('2026-09-22','INOD'):('BOARD_APPOINTMENT','Appointment of independent director is not automatically price-relevant growth catalyst'),
('2026-09-14','ARM'):('AGM_RESULTS','6-K contains AGM voting; not demonstrated cause of move'),
('2026-09-21','ARM'):('OTHER_6K','Short 6-K; cannot attribute Pump to positive economic development'),
('2026-09-24','ACAD'):('CLINICAL_DATA','Phase 2 RADIANT release; probability/market opportunity/downside not price-underwritten'),
('2026-10-05','CHRW'):('MERGER_ACQUIRER','Merger acquisition agreement with RXO; acquiring-firm synergy, integration and consideration costs unresolved'),
('2026-09-21','TPB'):('CEO_CHANGE','CEO resignation and succession; not an equity upside valuation'),
('2026-09-14','GLW'):('ATM_EQUITY_CAPACITY','Announced up-to $2 billion ATM common stock sale capacity; authorization is not completed dilution'),
('2026-09-15','BOOT'):('GUIDANCE_UPDATE','Expected fiscal second-quarter revenue and EPS high end of earlier guidance; not independently valued'),
('2026-09-14','PBF'):('DEBT_FINANCING','Announced planned $500 million exchangeable notes due 2032, redemption conditioned on financing'),
('2026-09-23','PAYX'):('QUARTERLY_EARNINGS','Fiscal-quarter results disclosed with Exhibit 99.1; forward return/valuation not independently verified'),
('2026-09-11','DELL'):('DEBT_UNDERWRITING','Debt securities underwriting, not automatically positive earnings surprise'),
('2026-09-16','MGY'):('ACQUISITION_AND_DEBT_ASSUMPTION','Acquisition closing and $600m target notes at 7.5%; synergy, leverage and downside need underwriting'),
('2026-09-11','M'):('QUARTERLY_EARNINGS','Macy earnings results press release; no independently bounded target/downside'),
('2026-09-24','PTC'):('NOT_IN_COHORT','Reserved for transaction not matched'),
('2026-09-11','ACVA'):('CASH_MERGER','Cash offer reference scenario RR<2, not original Gate FAIL'),
('2026-09-14','BWIN'):('CASH_MERGER','Cash offer reference scenario RR<2, not original Gate FAIL'),
('2026-10-05','PTC'):('CASH_MERGER','Cash offer reference scenario RR<2, not original Gate FAIL'),
('2026-10-05','RXO'):('FLOATING_MIXED_CONSIDERATION_MERGER','Cash plus stock offer reference scenario RR<2, not original Gate FAIL'),
}
out=[]
for e in cohort:
    s=e['symbol'];d=e['session'];k=(d,s)
    f=fin[k];fil=filings[k];cl=quality[k];h=headlines[k];rr=reverse[k]
    fields=f['fields']
    first=datetime.date.fromisoformat(d)
    fresh={t: v for t,v in fields.items() if 0<=(first-datetime.date.fromisoformat(v['end'])).days<=185}
    core=('cash','assets','liabilities','revenue','net_income','operating_cash')
    corefresh=sum(t in fresh for t in core)
    ni=fresh.get('net_income',{}).get('val')
    cfo=fresh.get('operating_cash',{}).get('val')
    base_finance_positive=ni is not None and cfo is not None and ni>0 and cfo>0
    econ_pos=base_finance_positive or k in recovered_positive
    available=k in sec
    if available:
        t=sec[k]
        accepted=datetime.datetime.fromisoformat(t['accepted_sec_at'].replace('Z','+00:00'))
        pkt=datetime.datetime.fromisoformat(e['packet_generated']).astimezone(datetime.timezone.utc)
        assert accepted<=pkt,(s,d,accepted,pkt)
    code,claim=primary.get(k,('SOURCE_AVAILABLE_CAUSALITY_UNVERIFIED' if available else 'NO_7D_PRIMARY_8K_6K','No independently verified catalyst valuation'))
    deal=deals.get(s) if s in ('ACVA','BWIN','PTC','RXO') else None
    rows={
    'session':d,'symbol':s,'kind':e['kind'],
    'volume_ratio':e['volume_ratio'],'original_1d_move_pct':e['ret_1d_pct'],
    'priority_rank_proxy':e['priority'],
    'historical_12_dossier':s in dossiers,
    'stored_older_score':dossiers[s][0] if s in dossiers else '',
    'stored_older_mq':dossiers[s][1] if s in dossiers else '',
    'stored_older_rr':dossiers[s][2] if s in dossiers else '',
    'gate_at_PD_session':'UNKNOWN_NOT_FULL_GATE_SCORED',
    'full_economic_GATE_PASS_proven':False,
    'historical_BUY_from_PD_proven':False,
    'sec_primary_within7d_asof':available,
    'sec_primary_url':fil['latest_8k6k_url'] if available else '',
    'sec_primary_accepted':fil['latest_8k6k_accepted_at'] if available else '',
    'source_case_category':code,'source_case_note':claim,
    'fresh_core_fields_6':corefresh,
    'positive_ni_and_operating_cf_ASOF':econ_pos,
    'finance_sign_source':('SEC_COMPANYFACTS_BASELINE' if base_finance_positive else 'ORIGINAL_6K_R3_RESTORED' if k in recovered_positive else 'NOT_BOTH_POSITIVE_OR_NOT_COMPARABLE'),
    'news_headline_asof_found':h['news_state']=='ASOF_HEADLINE_PRESENT_NOT_PRIMARY_VERIFIED',
    'dated_financial_report':fil['financial_url'],
    'deal_reference_RR2_scenario_below_gate':bool(deal),
    'deal_break_reference_RR':deal['RR_deal_break_proxy'] if deal else '',
    'reverse_RR2_target_if_prejump_bear':rr['required_bull_target_prejump_RR2_usd'],
    'source_packet_generated':e['packet_generated'],
    'research_priority_lane':('A_PRIMARY_POSITIVE_FINANCE_NEEDS_CAUSAL_VALUE' if available and econ_pos else
            'B_PRIMARY_OTHER_NEEDS_UNDERWRITE' if available else
            'C_FINANCE_POSITIVE_NEEDS_PRIMARY_CATALYST' if econ_pos else 'D_EVIDENCE_GAP'),
    }
    out.append(rows)
assert len(out)==326
assert len(set((x['session'],x['symbol']) for x in out))==326
assert len([x for x in out if x['historical_12_dossier']])==8
assert len([x for x in out if not x['historical_12_dossier']])==318
assert len(set(x['symbol'] for x in out if x['historical_12_dossier']))==7
assert len([x for x in out if x['sec_primary_within7d_asof']])==89
assert len([x for x in out if x['sec_primary_within7d_asof'] and x['positive_ni_and_operating_cf_ASOF'] and not x['historical_12_dossier']])==31
assert all(x['gate_at_PD_session']=='UNKNOWN_NOT_FULL_GATE_SCORED' for x in out)
assert len({r['symbol'] for r in pd_all})==707
with (B/'pd_gate_asof_research_matrix_326.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(out[0]),lineterminator='\n');w.writeheader();w.writerows(out)
summary={'total_pd_events_all':len(pd_all),'unique_pd_symbols_all':707,'cohort_episodes':326,
'cohort_tickers':len({x['symbol'] for x in out}),
'preexisting_archived_candidate_dossier_episodes':8,
'preexisting_archived_candidate_dossier_tickers':7,
'never_full_gate_at_event_episodes':326,
'cohort_318_without_archived_candidate':318,
'sec_primary_timed_8k6k_episodes':89,
'primary_plus_positive_finance_in_318':31,
'primary_plus_positive_finance_before_R3_6K_restoration':29,
'restored_6K_finance_sign_episodes':len(recovered_positive),
'primary_plus_positive_finance_unique_tickers':len({x['symbol'] for x in out if x['research_priority_lane']=='A_PRIMARY_POSITIVE_FINANCE_NEEDS_CAUSAL_VALUE' and not x['historical_12_dossier']}),
'deal_scenario_reference_rr_below2':sum(x['deal_reference_RR2_scenario_below_gate'] for x in out),
'manually_source_identified_episodes':sum(x['source_case_category'] not in ('SOURCE_AVAILABLE_CAUSALITY_UNVERIFIED','NO_7D_PRIMARY_8K_6K') for x in out),
'lanes':dict(collections.Counter(x['research_priority_lane'] for x in out)),
'conclusion':'ZERO VERIFIED FULL-GATE PD BUYS; NOT ZERO TRUE POSSIBLE PASSES. Historical source missing for almost all at-event economic Gate.',
'original_full_gate_coverage':'0 complete 326 PIT Score+MQ+priced RR+Entry+Execution audit records; old dossier 8 are older than events',
'anti_lookahead':'Prices and later performance never used for Gate PASS; original 8K acceptance <= packet; document coverage is not catalyst causal proof',
'no_production_changes':True}
(B/'pd_gate_asof_research_summary_326.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(summary,separators=(',',':')))
