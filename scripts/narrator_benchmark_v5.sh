#!/usr/bin/env bash
set +e
mkdir -p artifacts/runner3-narrator-v5 work/voice work/scenes
LOG=artifacts/runner3-narrator-v5/render.log
exec > >(tee "$LOG") 2>&1
STATUS=0

echo "START=$(date -u +%FT%TZ)"

echo '--- download assets ---'
if ! curl -L --fail --retry 3 'https://download.blender.org/durian/trailer/sintel_trailer-720p.mp4' -o work/source.mp4; then
  curl -L --fail --retry 3 'https://archive.org/download/namakura-gatana-1917/Namakura%20Gatana%201917%20restoration.mp4' -o work/source.mp4 || STATUS=$?
fi
curl -L --fail --retry 3 'https://archive.org/download/jamendo-621715/01-2294083-Waveloom-TikTok%20Phonk.mp3' -o work/bgm.mp3 || true
curl -L --fail --retry 3 'https://opengraph.githubassets.com/1/NarratorAI-Studio/narrator-ai-cli' -o work/repo-card.png || true
ffprobe -v error -show_entries format=duration,size -of default=nw=1 work/source.mp4 || STATUS=$?

if [ "$STATUS" -eq 0 ]; then
python - <<'PY' || STATUS=$?
import json, subprocess, os
lines=[
 "Bản trước tệ vì nó chỉ là slide ghép bằng FFmpeg.",
 "Runner ba cho phép dùng footage thật, neural voice, nhạc nền và dựng video dọc có chuyển động.",
 "Đây vẫn chưa phải backend Narrator AI vì chưa có API key của dịch vụ đó.",
 "Nhưng runner có Internet và môi trường Linux đầy đủ, nên execution mạnh hơn rõ rệt.",
 "Nếu footage và voice đầu vào tốt, chất lượng có thể tăng mạnh. Runner giải quyết phần máy móc, không thay thế chất lượng nguồn."
]
def run(cmd):
    print('+',' '.join(map(str,cmd)),flush=True)
    subprocess.check_call(cmd)
meta=[]
for i,text in enumerate(lines,1):
    out=f'work/voice/v{i}.mp3'
    try:
        run(['edge-tts','--voice','vi-VN-HoaiMyNeural','--rate=+14%','--text',text,'--write-media',out])
        if os.path.getsize(out)<1000: raise RuntimeError('tiny edge output')
    except Exception as e:
        print('edge-tts failed, fallback espeak:',e)
        wav=f'work/voice/v{i}.wav'
        run(['espeak-ng','-v','vi','-s','165','-w',wav,text])
        run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',wav,'-c:a','libmp3lame','-b:a','128k',out])
    dur=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',out],text=True).strip())
    meta.append({'i':i,'text':text,'duration':dur})
srcdur=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0','work/source.mp4'],text=True).strip())
starts=[5.0,srcdur*.18,srcdur*.36,srcdur*.54,srcdur*.72]
for m,start in zip(meta,starts):
    i=m['i']; dur=m['duration']+.10
    start=min(max(0,start),max(0,srcdur-dur-.2))
    vf=("scale=-2:1920," "crop=1080:1920:x='(iw-ow)/2+18*sin(0.5*t)':y=0," "eq=contrast=1.10:saturation=1.08:brightness=-0.015," "unsharp=5:5:0.45:5:5:0.0,vignette=PI/5,fps=30,format=yuv420p")
    run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',f'{start:.2f}','-i','work/source.mp4','-t',f'{dur:.3f}','-an','-vf',vf,'-c:v','libx264','-preset','veryfast','-crf','21',f'work/scenes/s{i}.mp4'])
if os.path.exists('work/repo-card.png') and os.path.getsize('work/repo-card.png')>1000:
    dur=meta[2]['duration']+.10
    run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i','work/scenes/s3.mp4','-loop','1','-i','work/repo-card.png','-t',f'{dur:.3f}','-filter_complex',"[1:v]scale=900:-2,format=rgba,colorchannelmixer=aa=0.95[card];[0:v][card]overlay=(W-w)/2:(H-h)/2-80",'-an','-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p','work/scenes/s3x.mp4'])
    os.replace('work/scenes/s3x.mp4','work/scenes/s3.mp4')
with open('work/video.txt','w') as f:
    [f.write(f"file 'scenes/s{i}.mp4'\n") for i in range(1,6)]
with open('work/audio.txt','w') as f:
    [f.write(f"file 'voice/v{i}.mp3'\n") for i in range(1,6)]
def stamp(x):
    h=int(x//3600); x-=h*3600; mm=int(x//60); x-=mm*60; s=int(x); ms=int(round((x-s)*1000))
    if ms>=1000: s+=1; ms=0
    return f'{h:02}:{mm:02}:{s:02},{ms:03}'
t=0.0
with open('work/subs.srt','w',encoding='utf-8') as f:
    for idx,m in enumerate(meta,1):
        f.write(f"{idx}\n{stamp(t)} --> {stamp(t+m['duration'])}\n{m['text']}\n\n")
        t+=m['duration']+.10
json.dump(meta,open('work/meta.json','w'),ensure_ascii=False,indent=2)
PY
fi

if [ "$STATUS" -eq 0 ]; then
  (cd work && ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i video.txt -c copy visual.mp4) || STATUS=$?
  (cd work && ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i audio.txt -c:a aac -b:a 192k narration.m4a) || STATUS=$?
fi

if [ "$STATUS" -eq 0 ]; then
  DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 work/visual.mp4)
  if [ -s work/bgm.mp3 ]; then
    ffmpeg -hide_banner -loglevel error -y -i work/visual.mp4 -i work/narration.m4a -ss 8 -stream_loop -1 -i work/bgm.mp3 \
      -filter_complex "[0:v]drawbox=x=0:y=0:w=iw:h=160:color=black@0.20:t=fill,drawtext=font='Noto Sans':text='RUNNER-3 VIDEO TEST':fontcolor=white:fontsize=42:x=58:y=54,subtitles=work/subs.srt:force_style='FontName=Noto Sans,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H90000000,BorderStyle=3,BackColour=&H78000000,Outline=1,Shadow=0,MarginV=145,Alignment=2'[v];[1:a]volume=1.0[voice];[2:a]volume=0.08,highpass=f=60,lowpass=f=12000[bg];[voice][bg]amix=inputs=2:duration=first:dropout_transition=2,alimiter=limit=0.94[a]" \
      -map '[v]' -map '[a]' -t "$DUR" -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 160k -movflags +faststart artifacts/runner3-narrator-v5/video.mp4 || STATUS=$?
  else
    ffmpeg -hide_banner -loglevel error -y -i work/visual.mp4 -i work/narration.m4a \
      -filter_complex "[0:v]drawtext=font='Noto Sans':text='RUNNER-3 VIDEO TEST':fontcolor=white:fontsize=42:x=58:y=54,subtitles=work/subs.srt:force_style='FontName=Noto Sans,FontSize=18,BorderStyle=3,BackColour=&H78000000,MarginV=145,Alignment=2'[v]" \
      -map '[v]' -map 1:a:0 -t "$DUR" -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 160k -movflags +faststart artifacts/runner3-narrator-v5/video.mp4 || STATUS=$?
  fi
fi

echo "STATUS=$STATUS" | tee artifacts/runner3-narrator-v5/status.txt
echo "END=$(date -u +%FT%TZ)" | tee -a artifacts/runner3-narrator-v5/status.txt
if [ -s artifacts/runner3-narrator-v5/video.mp4 ]; then
  ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate -show_entries format=duration,size -of default=nw=1 artifacts/runner3-narrator-v5/video.mp4 | tee artifacts/runner3-narrator-v5/probe.txt
fi
exit 0
