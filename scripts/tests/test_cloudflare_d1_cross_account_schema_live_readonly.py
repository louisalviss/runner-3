#!/usr/bin/env python3
"""Synthetic source/target D1 schema comparison, never live API calls."""
import unittest
from unittest.mock import patch
import cloudflare_d1_cross_account_schema_live_readonly as m

S="01234567-89ab-cdef-0123-456789abcdef"
T="fedcba98-7654-3210-fedc-ba9876543210"
TABLE={"type":"table","name":"run","sql":"CREATE TABLE run (id TEXT PRIMARY KEY)"}
TABLE2={"type":"table","name":"run","sql":"CREATE TABLE run (id TEXT PRIMARY KEY, note TEXT)"}

def fake(token,account,database):
    if database is None:
        dbs=({"runner3-core":S,"runner3-rss":S}
              if account==m.SOURCE else
              {"runner3-core":T,"runner3-rss":T,"louis-context-index":T})
        return {"success":True,"result":[{"name":k,"uuid":v} for k,v in dbs.items()],
                "result_info":{"page":1,"count":len(dbs),"total_count":len(dbs)}}
    row=(TABLE2 if account==m.TARGET and database==T else TABLE)
    return {"success":True,"result":[{"success":True,"results":[row],
                                      "meta":{"rows_written":0,"changed_db":False}}]}

class TestSchema(unittest.TestCase):
    def test_reports_only_aggregates_and_holds_cutover(self):
        r=m.compare("source-token-123456789","target-token-123456789",fake)
        self.assertEqual(r["shared_databases_compared"],2)
        self.assertFalse(r["all_shared_schema_exact_equal"])
        self.assertEqual(sum(x["common_object_definition_differences"] for x in r["per_database"]),2)
        self.assertEqual(r["target_only_database_names"],["louis-context-index"])
        self.assertEqual(r["d1_writes"],0)
        self.assertEqual(r["r2_requests"],0)
        self.assertFalse(r["cutover_ready"])
        self.assertNotIn("CREATE TABLE",str(r))

    def test_identical_tokens_rejected(self):
        with self.assertRaises(m.Hold):
            m.compare("same","same",fake)

    def test_extra_db_rejected(self):
        def extra(token,account,db):
            out=fake(token,account,db)
            if db is None:
                out["result"].append({"name":"unknown-new-db","uuid":S})
                out["result_info"]["count"]+=1
                out["result_info"]["total_count"]+=1
            return out
        with self.assertRaises(m.Hold):
            m.compare("source","target",extra)

    def test_incomplete_pagination_rejected(self):
        def page(token,account,db):
            out=fake(token,account,db)
            if db is None: out["result_info"]["total_count"]+=1
            return out
        with self.assertRaises(m.Hold):
            m.compare("source","target",page)

    def test_write_metadata_rejected(self):
        def write(token,account,db):
            out=fake(token,account,db)
            if db is not None:out["result"][0]["meta"]["rows_written"]=1
            return out
        with self.assertRaises(m.Hold):
            m.compare("source","target",write)

    def test_source_only_and_target_only_diff(self):
        def distinct(token,account,db):
            o=fake(token,account,db)
            if db is not None:
                if account==m.SOURCE:
                    o["result"][0]["results"].append({"type":"table","name":"source_extra","sql":"CREATE TABLE source_extra (id INT)"})
                else:
                    o["result"][0]["results"].append({"type":"table","name":"target_extra","sql":"CREATE TABLE target_extra (id INT)"})
            return o
        r=m.compare("source","target",distinct)
        self.assertEqual(r["per_database"][0]["source_only_objects"],1)
        self.assertEqual(r["per_database"][0]["target_only_objects"],1)
        for row in r["per_database"]:
            self.assertEqual(row["source_only_types"]["table"],1)
            self.assertEqual(row["target_only_types"]["table"],1)
            self.assertEqual(row["source_only_table_names"],["source_extra"])
            self.assertEqual(row["target_only_table_names"],["target_extra"])
            self.assertEqual(row["source_only_types"]["index"],0)
            self.assertEqual(row["target_only_types"]["trigger"],0)
        self.assertNotIn("CREATE TABLE",str(r))

    def test_nonstandard_table_name_is_not_disclosed(self):
        def irregular(token,account,db):
            o=fake(token,account,db)
            if db is not None and account==m.SOURCE:
                o["result"][0]["results"].append({
                    "type":"table","name":"weird-table",
                    "sql":'CREATE TABLE "weird-table" (id INT)'})
            return o
        r=m.compare("source","target",irregular)
        for row in r["per_database"]:
            self.assertEqual(row["source_only_types"]["table"],1)
            self.assertEqual(row["source_only_table_names"],[])
            self.assertEqual(row["nonstandard_source_only_table_name_count"],1)
            self.assertNotIn("weird-table",str(row))

    def test_schema_query_restricted(self):
        self.assertTrue(m.SCHEMA_SQL.startswith("SELECT type,name,sql FROM sqlite_master"))
        self.assertNotIn("recommendation_runs",m.SCHEMA_SQL)
        self.assertFalse(m.api.__code__.co_consts.count("DELETE"))

if __name__=="__main__": unittest.main()
