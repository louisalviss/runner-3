#!/usr/bin/env python3
"""Offline S3 migration batch tests; secrets and network replaced by mocks."""
import importlib.util, os
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("batch","scripts/cloudflare_r2_native_batch.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def ob(k,size,**extra): return {"key":k,"size":size,**extra}

# Missing/target reconciliation gates.
exist,missing=m.preflight([ob("a",10),ob("b",20)],{"a":10})
assert len(exist)==1 and len(missing)==1
print("PASS reconcile")
for source,target,why in [
    ([ob("a",10)],{"a":11},"TARGET_EXISTING_SIZE_DRIFT_ABORT"),
    ([ob("a",10)],{"a":10,"extra":2},"TARGET_UNEXPECTED_KEYS_ABORT")
]:
    try: m.preflight(source,target);assert False
    except m.GateError as err: assert str(err)==why
    print("PASS",why)

planned,summary=m.plan_batch([
    ob("good",5,custom_metadata={"flow":"proof"}),
    ob("empty",0),
    ob("large",10_000_001),
    ob("unicode",42,custom_metadata={"emoji":"π"}),
])
assert len(planned)==2 and summary["planned_bytes"]==5
assert summary["skipped_large_count"]==1
assert summary["skipped_metadata_count"]==1
print("PASS planned-bounds")

class FakeClient:
    def __init__(self, keys=None):
        self.keys=dict(keys or {})
        self.writes=[]
    def list_objects_v2(self,**args):
        return {"IsTruncated":False,"Contents":[{"Key":k,"Size":v} for k,v in self.keys.items()]}
    def head_object(self,**args): return {"ContentLength":123}

env={"CLOUDFLARE_API_TOKEN":"dummy","CLOUDFLARE_ACCOUNT_ID":m.SOURCE_ACCOUNT}
fake=FakeClient({"first":1})
source=[ob("first",1),ob("second",2),ob("third",3)]
def mock_copy(client,token,bucket,obj):
    assert bucket==m.BUCKET
    assert obj["key"] not in client.keys
    client.keys[obj["key"]]=obj["size"]
    return {"object_bytes":obj["size"],"uploaded":True,"object_verified":True}

with patch.dict(os.environ,env,clear=True),patch.object(m,"target_s3",return_value=fake),\
     patch.object(m,"source_list",return_value=source),patch.object(m,"copy_one",side_effect=mock_copy):
    a=m.run("audit")
    assert a["result"]=="READ_ONLY_AUDIT" and a["missing_before"]==2 and len(fake.keys)==1
    print("PASS audit-is-readonly")
    b=m.run("batch")
    assert b["verified_count"]==2 and b["uploaded_count"]==2
    assert b["missing_after_snapshot"]==0 and b["full_bucket_parity_verified"] is False
    assert b["cutover_ready"] is False and b["source_deleted"] is False
    print("PASS bounded-copy-count-and-no-cutover")

# Faulty target listing must fail closed, even if a batch could otherwise run.
class LoopClient:
    def list_objects_v2(self,**kw):
        return {"IsTruncated":True,"NextContinuationToken":"same","Contents":[]}
try: m.target_list(LoopClient());assert False
except m.GateError as err:assert str(err)=="TARGET_CURSOR_INVALID"
print("PASS target-cursor-loop-abort")
