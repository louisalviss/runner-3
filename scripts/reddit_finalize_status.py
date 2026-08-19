#!/usr/bin/env python3
import datetime,json,os
from pathlib import Path

outdir=Path(os.environ.get('OUTDIR','artifacts/reddit-unsolved'))
base_url=''
try:
    base_url=json.loads(Path('ops/r2-media/status.json').read_text(encoding='utf-8')).get('baseUrl','')
except Exception:
    pass
prefix=os.environ.get('PREFIX','listen/reddit-creepiest-unsolved-v1')
steps={
    'install':os.environ.get('INSTALL_OUTCOME','unknown'),
    'redditFetch':os.environ.get('FETCH_OUTCOME','unknown'),
    'render':os.environ.get('RENDER_OUTCOME','unknown'),
    'publish':os.environ.get('PUBLISH_OUTCOME','unknown'),
}
ready=steps['publish']=='success'
duration=None; case_count=None
try:
    ch=json.loads((outdir/'chapters.json').read_text(encoding='utf-8'))
    if ch.get('duration_seconds') is not None: duration=float(ch['duration_seconds'])
    if isinstance(ch.get('selected_cases'),list): case_count=len(ch['selected_cases'])
except Exception:
    pass
obj={
    'status':'ready' if ready else 'failed',
    'episodeId':'reddit-creepiest-unsolved-v1',
    'playerUrl':f'{base_url}/{prefix}/index.html' if ready and base_url else '',
    'audioUrl':f'{base_url}/{prefix}/episode.mp3' if ready and base_url else '',
    'voice':'vi-VN-NamMinhNeural',
    'resume':'localStorage/same-browser',
    'steps':steps,
    'durationSeconds':duration,
    'caseCount':case_count,
    'updatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
p=Path('ops/reddit-narrator/latest.json'); p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(obj,ensure_ascii=False))
