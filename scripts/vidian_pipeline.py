#!/usr/bin/env python3
import argparse
import gzip
import hashlib
import json
import re
import threading
import time
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
UA = "Mozilla/5.0 (compatible; runner-3/VidianPipeline/2.1)"
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
STOP=set("và là của có cho trong một những các được với này đó khi thì đã đang sẽ nhưng mà hay về từ đến ra vào ở trên dưới theo như nên cũng rất không chỉ lại còn hơn sau trước nếu do bởi vì để tại người thứ nào nhiều ít qua làm bị đi thấy nói vẫn thể phải thật the and of to a in is for on that with as by it".split())
MARKERS=("ủng hộ tác giả","thư hữu cần","bằng hữu tới","bài viết ngẫu nhiên","tiên hiền thư viện","liên hệ quảng cáo")
NEG={"không","chưa","chẳng","chả","đừng","không thể","chưa từng","không còn"}
MODAL={"có thể","có khả năng","khả năng","có lẽ","dường như","chắc chắn","rất có thể","được cho là","cho rằng","suy đoán","phỏng đoán","có vẻ"}
CAUSAL={"vì","do","bởi","nên","vì thế","do đó","bởi vậy","khiến","dẫn đến","dẫn tới","nhờ","kết quả là"}
TEMP={"trước","sau","khi","rồi","tiếp đó","sau đó","trước đó","cuối cùng","ban đầu","từng","hiện tại","lúc","đến khi"}
COND={"nếu","nếu như","chỉ khi","trừ khi","miễn là","trong trường hợp"}
COMP={"hơn","kém","bằng","ít hơn","nhiều hơn","cao hơn","thấp hơn","lớn hơn","nhỏ hơn"}
ATTR={"theo","cho rằng","nhận định","suy đoán","phỏng đoán","khẳng định","tiết lộ","cho biết"}
_HTTP_LOCAL=threading.local(); _DEPENDENCY_MODEL=None

def clean(x): return re.sub(r"\s+"," ",x or "").strip()
def tokens(x): return re.findall(r"[0-9A-Za-zÀ-ỹĐđ]+",(x or "").lower())

def session():
    s=getattr(_HTTP_LOCAL,"session",None)
    if s is None:
        s=requests.Session(); s.headers.update({"User-Agent":UA,"Accept-Language":"vi,en;q=0.8"})
        retry=Retry(total=3,connect=3,read=3,backoff_factor=.7,status_forcelist=(429,500,502,503,504),allowed_methods=frozenset(["GET"]))
        adapter=HTTPAdapter(max_retries=retry,pool_connections=8,pool_maxsize=8); s.mount("https://",adapter); s.mount("http://",adapter); _HTTP_LOCAL.session=s
    return s

def dependency_model():
    global _DEPENDENCY_MODEL
    if _DEPENDENCY_MODEL is None:
        from underthesea.pipeline.dependency_parse import init_parser
        _DEPENDENCY_MODEL=init_parser()
    return _DEPENDENCY_MODEL

def dependency_parse_batch(texts,batch_size=5000,buckets=8):
    from underthesea import word_tokenize
    tokenized=[word_tokenize(text) for text in texts]
    if not tokenized:return []
    dataset=dependency_model().predict(tokenized,batch_size=batch_size,buckets=buckets)
    out=[]
    for sentence in dataset.sentences:
        values=sentence.values; out.append(list(zip(values[1],values[6],values[7])))
    return out

def parser_smoke():
    started=time.time(); samples=["Tôi yêu Việt Nam.","Sinh viên đọc sách ở thư viện.","Tối nay Hà Nội có mưa lớn."]
    batch=dependency_parse_batch(samples)
    if len(batch)!=len(samples):raise SystemExit(f"dependency parser batch mismatch: {len(batch)}!={len(samples)}")
    sizes=[]
    for dep in batch:
        if not dep or not all(isinstance(x,(tuple,list)) and len(x)==3 for x in dep):raise SystemExit("dependency parser returned invalid structure")
        if not any(int(head)==0 or str(rel)=="root" for _,head,rel in dep):raise SystemExit("dependency parser returned no root")
        sizes.append(len(dep))
    print(json.dumps({"parser_smoke":"ok","sentences":len(samples),"tokens":sizes,"elapsed_sec":round(time.time()-started,3)}),flush=True)

def canon(h):
    if not h:return None
    u=urljoin(BASE,h);p=urlparse(u)
    if p.netloc not in {"vidian.vn","www.vidian.vn"}:return None
    m=re.search(r"/chi-tiet/([^/?#]+)",p.path);return f"{BASE}/chi-tiet/{m.group(1)}" if m else None

def category(h):
    p=urlparse(urljoin(BASE,h or ""));m=re.search(r"/danh-muc/([^/?#]+)/?",p.path);return m.group(1) if m and p.netloc in {"vidian.vn","www.vidian.vn"} else None

def discover_categories():
    out=set(SEEDS)
    try:
        r=session().get(BASE+"/",timeout=15);r.raise_for_status();soup=BeautifulSoup(r.text,"html.parser")
        for a in soup.find_all("a",href=True):
            c=category(a["href"])
            if c:out.add(c)
    except Exception as e:print("DISCOVER_WARN",repr(e),flush=True)
    return sorted(out)

def last_page(slug):
    for u in (f"{BASE}/danh-muc/{slug}/1/",f"{BASE}/danh-muc/{slug}/"):
        try:
            r=session().get(u,timeout=15)
            if not r.ok:continue
            soup=BeautifulSoup(r.text,"html.parser");nums={1};rx=re.compile(rf"/danh-muc/{re.escape(slug)}/(\d+)/?")
            for a in soup.find_all("a",href=True):
                m=rx.search(urlparse(urljoin(BASE,a["href"])).path)
                if m:nums.add(int(m.group(1)))
            return max(nums)
        except Exception:pass
    return 0

def fetch_listing(slug,page):
    u=f"{BASE}/danh-muc/{slug}/{page}/"
    try:
        r=session().get(u,timeout=20);r.raise_for_status();soup=BeautifulSoup(r.text,"html.parser");d={}
        for a in soup.find_all("a",href=True):
            c=canon(a["href"])
            if c:
                t=clean(a.get_text(" ",strip=True));d[c]=max(d.get(c,""),t,key=len)
        return slug,page,d,None
    except Exception as e:return slug,page,{},f"{type(e).__name__}:{e}"

def inventory(outdir):
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True);cats=discover_categories();ranges={}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs={ex.submit(last_page,c):c for c in cats}
        for f in as_completed(fs):ranges[fs[f]]=f.result()
    jobs=[(c,p) for c,n in ranges.items() for p in range(1,n+1)];by={};failures=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        fs=[ex.submit(fetch_listing,c,p) for c,p in jobs]
        for i,f in enumerate(as_completed(fs),1):
            c,p,d,err=f.result()
            if err:failures.append({"category":c,"page":p,"error":err})
            for u,t in d.items():by[u]=max(by.get(u,""),t,key=len)
            if i%50==0 or i==len(jobs):print("LISTING",i,"/",len(jobs),flush=True)
    rows=[{"url":u,"listing_title":t,"trusted":u not in UNTRUSTED} for u,t in sorted(by.items())];trusted=[r for r in rows if r["trusted"]]
    payload={"generated_utc":datetime.now(timezone.utc).isoformat(),"categories":ranges,"page_failures":failures,"all_urls":len(rows),"trusted_urls":len(trusted),"known_untrusted":len([r for r in rows if not r["trusted"]]),"rows":rows}
    (out/"vidian_inventory.json").write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8");print(json.dumps({k:payload[k] for k in ("all_urls","trusted_urls","known_untrusted")}),flush=True)
    if failures:print("PAGE_FAILURES",len(failures),flush=True)
    if len(trusted)<8500:raise SystemExit(f"inventory unexpectedly small: {len(trusted)}")

def is_marker(x):
    low=clean(x).lower().strip(" :-–—");return low in {"nguồn","từ khóa"} or low.startswith("nguồn:") or low.startswith("từ khóa:") or any(low.startswith(m) for m in MARKERS)

def extract(root):
    for n in root.xpath("//script|//style|//noscript|//template|//svg|//form"):
        try:n.drop_tree()
        except Exception:pass
    h1s=root.xpath("//h1[1]")
    if not h1s:raise ValueError("missing-h1")
    h1=h1s[0];paras=[];buf=[];last_parent=None
    def flush():
        nonlocal buf
        t=clean(" ".join(buf));buf=[]
        if len(t)>=20:paras.append(t)
    for node in h1.xpath("following::text()"):
        parent=node.getparent();x=clean(str(node))
        if not x:continue
        if is_marker(x):flush();break
        if x.lower() in {"video","rank","tìm kiếm","chat","user"}:continue
        pid=id(parent)
        if last_parent is not None and pid!=last_parent:flush()
        buf.append(x);last_parent=pid
    flush()
    if sum(map(len,paras))<100:raise ValueError("article-region-too-short")
    return paras

def sentence_split(text):
    xs=[clean(x) for x in re.split(r'(?<=[.!?…])\s+(?=[A-ZÀ-ỸĐ0-9“"(\[])',text) if len(clean(x))>=25];return xs or ([clean(text)] if clean(text) else [])

def phrase_matches(text,phrases):
    low=" ".join(tokens(text));out=[]
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
    c=Counter(re.findall(r"(?<!\w)(?:\d{1,4}(?:[.,]\d+)?%?|20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d+\s*(?:năm|tháng|ngày|tuổi|cấp|tầng|lần|người|vạn|triệu|tỷ))(?!\w)",text.lower()));return [{"value":k,"count":v} for k,v in sorted(c.items())]

def frame_from_dep(sent,idx,dep):
    nodes=[{"word":str(w),"head":int(h),"rel":str(r)} for w,h,r in dep];roots=[i for i,n in enumerate(nodes,1) if n["rel"]=="root" or n["head"]==0];root_i=roots[0] if roots else None;pred=nodes[root_i-1]["word"] if root_i else "";subjects=[];objects=[];comps=[]
    for n in nodes:
        if n["rel"].startswith(("nsubj","csubj")):subjects.append(n["word"])
        elif n["rel"] in {"obj","iobj"}:objects.append(n["word"])
        elif n["rel"].startswith("obl") or n["rel"] in {"advmod","xcomp","ccomp"}:comps.append(n["word"])
    terms=Counter(t for t in tokens(sent) if len(t)>=2 and t not in STOP and not t.isdigit());edges=[]
    for n in nodes:
        if n["rel"]=="punct":continue
        head="ROOT" if n["head"]==0 else nodes[n["head"]-1]["word"];edges.append({"dependent":n["word"],"relation":n["rel"],"head":head})
    return {"sentence_index":idx,"source_sentence_sha256":hashlib.sha256(clean(sent).encode()).hexdigest(),"predicate_root":pred,"subjects":subjects[:8],"objects":objects[:8],"obliques_and_complements":comps[:12],"negation":phrase_matches(sent,NEG),"modality_uncertainty":phrase_matches(sent,MODAL),"causal_cues":phrase_matches(sent,CAUSAL),"temporal_cues":phrase_matches(sent,TEMP),"condition_cues":phrase_matches(sent,COND),"comparison_cues":phrase_matches(sent,COMP),"attribution_cues":phrase_matches(sent,ATTR),"entities":entities(sent),"numeric_signals":numeric(sent),"residual_lexicon":[{"term":t,"count":c} for t,c in sorted(terms.items())],"dependency_edges":edges,"word_count":len(tokens(sent))}

def parse_error_frame(sent,idx,error):
    return {"sentence_index":idx,"source_sentence_sha256":hashlib.sha256(clean(sent).encode()).hexdigest(),"parse_error":f"{type(error).__name__}:{str(error)[:160]}","entities":entities(sent),"numeric_signals":numeric(sent),"residual_lexicon":[{"term":t,"count":c} for t,c in Counter(tokens(sent)).most_common(80)]}

def parse_many(texts,group_size=512):
    if not texts:return []
    results=[None]*len(texts)
    def parse_range(lo,hi):
        batch=texts[lo:hi]
        try:
            parsed=dependency_parse_batch(batch)
            if len(parsed)!=len(batch):raise ValueError(f"batch-size-mismatch:{len(parsed)}!={len(batch)}")
            for j,dep in enumerate(parsed,lo):results[j]=dep
        except Exception as exc:
            if hi-lo==1:results[lo]=exc;return
            mid=lo+(hi-lo)//2;parse_range(lo,mid);parse_range(mid,hi)
    for lo in range(0,len(texts),group_size):
        hi=min(lo+group_size,len(texts));parse_range(lo,hi);print("PARSE_BATCH",hi,"/",len(texts),flush=True)
    return results

def prepare_article(row):
    u=row["url"];started=time.time();o={"url":u,"listing_title":row.get("listing_title",""),"status":"fetch-error","http_status":0,"title":"","paragraph_count":0,"sentence_count":0,"parse_success_sentences":0,"parse_failed_sentences":0,"sections":[],"source_prose_persisted":False,"schema":"semantic-reconstruction-frames-v3"}
    try:
        r=session().get(u,timeout=(6,25),allow_redirects=True);o["http_status"]=r.status_code;o["html_sha256"]=hashlib.sha256(r.content).hexdigest()
        if not r.ok:o["status"]=f"http-{r.status_code}";return o
        root=html.fromstring(r.content,base_url=r.url);paras=extract(root);full=clean(" ".join(paras));o["clean_body_sha256"]=hashlib.sha256(full.encode()).hexdigest();o["paragraph_count"]=len(paras);title=root.xpath('//meta[@property="og:title"]/@content') or root.xpath('//h1[1]//text()') or root.xpath('//title/text()');o["title"]=clean(title[0]) if title else "";o["_paragraphs"]=paras;o["status"]="fetched"
    except Exception as e:o["status"]=f"error:{type(e).__name__}:{str(e)[:120]}"
    finally:o["fetch_elapsed_sec"]=round(time.time()-started,3)
    return o

def semanticize_prepared(prepared,parse_group_size=512):
    flat_texts=[];layouts={}
    for ai,rec in enumerate(prepared):
        paras=rec.pop("_paragraphs",None)
        if rec.get("status")!="fetched" or not paras:continue
        layout=[];si=0
        for pi,paragraph in enumerate(paras):
            items=[]
            for sent in sentence_split(paragraph):
                fi=len(flat_texts);flat_texts.append(sent);items.append((fi,si,sent));si+=1
            layout.append(items)
        layouts[ai]=layout;rec["sentence_count"]=si
    parse_started=time.time();parsed_results=parse_many(flat_texts,group_size=parse_group_size);parse_elapsed=time.time()-parse_started
    for ai,rec in enumerate(prepared):
        layout=layouts.get(ai)
        if layout is None:rec["elapsed_sec"]=rec.get("fetch_elapsed_sec",0);rec["fetched_at_utc"]=datetime.now(timezone.utc).isoformat();continue
        sec={"section_index":0,"heading":"","paragraphs":[]}
        for pi,items in enumerate(layout):
            prec={"paragraph_index":pi,"sentences":[]}
            for fi,si,sent in items:
                result=parsed_results[fi]
                if isinstance(result,Exception):frame=parse_error_frame(sent,si,result);rec["parse_failed_sentences"]+=1
                else:
                    try:frame=frame_from_dep(sent,si,result);rec["parse_success_sentences"]+=1
                    except Exception as exc:frame=parse_error_frame(sent,si,exc);rec["parse_failed_sentences"]+=1
                prec["sentences"].append(frame)
            sec["paragraphs"].append(prec)
        rec["sections"]=[sec];rec["status"]="ok" if not rec["parse_failed_sentences"] else "partial-parse";rec["elapsed_sec"]=round(rec.get("fetch_elapsed_sec",0)+parse_elapsed,3);rec["fetched_at_utc"]=datetime.now(timezone.utc).isoformat()
    return prepared

def chunk(inventory_path,outdir,index,count,fetch_workers=8,parse_group_size=512):
    inv=json.loads(Path(inventory_path).read_text());rows=[r for r in inv["rows"] if r.get("trusted")];selected=[r for i,r in enumerate(rows) if i%count==index];out=Path(outdir);out.mkdir(parents=True,exist_ok=True);p=out/f"vidian_semantic_frame_chunk_{index:02d}.jsonl"
    fetch_started=time.time();prepared=[None]*len(selected)
    with ThreadPoolExecutor(max_workers=min(fetch_workers,max(1,len(selected)))) as ex:
        future_to_i={ex.submit(prepare_article,row):i for i,row in enumerate(selected)};done=0
        for future in as_completed(future_to_i):
            i=future_to_i[future]
            try:prepared[i]=future.result()
            except Exception as e:
                row=selected[i];prepared[i]={"url":row["url"],"listing_title":row.get("listing_title",""),"status":f"error:{type(e).__name__}:{str(e)[:120]}","http_status":0,"title":"","paragraph_count":0,"sentence_count":0,"parse_success_sentences":0,"parse_failed_sentences":0,"sections":[],"source_prose_persisted":False,"schema":"semantic-reconstruction-frames-v3","fetch_elapsed_sec":0}
            done+=1
            if done%25==0 or done==len(selected):print("PREFETCH",index,done,"/",len(selected),flush=True)
    fetch_elapsed=time.time()-fetch_started;semantic_started=time.time();prepared=semanticize_prepared(prepared,parse_group_size=parse_group_size);semantic_elapsed=time.time()-semantic_started;ok=bad=sent=parsed=parse_failed=0
    with p.open("w",encoding="utf-8",buffering=1) as f:
        for rec in prepared:
            f.write(json.dumps(rec,ensure_ascii=False)+"\n");sent+=rec.get("sentence_count",0);parsed+=rec.get("parse_success_sentences",0);parse_failed+=rec.get("parse_failed_sentences",0)
            if rec["status"] in {"ok","partial-parse"}:ok+=1
            else:bad+=1
    rate=parsed/sent if sent else 0;summary={"chunk":index,"chunks":count,"rows":len(selected),"ok_or_partial":ok,"fetch_failed":bad,"sentences":sent,"parse_success":parsed,"parse_failed":parse_failed,"parse_rate":rate,"fetch_elapsed_sec":round(fetch_elapsed,3),"semantic_elapsed_sec":round(semantic_elapsed,3),"completed_utc":datetime.now(timezone.utc).isoformat()};(out/f"chunk_{index:02d}_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(summary,ensure_ascii=False),flush=True)
    if sent==0 or rate<.95:raise SystemExit(f"dependency parse rate too low: {rate:.4f}")
    if bad:raise SystemExit(f"{bad} article fetch/extraction failures")

def merge(indir,outdir,inventory_path,count):
    inv=json.loads(Path(inventory_path).read_text());expected=len([r for r in inv["rows"] if r.get("trusted")]);src=Path(indir);files=sorted(src.rglob("vidian_semantic_frame_chunk_*.jsonl"))
    if len(files)!=count:raise SystemExit(f"expected {count} chunk files, found {len(files)}")
    rows=[]
    for p in files:
        for line in p.open(encoding="utf-8"):
            if line.strip():rows.append(json.loads(line))
    urls=[r["url"] for r in rows];out=Path(outdir);out.mkdir(parents=True,exist_ok=True);chunks=out/"chunks";chunks.mkdir(exist_ok=True)
    for p in files:
        with gzip.open(chunks/(p.name+".gz"),"wb",compresslevel=9) as g:g.write(p.read_bytes())
    manifest=[{"url":r["url"],"title":r.get("title",""),"listing_title":r.get("listing_title",""),"status":r.get("status",""),"paragraph_count":r.get("paragraph_count",0),"sentence_count":r.get("sentence_count",0),"clean_body_sha256":r.get("clean_body_sha256",""),"html_sha256":r.get("html_sha256","")} for r in sorted(rows,key=lambda x:x["url"])];(out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False),encoding="utf-8");total=sum(r.get("sentence_count",0) for r in rows);parsed=sum(r.get("parse_success_sentences",0) for r in rows);failed_parse=sum(r.get("parse_failed_sentences",0) for r in rows);summary={"schema":"semantic-reconstruction-frames-v3","expected_trusted_urls":expected,"records":len(rows),"unique_urls":len(set(urls)),"chunk_files":len(files),"ok_articles":sum(r.get("status")=="ok" for r in rows),"partial_parse_articles":sum(r.get("status")=="partial-parse" for r in rows),"failed_articles":sum(r.get("status") not in {"ok","partial-parse"} for r in rows),"total_sentences":total,"parse_success_sentences":parsed,"parse_failed_sentences":failed_parse,"parse_rate":parsed/total if total else 0,"source_prose_persisted":False,"completed_utc":datetime.now(timezone.utc).isoformat()};(out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(summary,ensure_ascii=False),flush=True)
    if len(rows)!=expected or len(set(urls))!=expected:raise SystemExit(3)
    if summary["failed_articles"]:raise SystemExit(4)
    if total==0 or summary["parse_rate"]<.95:raise SystemExit(5)

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="cmd",required=True);sub.add_parser("smoke");a=sub.add_parser("inventory");a.add_argument("--out",default="vidian_inventory");a=sub.add_parser("chunk");a.add_argument("--inventory",required=True);a.add_argument("--out",required=True);a.add_argument("--index",type=int,required=True);a.add_argument("--count",type=int,default=32);a.add_argument("--fetch-workers",type=int,default=8);a.add_argument("--parse-group-size",type=int,default=512);a=sub.add_parser("merge");a.add_argument("--inventory",required=True);a.add_argument("--input",required=True);a.add_argument("--out",required=True);a.add_argument("--count",type=int,default=32);x=ap.parse_args()
    if x.cmd=="smoke":parser_smoke()
    elif x.cmd=="inventory":inventory(x.out)
    elif x.cmd=="chunk":chunk(x.inventory,x.out,x.index,x.count,x.fetch_workers,x.parse_group_size)
    else:merge(x.input,x.out,x.inventory,x.count)
if __name__=="__main__":main()
