#!/usr/bin/env python3
import json, re, subprocess, sys, tempfile
from pathlib import Path
from urllib.parse import urlparse
import requests

ROOT=Path(__file__).resolve().parents[1]
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36'

def run(cmd, **kw):
    return subprocess.run(cmd, text=True, capture_output=True, **kw)

def media_urls(obj):
    out=[]
    def walk(x):
        if isinstance(x,dict):
            for v in x.values(): walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
        elif isinstance(x,str) and ('video.twimg.com' in x or '.mp4' in x):
            u=x.replace('\\/','/')
            if u.startswith('http') and u not in out: out.append(u)
    walk(obj); return out

def inspect(url:str):
    m=re.search(r'/status/(\d+)',url)
    if not m: return None
    tid=m.group(1); out=ROOT/'evidence'/'x-video-inspect'/tid
    if out.exists():
        import shutil; shutil.rmtree(out)
    (out/'frames').mkdir(parents=True,exist_ok=True)
    (out/'source-url.txt').write_text(url+'\n')
    report={'id':tid,'url':url,'attempts':[]}
    with tempfile.TemporaryDirectory(prefix='x-video-') as td:
        td=Path(td); video=None; meta={}
        p=run([sys.executable,'-m','yt_dlp','--dump-single-json','--skip-download','--no-warnings',url],timeout=90)
        report['attempts'].append({'method':'yt-dlp-meta','rc':p.returncode,'stderr':p.stderr[-1200:]})
        if p.returncode==0:
            try: meta=json.loads(p.stdout); (out/'yt-dlp-info.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
            except Exception: pass
        p=run([sys.executable,'-m','yt_dlp','--no-playlist','--no-warnings','-f','bv*+ba/b','--merge-output-format','mp4','-o',str(td/'source.%(ext)s'),url],timeout=180)
        report['attempts'].append({'method':'yt-dlp-download','rc':p.returncode,'stderr':p.stderr[-1600:]})
        candidates=[x for x in td.glob('source.*') if x.suffix.lower() in {'.mp4','.webm','.mkv','.mov'}]
        if candidates: video=max(candidates,key=lambda x:x.stat().st_size)
        if video is None:
            found=[]
            for name,ep in [('fxtwitter',f'https://api.fxtwitter.com/status/{tid}'),('vxtwitter',f'https://api.vxtwitter.com/Twitter/status/{tid}')]:
                try:
                    r=requests.get(ep,headers={'User-Agent':UA,'Accept':'application/json'},timeout=35)
                    report['attempts'].append({'method':name,'http':r.status_code,'bytes':len(r.content)})
                    (out/f'{name}-response.txt').write_text(r.text,errors='ignore')
                    if r.ok:
                        try:
                            obj=r.json(); (out/f'{name}.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2)); found += media_urls(obj)
                        except Exception: pass
                except Exception as e: report['attempts'].append({'method':name,'error':repr(e)})
            (out/'media-urls.json').write_text(json.dumps(list(dict.fromkeys(found)),indent=2))
            for u in reversed(list(dict.fromkeys(found))):
                try:
                    r=requests.get(u,headers={'User-Agent':UA},timeout=60)
                    if r.ok and len(r.content)>10000:
                        video=td/'source.mp4'; video.write_bytes(r.content); report['downloaded_media_url']=u; break
                except Exception as e: report['attempts'].append({'method':'media-url','error':repr(e)})
        if video is None:
            report['status']='NO_VIDEO'; (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)); return out
        probe=run(['ffprobe','-v','error','-show_entries','format=duration,size','-show_entries','stream=codec_name,width,height,r_frame_rate','-of','json',str(video)],timeout=30)
        (out/'meta.json').write_text(probe.stdout or '{}')
        try: duration=float(json.loads(probe.stdout)['format']['duration'])
        except Exception: duration=0.0
        report['status']='VIDEO_OK'; report['source_bytes']=video.stat().st_size; report['duration']=duration
        if meta:
            report['post']={k:meta.get(k) for k in ['title','description','uploader','uploader_id','timestamp','duration','width','height','view_count','like_count','repost_count','comment_count','webpage_url'] if meta.get(k) is not None}
        if duration>0:
            fracs=[.005,.04,.08,.13,.19,.26,.34,.42,.50,.58,.66,.74,.82,.89,.95,.99]
            for i,f in enumerate(fracs,1):
                t=max(0,min(duration-.03,duration*f))
                subprocess.run(['ffmpeg','-loglevel','error','-y','-ss',f'{t:.3f}','-i',str(video),'-frames:v','1','-q:v','2',str(out/'frames'/f'frame-{i:02d}.jpg')])
            subprocess.run(['ffmpeg','-loglevel','error','-y','-i',str(video),'-vf','fps=1/2,scale=480:-1,tile=4x4','-frames:v','1',str(out/'contact-sheet.jpg')])
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return out

if __name__=='__main__':
    for u in sys.argv[1:]:
        if (urlparse(u).hostname or '').lower() in {'x.com','www.x.com','twitter.com','www.twitter.com'}:
            p=inspect(u); print(str(p) if p else '')
