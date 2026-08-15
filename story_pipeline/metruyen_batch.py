#!/usr/bin/env python3
import argparse
import concurrent.futures
import hashlib
import json
import random
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE="https://metruyenchuvn.org"
STORY="https://metruyenchuvn.org/vuong-bai-tien-hoa"
BOOK_ID=13343
KNOWN_EMPTY={
 "https://metruyenchuvn.org/vuong-bai-tien-hoa/chuong-91-2DOVcFGWwY42",
 "https://metruyenchuvn.org/vuong-bai-tien-hoa/chuong-92-WvhIANo1oBKG",
}
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def headers(json_mode=False):
    return {
        "User-Agent":UA,
        "Accept":"application/json,text/plain,*/*" if json_mode else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language":"vi-VN,vi;q=0.9,en;q=0.7",
        "Referer":STORY,
        "Cache-Control":"no-cache",
    }


def get(url, json_mode=False, retries=7):
    last=None
    for attempt in range(retries):
        try:
            r=requests.get(url,headers=headers(json_mode),timeout=35,allow_redirects=True)
            if r.status_code==200:
                return r
            last=RuntimeError(f"HTTP {r.status_code}")
            if r.status_code in (403,429):
                time.sleep(min(25,3*(attempt+1))+random.random()*2)
            else:
                time.sleep(min(6,0.7*(2**attempt))+random.random())
        except Exception as e:
            last=e
            time.sleep(min(8,0.7*(2**attempt))+random.random())
    raise RuntimeError(f"GET failed {url}: {last}")


def norm(s):
    return re.sub(r"\s+"," ",(s or "").replace("\xa0"," ")).strip()


def list_page(page):
    url=f"{BASE}/get/listchap/{BOOK_ID}?page={page}"
    r=get(url,json_mode=True)
    payload=r.json()
    soup=BeautifulSoup(payload.get("data") or "","html.parser")
    out=[]; seen=set()
    for a in soup.find_all("a",href=True):
        href=a["href"].strip()
        if not href.startswith("/vuong-bai-tien-hoa/chuong-"):
            continue
        full=urljoin(BASE,href)
        if full in seen: continue
        seen.add(full)
        out.append({"list_page":page,"page_pos":len(out)+1,"url":full,"site_title":norm(a.get_text(" ",strip=True))})
    if page<13 and len(out)<80:
        raise RuntimeError(f"list page {page} suspiciously short: {len(out)}")
    if not out:
        raise RuntimeError(f"list page {page} empty")
    return out


def body_from_html(text):
    soup=BeautifulSoup(text or "","html.parser")
    node=soup.select_one("div.truyen")
    if node is None:
        return ""
    for tag in node(["script","style","noscript","svg","template"]):
        tag.decompose()
    lines=[]
    for raw in node.get_text("\n").splitlines():
        s=norm(raw)
        if s: lines.append(s)
    return "\n\n".join(lines).strip()


def fetch_one(rec):
    # Small jitter spreads requests without materially delaying the run.
    time.sleep(random.random()*0.35)
    r=get(rec["url"],json_mode=False)
    body=body_from_html(r.text)
    if len(body)<500:
        if rec["url"] in KNOWN_EMPTY:
            return {**rec,"empty_terminal_shell":True,"ok":True,"body":"","chars":0}
        raise ValueError(f"body too short: {len(body)}")
    return {**rec,"final_url":r.url,"body":body,"chars":len(body),"sha256":hashlib.sha256(body.encode()).hexdigest(),"ok":True}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--page",type=int,required=True); ap.add_argument("--out",required=True); ap.add_argument("--workers",type=int,default=2)
    args=ap.parse_args()
    if not 1<=args.page<=13: raise SystemExit("page must be 1..13")
    records=list_page(args.page)
    results=[]; fails=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs={ex.submit(fetch_one,r):r for r in records}
        for fut in concurrent.futures.as_completed(futs):
            rec=futs[fut]
            try: results.append(fut.result())
            except Exception as e: fails.append({"url":rec["url"],"site_title":rec["site_title"],"error":f"{type(e).__name__}: {e}"})
    # Sequential recovery minimizes false failures from transient WAF/rate limits.
    if fails:
        ok_by={r["url"]:r for r in results}; again=[]
        source={r["url"]:r for r in records}
        for f in fails:
            time.sleep(1.0+random.random())
            try: ok_by[f["url"]]=fetch_one(source[f["url"]])
            except Exception as e: again.append({**f,"retry_error":f"{type(e).__name__}: {e}"})
        results=list(ok_by.values()); fails=again
    results.sort(key=lambda x:x["page_pos"])
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({"page":args.page,"count":len(results),"failed":fails,"records":results},ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"page":args.page,"listed":len(records),"ok":len(results),"failed":len(fails),"chars":sum(x.get('chars',0) for x in results)},ensure_ascii=False),flush=True)
    if fails: raise SystemExit(2)

if __name__=="__main__": main()
