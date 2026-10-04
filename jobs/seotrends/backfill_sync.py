#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, pathlib, shutil, subprocess, tarfile
from datetime import datetime, timezone

BASE=pathlib.Path('/var/lib/seotrends-public')
SCANS=BASE/'scans'
CHANGES=BASE/'changes'
REPORT=BASE/'backfill-repair-latest.json'
STATE=BASE/'telegram-backfill-sync-state.json'
UPLOAD_ROOT=pathlib.Path('/var/lib/telegram-upload/seotrends/backfill')
WRAPPER='/opt/telegram-mtproto/run-secure.sh'
TARGET='-1004357761890'
ALLOWED=[
    ('changes','{day}-added.txt','added.txt'),
    ('changes','{day}-removed.txt','removed.txt'),
    ('scans','{day}-candidates.jsonl','candidates.jsonl'),
    ('scans','{day}-candidates.csv','candidates.csv'),
    ('scans','{day}-shortlist.md','shortlist.md'),
    ('scans','{day}-semrush-results.md','semrush-results.md'),
    ('scans','{day}-terminal-verdicts.json','terminal-verdicts.json'),
    ('scans','{day}-terminal-verdicts.md','terminal-verdicts.md'),
]
def load(p):
    try:return json.loads(p.read_text(encoding='utf-8'))
    except Exception:return {}
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def atomic(p,obj):
    t=p.with_suffix(p.suffix+'.tmp'); t.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); t.replace(p)
def main():
    rep=load(REPORT); changed=[r for r in rep.get('report') or [] if r.get('changed')]
    if not changed:
        print(json.dumps({'status':'NOOP','reason':'no_changed_dates'})); return 0
    manifest={'schema':'seotrends-derived-backfill-v1','source_report_generated_at':rep.get('generated_at'),'days':[]}
    source_map={}
    for r in changed:
        day=r['date']; files=[]
        for root,tpl,dest in ALLOWED:
            src=(CHANGES if root=='changes' else SCANS)/tpl.format(day=day)
            if src.exists() and src.is_file():
                files.append({'name':dest,'sha256':sha(src),'size':src.stat().st_size}); source_map[(day,dest)]=src
        term=load(SCANS/f'{day}-terminal-verdicts.json')
        manifest['days'].append({'date':day,'semrush_before':r.get('before'),'semrush_after':r.get('after'),'terminal_before':r.get('terminal_before'),'terminal_after':r.get('terminal_after'),'terminal_counts':term.get('counts') or {},'files':files})
    canon=json.dumps(manifest,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    fp=hashlib.sha256(canon).hexdigest()
    if load(STATE).get('fingerprint')==fp:
        print(json.dumps({'status':'NOOP','reason':'already_synced','fingerprint':fp})); return 0
    stage=UPLOAD_ROOT/fp[:16]; stage.mkdir(parents=True,exist_ok=True)
    for d in manifest['days']:
        dd=stage/d['date']; dd.mkdir(parents=True,exist_ok=True)
        for f in d['files']: shutil.copy2(source_map[(d['date'],f['name'])],dd/f['name'])
    (stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    archive=stage/f'seotrends-derived-backfill-{manifest["days"][0]["date"]}-to-{manifest["days"][-1]["date"]}.tar.gz'
    with tarfile.open(archive,'w:gz') as tf:
        tf.add(stage/'manifest.json',arcname='manifest.json')
        for d in manifest['days']:
            tf.add(stage/d['date'],arcname=d['date'])
    archive_sha=sha(archive)
    caption=f'SeoTrends derived correction/backfill {manifest["days"][0]["date"]}..{manifest["days"][-1]["date"]} | days={len(manifest["days"])} | sha256={archive_sha}'
    up=subprocess.run([WRAPPER,'upload-local',TARGET,str(archive),caption],text=True,capture_output=True,timeout=600)
    if up.returncode: raise RuntimeError('TELEGRAM_UPLOAD_FAIL:'+(up.stderr or up.stdout or '')[-500:])
    lines=[f'SeoTrends BACKFILL SYNC | {len(manifest["days"])} corrected day(s) | public + derived summaries only']
    for d in manifest['days']:
        c=d.get('terminal_counts') or {}
        lines.append(f'{d["date"]}: Semrush {d.get("semrush_before")}→{d.get("semrush_after")}; terminal {d.get("terminal_before")}→{d.get("terminal_after")}; BUILD={c.get("BUILD",0)} WATCH={c.get("WATCH",0)} DROP={c.get("DROP",0)} BLOCKED={c.get("BLOCKED",0)}')
    lines.append(f'sha256={archive_sha}')
    msg='\n'.join(lines)
    send=subprocess.run([WRAPPER,'send',TARGET,msg],text=True,capture_output=True,timeout=120)
    if send.returncode: raise RuntimeError('TELEGRAM_SEND_FAIL:'+(send.stderr or send.stdout or '')[-500:])
    atomic(STATE,{'fingerprint':fp,'archive_sha256':archive_sha,'synced_at':datetime.now(timezone.utc).isoformat(),'days':[d['date'] for d in manifest['days']]})
    print(json.dumps({'status':'PASS','days':[d['date'] for d in manifest['days']],'fingerprint':fp,'archive':str(archive),'archive_sha256':archive_sha},ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
