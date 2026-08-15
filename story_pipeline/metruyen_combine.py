#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from story_pipeline import metruyen_full as core


def clean_text(text,bible):
    text=unicodedata.normalize('NFC',text or '')
    text=core.normalize_entities(text,bible)
    text=text.replace('part-time','làm thêm').replace('Part-time','Làm thêm')
    text=text.replace(' . . . . ','…').replace('. . . .','…').replace('. . .','…').replace('……','…')
    text=re.sub(r'[ \t]+([,.;:!?])',r'\1',text)
    text=re.sub(r'([,.;:!?])(?=[A-Za-zÀ-ỹĐđ])',r'\1 ',text)
    text=re.sub(r'[ \t]{2,}',' ',text)
    text=re.sub(r'\n{3,}','\n\n',text)
    return text.strip()


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--out',required=True); ap.add_argument('--bible',required=True)
    args=ap.parse_args(); root=Path(args.input); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    bible=core.read_json(args.bible)
    pages=[]
    for p in sorted(root.rglob('page-*.json')):
        d=json.loads(p.read_text(encoding='utf-8'))
        if d.get('failed'): raise SystemExit(f"batch has failures: {p}: {d['failed']}")
        pages.append(d)
    if len(pages)!=13: raise SystemExit(f"expected 13 batch files, got {len(pages)}")
    pages.sort(key=lambda d:d['page'])
    raw=[]; empty=[]
    for d in pages:
        for r in sorted(d['records'],key=lambda x:x['page_pos']):
            if r.get('empty_terminal_shell'):
                empty.append(r['url']); continue
            raw.append(r)
    if len(raw)!=1212: raise SystemExit(f"expected 1212 content chapters, got {len(raw)}, empty={empty}")
    if len(empty)!=2: raise SystemExit(f"expected exactly two verified terminal shells, got {empty}")

    volume=1; prev=None; records=[]
    for seq,r in enumerate(raw,start=1):
        m=re.search(r'Chương\s*0*(\d+)',r.get('site_title',''),re.I)
        site_no=int(m.group(1)) if m else None
        if site_no is not None and prev is not None and site_no<prev and site_no<=5: volume+=1
        body=clean_text(r['body'],bible)
        rec={**r,'seq':seq,'volume':volume,'site_no':site_no,'body':body,'chars':len(body),'sha256':hashlib.sha256(body.encode('utf-8')).hexdigest()}
        records.append(rec)
        if site_no is not None: prev=site_no

    issues=[]; seen={}
    for r in records:
        if r['chars']<500: issues.append({'seq':r['seq'],'type':'short','chars':r['chars']})
        for marker in ['Tải Ebook','Truyện Hot Mới','Bạn có thể dùng phím','《 Chương trước']:
            if marker in r['body']: issues.append({'seq':r['seq'],'type':'boilerplate','value':marker})
        if r['sha256'] in seen: issues.append({'seq':r['seq'],'type':'duplicate_body','same_as':seen[r['sha256']]})
        else: seen[r['sha256']]=r['seq']

    manifest={'story':'Vương Bài Tiến Hóa','author':'Quyển Thổ','source':'MeTruyen','reference_master':'TTV count/title structure','content_chapters':len(records),'ignored_empty_terminal_shells':empty,'volumes_inferred':volume,'story_bible_version':bible.get('version'),'total_chars':sum(r['chars'] for r in records),'failed':0,'ok':len(records),'requested':len(records),'index_chapters':len(records)}
    qa={'checked':len(records),'issue_count':len(issues),'issues':issues,'min_chars':min(r['chars'] for r in records),'max_chars':max(r['chars'] for r in records),'avg_chars':round(sum(r['chars'] for r in records)/len(records),1)}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
    meta=[{k:r.get(k) for k in ('seq','volume','site_no','site_title','url','final_url','chars','sha256')} for r in records]
    (out/'chapters.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    picks=[1,2,3,len(records)//2,len(records)//2+1,len(records)-2,len(records)-1,len(records)]
    by={r['seq']:r for r in records}; samples=[]
    for seq in sorted(set(picks)):
        r=by[seq]; samples.append(f"{'='*72}\n{core.chapter_label(r)}\n{'='*72}\n\n{r['body']}")
    (out/'sample_spread.txt').write_text('\n\n'.join(samples),encoding='utf-8')
    epub=core.build_epub(records,out/'Vuong_Bai_Tien_Hoa_MeTruyen_BienTap.epub')
    print(json.dumps({'epub':str(epub),'epub_bytes':epub.stat().st_size,'qa_issues':len(issues),**manifest},ensure_ascii=False),flush=True)

if __name__=='__main__': main()
