import json,pathlib,subprocess,tempfile,unittest
sh=pathlib.Path('/usr/local/sbin/seotrends-github-fallback').read_text()
mark='SOURCE_ALREADY_COMPLETE=$(python3 - "$BASE/scans/$DAY-semrush-queue.json" "$DAY" <<\'PY\'\n'
assert mark in sh
snippet=sh.split(mark,1)[1].split('\nPY\n)',1)[0]
class GuardTests(unittest.TestCase):
 def check(self,queue,day):
  with tempfile.TemporaryDirectory() as td:
   f=pathlib.Path(td)/'queue.json';f.write_text(json.dumps(queue))
   r=subprocess.run(['python3','-',str(f),day],input=snippet,text=True,capture_output=True)
   self.assertEqual(r.returncode,0,r.stderr)
   return r.stdout.strip()
 def valid(self):
  return {'date':'2026-10-14','scan_terminal':True,'added_total':217,'scanned':217,'count':14,'items':[{'domain':str(i)+'.example'} for i in range(14)]}
 def test_complete_original_protected(self):self.assertEqual(self.check(self.valid(),'2026-10-14'),'yes')
 def test_replay_zero_does_not_count_as_completed_discovery(self):
  v=self.valid();v.update(added_total=0,scanned=0,count=0,items=[])
  self.assertEqual(self.check(v,'2026-10-14'),'no')
 def test_incomplete_source_can_resume(self):
  v=self.valid();v['scanned']=200
  self.assertEqual(self.check(v,'2026-10-14'),'no')
 def test_stale_date_not_mistaken(self):
  self.assertEqual(self.check(self.valid(),'2026-10-15'),'no')
 def test_truncated_queue_does_not_pass(self):
  v=self.valid();v['count']=15
  self.assertEqual(self.check(v,'2026-10-14'),'no')
if __name__=='__main__':unittest.main(verbosity=2)
