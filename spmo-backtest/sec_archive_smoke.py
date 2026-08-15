#!/usr/bin/env python3
import requests

UA={"User-Agent":"Louis SPMO research contact: louisalviss@users.noreply.github.com"}
urls=[
    "https://www.sec.gov/Archives/edgar/data/1378872/000175272425091932/primary_doc.xml",
    "https://www.sec.gov/Archives/edgar/full-index/2025/QTR2/master.idx",
]
for u in urls:
    r=requests.get(u,headers=UA,timeout=30)
    print(u, r.status_code, r.headers.get("content-type"), len(r.content))
    print(r.text[:180].replace("\n"," "))
