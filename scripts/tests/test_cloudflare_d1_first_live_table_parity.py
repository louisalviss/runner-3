"""Synthetic only: no Cloudflare calls, row exports, credentials, or D1 mutation."""
import copy
import importlib.util
import pathlib
import unittest

SCRIPT=pathlib.Path(__file__).resolve().parents[1]/"cloudflare_d1_first_live_table_parity.py"
spec=importlib.util.spec_from_file_location("d1pilot",SCRIPT)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
T1="fake_source_token_123456789"
T2="fake_target_token_123456789"

def schema():
    return [{"cid":i,"name":name,"type":"TEXT" if i==0 else "",
             "notnull":0,"dflt_value":None,"pk":1 if i==0 else 0,"hidden":0}
            for i,name in enumerate(m.COLUMNS)]

def row(identity="render-1",metadata="{}"):
    return dict(zip(m.COLUMNS,(identity,"rss",3,2,0.25,"v1",
               "2026-10-22 00:00:00",metadata)))

def fake_api(src=None,dst=None,srcmeta=None,dstmeta=None):
    source=[row()] if src is None else src
    target=copy.deepcopy(source) if dst is None else dst
    def fetch(token,account,uuid,sql):
        assert (account,uuid) in ((m.SRC_ACCOUNT,m.SRC_UUID),
                                   (m.DST_ACCOUNT,m.DST_UUID))
        if sql==m.META_SQL:
            return copy.deepcopy(srcmeta if account==m.SRC_ACCOUNT and srcmeta is not None else
                                 dstmeta if account==m.DST_ACCOUNT and dstmeta is not None else schema())
        assert sql==m.ROWS_SQL
        return copy.deepcopy(source if account==m.SRC_ACCOUNT else target)
    return fetch

class LivePilotContract(unittest.TestCase):
    def test_equal_is_not_cutover(self):
        r=m.probe(T1,T2,fake_api())
        self.assertEqual(r["status"],"ONE_TABLE_SNAPSHOT_EQUAL_NOT_CUTOVER_PROOF")
        self.assertEqual(r["matching_key_payload_pairs"],1)
        self.assertFalse(r["cutover_ready"])
        self.assertFalse(r["row_parity_verified_all_d1"])
    def test_changed_payload(self):
        r=m.probe(T1,T2,fake_api(dst=[row(metadata='{"changed":true}')]))
        self.assertEqual(r["changed_payloads"],1)
        self.assertEqual(r["status"],"ROW_DIFFERENCES_HOLD")
    def test_target_only_not_proven_deleted(self):
        r=m.probe(T1,T2,fake_api(src=[],dst=[row()]))
        self.assertEqual(r["target_only_keys_unresolved"],1)
        self.assertFalse(r["source_delete_proven"])
    def test_source_only(self):
        r=m.probe(T1,T2,fake_api(src=[row()],dst=[]))
        self.assertEqual(r["source_only_keys"],1)
    def test_report_hides_rows(self):
        s=str(m.probe(T1,T2,fake_api()))
        self.assertNotIn("render-1",s)
        self.assertNotIn("2026-10-22 00:00:00",s)
        self.assertNotIn("key_hmac",s)
    def test_schema_columns_drift_blocks(self):
        t=schema()
        t[1]["name"]="wrong"
        with self.assertRaisesRegex(m.Blocked,"SCHEMA_COLUMNS_DRIFT"):
            m.probe(T1,T2,fake_api(dstmeta=t))
    def test_schema_types_differ_blocks(self):
        t=schema();t[1]["type"]="INT"
        with self.assertRaisesRegex(m.Blocked,"SCHEMA_METADATA_DIFFERENT"):
            m.probe(T1,T2,fake_api(dstmeta=t))
    def test_primary_key_drift_blocks(self):
        t=schema();t[0]["pk"]=0
        with self.assertRaisesRegex(m.Blocked,"SCHEMA_PRIMARY_KEY_DRIFT"):
            m.probe(T1,T2,fake_api(srcmeta=t))
    def test_over_cap_blocks(self):
        with self.assertRaisesRegex(m.Blocked,"ROW_CAP_EXCEEDED"):
            m.probe(T1,T2,fake_api(src=[row(str(i)) for i in range(251)]))
    def test_duplicate_pk_blocks(self):
        with self.assertRaisesRegex(m.Blocked,"DUPLICATE_PRIMARY_KEY"):
            m.probe(T1,T2,fake_api(src=[row(),row()]))
    def test_integer_real_distinguished(self):
        self.assertNotEqual(m.typed(1),m.typed(1.0))
    def test_null_and_empty_distinguished(self):
        self.assertNotEqual(m.typed(None),m.typed(""))
    def test_blob_rejected(self):
        with self.assertRaisesRegex(m.Blocked,"UNSUPPORTED_BLOB"):
            m.typed(b"raw")
    def test_missing_token_blocks(self):
        with self.assertRaisesRegex(m.Blocked,"ACCOUNT_TOKENS"):
            m.probe("",T2,fake_api())
    def test_same_token_blocks(self):
        with self.assertRaisesRegex(m.Blocked,"ACCOUNT_TOKENS"):
            m.probe(T1,T1,fake_api())
    def test_source_changes_between_reads(self):
        reads=[0]
        def fetch(token,account,uuid,sql):
            if sql==m.META_SQL:return schema()
            if account==m.SRC_ACCOUNT:
                reads[0]+=1
                return [row(metadata="v"+str(reads[0]))]
            return [row()]
        self.assertEqual(m.probe(T1,T2,fetch)["status"],"UNSTABLE_WRITERS_HOLD")
    def test_target_changes_between_reads(self):
        reads=[0]
        def fetch(token,account,uuid,sql):
            if sql==m.META_SQL:return schema()
            if account==m.DST_ACCOUNT:
                reads[0]+=1
                return [row(metadata="v"+str(reads[0]))]
            return [row()]
        self.assertEqual(m.probe(T1,T2,fetch)["status"],"UNSTABLE_WRITERS_HOLD")
    def test_sql_allowlist_blocks_delete(self):
        with self.assertRaisesRegex(m.Blocked,"ROUTE_OR_SQL"):
            m.request_json(T1,m.SRC_ACCOUNT,m.SRC_UUID,"DELETE FROM recommendation_runs")
    def test_summary_only_counts(self):
        r=m.probe(T1,T2,fake_api(src=[row("a"),row("b")],dst=[row("a")]))
        self.assertEqual(r["source_rows_observed"],2)
        self.assertEqual(r["d1_writes"],0)
    def test_nested_json_row_value_rejected(self):
        item=row();item["metadata_json"]={"secret":"do not emit"}
        with self.assertRaisesRegex(m.Blocked,"UNSUPPORTED_BLOB"):
            m.probe(T1,T2,fake_api(src=[item]))

if __name__=="__main__":
    unittest.main()
