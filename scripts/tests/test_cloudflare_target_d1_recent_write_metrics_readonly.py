"""Offline API contract tests for Cloudflare target D1 GraphQL metrics."""
import datetime as dt
import io
import json
import unittest
from unittest.mock import patch
import urllib.error
import cloudflare_target_d1_recent_write_metrics_readonly as m

TODAY=dt.date(2026,10,29)
START=TODAY-dt.timedelta(days=3)

def records(db,magnitude=0):
    return {
        "data":{"viewer":{"accounts":[{
            "d1AnalyticsAdaptiveGroups":[
                {"dimensions":{"date":"2026-10-28","databaseId":db},
                 "sum":{"writeQueries":magnitude}}
            ]
        }]}}
    }

class Response:
    status=200
    def __init__(self,data): self.data=json.dumps(data).encode()
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n): return self.data[:n]

class TestD1Metrics(unittest.TestCase):
    def test_read_no_sql_and_redacted_counts(self):
        captured=[]
        def opener(req,timeout):
            self.assertEqual(req.full_url,m.GRAPHQL)
            self.assertEqual(req.get_method(),"POST")
            body=json.loads(req.data)
            self.assertEqual(body["query"],m.QUERY)
            self.assertEqual(body["variables"]["account"],m.ACCOUNT)
            self.assertEqual(body["variables"]["from"],START.isoformat())
            self.assertEqual(body["variables"]["to"],TODAY.isoformat())
            self.assertTrue("SELECT" not in body["query"])
            captured.append(body["variables"]["db"])
            return Response(records(body["variables"]["db"],3))
        for name in m.D1S:
            result=m.read("fake-readonly-audit-token-123",name,START,TODAY,opener)
            self.assertEqual(result,[{"date_utc":"2026-10-28","write_queries":3}])
        self.assertEqual(len(captured),2)

    def test_missing_permission_holds_and_does_not_leak(self):
        def denied(req,timeout):
            raise urllib.error.HTTPError(req.full_url,403,"forbidden",{},None)
        with self.assertRaisesRegex(m.Hold,"HTTP_403"):
            m.read("fake-readonly-audit-token-123",
                   "runner3-core",START,TODAY,denied)

    def test_unauthorized_graphql_result_holds(self):
        def failed(req,timeout):
            return Response({"errors":[{"message":"do not log token"}]})
        with self.assertRaisesRegex(m.Hold,"GRAPHQL_UNAUTHORIZED"):
            m.read("fake-readonly-audit-token-123",
                   "runner3-core",START,TODAY,failed)

    def test_wrong_target_database_holds(self):
        def wrong(req,timeout):
            return Response(records("00000000-0000-0000-0000-000000000000",1))
        with self.assertRaises(m.Hold):
            m.read("fake-readonly-audit-token-123",
                   "runner3-core",START,TODAY,wrong)

    def test_dedup_and_negative_rejected(self):
        def dup(req,timeout):
            x=records(json.loads(req.data)["variables"]["db"],1)
            x["data"]["viewer"]["accounts"][0]["d1AnalyticsAdaptiveGroups"]*=2
            return Response(x)
        with self.assertRaises(m.Hold):
            m.read("fake-readonly-audit-token-123",
                   "runner3-core",START,TODAY,dup)

    def test_complete_zero_window_does_not_prove_quiescence(self):
        def complete_zero(token,name,start,end):
            return [{"date_utc":(start+dt.timedelta(days=i)).isoformat(),
                     "write_queries":0} for i in range(4)]
        now=dt.datetime(2026,10,29,12,tzinfo=dt.timezone.utc)
        report=m.assess("fake-readonly-audit-token-123",now,complete_zero)
        self.assertTrue(report["all_target_databases_date_coverage_complete"])
        for value in report["databases"].values():
            self.assertTrue(value["calendar_window_coverage_complete"])
            self.assertEqual(value["missing_days_utc"],[])
            self.assertIs(value["write_activity_detected"],False)
        self.assertFalse(report["writer_quiescence_proven"])
        self.assertFalse(report["cutover_ready"])

    def test_incomplete_zero_window_is_unknown_not_false(self):
        def partial(token,name,start,end):
            return [{"date_utc":start.isoformat(),"write_queries":0}]
        now=dt.datetime(2026,10,29,12,tzinfo=dt.timezone.utc)
        report=m.assess("fake-readonly-audit-token-123",now,partial)
        self.assertFalse(report["all_target_databases_date_coverage_complete"])
        for value in report["databases"].values():
            self.assertIsNone(value["write_activity_detected"])
            self.assertFalse(value["calendar_window_coverage_complete"])
            self.assertEqual(value["missing_days_utc"],
                             ["2026-10-27","2026-10-28","2026-10-29"])
            self.assertEqual(value["write_queries_in_returned_groups"],0)

    def test_positive_partial_window_is_detected_but_incomplete(self):
        def partial(token,name,start,end):
            return [{"date_utc":"2026-10-29","write_queries":7}]
        now=dt.datetime(2026,10,29,12,tzinfo=dt.timezone.utc)
        report=m.assess("fake-readonly-audit-token-123",now,partial)
        self.assertFalse(report["all_target_databases_date_coverage_complete"])
        for value in report["databases"].values():
            self.assertIs(value["write_activity_detected"],True)
            self.assertFalse(value["calendar_window_coverage_complete"])
            self.assertEqual(value["write_queries_in_returned_groups"],7)

    def test_duplicate_or_invalid_day_from_reader_fails_closed(self):
        now=dt.datetime(2026,10,29,12,tzinfo=dt.timezone.utc)
        def duplicates(token,name,start,end):
            return [{"date_utc":start.isoformat(),"write_queries":0}]*2
        with self.assertRaisesRegex(m.Hold,"METRIC_DAY_COVERAGE_INVALID"):
            m.assess("fake-readonly-audit-token-123",now,duplicates)
        def negative(token,name,start,end):
            return [{"date_utc":start.isoformat(),"write_queries":-1}]
        with self.assertRaisesRegex(m.Hold,"METRIC_DAY_COVERAGE_INVALID"):
            m.assess("fake-readonly-audit-token-123",now,negative)

    def test_assess_does_not_prove_quiescence(self):
        def fake(token,name,start,end):
            return ([{"date_utc":"2026-10-28","write_queries":2}]
                    if name=="runner3-core" else [])
        now=dt.datetime(2026,10,29,12,tzinfo=dt.timezone.utc)
        report=m.assess("fake-readonly-audit-token-123",now,fake)
        self.assertTrue(report["databases"]["runner3-core"]["write_activity_detected"])
        self.assertIsNone(report["databases"]["runner3-content-intelligence"]["write_activity_detected"])
        self.assertFalse(report["all_target_databases_date_coverage_complete"])
        self.assertFalse(report["writer_quiescence_proven"])
        self.assertFalse(report["cutover_ready"])
        self.assertEqual(report["d1_sql_requests"],0)
        self.assertEqual(report["d1_writes"],0)
        self.assertEqual(report["r2_requests"],0)
        self.assertNotIn("fake-readonly-audit-token",str(report))

if __name__=="__main__":
    unittest.main()
