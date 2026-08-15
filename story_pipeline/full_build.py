#!/usr/bin/env python3
import argparse, concurrent.futures, hashlib, html, json, os, random, re, sys, time, uuid, zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://tienvuc.info/vuong-bai-tien-hoa-ban-dich/chuong-{}"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 runner-3-vbth-full/1.0"


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def normalize_lines(text):
    out=[]
    for raw in text.replace("\r", "\n").split("\n"):
        s=re.sub(r"\s+", " ", raw).strip()
        if s: out.append(s)
    return out


def extract_page(html_text, part):
    soup=BeautifulSoup(html_text or "", "html.parser")
    for tag in soup(["script","style","noscript","svg","template"]):
        tag.decompose()
    lines=normalize_lines(soup.get_text("\n"))
    heading_re=re.compile(rf"^Chương\s+{part}\.\s*(.+)$", re.I)
    heading_idx=None; source_title=None
    for i,s in enumerate(lines):
        m=heading_re.match(s)
        if m:
            heading_idx=i; source_title=m.group(1).strip(); break
    if heading_idx is None:
        raise ValueError(f"chapter heading not found for {part}")
    start=None
    for i in range(heading_idx+1, min(len(lines), heading_idx+20)):
        if lines[i] == "Chương sau":
            start=i+1; break
    if start is None:
        start=heading_idx+1
    end=len(lines)
    for i in range(start, len(lines)):
        if lines[i] in {"Chương trước", "Chương sau"}:
            end=i; break
    body_lines=lines[start:end]
    boiler={"Tiên Vực","Thể Loại","Danh sách","Bảng xếp hạng","Truyện miễn phí","Truyện đã hoàn","Truyện mới cập nhật","Vương Bài Tiến Hóa (Bản dịch)"}
    body_lines=[x for x in body_lines if x not in boiler]
    body="\n\n".join(body_lines).strip()
    if len(body) < 700:
        raise ValueError(f"body too short for {part}: {len(body)}")
    return source_title, body


def normalize_entities(body, bible):
    # Longer aliases first to avoid partial replacement. Only exact string normalization.
    pairs=[]
    for ent in bible.get("entities", []):
        canonical=str(ent.get("canonical", "")).strip()
        for alias in ent.get("aliases", []):
            alias=str(alias).strip()
            if alias and canonical and alias != canonical:
                pairs.append((alias, canonical))
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    for alias, canonical in pairs:
        body=body.replace(alias, canonical)
    return body


def light_edit(body):
    # Conservative mechanical editing only: typography/spacing and a few source-wide obvious artifacts.
    body=body.replace("part-time", "làm thêm")
    body=body.replace("Part-time", "Làm thêm")
    body=re.sub(r"[ \t]+([,.;:!?])", r"\1", body)
    body=re.sub(r"([,.;:!?])(?=[A-Za-zÀ-ỹ])", r"\1 ", body)
    body=re.sub(r"\n{3,}", "\n\n", body)
    body=re.sub(r" {2,}", " ", body)
    return body.strip()


def fetch_one(part, bible, retries=4):
    url=BASE.format(part)
    headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    last=None
    for attempt in range(1,retries+1):
        try:
            r=requests.get(url, headers=headers, timeout=25, allow_redirects=True)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            title, body=extract_page(r.text, part)
            body=normalize_entities(body, bible)
            body=light_edit(body)
            sha=hashlib.sha256(body.encode("utf-8")).hexdigest()
            return {"part":part,"url":r.url,"title":title,"body":body,"chars":len(body),"sha256":sha,"ok":True}
        except Exception as e:
            last=f"{type(e).__name__}: {e}"
            time.sleep(min(4, 0.5*(2**(attempt-1))) + random.random()*0.4)
    return {"part":part,"url":url,"ok":False,"error":last}


def chapter_xhtml(part, title, body):
    paras=[]
    for p in body.split("\n\n"):
        p=p.strip()
        if not p: continue
        if re.fullmatch(r"[-—–_=*·•]{4,}", p):
            paras.append("<hr/>")
        else:
            paras.append(f"<p>{html.escape(p)}</p>")
    h=html.escape(f"Chương {part}. {title}")
    return f'''<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="vi" lang="vi"><head><meta charset="utf-8"/><title>{h}</title><link rel="stylesheet" type="text/css" href="style.css"/></head><body><h1>{h}</h1>{''.join(paras)}</body></html>'''


def build_epub(records, output):
    output=Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    uid=str(uuid.uuid4())
    style='body{font-family:serif;line-height:1.55;margin:5%;}h1{font-size:1.35em;text-align:center;margin:1.5em 0;}p{text-align:justify;text-indent:1.2em;margin:.35em 0;}hr{border:0;border-top:1px solid #aaa;margin:1.5em 20%;}'
    manifest=[]; spine=[]; nav=[]; ncx=[]
    for r in records:
        n=r["part"]; fn=f"ch{n:04d}.xhtml"; iid=f"ch{n:04d}"
        label=f"Chương {n}. {r['title']}"
        manifest.append(f'<item id="{iid}" href="{fn}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{iid}"/>')
        nav.append(f'<li><a href="{fn}">{html.escape(label)}</a></li>')
        ncx.append(f'<navPoint id="nav{n}" playOrder="{n}"><navLabel><text>{html.escape(label)}</text></navLabel><content src="{fn}"/></navPoint>')
    nav_doc=f'''<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="vi"><head><title>Mục lục</title></head><body><nav epub:type="toc" id="toc"><h1>Mục lục</h1><ol>{''.join(nav)}</ol></nav></body></html>'''
    ncx_doc=f'''<?xml version="1.0" encoding="UTF-8"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head><meta name="dtb:uid" content="urn:uuid:{uid}"/></head><docTitle><text>Vương Bài Tiến Hóa</text></docTitle><navMap>{''.join(ncx)}</navMap></ncx>'''
    opf=f'''<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">urn:uuid:{uid}</dc:identifier><dc:title>Vương Bài Tiến Hóa</dc:title><dc:creator>Quyển Thổ</dc:creator><dc:language>vi</dc:language><dc:description>Bản TiênVuc đã làm sạch và chuẩn hóa thuật ngữ.</dc:description><meta property="dcterms:modified">{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}</meta></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/><item id="css" href="style.css" media-type="text/css"/>{''.join(manifest)}</manifest><spine toc="ncx">{''.join(spine)}</spine></package>'''
    container='''<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'''
    with zipfile.ZipFile(output,"w") as z:
        z.writestr("mimetype","application/epub+zip",compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",container)
        z.writestr("OEBPS/style.css",style)
        z.writestr("OEBPS/nav.xhtml",nav_doc)
        z.writestr("OEBPS/toc.ncx",ncx_doc)
        z.writestr("OEBPS/content.opf",opf)
        for r in records:
            z.writestr(f"OEBPS/ch{r['part']:04d}.xhtml", chapter_xhtml(r['part'],r['title'],r['body']), compress_type=zipfile.ZIP_DEFLATED)
    return output


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--start',type=int,default=1); ap.add_argument('--end',type=int,default=2888); ap.add_argument('--workers',type=int,default=8); ap.add_argument('--bible',default='story_pipeline/config/story_bible.json'); ap.add_argument('--out',default='vbth_full')
    args=ap.parse_args(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    bible=read_json(args.bible)
    parts=list(range(args.start,args.end+1)); results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs={ex.submit(fetch_one,p,bible):p for p in parts}
        done=0
        for fut in concurrent.futures.as_completed(futs):
            r=fut.result(); results.append(r); done+=1
            if done % 100 == 0 or not r.get('ok'):
                print(json.dumps({'done':done,'total':len(parts),'last_part':r.get('part'),'ok':r.get('ok'),'error':r.get('error')},ensure_ascii=False),flush=True)
    results.sort(key=lambda x:x['part'])
    failed=[r for r in results if not r.get('ok')]
    # One sequential recovery pass for any failed URLs.
    if failed:
        recovered=[]
        for old in failed:
            r=fetch_one(old['part'],bible,retries=6); recovered.append(r); print({'recovery':old['part'],'ok':r.get('ok')},flush=True)
        by={r['part']:r for r in results}
        for r in recovered: by[r['part']]=r
        results=[by[p] for p in parts]; failed=[r for r in results if not r.get('ok')]
    manifest={'story':'Vương Bài Tiến Hóa','source':'TiênVuc','requested':len(parts),'ok':len(parts)-len(failed),'failed':len(failed),'failed_parts':[x['part'] for x in failed],'total_chars':sum(x.get('chars',0) for x in results),'story_bible_version':bible.get('version')}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    if failed:
        print(json.dumps(manifest,ensure_ascii=False)); raise SystemExit(2)
    # QA before packaging.
    issues=[]
    known_bad=['Chương trước','Chương sau','Tiên Vực\n','Đăng nhập']
    for r in results:
        for bad in known_bad:
            if bad in r['body']: issues.append({'part':r['part'],'type':'boilerplate','value':bad})
        if r['chars'] < 700: issues.append({'part':r['part'],'type':'short','chars':r['chars']})
    qa={'checked':len(results),'issues':issues,'issue_count':len(issues),'min_chars':min(r['chars'] for r in results),'max_chars':max(r['chars'] for r in results),'avg_chars':round(sum(r['chars'] for r in results)/len(results),1)}
    (out/'qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
    # Save compact chapter metadata, not prose duplication.
    meta=[{k:r[k] for k in ('part','url','title','chars','sha256')} for r in results]
    (out/'chapters.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    epub=build_epub(results,out/'Vuong_Bai_Tien_Hoa_TienVuc_BienTap.epub')
    print(json.dumps({'epub':str(epub),'size':epub.stat().st_size,'qa_issues':len(issues),**manifest},ensure_ascii=False),flush=True)

if __name__=='__main__': main()
