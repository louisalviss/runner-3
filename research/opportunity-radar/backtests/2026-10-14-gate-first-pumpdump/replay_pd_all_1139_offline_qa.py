#!/usr/bin/env python3
"""Recheck complete archived 1139 P/D source evidence; NO economic-Gate inference."""
import csv,json,datetime,statistics,collections
from pathlib import Path
from zoneinfo import ZoneInfo
P=Path(__file__).resolve().parent
def read(name):
 with (P/name).open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
market=read('PD_ALL_1139_GATE_EVIDENCE_MATRIX.csv')
sec=read('PD_ALL_1139_SEC_PIT_SOURCE_COVERAGE.csv')
fin=read('PD_ALL_1139_ASOF_FINANCIAL_GATE_INPUTS.csv')
price=read('PD_ALL_1139_NEXTOPEN_PRICE_ONLY_OUTCOMES.csv')
assert len(market)==len(sec)==len(fin)==len(price)==1139
key=lambda q:[(x['session'],x['symbol']) for x in q]
assert key(market)==key(sec)==key(fin)==key(price)
assert len(set(key(market)))==1139
assert len({x['symbol'] for x in market})==707
assert sum(x['in_previously_prioritized_326']=='True' for x in market)==326
assert sum(x['liquidity_research_filter_cap1b_ADV10m_price5']=='True' for x in market)==797
assert sum(x['liquidity_and_volume']=='True' for x in market)==418
assert sum(x['older_stored_dossier_exists']=='True' for x in market)==22
assert sum(int(x['sec_known_prior_8k6k_7d'])>0 for x in sec)==258
assert sum(x['sec_prior_10q10k20f_any']=='True' for x in sec)==1119
assert sum(int(x['financial_core_fresh185'])>=4 for x in fin)==963
assert sum(int(x['financial_core_fresh185'])==6 for x in fin)==725
by=collections.Counter(x['financial_NI_CFO_sign'] for x in fin)
assert by=={'POSITIVE_NET_INCOME_AND_OPERATING_CF':336,
 'NEGATIVE_NET_INCOME_AND_OPERATING_CF':365,'MIXED_SIGNS':227,'MISSING_OR_STALE_SIGN':211},by
assert sum(bool(x['hypothetical_entry_next_NYSE_open_day']) for x in price)==1126
assert sum(x.get('price_only_nextopen_5d_net50_pct') not in ('',None) for x in price)==951
assert sum(x.get('price_only_nextopen_20d_net50_pct') not in ('',None) for x in price)==432
for e in market:
 assert e['at_P_D_session_full_Gate_status']=='UNKNOWN_NOT_FULL_PIT_ECONOMIC_GATE'
 assert e['original_PD_origin_BUY_SIGNAL_verified']=='False'
for e in price:
 if not e['hypothetical_entry_next_NYSE_open_day']:continue
 after=datetime.datetime.combine(datetime.date.fromisoformat(e['hypothetical_entry_next_NYSE_open_day']),
  datetime.time(9,30),tzinfo=ZoneInfo('America/New_York')).astimezone(datetime.timezone.utc)
 assert after>datetime.datetime.fromisoformat(e['packet_generated']).astimezone(datetime.timezone.utc)
 for h in (1,5,20):
  v=e.get(f'price_only_exit_{h}d_date')
  if v:assert v<='2026-10-15'
stats=json.loads((P/'PD_ALL_1139_PRICE_ONLY_OUTCOME_SUMMARY.json').read_text())
assert stats['by_group']['all']['5D']['N']==951
assert abs(stats['by_group']['all']['5D']['mean_net_pct']+.482)<.0001
print(json.dumps({'PASS':True,'event_rows':len(market),'unique_issuers':707,'matured_5D':951,
'unknown_gate':1139,'price_only_not_trade':True,'data_source_cutoffs':True},separators=(',',':')))
