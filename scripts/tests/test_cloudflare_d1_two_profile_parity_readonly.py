#!/usr/bin/env python3
"""Synthetic tests only; no Cloudflare requests or personally identifying rows."""
import unittest
import cloudflare_d1_two_profile_parity_readonly as m

SRC="dummy-source-reader-credential-123"
DST="dummy-target-reader-credential-456"

def meta(table):
 cols,pk=m.TABLES[table]
 return [{"cid":i,"name":name,
          "type":"TEXT" if name.endswith("key") or name in ("feature_type","updated_at") else "REAL",
          "pk":pk.index(name)+1 if name in pk else 0,
          "notnull":1,"dflt_value":None,"hidden":0}
         for i,name in enumerate(cols)]

def sample(table):
 cols,_=m.TABLES[table]
 row={name:(
     "one" if name.endswith("key") or name=="feature_type" else
     "2026-10-29T00:00Z" if name=="updated_at" else
     1 if name.endswith("count") else 0.5)
     for name in cols}
 return [row]

def reader(token,account,uid,sql):
 assert (token,account,uid) in (
    (SRC,m.SOURCE,m.SOURCE_D1),(DST,m.TARGET,m.TARGET_D1))
 for table in m.TABLES:
  if sql==m.META_SQL[table]:return meta(table)
  if sql==m.DATA_SQL[table]:return sample(table)
 raise AssertionError("Nonallowlisted query")

class TestTwoProfiles(unittest.TestCase):
 def test_two_bounded_tables_equal(self):
  out=m.compare(SRC,DST,reader)
  self.assertEqual(set(out["databases"]["runner3-content-intelligence"]),set(m.TABLES))
  for data in out["databases"]["runner3-content-intelligence"].values():
   self.assertEqual(data["source_rows_observed"],1)
   self.assertEqual(data["target_rows_observed"],1)
   self.assertEqual(data["matching_key_payload_pairs"],1)
   self.assertEqual(data["source_only_keys"],0)
   self.assertEqual(data["changed_payloads"],0)
   self.assertTrue(all(count==0 for count in
                       data["common_pk_column_difference_counts"].values()))
   self.assertEqual(data["status"],"EQUAL_SNAPSHOT_NOT_CUTOVER")
  self.assertFalse(out["accountwide_row_parity_verified"])
  self.assertFalse(out["cutover_ready"])
  self.assertFalse(out["sensitive_keys_and_values_exported"])
  self.assertNotIn("dummy-source",str(out))
  self.assertNotIn("one",str(out))

 def test_payload_mismatch_is_reported_not_exported(self):
  def different(t,a,u,sql):
   rows=reader(t,a,u,sql)
   if t==DST and sql in m.DATA_SQL.values():
    rows[0]["weight"]=0.8
   return rows
  out=m.compare(SRC,DST,different)
  for data in out["databases"]["runner3-content-intelligence"].values():
   self.assertEqual(data["changed_payloads"],1)
   self.assertEqual(data["common_pk_column_difference_counts"]["weight"],1)
   self.assertEqual(sum(data["common_pk_column_difference_counts"].values()),1)
   self.assertEqual(data["status"],"DIFFERENT_SNAPSHOT_HOLD")
  self.assertNotIn("0.8",str(out))

 def test_only_timestamp_delta_is_attributed_without_value(self):
  def different(t,a,u,sql):
   rows=reader(t,a,u,sql)
   if t==DST and sql in m.DATA_SQL.values():
    rows[0]["updated_at"]="2026-10-29T02:30Z"
   return rows
  out=m.compare(SRC,DST,different)
  for data in out["databases"]["runner3-content-intelligence"].values():
   self.assertEqual(data["changed_payloads"],1)
   self.assertEqual(data["common_pk_column_difference_counts"]["updated_at"],1)
   self.assertEqual(data["common_pk_column_difference_counts"]["weight"],0)
  self.assertNotIn("02:30",str(out))

 def test_target_only_source_only(self):
  def other_key(t,a,u,sql):
   rows=reader(t,a,u,sql)
   if t==DST and sql in m.DATA_SQL.values():
    cols,_=m.TABLES[next(k for k,v in m.DATA_SQL.items() if v==sql)]
    first=cols[0]
    rows[0][first]="other"
   return rows
  out=m.compare(SRC,DST,other_key)
  for data in out["databases"]["runner3-content-intelligence"].values():
   self.assertEqual(data["source_only_keys"],1)
   self.assertEqual(data["target_only_keys"],1)

 def test_schema_change_holds(self):
  def altered(t,a,u,sql):
   rows=reader(t,a,u,sql)
   if t==DST and sql in m.META_SQL.values():rows[0]["dflt_value"]="DIFFERENT"
   return rows
  with self.assertRaises(m.Hold):
   m.compare(SRC,DST,altered)

 def test_detects_unstable_snapshots(self):
  seen={}
  def altered(t,a,u,sql):
   rows=reader(t,a,u,sql)
   if t==SRC and sql in m.DATA_SQL.values():
    k=(t,sql)
    seen[k]=seen.get(k,0)+1
    if seen[k]>1:rows[0]["weight"]=0.9
   return rows
  with self.assertRaisesRegex(m.Hold,"SNAPSHOT_UNSTABLE"):
   m.compare(SRC,DST,altered)

 def test_row_limit_and_duplicate_pk(self):
  key=b"x"*32
  for table in m.TABLES:
   with self.assertRaisesRegex(m.Hold,"ROW_CAP_EXCEEDED"):
    m.fingerprint(sample(table)*101,table,key)
   with self.assertRaisesRegex(m.Hold,"DUPLICATE_PK"):
    m.fingerprint(sample(table)*2,table,key)

 def test_malformed_and_unexpected_value(self):
  with self.assertRaises(m.Hold):m.typed({"secret":"bad"})
  with self.assertRaises(m.Hold):m.typed(float("nan"))
  with self.assertRaises(m.Hold):
   m.fingerprint([{"row":"unexpected"}],"interest_profile",b"x"*32)

 def test_wrong_scope_rejected(self):
  with self.assertRaises(m.Hold):
   m.compare(SRC,SRC,reader)
  with self.assertRaises(m.Hold):
   m.remote(SRC,m.TARGET,m.SOURCE_D1,m.DATA_SQL["interest_profile"])
  with self.assertRaises(m.Hold):
   m.remote(SRC,m.SOURCE,m.SOURCE_D1,"DROP TABLE interest_profile")

if __name__=="__main__":
 unittest.main()
