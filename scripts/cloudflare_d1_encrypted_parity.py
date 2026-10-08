#!/usr/bin/env python3
"""Read-only source D1 table-count audit; encrypted output, never plaintext in repo."""
import base64,datetime,hashlib,json,os,pathlib,secrets,urllib.error,urllib.request
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
ACCOUNT="7415a87f6bce7884e73ad7cfed5782df"
ALLOW={"runner3-core","runner3-content-intelligence"}
BASE="https://api.cloudflare.com/client/v4"
def fetch(token,method,path,payload=None):
    headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"}
    data=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(BASE+path,headers=headers,data=data,method=method)
    try:
        with urllib.request.urlopen(req,timeout=35) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:
        return e.code,{}
def rows(v):
    res=v.get("result") or []
    return (res[0].get("results") or []) if isinstance(res,list) and res else []
def main():
    token=os.environ.get("CF_TOKEN") or ""
    account=os.environ.get("CF_ACCOUNT") or ""
    if not token or account!=ACCOUNT:raise SystemExit("ACCOUNT_PRECONDITION_FAILED")
    code,data=fetch(token,"GET",f"/accounts/{ACCOUNT}/d1/database?per_page=100")
    if code!=200 or not data.get("success"):raise SystemExit("D1_LIST_DENIED")
    dbs={x.get("name"):x.get("uuid") for x in (data.get("result") or [])}
    manifest={"account":ACCOUNT,"time_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"databases":{}}
    for name in sorted(ALLOW):
        uid=dbs.get(name)
        if not uid:raise SystemExit("REQUIRED_DATABASE_MISSING")
        endpoint=f"/accounts/{ACCOUNT}/d1/database/{uid}/query"
        c,j=fetch(token,"POST",endpoint,{"sql":"SELECT name,type,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"})
        if c!=200 or not j.get("success"):raise SystemExit("SCHEMA_QUERY_DENIED_"+name)
        tables={}
        for t in rows(j):
            table=t.get("name")
            if not table or table=="_cf_KV":continue
            safe=table.replace('"','""')
            c2,k=fetch(token,"POST",endpoint,{"sql":'SELECT COUNT(*) AS n FROM "'+safe+'"'})
            count=rows(k)[0].get("n") if c2==200 and k.get("success") and rows(k) else None
            ddl=(t.get("sql") or "").strip()
            tables[table]={"count":count,"ddl_sha256":hashlib.sha256(ddl.encode()).hexdigest()}
        manifest["databases"][name]={"table_count":len(tables),"tables":tables}
        print("ENCRYPTED_SOURCE_D1_PREPARED",name,len(tables))
    pub=serialization.load_pem_public_key(pathlib.Path("ops/cloudflare-account-rehome/courier-public-20261008.pem").read_bytes())
    key=secrets.token_bytes(32)
    nonce=secrets.token_bytes(12)
    aad=b"cf-d1-schema-parity-v1"
    cipher=AESGCM(key).encrypt(nonce,json.dumps(manifest,separators=(",",":")).encode(),aad)
    wrapped=pub.encrypt(key,padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    envelope={"version":1,"nonce":base64.b64encode(nonce).decode(),"aad":base64.b64encode(aad).decode(),"wrapped_key":base64.b64encode(wrapped).decode(),"ciphertext":base64.b64encode(cipher).decode()}
    target=pathlib.Path("courier-out")
    target.mkdir(exist_ok=True)
    (target/"d1-envelope.json").write_text(json.dumps(envelope,separators=(",",":"))+"\n")
    print("ENCRYPTED_D1_SCHEMA_AUDIT_READY",len(manifest["databases"]))
if __name__=="__main__":main()
