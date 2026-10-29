#!/usr/bin/env python3
"""Purely synthetic profile gates; no external Cloudflare calls."""
import copy
import unittest
import cloudflare_d1_derived_profile_reconcile_gate as g

SOURCE = (
  "export function profileProjectionCte() { FROM user_content_events "
  "JOIN normalized_features FROM content_features f }\n"
  "export async function recomputeInterestProfile(env) {\n"
  "INSERT INTO interest_profile( DELETE FROM interest_profile "
  "INSERT INTO interest_family_profile( DELETE FROM interest_family_profile }"
)
COLS=("weight","evidence_count","positive_count",
      "negative_count","confidence","updated_at")

def profile(s,t,shared,matched,changed,sourceonly,targetonly):
  assert s==shared+sourceonly and t==shared+targetonly
  return {
    "source_rows_observed":s,"target_rows_observed":t,
    "common_keys_compared":shared,
    "matching_key_payload_pairs":matched,"changed_payloads":changed,
    "source_only_keys":sourceonly,"target_only_keys":targetonly,
    "schema_equal":True,"snapshot_stable_during_probe":True,
    "bounded_complete_table":True,
    "common_pk_column_difference_counts":{
      name:(changed if name in ("weight","updated_at") else 0)
      for name in COLS
    },
  }

def audit():
  return {
    "status":"TWO_BOUNDED_TABLES_READ_ONLY_NOT_ACCOUNTWIDE_PARITY",
    "sensitive_keys_and_values_exported":False,
    "fingerprints_exported":False,
    "atomic_snapshot":False,
    "accountwide_row_parity_verified":False,
    "deletion_parity_verified":False,
    "d1_writes":0,
    "cutover_ready":False,
    "databases":{"runner3-content-intelligence":{
      "interest_family_profile":profile(13,13,13,1,12,0,0),
      "interest_profile":profile(28,26,25,4,21,3,1),
    }},
  }

class TestProfileGate(unittest.TestCase):
  def test_plan_is_hard_hold_not_write(self):
    out=g.assess(audit(),SOURCE)
    self.assertFalse(out["cutover_ready"])
    self.assertFalse(out["upstream_row_parity_verified"])
    self.assertFalse(out["writer_quiescence_verified"])
    self.assertFalse(out["recovery_bookmark_installed"])
    self.assertEqual(out["d1_writes"],0)
    self.assertEqual(out["production_target_changes"],0)
    self.assertEqual(
      out["profile_tables"]["interest_profile"]["target_only_preserve_for_review"],1)
    self.assertEqual(
      out["profile_tables"]["interest_profile"]["payload_conflicts"],21)
    self.assertTrue(all(not info["direct_copy_authorized"]
                        for info in out["profile_tables"].values()))
    self.assertNotIn("feature_key",str(out))
    self.assertNotIn("session",str(out))

  def test_equal_profile_is_still_not_migration_pass(self):
    value=audit()
    for table in value["databases"]["runner3-content-intelligence"]:
      n=2
      value["databases"]["runner3-content-intelligence"][table]=profile(
        n,n,n,n,0,0,0)
    out=g.assess(value,SOURCE)
    self.assertFalse(out["cutover_ready"])
    self.assertFalse(out["profile_tables"]["interest_profile"]["recompute_authorized"])

  def test_inconsistent_pk_accounting_rejected(self):
    obj=audit()
    obj["databases"]["runner3-content-intelligence"]["interest_profile"]["target_rows_observed"]=27
    with self.assertRaisesRegex(g.Hold,"PK_CENSUS"):
      g.assess(obj,SOURCE)

  def test_untrusted_artifact_rejected(self):
    for key,value in (("d1_writes",1),("atomic_snapshot",True),
                      ("accountwide_row_parity_verified",True),
                      ("sensitive_keys_and_values_exported",True)):
      obj=audit()
      obj[key]=value
      with self.subTest(key=key),self.assertRaises(g.Hold):
        g.assess(obj,SOURCE)

  def test_missing_or_unreliable_source_rejected(self):
    with self.assertRaises(g.Hold):
      g.assess(audit(),"not from profile code")
    with self.assertRaises(g.Hold):
      g.assess(audit(),SOURCE.replace("DELETE FROM interest_profile",""))

  def test_bad_schema_or_capture_rejected(self):
    for prop in ("schema_equal","snapshot_stable_during_probe",
                 "bounded_complete_table"):
      obj=audit()
      obj["databases"]["runner3-content-intelligence"]["interest_profile"][prop]=False
      with self.subTest(prop=prop),self.assertRaises(g.Hold):
        g.assess(obj,SOURCE)

  def test_column_delta_out_of_bounds_rejected(self):
    obj=audit()
    obj["databases"]["runner3-content-intelligence"]["interest_family_profile"][
       "common_pk_column_difference_counts"]["weight"]=101
    with self.assertRaises(g.Hold):
      g.assess(obj,SOURCE)

  def test_no_secret_or_raw_rows_in_plan(self):
    result=g.assess(audit(),SOURCE)
    self.assertNotIn("raw",str(result))
    self.assertNotIn("SECRET",str(result))
    self.assertEqual(set(result["profile_tables"]),set(g.EXPECTED))

if __name__=="__main__":
  unittest.main()
