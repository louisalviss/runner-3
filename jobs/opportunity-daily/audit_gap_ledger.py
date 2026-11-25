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


def reconcile_dd(rows, backlog):
 """Keep source history; count only distinct unresolved DD identities."""
 archived = {str(x['id']) for x in backlog.get('reviewed_archived', []) if isinstance(x,dict) and str(x.get('id','')).isdigit()}
 closed = {str(x['id']) for x in backlog.get('closed_historical', []) if isinstance(x,dict) and str(x.get('id','')).isdigit()}
 latest = {}
 dispositions = []
 for x in rows:
  ident = str(x.get('identity') or '')
  if not ident: continue
  if ident.startswith('flippa:') and x.get('source') == 'FLIPPA':
   key = ident.removeprefix('flippa:')
   reason = 'CONFIRMED_CLOSED' if key in closed else 'REVIEWED_ARCHIVED' if key in archived else None
   if reason:
    dispositions.append(dict(x, pending=False, resolution=reason))
    continue
  prev = latest.get(ident)
  if prev is None or str(x.get('day','')) >= str(prev.get('day','')):
   latest[ident] = x
 return list(latest.values()), dispositions


# Dated preliminary review receipt, not a qualification or resolution gate.
# Canonical Dropbox Acquisition - Idea Radar.md rev 016611a8b6ec34b000000034da19313.
SEO64_REVIEW_DAY = '2026-11-25'
SEO64_REVIEW_REF = 'ACQUISITION_SEO64_TRIAGE_20261125'
SEO64_REPORT_HASHES = {
  "2026-10-15": "9b18a87ec1c642ad07992ce9e1d6b15368178723b44ab6a47d76583f28e79766",
  "2026-10-16": "91958b82c40666dfc2c2d1778381eb9e7d792d0664da9b5b17f260dc0a3e5663",
  "2026-10-17": "ccc80a54cb46672b3846c3ef1961129136f0f48cd326adf5cfae8761d0bf4fd4",
  "2026-10-19": "d8f482e6543016ba6efeaa38ae971ea15e58a912ebf4f1a899ef71e8324eecc5",
  "2026-10-20": "ff0703ec1f9d78c6f36f49a2f9ed90fa297f9e9c7175714671a39d6c721defbb",
  "2026-10-21": "e2c0e91ee47e25db4ed8da19570525bf33e88d1b6766838a87ce98969ee2088f",
  "2026-10-24": "3f14c4413a3b237a9be8f724a1822b2abec175ae68f40dd5a69a5c548d7f8b2e",
  "2026-10-25": "6a08a29e610a82c5ff4b3969f9b7c126b998761c94a191dd2318811ae82b0b50",
  "2026-10-26": "cafb129e9ec491ad6d58481ef1428712a59051c22abf3b9534730df70fee6e0f",
  "2026-10-27": "7adc4213904ab878714a97c983f97aa1653cb1180b87b6746eb1e3ccf526c2b1",
  "2026-10-28": "fb72d2758c2fb22195934f5c0d7ee98d3e1f02ef56026463d94e55987333200f",
  "2026-10-29": "6bfc9367a495b7078bd7b4d220e4984cb708b03c27527aad85a8f11ef9ad7364",
  "2026-11-05": "b48d08e03f4acbc9ef4dc43dc6d592bc8dfc552627fe50d97d77d192efcabdf8",
  "2026-11-06": "0413f0a9b152cf33ac28df1819be1795c0e75f1b3a52153e80c1d3e0434e98e4"
}
SEO64_TRIAGE = {
  "adspyder.io": [
    "2026-10-15",
    "999d0e32ac1cb4a70168755784384c66f2a76da34daf9b073b2b03ff3725c19e",
    "DEFER_GAP_UNPROVEN"
  ],
  "arcweave.com": [
    "2026-10-15",
    "c3e892ecaacf2d3648f4adfc4934641d69b9661b86d0dd22d581e902885f8876",
    "DEFER_GAP_UNPROVEN"
  ],
  "docsautomator.co": [
    "2026-10-15",
    "f0b52618519fd29d4c8c4c88672f494bc47c22caa441fe0919c0949e460f353a",
    "DROP_DIRECT_CLONE"
  ],
  "fyi.app": [
    "2026-10-15",
    "8fcb6925bdb134df8a15483bdc2b4ce23e357d6faea614bf1e46bfb59d13b67b",
    "TRAFFIC_ATTRIBUTION_REVIEW"
  ],
  "hixbypass.com": [
    "2026-10-15",
    "dbed15d536550aa2a9f6348d07854df32ff1fd0f1ff4e728a8ae510af69d487f",
    "MODEL_RISK"
  ],
  "klang.io": [
    "2026-10-15",
    "88d2f097f83df6c087e8f78c0a78b13f1c2eb8712d43b6db2094c1a7ca578217",
    "COMPETITION_CHECK"
  ],
  "rapidscada.org": [
    "2026-10-15",
    "aee16c214cf3f1c01ef52c64cf03220ae3ab32ddb9b9fa14008739b2cba9f730",
    "ENTERPRISE_SCOPE"
  ],
  "remberg.com": [
    "2026-10-15",
    "3bd7168c1a7d91b2955b6baca7bf4b7bafe6359453e619e0d8560f0bf776a751",
    "ENTERPRISE_SCOPE"
  ],
  "snowball-analytics.com": [
    "2026-10-15",
    "492e7df11d81010325d5c2e4104e1e5c1398eb49816722d308446f0196cd0a32",
    "DEFER_GAP_UNPROVEN"
  ],
  "acpatterns.com": [
    "2026-10-16",
    "03e5b7d9c9963d1a3d555a1904bfff95007affa20edcfd19f74923bb45a5b107",
    "COMMODITY_CONTENT"
  ],
  "flexiv.com": [
    "2026-10-16",
    "41354bea7cb41f9ac374b2b16cdc7eeb0c948b0908b56af6add9e4d7a81d026b",
    "OUTSIDE_SCOPE"
  ],
  "linkdm.com": [
    "2026-10-16",
    "74964439454a525ab9165832f36e9043bf85297ae6c4de7621905d7fb9051a8e",
    "DEFER_GAP_UNPROVEN"
  ],
  "deciphertools.com": [
    "2026-10-17",
    "6cfa823c6b935621024877380b5f0f7636c67b71ac3d6cc8f21f29b19378cbec",
    "DROP_DIRECT_CLONE"
  ],
  "effectmatrix.com": [
    "2026-10-17",
    "39d2d9280ca2b1198f4158c7c3c62dbd8353c7064fa7909aaca51dc262e5b7db",
    "COMMODITY_CONTENT"
  ],
  "monsterwriter.com": [
    "2026-10-17",
    "3b682302cf307d511dd9c97c51c78ba89c9360f6dff5adebc1f232f57b565443",
    "COMMODITY_CONTENT"
  ],
  "unitslab.com": [
    "2026-10-17",
    "c05f671ebb07eb2f88943de6e454b6f9932d19d93946a2ad135f95bd90e5d172",
    "COMMODITY_CONTENT"
  ],
  "abkco.com": [
    "2026-10-19",
    "1e70665a17ae88485983f4bbf2ae054d804da78c02267297ee4d15e346554365",
    "OUTSIDE_SCOPE"
  ],
  "amalytix.com": [
    "2026-10-19",
    "fe968fe46112586732146b2f7d6e6f222c558969441b9b7d2d571ba6d9dad021",
    "DEFER_GAP_UNPROVEN"
  ],
  "avatarsdk.com": [
    "2026-10-19",
    "4c71064ae35a109201162c01dbfd30d276f047647e4bd4c2431223ed1e93afd1",
    "DEFER_GAP_UNPROVEN"
  ],
  "codex.io": [
    "2026-10-19",
    "e5d545438460bd7283d40feb62932a5fcda493becee6758600fb9656b1e80338",
    "TRAFFIC_ATTRIBUTION_REVIEW"
  ],
  "kidkare.com": [
    "2026-10-19",
    "d77ab2a74602c18bd57d7448175b4c652cca7f3427b78766f022cb430108a81e",
    "ENTERPRISE_SCOPE"
  ],
  "mailjerry.com": [
    "2026-10-19",
    "4e18bb1a12760a0ccab0204f37f7cad40e9ce0fc1fdc9119b32981ec6d545fb7",
    "DEFER_INDIVIDUAL"
  ],
  "window-cleaning-supply.com": [
    "2026-10-19",
    "0d7e7b8f59d8aa3dbd459a98df037b74d84d6c0bb8922c6a26850f56bee79561",
    "OUTSIDE_SCOPE"
  ],
  "nationalcompliance.com": [
    "2026-10-20",
    "cfa68f4d534706691a21ea517683dc938b9ff3646668c8541cd1cf6eb1c095e2",
    "ENTERPRISE_SCOPE"
  ],
  "elser.ai": [
    "2026-10-21",
    "698550a2a530c0c7daf1b9a18c1bdf846a1f7b53cada175391e9a18a01099735",
    "MODEL_RISK"
  ],
  "guestpix.com": [
    "2026-10-21",
    "275f619e3beef8ac338a72b8543306829116a383f0b741aa3fd436f6d29b5ad5",
    "DEFER_INDIVIDUAL"
  ],
  "heyiris.ai": [
    "2026-10-21",
    "8debf70cc0a9dcfd8d05b7dfdcda6b1bb2dee7b1b8f2f0022c63c00f1565472d",
    "DEFER_GAP_UNPROVEN"
  ],
  "spydialer.com": [
    "2026-10-21",
    "bd6300d8e3a1ce729189a5f8b317d329b37dacb89e55f2a8c49945182b09b0d3",
    "MODEL_RISK"
  ],
  "hyresult.com": [
    "2026-10-24",
    "002fa431d73b022182790d3149d541255bf56e687cdfaa1582fb5166b64975b7",
    "DEFER_GAP_UNPROVEN"
  ],
  "kldiscovery.com": [
    "2026-10-24",
    "0adc6434fd1c51117f779a7a6f868873ae28fb0f681e14593a5453a1c30ccf23",
    "ENTERPRISE_SCOPE"
  ],
  "novusautomation.com": [
    "2026-10-24",
    "53aba332b4ba119c537ebf347e07f23602c43259113c3d4d8799587dec7e5e58",
    "OUTSIDE_SCOPE"
  ],
  "timezonewizard.com": [
    "2026-10-24",
    "b684b7484a4ebf6b3d6aa8dc1fc82084e05738c3fa073695f32e19fd4959d604",
    "COMMODITY_CONTENT"
  ],
  "topdon.us": [
    "2026-10-24",
    "aee572a686f8cc6ac3a6a0906b1b43f61909c335a75201b39ecc0a4c53f578f7",
    "OUTSIDE_SCOPE"
  ],
  "ukeysoft.com": [
    "2026-10-24",
    "8320a87d27cb529d83041da0ee984a2764fc373b002dbc6040033594b6fc2395",
    "MODEL_RISK"
  ],
  "mcskins.top": [
    "2026-10-25",
    "09f87243dc86f3a6d94b24da4201051377f64385dcd44a5bdbb52888f1f89478",
    "COMMODITY_CONTENT"
  ],
  "pointandpay.com": [
    "2026-10-25",
    "cfa58bbdfd401bcf1a95dbb387a93bf9a6270b9f42f3bb05f1935f356516e9bc",
    "ENTERPRISE_SCOPE"
  ],
  "codewords.ai": [
    "2026-10-26",
    "319cacee79a7500d3a2bfed4e4228a858ac1d8eb2822cd07d58fd832f37b0a1b",
    "DEFER_GAP_UNPROVEN"
  ],
  "djeventplanner.com": [
    "2026-10-26",
    "aa4b65526172da64951079020c8031848b77e71826b597ae1dac3b1f712b2a9f",
    "COMPETITION_CHECK"
  ],
  "reiclub.com": [
    "2026-10-26",
    "a268ad5549f170793ff20b0ff1dc477dfc0ef902cc7ebda783ad3ba349492e8f",
    "COMMODITY_CONTENT"
  ],
  "arbostar.com": [
    "2026-10-27",
    "03910a738a83ae1da63067aaa4c6bd7770f729dda76451c34295ee48144436f1",
    "DEFER_INDIVIDUAL"
  ],
  "limberhealth.com": [
    "2026-10-27",
    "9df9a72fce34974329c6e5c83562c475e07d2e2e6f9ee1303419715c51ed5830",
    "ENTERPRISE_SCOPE"
  ],
  "multiviewcorp.com": [
    "2026-10-27",
    "cec8653f03d2026e53de549cb6b286899a6ffbd52320606f1f95b40087db753a",
    "ENTERPRISE_SCOPE"
  ],
  "trafficpeak.io": [
    "2026-10-27",
    "adb6e0c117fce4e7a44b8dd8ebcd457459a705437d8fd9d6cc5eb6d8a0695960",
    "MODEL_RISK"
  ],
  "veros.com": [
    "2026-10-27",
    "8374304e479b36aa4b17a1ed3a72963dc9059e60ad3bf2057cc485a02bbc8dcf",
    "ENTERPRISE_SCOPE"
  ],
  "vespertool.com": [
    "2026-10-27",
    "9f4886fadc379e0fd775cf5214390339afcfb835a11398b8468b6e1d94a53cef",
    "ENTERPRISE_SCOPE"
  ],
  "app.powerbi.com": [
    "2026-10-28",
    "06d0c3b65829094470df42898e983a42e8d910588407b48667de91beab49cc31",
    "TRAFFIC_ATTRIBUTION_REVIEW"
  ],
  "mednetsolutions.com": [
    "2026-10-28",
    "fb83f680401164eb2d7f9506a76961184c92bb81a914c6416a384844c138111d",
    "ENTERPRISE_SCOPE"
  ],
  "mimacom.com": [
    "2026-10-28",
    "872d80102a1f14cef63a2aa0ac5ad1c1d434cc61db8fff538a1bc4e36b7093b3",
    "OUTSIDE_SCOPE"
  ],
  "bricxlabs.com": [
    "2026-10-29",
    "06ab6e981c320f9e898dd0b0c015f3a552627199b095055a15ccc63672f14a9f",
    "OUTSIDE_SCOPE"
  ],
  "grantome.com": [
    "2026-10-29",
    "607397fedd85af63b3ab3c04d30326a06a155cba8b8cff5cd7f47afbc171ed06",
    "COMPETITION_CHECK"
  ],
  "iatrox.com": [
    "2026-10-29",
    "d3ffa2536157b636ef406a7ad07ca31ad0c2ab182873f94c56458e03b85e652e",
    "ENTERPRISE_SCOPE"
  ],
  "onedoor.com": [
    "2026-10-29",
    "fb883a5efbd284f0a4c8e7ce07eba31435f8095f61faa863652a81b755e0cc78",
    "ENTERPRISE_SCOPE"
  ],
  "disc-tools.com": [
    "2026-11-05",
    "15d35153f3d8df3ba61bb9fd729d7d95f95ea5749c9b41af6968f7516364c573",
    "COMMODITY_CONTENT"
  ],
  "planera.io": [
    "2026-11-05",
    "2d1164fff30bc6d058bfb879c4cd5a55a658aed1adb98df26647f0de54ab3032",
    "COMPETITION_CHECK"
  ],
  "ro.qrcodechimp.com": [
    "2026-11-05",
    "f576b3d3910ff9687478b461b38618b9ea33ca95d1b705612ec663a5ee8b189b",
    "TRAFFIC_ATTRIBUTION_REVIEW"
  ],
  "sesamehr.com": [
    "2026-11-05",
    "7169bb49d9a8f96acc905728bb63a5f64d9b775a6fb225d43eb9c93c503d1373",
    "DEFER_GAP_UNPROVEN"
  ],
  "th.qr-code-generator.com": [
    "2026-11-05",
    "73c3829786f4be7737fea1889c912ac8661e1dab74153df0af3c6c0ab59e53af",
    "TRAFFIC_ATTRIBUTION_REVIEW"
  ],
  "tools.pdf24.org": [
    "2026-11-05",
    "e2b9199569570903ee78f92839c37a44860d5ac9885802c94f03a2601638bf4d",
    "COMMODITY_CONTENT"
  ],
  "urbistat.com": [
    "2026-11-05",
    "3c18a1a79644b5124710476c97389e93d53d497dc81ec4265918851d02355917",
    "COMMODITY_CONTENT"
  ],
  "bounties.kick.com": [
    "2026-11-06",
    "4303f55d48abf43c157eb8816ea56076bc5e621f8249633c7687f6677c12f28f",
    "TRAFFIC_ATTRIBUTION_REVIEW"
  ],
  "ezus.io": [
    "2026-11-06",
    "4bffe7b4b1804da4e37fa29b809bfe636c9ba09481f1b1f2fb2f961b268fde12",
    "DEFER_GAP_UNPROVEN"
  ],
  "fasttrack.ai": [
    "2026-11-06",
    "3c63df42cbc5468722cbdc11c393d7f01ebbe31c036d99db61daf46754489363",
    "MODEL_RISK"
  ],
  "flowvella.com": [
    "2026-11-06",
    "45ec3aa7cb293c0f1382e313c3709ffc75a9406ccdd6095d7a00211c72ea9ac8",
    "COMMODITY_CONTENT"
  ],
  "tritontools.com": [
    "2026-11-06",
    "63320c9a7ab45677e88a6be5a200df31b33170d81a4c693d8c95f13704190e75",
    "OUTSIDE_SCOPE"
  ]
}

def annotate_preliminary_triage(rows, end, seo_root, report_hashes):
 """Bind a preliminary screen to the exact dated export and report.
 A changed/new snapshot remains untriaged. No DD resolution or approval."""
 out = []
 for row in rows:
  ident = row.get('identity')
  receipt = SEO64_TRIAGE.get(ident)
  item = dict(row)
  if receipt and row.get('source') == 'SEOTRENDS' and end >= SEO64_REVIEW_DAY:
   day, export_sha, group = receipt
   if (row.get('day') == day and report_hashes.get(day) == SEO64_REPORT_HASHES.get(day)
       and sourcehash(seo_root/(day+'-semrush')/(ident+'.json')) == export_sha):
    item['preliminary_triage'] = {'status':'SCREENED_PRELIMINARY','group':group,
       'review_day':SEO64_REVIEW_DAY,'review_ref':SEO64_REVIEW_REF,
       'source_export_sha256':export_sha,'semantic_dd_complete':False}
  out.append(item)
 return out


def reconcile_semantic_cycle(rows, end, seo_root, daily_evidence):
 """Close this research cycle only on the exact source-bound negative decision.
 Deferred is not resolved, qualified, or an active unreviewed DD task."""
 active, dropped, deferred = [], [], []
 cache = {}
 for row in rows:
  ident, day = row.get('identity'), row.get('day')
  triage = row.get('preliminary_triage') or {}
  # Only the previously source-bound cohort can consume these retrospective receipts.
  if (row.get('source') != 'SEOTRENDS' or row.get('category') != 'BUILD_DD'
      or triage.get('status') != 'SCREENED_PRELIMINARY'):
   active.append(row); continue
  if day not in cache:
   path = seo_root/(day+'-semantic-business-dd.json')
   data = j(path)
   cache[day] = (data, sourcehash(path))
  data, file_sha = cache[day]
  if (not file_sha or not isinstance(data,dict) or data.get('date') != day
      or data.get('source') != 'derived-semantic-dd-v1'
      or data.get('status') != 'PASS_SOURCE_PLUS_SEMANTIC_SCREEN'
      or data.get('coverage_scope') != 'selected_legacy_build_dd_identities_only_not_full_daily_shortlist'
      or data.get('approved_build') != 0 or data.get('buy_now') != 0):
   active.append(row); continue
  items = data.get('items')
  matches = [x for x in items if isinstance(x,dict) and x.get('domain') == ident] if isinstance(items,list) else []
  if len(matches) != 1:
   active.append(row); continue
  x = matches[0]
  evidence = daily_evidence.get(day) or {}
  verdict = x.get('semantic_verdict')
  try:
   reviewed = datetime.datetime.fromisoformat(x.get('reviewed_at',''))
   valid_date = reviewed.tzinfo is not None and SEO64_REVIEW_DAY <= reviewed.astimezone(TZ).date().isoformat() <= end
  except (ValueError,TypeError):
   valid_date = False
  expected = {'source_report_sha256':evidence.get('daily'),
              'source_queue_sha256':evidence.get('queue'),
              'source_terminal_sha256':evidence.get('serp'),
              'source_export_sha256':triage.get('source_export_sha256')}
  if (not valid_date or not all(v and x.get(k)==v for k,v in expected.items())
      or x.get('review_scope') != 'historical_build_dd_current_cycle_disposition_only'
      or x.get('terminal_verdict') != 'WATCH' or x.get('product_intent_checked') is not True
      or x.get('approved_build') is not False or x.get('full_positive_business_dd_complete') is not False
      or verdict not in ('DROP_THIS_CYCLE','DEFER_GAP_UNPROVEN')
      or not isinstance(x.get('business_reason'),str) or not x['business_reason'].strip()):
   active.append(row); continue
  item = dict(row, pending=False, cycle_disposition=verdict,
              semantic_cycle_reviewed=True, full_positive_business_dd_complete=False,
              semantic_review_ref={'file':day+'-semantic-business-dd.json','sha256':file_sha,
                  'reviewed_at':x['reviewed_at'],'business_reason':x['business_reason']})
  if verdict == 'DROP_THIS_CYCLE':
   dropped.append(dict(item,resolution='SEO_DROP_THIS_CYCLE'))
  else:
   deferred.append(item)
 return active, dropped, deferred

def audit():
 now=datetime.datetime.now(TZ)
 # Do not count today's future 08:05/09:15/10:00 jobs as missing before audit time.
 end=now.date() if now.hour>=10 else now.date()-datetime.timedelta(days=1)
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
   bydomain={str(i.get('domain') or '').lower():i for i in sem.get('items') or []}
   for item in candidates:
    domain=str(item.get('domain') or '').lower()
    result=bydomain.get(domain) or {}
    if result.get('status')=='PASS':continue
    pending.append({'day':day,'domain':domain,'reason':result.get('reason') or sem.get('global_blocker') or sem.get('status') or 'MISSING','seo_source_sha256':sourcehash(qpath)})
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
 active_dd,resolved_dd=reconcile_dd(dd,backlog)
 active_dd=annotate_preliminary_triage(active_dd,end.isoformat(),S,{x['day']:x['evidence_sha256']['daily'] for x in days})
 screened_dd=[x for x in active_dd if x.get('preliminary_triage')]
 unscreened_dd=[x for x in active_dd if not x.get('preliminary_triage')]
 active_dd,seo_dropped,seo_deferred=reconcile_semantic_cycle(active_dd,end.isoformat(),S,{x['day']:x['evidence_sha256'] for x in days})
 resolved_dd.extend(seo_dropped)
 ddc=Counter(x['category'] for x in active_dd)
 status='PASS' if not pending and not missing_flippa and all(x['acceptance']=='PASS' for x in days) else 'UNRESOLVED_GAPS'
 summary={'scope_start':FIRST.isoformat(),'scope_end':end.isoformat(),'days_checked':len(days),'scanned':totals['discovery_scanned'],'source_days_complete':totals['source_days_complete'],'semrush_serp_pass_days':totals['provider_days_complete'],'flippa_pass_days':totals['flippa_days_complete'],'acceptance_pass_days':totals['acceptance_pass_days'],'semrush_pass_shortlists':sum(x['semrush_pass_count'] for x in days),'unique_unprocessed_domains':len({x['domain'] for x in pending}),'unprocessed_domain_rows':len(pending),'dd_pending_items':len(active_dd),'dd_categories':dict(ddc),'historical_dd_items':len({x['identity'] for x in dd}),'dd_resolved_items':len({x['identity'] for x in resolved_dd}),'dd_resolved_categories':dict(Counter(x['resolution'] for x in {r['identity']:r for r in resolved_dd}.values())),'flippa_missing_days':missing_flippa,'cumulative_flippa_active':backlog.get('active_count'),'cumulative_flippa_closed_historical':backlog.get('closed_historical_count'),'last_verified_flippa_recent':backlog.get('last_scoped_recent_scan'),'full_inventory_observation':backlog.get('last_full_inventory_observation'),'cannot_reconstruct_expired_flippa_recent_windows':bool(missing_flippa)}
 summary.update({'dd_preliminary_screened_items':len(screened_dd),'dd_preliminary_unscreened_items':len(unscreened_dd),'dd_preliminary_groups':dict(Counter(x['preliminary_triage']['group'] for x in screened_dd))})
 summary.update({'dd_cycle_disposed_items':len(seo_dropped)+len(seo_deferred),'dd_cycle_drop_items':len(seo_dropped),'dd_deferred_items':len(seo_deferred)})
 ledger={'schema':'acquisition-gap-ledger-v1','generated_at':datetime.datetime.now(TZ).isoformat(),'status':status,'summary':summary,'daily':days,'pending_semrush':pending,'historical_dd_candidates':dd,'pending_dd_candidates':active_dd,'deferred_dd_candidates':seo_deferred,'semantic_cycle_dispositions':seo_dropped+seo_deferred,'preliminary_screened_dd_candidates':screened_dd,'preliminary_unscreened_dd_candidates':unscreened_dd,'resolved_dd_history':resolved_dd,'limits':{'source_traffic_not_new_site_forecast':True,'seller_metrics_not_audited':True,'historical_listings_not_guaranteed_live':True,'unobserved_inventory_not_proven_empty':True,'no_social_check':True,'no_purchase_or_build_authorized':True}}
 output=O/('gap-ledger-'+end.isoformat()+'.json')
 temp=output.with_suffix('.json.tmp');temp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n');temp.replace(output)
 lines=['# Acquisition Radar — retrospective gap audit '+FIRST.isoformat()+' to '+end.isoformat(),'',
 'STATUS: '+status,'Audit generated: '+ledger['generated_at'],'',
 '## Totals',
 '- Discovery '+str(summary['scanned'])+' domains across '+str(summary['source_days_complete'])+'/'+str(summary['days_checked'])+' complete daily source snapshots.',
 '- Semrush/SERP finished: '+str(summary['semrush_pass_shortlists'])+' shortlisted domains; pending: '+str(summary['unique_unprocessed_domains'])+' distinct domains.',
 '- Flippa daily feed: '+str(summary['flippa_pass_days'])+'/'+str(summary['days_checked'])+' complete; missing capture days '+', '.join(missing_flippa)+'.',
 '- Distinct active DD hypotheses awaiting review (not BUY/BUILD approvals): '+str(summary['dd_pending_items'])+' ('+str(summary['dd_categories'])+').',
 '- Existing cumulative Flippa backlog '+str(summary['cumulative_flippa_active'])+' tracked + '+str(summary['cumulative_flippa_closed_historical'])+' historical closed; last recent feed '+str(summary['last_verified_flippa_recent'])+'.',
 '- Daily independent acceptance '+str(summary['acceptance_pass_days'])+'/'+str(summary['days_checked'])+' PASS; sync status recorded separately for every day.','',
 '- Historical DD identities: '+str(summary['historical_dd_items'])+'; already resolved: '+str(summary['dd_resolved_items'])+' (history retained).',
 '- Preliminary screens: '+str(len(screened_dd))+' complete; '+str(len(unscreened_dd))+' not screened. Preliminary screening alone is not semantic completion.',
 '- SeoTrends current-cycle dispositions: '+str(len(seo_dropped))+' DROP; '+str(len(seo_deferred))+' DEFER (separate from active review). No positive business DD or approval inferred.',
 '## Daily evidence matrix','',
 '| Date | Discovery | Semrush pass | Exact SERP | Flippa | Acceptance |',
 '|---|---:|---|---|---|---|']
 for x in days:
  lines.append('| '+x['day']+' | '+str(x['scanned'])+'/'+str(x['source_count'])+' | '+str(x['semrush'])+' '+str(x['semrush_pass_count'])+'/'+str(x['shortlist'])+' | '+x['serp']+' | '+('PASS' if x['flippa_daily_complete'] else 'MISSING')+' | '+x['acceptance']+' |')
 lines += ['', '## Pending BUILD/BUY DD hypotheses (NOT APPROVED)','',
 '| Date | Candidate | Lane | Organic US modeled / month | Preliminary screen |','|---|---|---|---:|---|']
 for x in active_dd:
  lines.append('| '+x['day']+' | '+str(x['identity'])+' | '+str(x['category'])+' | '+str(x.get('modelled_us_organic_month') or 'N/A')+' | '+str((x.get('preliminary_triage') or {}).get('group','UNSCREENED'))+' |')
 lines += ['', '## Deferred SeoTrends hypotheses (revisit only with new evidence)','',
 '| Date | Candidate | Reason |','|---|---|---|']
 for x in seo_deferred:
  lines.append('| '+x['day']+' | '+x['identity']+' | '+x['semantic_review_ref']['business_reason'].replace('|','/')+' |')
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
