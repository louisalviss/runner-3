import json, pathlib, subprocess, tempfile, unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'jobs'/'semrush-research'

class DiscoveryStageTests(unittest.TestCase):
    def runpy(self,name,*args):
        return subprocess.run(['python3',str(SCRIPTS/name),*map(str,args)],capture_output=True,text=True,check=True)

    def test_stage_antirepeat_and_finalize_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); cfg=root/'cfg'; cfg.mkdir()
            (cfg/'old.json').write_text(json.dumps({'themes':[{'theme_id':'old-pump','label':'Old Pump','seeds':['old pump calculator']}]}))
            universe={'projects':{'root':{'seeds':{'calculator':{'ideas':[
              {'phrase':'widget pressure calculator','volume':900,'difficulty':10,'cpc':1.0},
              {'phrase':'widget pressure sizing calculator','volume':700,'difficulty':12,'cpc':1.2},
              {'phrase':'old pump calculator','volume':5000,'difficulty':5,'cpc':2.0}
            ]}}}}}
            up=root/'universe.json'; up.write_text(json.dumps(universe))
            reg=root/'tested.json'; reg.write_text(json.dumps({'version':1,'records':[
              {'project':'old','cluster_id':'old-1','label':'legacy widget','serp_gate':'DROP_SERP_SATURATED','top_keywords':['legacy widget calculator']}
            ]}))
            out=root/'out'
            self.runpy('discovery_stage.py','--input',up,'--config-dir',cfg,'--tested-registry',reg,'--output-dir',out)
            q=json.loads((out/'serp-dd-queue.json').read_text())
            self.assertEqual(len(q['queue']),1)
            self.assertEqual(q['queue'][0]['label'],'widget pressure')
            serp={'created_at':'2026-10-07T00:00:00Z','results':[{**q['queue'][0],'serp_gate':'SERP_DD_PASS','avg_exact_tool_top10':3}]}
            sp=root/'serp.json'; sp.write_text(json.dumps(serp)); summary=root/'summary.json'
            j1=json.loads(self.runpy('discovery_finalize.py','--serp-results',sp,'--registry',reg,'--summary',summary).stdout)
            self.assertEqual(j1['registry_added'],1)
            j2=json.loads(self.runpy('discovery_finalize.py','--serp-results',sp,'--registry',reg,'--summary',summary).stdout)
            self.assertEqual(j2['registry_added'],0)

    def test_seed_bank_skips_used_roots(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); cfg=root/'cfg'; cfg.mkdir()
            (cfg/'used.json').write_text(json.dumps({'themes':[{'theme_id':'x','seeds':['rate calculator','fee calculator']}]}))
            out=root/'bank.json'
            self.runpy('modifier_seed_bank.py','--config-dir',cfg,'--output',out,'--count','3')
            bank=json.loads(out.read_text())
            seeds=[s for t in bank['themes'] for s in t['seeds']]
            self.assertNotIn('rate calculator',seeds)
            self.assertNotIn('fee calculator',seeds)
            self.assertEqual(len(seeds),3)

if __name__=='__main__':
    unittest.main()
