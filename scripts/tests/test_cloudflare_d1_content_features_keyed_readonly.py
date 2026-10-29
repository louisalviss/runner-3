"""Synthetic-only regression tests for bounded keyed content_features D1 audit."""
import copy
import unittest
from unittest.mock import patch
import cloudflare_d1_content_features_keyed_readonly as m

SRC_TOKEN="readonly-source-token-123456"
TGT_TOKEN="readonly-target-token-123456"
def feature(item,typ="concept",key="one",val="alpha",weight=1):
    return dict(item_id=item,feature_type=typ,feature_key=key,
                feature_value=val,weight=weight,confidence=0.9,
                model_version="v1",updated_at="now")

SOURCE_ROWS=[feature("a"),feature("a",key="two"),feature("b"),feature("c")]
TARGET_ROWS=[feature("a"),feature("b",weight=2),feature("d")]

def reader(token,account,db,cursor):
    rows=SOURCE_ROWS if account==m.SOURCE else TARGET_ROWS
    result=[copy.deepcopy(r) for r in rows
            if tuple(r[k] for k in m.KEY)>cursor][:m.PAGE]
    return result,len(result)

def receipt(source=4,target=3,capped=True):
    return dict(database="runner3-content-intelligence",
                production_writes=0,cutover_ready=False,
                tables={"content_features":dict(
                    schema_columns_and_pk_equal=True,
                    source_lower_bound=(0 if capped else source),
                    target_lower_bound=target,
                    source_count=(None if capped else source),
                    target_count=target,source_at_cap=capped,target_at_cap=False)})

class TestContentFeaturesKeyed(unittest.TestCase):
    def test_composite_key_and_conflict_are_distinct(self):
        result=m.audit(SRC_TOKEN,TGT_TOKEN,receipt(),reader)
        keys=("source_rows","target_rows","common_keys",
              "common_payload_matches","common_payload_conflicts",
              "source_only_keys","target_only_keys_preserve")
        self.assertEqual([result[k] for k in keys],[4,3,2,1,1,2,1])
        self.assertEqual(result["payload_difference_column_counts"]["weight"],1)
        self.assertEqual(result["d1_writes"],0)
        self.assertFalse(result["cutover_ready"])
        self.assertNotIn("alpha",str(result))
        self.assertNotIn("readonly-source-token",str(result))
    def test_payload_change_does_not_change_key(self):
        secret=b"k"*32
        _,key1,payload1=m.fingerprint(feature("a"),secret)
        _,key2,payload2=m.fingerprint(feature("a",weight=3),secret)
        self.assertEqual(key1,key2)
        self.assertNotEqual(payload1[0],payload2[0])
    def test_unordered_or_repeated_pk_fails(self):
        def unordered(token,account,db,cursor):
            return [feature("b"),feature("a")],2
        with self.assertRaisesRegex(m.Hold,"NONMONOTONIC_COMPOSITE_PK"):
            m.capture(SRC_TOKEN,m.SOURCE,m.SOURCE_D1,b"k"*32,unordered)
    def test_change_between_passes_fails(self):
        counter=[0]
        def changing(token,account,db,cursor):
            rows,cost=reader(token,account,db,cursor)
            if account==m.SOURCE:
                counter[0]+=1
                if counter[0]>1: rows[0]["feature_value"]="changed"
            return rows,cost
        with self.assertRaisesRegex(m.Hold,"FEATURE_SNAPSHOTS_UNSTABLE"):
            m.audit(SRC_TOKEN,TGT_TOKEN,receipt(),changing)
    def test_source_drift_diagnostic_only_aggregate_counts(self):
        calls={m.SOURCE:0,m.TARGET:0}
        def changing(token,account,db,cursor):
            rows,cost=reader(token,account,db,cursor)
            calls[account]+=1
            if account==m.SOURCE and calls[account]==2:
                rows.append(feature("z",val="secret-data"))
            return rows,len(rows)
        with self.assertRaises(m.Hold) as ctx:
            m.audit(SRC_TOKEN,TGT_TOKEN,receipt(),changing)
        reason=str(ctx.exception)
        self.assertIn("FEATURE_SNAPSHOTS_UNSTABLE",reason)
        self.assertIn("source_keys_added=1",reason)
        self.assertIn("source_keys_removed=0",reason)
        self.assertIn("source_shared_payload_changed=0",reason)
        self.assertIn("target_keys_added=0",reason)
        self.assertNotIn("secret-data",reason)
        self.assertNotIn(SRC_TOKEN,reason)
        self.assertEqual(calls[m.SOURCE],2)
        self.assertEqual(calls[m.TARGET],2)

    def test_target_payload_drift_distinguished_from_key_drift(self):
        calls={m.SOURCE:0,m.TARGET:0}
        def changing(token,account,db,cursor):
            rows,cost=reader(token,account,db,cursor)
            calls[account]+=1
            if account==m.TARGET and calls[account]==2:
                rows[0]["feature_value"]="private-modified-payload"
            return rows,cost
        with self.assertRaises(m.Hold) as ctx:
            m.audit(SRC_TOKEN,TGT_TOKEN,receipt(),changing)
        reason=str(ctx.exception)
        self.assertIn("source_keys_added=0",reason)
        self.assertIn("target_keys_added=0",reason)
        self.assertIn("target_keys_removed=0",reason)
        self.assertIn("target_shared_payload_changed=1",reason)
        self.assertNotIn("private-modified-payload",reason)

    def test_stable_snapshots_have_no_drift_output(self):
        self.assertIsNone(m.require_stable_snapshots({}, {}, {}, {}))
        self.assertEqual(m.drift_summary({}, {}),{
            "keys_added":0,"keys_removed":0,"shared_payload_changed":0
        })

    def test_count_receipt_must_still_match(self):
        with self.assertRaisesRegex(m.Hold,"BOUNDED_COUNT_RECEIPT_CHANGED"):
            m.audit(SRC_TOKEN,TGT_TOKEN,receipt(target=100),reader)
        with self.assertRaisesRegex(m.Hold,"BOUNDED_COUNT_RECEIPT_CHANGED"):
            m.audit(SRC_TOKEN,TGT_TOKEN,receipt(source=5,capped=False),reader)
    def test_distinct_scoped_tokens_required(self):
        with self.assertRaisesRegex(m.Hold,"SEPARATE_AUDIT_CREDENTIALS"):
            m.audit(SRC_TOKEN,SRC_TOKEN,receipt(),reader)
        with self.assertRaisesRegex(m.Hold,"INVALID_CREDENTIAL_OR_CURSOR"):
            m.read(SRC_TOKEN,m.TARGET,m.SOURCE_D1,("","",""))
    def test_excess_per_page_read_fails(self):
        def highcost(token,account,db,cursor):
            return [feature("a")],m.PAGE_READ_CAP+1
        with self.assertRaisesRegex(m.Hold,"PAGE_RESPONSE_OR_READ_METRIC_INVALID"):
            m.capture(SRC_TOKEN,m.SOURCE,m.SOURCE_D1,b"k"*32,highcost)
    def test_account_total_read_cap_across_passes(self):
        def costly(token,account,db,cursor):
            return reader(token,account,db,cursor)[0],m.PAGE_READ_CAP
        with patch.object(m,"TOTAL_READ_CAP",1500):
            with self.assertRaisesRegex(m.Hold,"ACCOUNT_READ_BUDGET_EXCEEDED"):
                m.audit(SRC_TOKEN,TGT_TOKEN,receipt(),costly)
    def test_unsupported_or_empty_key_fails(self):
        with self.assertRaises(m.Hold):m.typed({})
        with self.assertRaises(m.Hold):m.typed(float("nan"))
        with self.assertRaises(m.Hold):
            m.fingerprint(dict(feature("a"),item_id=""),b"k"*32)
    def test_exact_static_sql_and_finite_cap(self):
        self.assertIn('("item_id","feature_type","feature_key") > (?,?,?)',m.SQL)
        self.assertIn("LIMIT 250",m.SQL)
        self.assertEqual(len(m.KEY),3)
        self.assertLessEqual(m.MAX_PAGES*m.PAGE,m.CAP+m.PAGE)
        self.assertLessEqual(m.TOTAL_READ_CAP,75000)

if __name__=="__main__":unittest.main()
