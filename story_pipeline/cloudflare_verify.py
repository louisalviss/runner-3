import json, pathlib, re, sys

LOCKED = ['Phương Lâm','Mộng Yểm Không Gian','Yagami Iori','Kusanagi Kyo','Nest Sound']

def nums(s): return re.findall(r'(?<!\w)\d+(?:[.,]\d+)?(?!\w)', s)

def main():
    src=pathlib.Path('story_pipeline/benchmark_input')
    out=pathlib.Path('story_pipeline/benchmark_output')
    rows=[]; failed=False
    for rawf in sorted(src.glob('*.txt'))[:3]:
        editf=out/rawf.name
        if not editf.exists():
            rows.append({'file':rawf.name,'pass':False,'error':'missing output'}); failed=True; continue
        raw=rawf.read_text(encoding='utf-8'); edit=editf.read_text(encoding='utf-8')
        missing=[x for x in LOCKED if x in raw and x not in edit]
        nraw, nedit=nums(raw), nums(edit)
        ratio=len(edit)/max(1,len(raw))
        ok=(not missing and nraw==nedit and 0.65 <= ratio <= 1.45 and len(edit.strip())>80)
        rows.append({'file':rawf.name,'pass':ok,'length_ratio':round(ratio,3),'missing_locked_terms':missing,'numbers_raw':nraw,'numbers_edited':nedit})
        failed |= not ok
    (out/'qc.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(rows,ensure_ascii=False,indent=2))
    if failed: sys.exit(2)

if __name__=='__main__': main()
