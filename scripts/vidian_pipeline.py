#!/usr/bin/env python3
import argparse, gzip, hashlib, json, os, re, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from lxml import html
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://vidian.vn"
UA = "Mozilla/5.0 (compatible; runner-3/VidianPipeline/1.0)"
SEEDS = {"review","tin-tuc","tom-tat","tac-gia","tieu-diem-nhan-vat","trich-dan-kinh-dien","chi-dao-sang-tac","bang-xep-hang"}
UNTRUSTED = {
"https://vidian.vn/chi-tiet/-tu-tuong-dong-phuong-thanh-long-tay-phuong-bach-ho-nam-phuong-chu-tuoc-bac-phuong-huyen-vu",
"https://vidian.vn/chi-tiet/bac-minh-than-cong",
"https://vidian.vn/chi-tiet/bang-xep-hang-chien-luc-tam-bo-khuc-cua-tac-gia-than-dong",
"https://vidian.vn/chi-tiet/con-bang",
"https://vidian.vn/chi-tiet/cuu-am-chan-kinh",
"https://vidian.vn/chi-tiet/cuu-duong-than-cong",
"https://vidian.vn/chi-tiet/my-nhan-ma-mon-loan-loan",
"https://vidian.vn/chi-tiet/neu-giet-nguoi-co-the-lam-nang-song-lai-thi-ta-da-som-giet-het-thien-ha-roi",
"https://vidian.vn/chi-tiet/nhu-lai-than-chuong",
"https://vidian.vn/chi-tiet/nhung-bo-truyen-tien-hiep-hay-nhat-da-full",
"https://vidian.vn/chi-tiet/quy-hoa-bao-dien",
"https://vidian.vn/chi-tiet/tich-ta-kiem-pho",
"https://vidian.vn/chi-tiet/top-10-buc-tranh-co-trung-quoc-noi-tieng",
"https://vidian.vn/chi-tiet/tre-khong-doc-thuy-hu-gia-khong-xem-tam-quoc",
"https://vidian.vn/chi-tiet/gian-khach-hua-nhac",
}
STOP = set("và là của có cho trong một những các được với này đó khi thì đã đang sẽ nhưng mà hay về từ đến ra vào ở trên dưới theo như nên cũng rất không chỉ lại còn hơn sau trước nếu do bởi vì để tại người thứ nào nhiều ít qua làm bị đi thấy nói vẫn thể phải thật the and of to a in is for on that with as by it".split())
MARKERS = ("ủng hộ tác giả","thư hữu cần","bằng hữu tới","bài viết ngẫu nhiên","tiên hiền thư viện","liên hệ quảng cáo")
NEG = {"không","chưa","chẳng","chả","đừng","không thể","chưa từng","không còn"}
MODAL = {"có thể","có khả năng","khả năng","có lẽ","dường như","chắc chắn","rất có thể","được cho là","cho rằng","suy đoán","phỏng đoán","có vẻ"}
CAUSAL = {"vì","do","bởi","nên","vì thế","do đó","bởi vậy","khiến","dẫn đến","dẫn tới","nhờ","kết quả là"}
TEMP = {"trước","sau","khi","rồi","tiếp đó","sau đó","trước đó","cuối cùng","ban đầu","từng","hiện tại","lúc","đến khi"}
COND = {"nếu","nếu như","chỉ khi","trừ khi","miễn là","trong trường hợp"}
COMP = {"hơn","kém","bằng","ít hơn","nhiều hơn","cao hơn","thấp hơn","lớn hơn","nhỏ hơn"}
ATTR = {"theo","cho rằng","nhận định","suy đoán","phỏng đoán","khẳng định","tiết lộ","cho biết"}

def clean(x): return re.sub(r"\s+", " ", x or "").strip()
def tokens(x): return re.findall(r"[0-9A-Za-zÀ-ỹĐđ]+", (x or "").lower())
def session():
    s=requests.Session(); s.headers.update({"User-Agent":UA,"Accept-Language":"vi,en;q=0.8"})
    r=Retry(total=3,connect=3,read=3,backoff_factor=.7,status_forcelist=(429,500,502,503,504),allowed_methods=frozenset(["GET"]))
    s.mount("https://",HTTPAdapter(max_retries=r,pool_connections=4,pool_maxsize=4)); return s

def canon(h):
    if not h:return None
    u=urljoin(BASE,h); p=urlparse(u)
    if p.netloc not in {"vidian.vn","www.vidian.vn"}:return None
    m=re.search(r"/chi-tiet/([^/?#]+)",p.path)
    return f"{BASE}/chi-tiet/{m.group(1)}" if m else None

def category(h):
    p=urlparse(urljoin(BASE,h or "")); m=re.search(r"/danh-muc/([^/?#]+)/?",p.path)
    return m.group(1) if m and p.netloc in {"vidian.vn","www.vidian.vn"} else None

def discover_categories():
    out=set(SEEDS); s=session()
    try:
        r=s.get(BASE+"/",timeout=15); r.raise_for_status(); soup=BeautifulSoup(r.text,"html.parser")
        for a in soup.find_all("a",href=True):
            c=category(a["href"])
            if c:out.add(c)
    except Exception as e: print("DISCOVER_WARN",repr(e),flush=True)
    return sorted(out)

def last_page(slug):
    s=session()
    for u in (f"{BASE}/danh-muc/{slug}/1/",f"{BASE}/danh-muc/{slug}/"):
        try:
            r=s.get(u,timeout=15)
            if not r.ok:continue
            soup=BeautifulSoup(r.text,"html.parser"); nums={1}; rx=re.compile(rf"/danh-muc/{re.escape(slug)}/(\d+)/?")
            for a in soup.find_all("a",href=True):
                m=rx.search(urlparse(urljoin(BASE,a["href"])).path)
                if m:nums.add(int(m.group(1)))
            return max(nums)
        except Exception:pass
    return 0

def fetch_listing(slug,page):
    u=f"{BASE}/danh-muc/{slug}/{page}/"; s=session()
    try:
        r=s.get(u,timeout=20); r.raise_for_status(); soup=BeautifulSoup(r.text,"html.parser"); d={}
        for a in soup.find_all("a",href=True):
            c=canon(a["href"])
            if c:
                t=clean(a.get_text(" ",strip=True)); d[c]=max(d.get(c,""),t,key=len)
        return slug,page,d,None
    except Exception as e:return slug,page,{},f"{type(e).__name__}:{e}"

def inventory(outdir):
    out=Path(outdir); out.mkdir(parents=True,exist_ok=True); cats=discover_categories(); ranges={}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs={ex.submit(last_page,c):c for c in cats}
        for f in as_completed(fs): ranges[fs[f]]=f.result()
    jobs=[(c,p) for c,n in ranges.items() for p in range(1,n+1)]; by={}; failures=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        fs=[ex.submit(fetch_listing,c,p) for c,p in jobs]
        for i,f in enumerate(as_completed(fs),1):
            c,p,d,err=f.result()
            if err: failures.append({"category":c,"page":p,"error":err})
            for u,t in d.items(): by[u]=max(by.get(u,""),t,key=len)
            if i%50==0 or i==len(jobs): print("LISTING",i,"/",len(jobs),flush=True)
    rows=[{"url":u,"listing_title":t,"trusted":u not in UNTRUSTED} for u,t in sorted(by.items())]
    trusted=[r for r in rows if r["trusted"]]
    payload={"generated_utc":datetime.now(timezone.utc).isoformat(),"categories":ranges,"page_failures":failures,"all_urls":len(rows),"trusted_urls":len(trusted),"known_untrusted":len([r for r in rows if not r["trusted"]]),"rows":rows}
    (out/"vidian_inventory.json").write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({k:payload[k] for k in ("all_urls","trusted_urls","known_untrusted")}),flush=True)
    if failures: print("PAGE_FAILURES",len(failures),flush=True)
    if len(trusted)<8500: raise SystemExit(f"inventory unexpectedly small: {len(trusted)}")

def is_marker(x):
    low=clean(x).lower().strip(" :-–—")
    return low in {"nguồn","từ khóa"} or low.startswith("nguồn:") or low.startswith("từ khóa:") or any(low.startswith(m) for m in MARKERS)

def extract(root):
    for n in root.xpath("//script|//style|//noscript|//template|//svg|//form"):
        try:n.drop_tree()
        except Exception:pass
    h1s=root.xpath("//h1[1]")
    if not h1s:raise ValueError("missing-h1")
    h1=h1s[0]; paras=[]; buf=[]; last_parent=None
    def flush():
        nonlocal buf
        t=clean(" ".join(buf)); buf=[]
        if len(t)>=20:paras.append(t)
    for node in h1.xpath("following::text()"):
        parent=node.getparent(); x=clean(str(node))
        if not x:continue
        if is_marker(x):flush(); break
        if x.lower() in {"video","rank","tìm kiếm","chat","user"}:continue
        pid=id(parent)
        if last_parent is not None and pid!=last_parent:flush()
        buf.append(x); last_parent=pid
    flush()
    if sum(map(len,paras))<100:raise ValueError("article-region-too-short")
    return paras

def sentence_split(text):
    xs=[clean(x) for x in re.split(r'(?<=[.!?…])\s+(?=[A-ZÀ-ỸĐ0-9“"(\[])',text) if len(clean(x))>=25]
    return xs or ([clean(text)] if clean(text) else [])
def phrase_matches(text,phrases):
    low=" ".join(tokens(text)); out=[]
    for p in phrases:
        q=" ".join(tokens(p))
        if q and re.search(r"(?:^| )"+re.escape(q)+r"(?: |$)",low):out.append(p)
    return sorted(out)
def entities(text,n=30):
    c=Counter()
    for m in re.finditer(r"\b(?:[A-ZÀ-ỸĐ][A-Za-zÀ-ỹĐđ0-9'’.-]+(?:\s+|$)){1,5}",text):
        x=clean(m.group(0))
        if 2<=len(x)<=80:c[x]+=1
    return [{"name":x,"count":k} for x,k in c.most_common(n)]
def numeric(text):
    c=Counter(re.findall(r"(?<!\w)(?:\d{1,4}(?:[.,]\d+)?%?|20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d+\s*(?:năm|tháng|ngày|tuổi|cấp|tầng|lần|người|vạn|triệu|tỷ))(?!\w)",text.lower()))
    return [{"value":k,"count":v} for k,v in sorted(c.items())]
def frame_sentence(sent,idx):
    from underthesea import dependency_parse
    dep=dependency_parse(sent); nodes=[{"word":str(w),"head":int(h),"rel":str(r)} for w,h,r in dep]
    roots=[i for i,n in enumerate(nodes,1) if n["rel"]=="root" or n["head"]==0]; root_i=roots[0] if roots else None
    pred=nodes[root_i-1]["word"] if root_i else ""; subjects=[]; objects=[]; comps=[]
    for n in nodes:
        if n["rel"].startswith(("nsubj","csubj")):subjects.append(n["word"])
        elif n["rel"] in {"obj","iobj"}:objects.append(n["word"])
        elif n["rel"].startswith("obl") or n["rel"] in {"advmod","xcomp","ccomp"}:comps.append(n["word"])
    terms=Counter(t for t in tokens(sent) if len(t)>=2 and t not in STOP and not t.isdigit())
    edges=[]
    for n in nodes:
        if n["rel"]=="punct":continue
        head="ROOT" if n["head"]==0 else nodes[n["head"]-1]["word"]
        edges.append({"dependent":n["word"],"relation":n["rel"],"head":head})
    return {"sentence_index":idx,"source_sentence_sha256":hashlib.sha256(clean(sent).encode()).hexdigest(),"predicate_root":pred,"subjects":subjects[:8],"objects":objects[:8],"obliques_and_complements":comps[:12],"negation":phrase_matches(sent,NEG),"modality_uncertainty":phrase_matches(sent,MODAL),"causal_cues":phrase_matches(sent,CAUSAL),"temporal_cues":phrase_matches(sent,TEMP),"condition_cues":phrase_matches(sent,COND),"comparison_cues":phrase_matches(sent,COMP),"attribution_cues":phrase_matches(sent,ATTR),"entities":entities(sent),"numeric_signals":numeric(sent),"residual_lexicon":[{"term":t,"count":c} for t,c in sorted(terms.items())],"dependency_edges":edges,"word_count":len(tokens(sent))}

def article(row):
    u=row["url"]; o={"url":u,"listing_title":row.get("listing_title",""),"status":"fetch-error","http_status":0,"title":"","paragraph_count":0,"sentence_count":0,"parse_success_sentences":0,"parse_failed_sentences":0,"sections":[],"source_prose_persisted":False,"schema":"semantic-reconstruction-frames-v2"}
    started=time.time()
    try:
        r=session().get(u,timeout=(6,25),allow_redirects=True); o["http_status"]=r.status_code; o["html_sha256"]=hashlib.sha256(r.content).hexdigest()
        if not r.ok:o["status"]=f"http-{r.status_code}";return o
        root=html.fromstring(r.content,base_url=r.url); paras=extract(root); full=clean(" ".join(paras)); o["clean_body_sha256"]=hashlib.sha256(full.encode()).hexdigest(); o["paragraph_count"]=len(paras)
        title=root.xpath('//meta[@property="og:title"]/@content') or root.xpath('//h1[1]//text()') or root.xpath('//title/text()'); o["title"]=clean(title[0]) if title else ""
        sec={"section_index":0,"heading":"","paragraphs":[]}; si=0
        for pi,p in enumerate(paras):
            prec={"paragraph_index":pi,"sentences":[]}
            for sent in sentence_split(p):
                try:f=frame_sentence(sent,si);o["parse_success_sentences"]+=1
                except Exception as e:
                    f={"sentence_index":si,"source_sentence_sha256":hashlib.sha256(clean(sent).encode()).hexdigest(),"parse_error":f"{type(e).__name__}:{str(e)[:120]}","entities":entities(sent),"numeric_signals":numeric(sent),"residual_lexicon":[{"term":t,"count":c} for t,c in Counter(tokens(sent)).most_common(80)]};o["parse_failed_sentences"]+=1
                prec["sentences"].append(f);si+=1
            sec["paragraphs"].append(prec)
        o["sections"]=[sec];o["sentence_count"]=si;o["status"]="ok" if not o["parse_failed_sentences"] else "partial-parse"
    except Exception as e:o["status"]=f"error:{type(e).__name__}:{str(e)[:120]}"
    finally:o["elapsed_sec"]=round(time.time()-started,3);o["fetched_at_utc"]=datetime.now(timezone.utc).isoformat()
    return o

def chunk(inventory_path,outdir,index,count):
    inv=json.loads(Path(inventory_path).read_text()); rows=[r for r in inv["rows"] if r.get("trusted")]; selected=[r for i,r in enumerate(rows) if i%count==index]
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True); p=out/f"vidian_semantic_frame_chunk_{index:02d}.jsonl"; ok=bad=sent=parsed=0
    with p.open("w",encoding="utf-8",buffering=1) as f:
        for i,r in enumerate(selected,1):
            rec=article(r);f.write(json.dumps(rec,ensure_ascii=False)+"\n");f.flush();sent+=rec.get("sentence_count",0);parsed+=rec.get("parse_success_sentences",0)
            if rec["status"] in {"ok","partial-parse"}:ok+=1
            else:bad+=1
            if i%10==0 or i==len(selected):print("CHUNK",index,i,"/",len(selected),rec["status"],flush=True)
    s={"chunk":index,"chunks":count,"rows":len(selected),"ok_or_partial":ok,"fetch_failed":bad,"sentences":sent,"parse_success":parsed,"parse_rate":parsed/sent if sent else 0,"completed_utc":datetime.now(timezone.utc).isoformat()};(out/f"chunk_{index:02d}_summary.json").write_text(json.dumps(s,indent=2));print(json.dumps(s),flush=True)
    if bad:raise SystemExit(2)

def merge(indir,outdir,inventory_path):
    inv=json.loads(Path(inventory_path).read_text()); expected=len([r for r in inv["rows"] if r.get("trusted")]); src=Path(indir); files=sorted(src.rglob("vidian_semantic_frame_chunk_*.jsonl")); rows=[]
    for p in files:
        for line in p.open(encoding="utf-8"):
            if line.strip():rows.append(json.loads(line))
    urls=[r["url"] for r in rows]; out=Path(outdir);out.mkdir(parents=True,exist_ok=True); chunks=out/"chunks";chunks.mkdir(exist_ok=True)
    for p in files:
        dest=chunks/(p.name+".gz")
        with gzip.open(dest,"wb",compresslevel=9) as g:g.write(p.read_bytes())
    manifest=[{"url":r["url"],"title":r.get("title",""),"listing_title":r.get("listing_title",""),"status":r.get("status",""),"paragraph_count":r.get("paragraph_count",0),"sentence_count":r.get("sentence_count",0),"clean_body_sha256":r.get("clean_body_sha256",""),"html_sha256":r.get("html_sha256","")} for r in sorted(rows,key=lambda x:x["url"])]
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False));total=sum(r.get("sentence_count",0) for r in rows);parsed=sum(r.get("parse_success_sentences",0) for r in rows)
    summary={"schema":"semantic-reconstruction-frames-v2","expected_trusted_urls":expected,"records":len(rows),"unique_urls":len(set(urls)),"chunk_files":len(files),"ok_articles":sum(r.get("status")=="ok" for r in rows),"partial_parse_articles":sum(r.get("status")=="partial-parse" for r in rows),"failed_articles":sum(r.get("status") not in {"ok","partial-parse"} for r in rows),"total_sentences":total,"parse_success_sentences":parsed,"parse_rate":parsed/total if total else 0,"source_prose_persisted":False,"completed_utc":datetime.now(timezone.utc).isoformat()}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False),flush=True)
    if len(rows)!=expected or len(set(urls))!=expected or summary["failed_articles"]:raise SystemExit(3)

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("inventory");a.add_argument("--out",default="vidian_inventory")
    a=sub.add_parser("chunk");a.add_argument("--inventory",required=True);a.add_argument("--out",required=True);a.add_argument("--index",type=int,required=True);a.add_argument("--count",type=int,default=32)
    a=sub.add_parser("merge");a.add_argument("--inventory",required=True);a.add_argument("--input",required=True);a.add_argument("--out",required=True)
    x=ap.parse_args()
    if x.cmd=="inventory":inventory(x.out)
    elif x.cmd=="chunk":chunk(x.inventory,x.out,x.index,x.count)
    else:merge(x.input,x.out,x.inventory)
if __name__=="__main__":main()
