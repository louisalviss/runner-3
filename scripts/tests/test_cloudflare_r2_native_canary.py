#!/usr/bin/env python3
"""Offline contract for R2 S3 metadata canary, no credentials/network."""
import importlib.util, datetime as dt, hashlib, io, json, os, contextlib
from types import SimpleNamespace
from unittest.mock import patch
from botocore.exceptions import ClientError

spec=importlib.util.spec_from_file_location("canary","scripts/cloudflare_r2_native_canary.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
META={"owner":"manual-proof"}
B=b"canary payload from simulated REST"
OBJ={"key":"custom-proof","size":len(B),"custom_metadata":META,
     "http_metadata":{"contentType":"text/plain","cacheControl":"max-age=60"},
     "storage_class":"Standard"}

class FakeBody:
    def read(self,n): return B

class FakeS3:
    def __init__(self,existing=False,bad=False):
        self.existing=existing;self.bad=bad;self.puts=0;self.saved=None
        self.registered={}
        self.meta=SimpleNamespace(events=SimpleNamespace(register=self.register,unregister=self.unregister))
    def register(self,event,handler): self.registered[event]=handler
    def unregister(self,event,handler):
        assert self.registered[event] is handler
        del self.registered[event]
    def list_objects_v2(self,**k): return {"Contents":[]}
    def head_object(self,**k):
        if self.saved: return self.saved
        if self.existing: return dict(ContentLength=len(B),Metadata={"owner":"different" if self.bad else "manual-proof"},
                                      ContentType="text/plain",CacheControl="max-age=60",StorageClass="STANDARD")
        raise ClientError({"Error":{"Code":"404","Message":"Not Found"}},"HeadObject")
    def put_object(self,**k):
        assert "IfNoneMatch" not in k and k["Metadata"]==META
        req=SimpleNamespace(headers={})
        self.registered["before-sign.s3.PutObject"](req)
        assert req.headers["If-None-Match"]=="*"
        self.puts+=1
        self.saved={"Metadata":k["Metadata"],"ContentType":k["ContentType"],"CacheControl":k["CacheControl"],
                    "StorageClass":k["StorageClass"],"ContentLength":len(k["Body"])}
    def get_object(self,**k):return {"Body":FakeBody()}

env={"CLOUDFLARE_API_TOKEN":"synthetic-source","CLOUDFLARE_ACCOUNT_ID":m.SOURCE_ACCOUNT,
     "CLOUDFLARE_TARGET_R2_ACCESS_KEY_ID":"synthetic-id","CLOUDFLARE_TARGET_R2_SECRET_ACCESS_KEY":"synthetic-secret"}
for label,mode,existing,bad in [
    ("probe", "probe", False, False),
    ("new_metadata", "canary", False, False),
    ("existing_good", "canary", True, False),
    ("existing_drift", "canary", True, True),
]:
    mock=FakeS3(existing,bad)
    with patch.dict(os.environ,env,clear=True),patch.object(m.boto3,"client",return_value=mock),\
         patch.object(m,"source_list",return_value=[OBJ]),patch.object(m,"source_bytes",return_value=B):
        try:
            result=m.run(mode,"runner3-telegram-bobvolman-raw")
            assert not bad and result["status"]=="PASS"
            assert mock.puts==(1 if label=="new_metadata" else 0)
            assert not mock.registered
            if mode=="canary":assert result["object_verified"] and not result["cutover_ready"]
            print("PASS",label,"writes",mock.puts)
        except m.GateError as ex:
            assert bad and str(ex)=="TARGET_CUSTOM_METADATA_MISMATCH",(label,ex)
            assert mock.puts==0
            print("PASS",label,"fails_closed")
