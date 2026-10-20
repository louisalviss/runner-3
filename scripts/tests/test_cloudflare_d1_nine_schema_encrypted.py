#!/usr/bin/env python3
"""Synthetic-only contracts; no live Cloudflare, R2, GitHub or account secrets."""
import base64
import importlib.util
import json
import pathlib
import unittest
from unittest import mock
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding,rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "cloudflare_d1_nine_schema_encrypted.py"
spec = importlib.util.spec_from_file_location("nine_source_schema", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class NineSourceSchemaTests(unittest.TestCase):
    def setUp(self):
        self.ids = {n: f'00000000-0000-0000-0000-{i:012x}' for i,n in enumerate(sorted(module.EXPECTED_DATABASES),1)}
        self.calls = []
    def fake_api(self, token, method, route, payload=None):
        self.calls.append((method,route,payload))
        self.assertEqual(token, "fake-token-for-unit-tests")
        if method == "GET":
            return {"success":True, "result":[{"name":n,"uuid":uid} for n,uid in self.ids.items()],
                    "result_info":{"page":1,"count":9,"total_count":9,"total_pages":1}}
        if payload["sql"] == module.SCHEMA_SQL:
            return {"success":True,"result":[{"success":True,"results":[{"type":"table","name":"items",
                    "tbl_name":"items","sql":"CREATE TABLE items (id INTEGER PRIMARY KEY, title TEXT)"}]}]}
        if payload["sql"] == 'PRAGMA table_xinfo("items")':
            return {"success":True,"result":[{"success":True,"results":[
                {"cid":0,"name":"id","pk":1},{"cid":1,"name":"title","pk":0}]}]}
        self.fail("Unexpected SQL was called: " + str(payload))

    def test_nine_dbs_all_schema_no_payloads(self):
        with mock.patch.object(module,"request_json",self.fake_api):
            m=module.read_source_schema("fake-token-for-unit-tests")
        self.assertEqual(len(m["databases"]),9)
        self.assertEqual(m["evidence"],"SOURCE_ONLY_SCHEMA_PK_NO_ROWS")
        self.assertFalse(m["target_accessed"])
        self.assertFalse(m["target_row_parity_verified"])
        self.assertFalse(m["cutover_ready"])
        self.assertEqual([row[0] for row in self.calls].count("GET"),1)
        self.assertEqual([row[0] for row in self.calls].count("POST"),18)
        self.assertTrue(all('COUNT(' not in str(x[2]) and 'SELECT *' not in str(x[2]) for x in self.calls))
        self.assertEqual({tuple(v['tables']['items']['pk_columns']) for v in m['databases'].values()}, {('id',)})
        self.assertEqual({v['tables']['items']['row_count'] for v in m['databases'].values()}, {None})
        self.assertTrue(all(x[1].startswith('/accounts/'+module.SOURCE_ACCOUNT+'/d1/database') for x in self.calls))

    def test_envelope_encrypt_and_roundtrip(self):
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        pem=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        manifest={"secret":"synthetic ONLY", "databases":{"runner3-core":{}}, "cutover_ready":False}
        envelope=module.encrypt_result(manifest,pem)
        as_json=json.dumps(envelope)
        self.assertNotIn('synthetic ONLY',as_json)
        key_bytes=key.decrypt(base64.b64decode(envelope['wrapped_key']),padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
        dec=AESGCM(key_bytes).decrypt(base64.b64decode(envelope['nonce']),base64.b64decode(envelope['ciphertext']),base64.b64decode(envelope['aad']))
        self.assertEqual(json.loads(dec),manifest)

    def test_inventory_pagination_incomplete(self):
        with self.assertRaisesRegex(module.AuditBlocked,"D1_INVENTORY_PAGINATION_INCOMPLETE"):
            module.parse_db_inventory({'result':[{'name':n,'uuid':i} for n,i in self.ids.items()],
                                       'result_info':{'page':1,'count':9,'total_count':20}})

    def test_missing_database(self):
        items=[{'name':n,'uuid':i} for n,i in list(self.ids.items())[:-1]]
        with self.assertRaisesRegex(module.AuditBlocked,"SOURCE_REQUIRED_DATABASE_MISSING"):
            module.parse_db_inventory({'result':items,'result_info':{'page':1,'count':8,'total_count':8}})

    def test_no_mutating_sql_or_cross_account(self):
        for sql in ('DELETE FROM items','SELECT COUNT(*) FROM items','DROP TABLE items', 'INSERT INTO items VALUES (3)'):
            with self.assertRaises(module.AuditBlocked):
                module.request_json("fake", "POST", f"/accounts/{module.SOURCE_ACCOUNT}/d1/database/{next(iter(self.ids.values()))}/query",{'sql':sql})
        with self.assertRaises(module.AuditBlocked):
            module.request_json("fake","GET","/accounts/748a80810f77f447ee476543ef0e5014/d1/database?page=1&per_page=100")

    def test_quoted_table_name(self):
        self.assertEqual(module.quoted_pragma('Odd"Name'), 'PRAGMA table_xinfo("Odd""Name")')
        with self.assertRaises(module.AuditBlocked):
            module.quoted_pragma('unsafe\x00name')

    def test_malformed_d1_query_results(self):
        with self.assertRaises(module.AuditBlocked):
            module.results({'result':[{'success':False,'results':[]}]})
        with self.assertRaises(module.AuditBlocked):
            module.results({'result':[]})

    def test_empty_table_columns_blocks(self):
        original=self.fake_api
        def bad(token, method, route, payload=None):
            if payload and payload['sql'].startswith('PRAGMA'):
                return {'success':True,'result':[{'success':True,'results':[]}]}
            return original(token,method,route,payload)
        with mock.patch.object(module,'request_json',bad), self.assertRaisesRegex(module.AuditBlocked,'TABLE_COLUMNS_MISSING'):
            module.read_source_schema('fake-token-for-unit-tests')

if __name__ == '__main__':
    unittest.main(verbosity=1)
