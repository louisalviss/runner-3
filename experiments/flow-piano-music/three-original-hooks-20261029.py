
"""Flow Piano Music | 3 original 8-second hook auditions.
This is a deliberate short-form audition, not a 30-second algorithmic extension.
Do not promote any candidate before user listening feedback.
"""
import json,hashlib,math,struct,os,subprocess,ctypes as C,ctypes.util
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile

ROOT=Path('/tmp/flow-piano-music-hook-auditions-20261029');ROOT.mkdir(parents=True,exist_ok=True)
SF='/opt/flow-piano-music/assets/SalamanderGrandPiano-SF2-V3+20200602/SalamanderGrandPiano-V3+20200602.sf2'
assert Path(SF).is_file()
SR=44100;BPM=128;BEAT=60/BPM;BAR=4*BEAT;LEN=8.;TOTAL_BARS=4

# Explicit harmonic voicing and melody written per bar. No random motif generator.
# Note tuple = beat-position in bar, MIDI pitch, length beats, velocity.
DATA=[
 {'id':'A','title':'Falling Into Dawn','mood':'bittersweet, soft answer',
  'chords':[
    ('F#m9',42,49,[57,61,64,68]),
    ('Dmaj9',38,45,[54,57,61,64]),
    ('Aadd9',45,52,[56,61,64,71]),
    ('E7sus9',40,47,[56,59,62,69]),
   ],
  'melodies':[
    [(0.12,73,.86,88),(1.32,71,.44,73),(2.15,69,.96,82)],
    [(0.13,78,.72,95),(1.32,76,.43,72),(2.25,73,.88,82)],
    [(0.12,76,.72,93),(1.34,73,.43,72),(2.15,71,.93,81)],
    [(0.14,78,.66,94),(1.33,76,.47,77),(2.14,74,1.03,80)],
  ],
  'restrikes':[[2.97],[3.04],[2.92],[2.97]]
 },
 {'id':'B','title':'One More Summer','mood':'nostalgic, open upper chord hook',
  'chords':[
    ('Bbadd9',46,53,[58,62,65]),
    ('F/A',45,48,[57,60,65]),
    ('Gm7',43,50,[58,62,65]),
    ('Ebmaj9',39,46,[55,62,65,70]),
  ],
  'melodies':[
    [(0.08,77,.81,94),(1.12,75,.35,71),(1.93,74,.94,84)],
    [(0.12,72,.60,87),(1.10,74,.42,77),(2.12,69,1.02,86)],
    [(0.10,70,.60,84),(1.10,74,.40,76),(2.08,77,1.06,91)],
    [(0.07,79,.76,94),(1.28,77,.36,76),(2.16,74,1.05,87)]
  ],
  'restrikes':[[1.78,2.90],[2.92],[2.85],[2.86]]
 },
 {'id':'C','title':'Electric Memory','mood':'lively, syncopated, immediate hook',
  'chords':[
    ('C#m9',49,56,[64,68,71]),
    ('Aadd9',45,52,[61,64,71]),
    ('Eadd9/G#',44,47,[64,68,71]),
    ('Bsus4-to-B',47,54,[59,64,66]),
  ],
  'melodies':[
    [(0.09,76,.50,91),(.85,80,.64,95),(2.30,78,.82,84)],
    [(.09,78,.48,93),(.89,76,.59,84),(2.28,73,.85,86)],
    [(.08,80,.52,96),(.85,78,.59,86),(2.30,76,.82,90)],
    [(.10,78,.56,95),(.88,75,.57,84),(2.16,73,.42,82),(3.03,71,.53,77)]
  ],
  'restrikes':[[1.78,3.06],[1.74,3.06],[1.77,3.08],[2.73]]
 }
]

def render_one(item):
 events=[]
 def add(t,d,p,v,ch,kind):
  d=min(d,7.89-t)
  if d<=.04:return
  assert 0<=t<8 and 30<=p<=84 and 15<=v<=127
  events.append({'time':round(t,5),'duration':round(d,5),'pitch':p,'velocity':v,'ch':ch,'kind':kind})
 for bar,(label,bass,fifth,mid) in enumerate(item['chords']):
  start=bar*BAR
  # Quiet left-hand bass: the most common complaint was thuddy and mechanical sound.
  add(start+.01,BAR*.85,bass,50 if bar!=3 else 47,0,'bass')
  add(start+BEAT*2.50,BEAT*1.01,fifth,37,0,'fifth')
  # Spread middle chord low-to-high. Envelopes overlap as in piano sample video.
  for j,p in enumerate(mid):
   add(start+.050+j*.032,BAR*.74,p,57+3*j+(3 if bar==2 else 0),1,'sustain')
  for beat in item['restrikes'][bar]:
   for j,p in enumerate(mid[-3:-1]):
    add(start+BEAT*beat+j*.008,BEAT*.23,p,43+5*j,3,'chord-pulse')
  for beat,p,d,v in item['melodies'][bar]:
   add(start+BEAT*beat,BEAT*d,p,v,2,'hook')
 # Distinct variants can have small space at boundaries to avoid smear.
 events.sort(key=lambda n:(n['time'],n['pitch']))
 lib=C.CDLL(ctypes.util.find_library('fluidsynth'))
 VP=C.c_void_p;I=C.c_int;F=C.c_double
 def f(name,rt,args):
  fun=getattr(lib,name);fun.restype=rt;fun.argtypes=args;return fun
 settings=f('new_fluid_settings',VP,[])()
 f('fluid_settings_setnum',I,[VP,C.c_char_p,F])(settings,b'synth.sample-rate',SR)
 f('fluid_settings_setnum',I,[VP,C.c_char_p,F])(settings,b'synth.gain',.33)
 fi=f('fluid_settings_setint',I,[VP,C.c_char_p,I])
 fi(settings,b'synth.polyphony',152)
 fi(settings,b'synth.reverb.active',0)
 fi(settings,b'synth.chorus.active',0)
 synth=f('new_fluid_synth',VP,[VP])(settings)
 sid=f('fluid_synth_sfload',I,[VP,C.c_char_p,I])(synth,SF.encode(),1)
 assert sid>=0
 program=f('fluid_synth_program_select',I,[VP,I,I,I,I])
 for ch in range(4):program(synth,ch,sid,0,0)
 on=f('fluid_synth_noteon',I,[VP,I,I,I])
 off=f('fluid_synth_noteoff',I,[VP,I,I])
 cc=f('fluid_synth_cc',I,[VP,I,I,I])
 write=f('fluid_synth_write_float',I,[VP,I,VP,I,I,VP,I,I])
 tr=[]
 # Pedal gently lifted before each change; stops audible chord bleed.
 for bar in range(4):
  begin=bar*BAR
  for ch in range(4):
   tr.append((round((begin+.037)*SR),2,64,75,ch))
   tr.append((round((begin+BAR-.091)*SR),2,64,0,ch))
 for e in events:
  t=e['time']
  delay=.002 if e['ch']==0 else .008 if e['ch']==2 else .005
  start=round((t+delay)*SR);end=round(min(7.94,t+delay+e['duration'])*SR)
  tr.extend([(start,1,e['pitch'],e['velocity'],e['ch']),
             (end,0,e['pitch'],0,e['ch'])])
 tr.sort(key=lambda e:(e[0],e[1]))
 N=round(8*SR)
 left=np.zeros(N,dtype='float32');right=np.zeros(N,dtype='float32')
 index=pos=0
 while pos<N:
  while index<len(tr) and tr[index][0]<=pos:
   _,kind,p,v,ch=tr[index]
   if kind==0:off(synth,ch,p)
   elif kind==1:on(synth,ch,p,v)
   else:cc(synth,ch,p,v)
   index+=1
  limit=min(N,pos+4096,tr[index][0] if index<len(tr) else N)
  if limit<=pos:limit=pos+1
  write(synth,limit-pos,VP(left[pos:limit].ctypes.data),0,1,VP(right[pos:limit].ctypes.data),0,1)
  pos=limit
 audio=np.stack((left,right),axis=1).astype('float64')
 # Concert A+ style: subtract very low thump, preserve bright top tone.
 audio=signal.sosfilt(signal.butter(2,46,btype='highpass',fs=SR,output='sos'),audio,axis=0)
 def bell(x,freq,q,g):
  A=10**(g/40);w=2*np.pi*freq/SR;alpha=np.sin(w)/(2*q)
  b=np.array([1+alpha*A,-2*np.cos(w),1-alpha*A]);a=np.array([1+alpha/A,-2*np.cos(w),1-alpha/A])
  return signal.lfilter(b/a[0],a/a[0],x,axis=0)
 audio=bell(audio,150,.9,-1.7)
 audio=bell(audio,2050,.82,1.05)
 dry=audio.copy()
 for ch in range(2):
  for delay,gain in [(0.031,.061),(.072,.044),(.133,.029)]:
   i=round((delay+.006*ch)*SR)
   audio[i:,ch]+=dry[:-i,1-ch]*gain
 # very short room, deliberately not dramatic reverb
 rng=np.random.default_rng(4026)
 k=round(.65*SR)
 ir=rng.normal(0,1,(k,2))*np.exp(-np.arange(k)[:,None]/(SR*.13))
 ir[:round(.045*SR),:]=0
 ir*=.0008/max(abs(ir).max(),.001)
 for ch in range(2):
  audio[:,ch]+=signal.fftconvolve(dry[:,ch],ir[:,ch],mode='full')[:N]
 # Last note may continue after this 8s audition; fade only short last .22s
 fade=round(.20*SR);audio[-fade:]*=np.linspace(1,0,fade)[:,None]
 audio*=.74/max(float(abs(audio).max()),.001)
 assert np.isfinite(audio).all()
 tag=item['id']+'_'+item['title'].replace(' ','_')
 wav=ROOT/(tag+'.wav');mp3=ROOT/(tag+'.mp3')
 wavfile.write(str(wav),SR,(np.clip(audio,-1,1)*32767).astype('int16'))
 proc=subprocess.run(['ffmpeg','-loglevel','error','-y','-i',str(wav),
 '-af','loudnorm=I=-17:TP=-2.8:LRA=11,volume=-1.1dB,alimiter=limit=0.87:attack=5:release=85',
 '-codec:a','libmp3lame','-b:a','224k',str(mp3)],capture_output=True,text=True,timeout=32)
 if proc.returncode:raise RuntimeError(proc.stderr[-300:])
 return {'id':item['id'],'title':item['title'],'duration':8,'melody_count':sum(n['kind']=='hook' for n in events),
 'note_events':events,'chords':[x[0] for x in item['chords']],
 'mp3':str(mp3),'mp3_bytes':mp3.stat().st_size,
 'mp3_sha256':hashlib.sha256(mp3.read_bytes()).hexdigest(),
 'source':'original eight-second handmade motif; not copied from TikTok; no claim of musical acceptance'}

result=[render_one(item) for item in DATA]
# Continuous audition reel: 8s A / 0.65s pause / 8s B / 0.65s pause / 8s C
samples=[]
for r in result:
 w=ROOT/(r['id']+'_'+r['title'].replace(' ','_')+'.wav')
 rate,y=wavfile.read(str(w))
 assert rate==SR
 samples.append(y.astype('float64')/32768)
gap=np.zeros((round(.65*SR),2),dtype='float64')
joined=np.concatenate([samples[0],gap,samples[1],gap,samples[2]],axis=0)
reelwav=ROOT/'ABC_Piano_Hook_Listen_Comparison.wav'
wavfile.write(str(reelwav),SR,(np.clip(joined,-1,1)*32767).astype('int16'))
reelmp3=ROOT/'ABC_Piano_Hook_Listen_Comparison.mp3'
p=subprocess.run(['ffmpeg','-v','error','-y','-i',str(reelwav),'-codec:a','libmp3lame','-b:a','224k',str(reelmp3)],capture_output=True,text=True,timeout=45)
if p.returncode:raise RuntimeError(p.stderr[-220:])
meta={'name':'Flow Piano Music — original 8s hook auditions','date':'2026-10-29',
 'review':'PENDING USER LISTENING','why':'Previous two formula-composed 30s songs failed; try 3 short handmade distinct motifs before any video.',
 'sound':'Salamander Concert A+ sampled grand piano','candidates':result,
 'reel':{'duration':25.3,'sha256':hashlib.sha256(reelmp3.read_bytes()).hexdigest()},
 'independent_source':'Original note events created for each variant; no copyrighted TikTok melody copied'}
(ROOT/'hook_comparison_manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'RENDERED','candidates':[{'id':r['id'],'title':r['title'],'notes':r['melody_count'],'mp3_bytes':r['mp3_bytes'],'sha256':r['mp3_sha256']} for r in result],
'reel_bytes':reelmp3.stat().st_size,'reel_sha256':hashlib.sha256(reelmp3.read_bytes()).hexdigest(),
'manifest_bytes':(ROOT/'hook_comparison_manifest.json').stat().st_size},ensure_ascii=False))
