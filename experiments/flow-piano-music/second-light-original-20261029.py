
"""SECOND LIGHT — alternative original piano-hook composition (not a variation of AFTERGLOW).
Designed around musical rests and upper chord voicings, Flow Piano Music Concert A+ profile.
"""
from pathlib import Path
import os,sys,math,json,subprocess,hashlib,importlib.util,ctypes as C,ctypes.util
import numpy as np
from scipy import signal
from scipy.io import wavfile
ROOT=Path('/tmp/flow-piano-music-second-light-20261029');ROOT.mkdir(parents=True,exist_ok=True)
SF='/opt/flow-piano-music/assets/SalamanderGrandPiano-SF2-V3+20200602/SalamanderGrandPiano-V3+20200602.sf2'
assert Path(SF).exists()
BPM=128;BT=60/BPM;BAR=BT*4;DUR=30.;SR=44100
# Harmony intentionally lasts two bars for stability, and changes only on musical phrases.
# Right hand chord holds avoid the high melody range, with top notes positioned as a vocal-like motif.
score=[
 ('Bm11',35,42,[50,54,57,62,66]),('Bm11',35,42,[50,54,57,62,66]),
 ('Gmaj9',31,43,[50,55,59,62,66]),('Gmaj9',31,43,[50,55,59,62,66]),
 ('Dadd9/A',33,45,[50,54,57,62,64]),('Dadd9/A',33,45,[50,54,57,62,64]),
 ('Asus4',33,45,[52,57,62,64]),('Aadd9',33,45,[52,57,61,64]),
 ('Bm11',35,42,[50,54,57,62,66]),('Bm11',35,42,[50,54,57,62,66]),
 ('Gmaj9',31,43,[50,55,59,62,66]),('Gmaj9',31,43,[50,55,59,62,66]),
 ('Em9',40,47,[52,55,59,62,66]),('Em9',40,47,[52,55,59,62,66]),
 ('Asus4',33,45,[52,57,62,64]),('Bm(add9)',35,42,[50,54,59,61,66])
]
# Explicit human-authored top-line with silence; top notes form a singable, question-and-answer.
# Tuple: (beat position, MIDI pitch, length in beats, intent)
melodies=[
 [(0.12,78,.65,'call'),(.97,76,.36,'step'),(1.74,74,1.16,'resolve')],
 [( .28,74,.58,'echo'),(1.29,78,.62,'lift'),(2.28,76,.72,'trail')],
 [( .12,79,.75,'lift'),(1.18,78,.38,'step'),(2.08,74,1.10,'resolve')],
 [( .26,71,.73,'answer'),(1.73,74,.88,'answer')],
 [( .10,78,.67,'call'),(1.02,76,.41,'step'),(1.85,74,1.09,'resolve')],
 [( .22,71,.67,'answer'),(1.22,69,.48,'rest'),(2.65,74,.72,'lift')],
 [( .12,76,.69,'call'),(1.16,74,.41,'step'),(2.07,73,1.02,'fall')],
 [( .52,76,1.11,'long')],
 [( .12,78,.76,'call'),(.99,76,.39,'step'),(1.78,74,1.01,'resolve')],
 [( .33,74,.63,'answer'),(1.46,78,.87,'lift')],
 [( .13,79,.72,'lift'),(1.20,81,.49,'peak'),(2.10,78,.88,'release')],
 [( .50,74,1.30,'long')],
 [( .12,79,.68,'call'),(1.15,78,.43,'step'),(2.09,76,.90,'release')],
 [( .34,71,.58,'answer'),(1.56,74,.85,'lift')],
 [( .12,76,.60,'call'),(1.02,74,.40,'step'),(1.95,73,.92,'fall')],
 [( .08,78,.71,'arrival'),(1.06,74,.56,'resolve'),(2.21,71,1.15,'home')]
]
assert len(score)==len(melodies)==16
# Max nine melody pitch values across 30 seconds, deliberate repetition + contrast.
event=[]
def add(t,d,p,v,ch,tag):
 assert 0<=t<30 and d>0.035 and 30<=p<=82
 d=min(d,29.98-t)
 if d<=.035:return
 event.append({'start':round(t,5),'duration':round(d,5),'pitch':p,'velocity':min(110,max(23,round(v))),
  'channel':ch,'layer':tag})
arc=[.90,.86,1.00,.84,.94,.82,1.02,.77,1.04,.99,1.10,.89,1.13,1.04,1.12,.91]
for i,(chord,bass,fifth,voices) in enumerate(score):
 t=i*BAR;energy=arc[i]
 assert len(set(p%12 for p in voices))>=3
 # Left-hand piano roots quiet; intentionally leave low register breathing
 add(t+.008,BT*3.5,bass,46*energy,0,'BASS')
 if i%2==0 or i>=12:
  add(t+BT*2.2,BT*.95,fifth,36*energy,0,'BASS')
 # Whole-tone middle register chords. Gentle humanized roll in fixed purposeful order.
 for j,p in enumerate(voices):
  add(t+.034+.027*j, BT*(2.80 if j<3 else 2.49),p,(54+2.8*j)*energy,1,'HARMONY')
 # Pulses at sparse, alternating times; not relentless every eighth note.
 if i not in (1,3,7,11,15):
  attacks=([1.46,3.10] if i in (0,2,4,8,10,12,14) else [2.69])
  for k,at in enumerate(attacks):
   group=voices[2:4] if k==0 else voices[1:3]
   for jj,p in enumerate(group):
    add(t+BT*at+.011*jj,BT*(.25 if k==0 else .36),p,(46+3*jj)*energy,3,'CHORD_ECHO')
 # Top line enters from the first beat, with a vocal-like call/response structure.
 for k,(beat,p,d,intent) in enumerate(melodies[i]):
  accent=84 if intent in ('call','lift','arrival','peak') else 72 if intent in ('step','fall','trail') else 77
  add(t+BT*beat,BT*d,p,accent*energy+(4 if i>=8 and intent=='peak' else 0),2,'HOOK')
event.sort(key=lambda n:(n['start'],n['pitch']))
mel=[n for n in event if n['channel']==2]
assert len(mel)<53
assert len(event)<230
# Check hook motif repeats musically at bar 1,5,9 without copying external MIDI.
assert [x[1] for x in melodies[0]]==[78,76,74]
assert [x[1] for x in melodies[4]]==[78,76,74]
assert [x[1] for x in melodies[8]]==[78,76,74]

# Reuse Flow Piano Music's existing visual engine, but resize MIDI register and label dynamic chords.
src=Path('/opt/flow-piano-music/render.py').read_text(encoding='utf-8')
left=src.index('def labels_from_time(');right=src.index('def render_video(')
labels='CHORDS='+repr([(round(i*BAR,5),n) for i,(n,*_) in enumerate(score)])+'\n' + \
'''def labels_from_time(moment):
    chord=CHORDS[0][1]
    for start,label in CHORDS:
        if moment>=start:chord=label
    return chord

'''
vis=src[:left]+labels+src[right:]
vis=vis.replace('lane=17.5','lane=13.0')
vis=vis.replace('26+(70-p)*lane','26+(82-p)*lane')
vis=vis.replace('range(33,72)','range(30,83)')
vis=vis.replace('range(36,71)','range(36,83)')
vis=vis.replace("'EMOTIONAL',font=font_title","'SECOND LIGHT',font=font_title")
vis=vis.replace("'30s MIDI PERFORMANCE',font=font_song","'ORIGINAL PIANO HOOK',font=font_song")
vis=vis.replace("'A piano-roll composition study',font=font_regular","'The hook lives in the chords',font=font_regular")
vis=vis.replace("'PIANO CHORDS',font=font_label","'ORIGINAL MUSIC',font=font_label")
vis=vis.replace("'CHORD PROGRESSION',font=font_label","'HOOK & CHORDS',font=font_label")
vis=vis.replace("'ORIGINAL'","'HOOK'")
vis=vis.replace("'VARIATION'","'RETURN'")
vis=vis.replace("color={'SOURCE_ROLL':'#CCA052','VARIATION':'#DFB260','VARIATION_ECHO':'#B78A3F'}.get(layer,'#CCA052')",
   """color='#F0C66B' if note.get('channel')==2 else '#C79C56' if note.get('channel')==1 else '#AD8754'""")
vis=vis.replace("accent='#F5D489' if layer=='SOURCE_ROLL' else '#F8DCA0'",
   """accent='#FFE9A0' if note.get('channel')==2 else '#D2B788'""")
vp=ROOT/'second_light_visual.py'
vp.write_text(vis)
spec=importlib.util.spec_from_file_location('second_light_visual',str(vp))
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
MID=ROOT/'Second_Light_Original_Piano_30s.mid'
mod.write_midi(event,MID)

# High-velocity-resolution Salamander Grand piano with register-aware dynamics,
# gently released sustain, controlled room reflections and no other instruments.
lib=C.CDLL(ctypes.util.find_library('fluidsynth'))
VP=C.c_void_p;I=C.c_int;D=C.c_double
def call(name,r,args):
 f=getattr(lib,name);f.restype=r;f.argtypes=args;return f
settings=call('new_fluid_settings',VP,[])()
call('fluid_settings_setnum',I,[VP,C.c_char_p,D])(settings,b'synth.sample-rate',SR)
call('fluid_settings_setnum',I,[VP,C.c_char_p,D])(settings,b'synth.gain',.36)
seti=call('fluid_settings_setint',I,[VP,C.c_char_p,I])
for key,v in [(b'synth.polyphony',256),(b'synth.reverb.active',0),(b'synth.chorus.active',0)]:
 seti(settings,key,v)
synth=call('new_fluid_synth',VP,[VP])(settings)
sfid=call('fluid_synth_sfload',I,[VP,C.c_char_p,I])(synth,SF.encode(),1)
assert sfid>=0
select=call('fluid_synth_program_select',I,[VP,I,I,I,I])
for ch in range(4):select(synth,ch,sfid,0,0)
on=call('fluid_synth_noteon',I,[VP,I,I,I])
off=call('fluid_synth_noteoff',I,[VP,I,I])
cc=call('fluid_synth_cc',I,[VP,I,I,I])
write=call('fluid_synth_write_float',I,[VP,I,VP,I,I,VP,I,I])
timeline=[]
for bar in range(16):
 t=bar*BAR
 for ch in range(4):
  timeline.append((round((t+.035)*SR),2,64,82,ch))
  timeline.append((round((t+BAR-.091)*SR),2,64,0,ch))
for n in event:
 st=n['start']+(0.003 if n['channel']==0 else 0.007 if n['channel']==1 else 0.011)
 end=min(29.999,st+n['duration'])
 timeline.append((round(st*SR),1,n['pitch'],n['velocity'],n['channel']))
 timeline.append((round(end*SR),0,n['pitch'],0,n['channel']))
timeline.sort(key=lambda x:(x[0],x[1]))
N=round(DUR*SR)
L=np.zeros(N,dtype=np.float32);R=np.zeros(N,dtype=np.float32)
pos=ix=0
while pos<N:
 while ix<len(timeline) and timeline[ix][0]<=pos:
  _,kind,p,v,ch=timeline[ix]
  if kind==0:off(synth,ch,p)
  elif kind==1:on(synth,ch,p,v)
  else:cc(synth,ch,p,v)
  ix+=1
 stop=min(N,pos+4096,timeline[ix][0] if ix<len(timeline) else N)
 if stop<=pos:stop=pos+1
 write(synth,stop-pos,VP(L[pos:stop].ctypes.data),0,1,VP(R[pos:stop].ctypes.data),0,1)
 pos=stop
audio=np.stack((L,R),axis=1).astype(np.float64)
audio=signal.sosfilt(signal.butter(2,45,fs=SR,btype='highpass',output='sos'),audio,axis=0)
def eq(x,f,q,db):
 A=10**(db/40);w=2*np.pi*f/SR;alpha=np.sin(w)/(2*q)
 b=np.array([1+alpha*A,-2*np.cos(w),1-alpha*A])
 a=np.array([1+alpha/A,-2*np.cos(w),1-alpha/A])
 return signal.lfilter(b/a[0],a/a[0],x,axis=0)
audio=eq(audio,144,1.,-2.3)
audio=eq(audio,2350,.85,1.3)
dry=audio.copy()
for c in range(2):
 for delay,amp in [(.028,.065),(.066,.052),(.118,.031),(.185,.019)]:
  d=round((delay+.004*c)*SR)
  audio[d:,c]+=dry[:-d,1-c]*amp
rng=np.random.default_rng(31626)
k=round(.73*SR)
kernel=rng.normal(0,1,(k,2))*np.exp(-np.arange(k)[:,None]/(SR*.145))
kernel[:round(.045*SR),:]=0
kernel*=.00085/max(abs(kernel).max(),.001)
for c in range(2):
 audio[:,c]+=signal.fftconvolve(dry[:,c],kernel[:,c],mode='full')[:N]
audio[-round(.7*SR):]*=np.linspace(1,0,round(.7*SR))[:,None]
audio*=.74/max(float(abs(audio).max()),.001)
assert np.isfinite(audio).all()
WAV=ROOT/'Second_Light_Original_Piano_30s.wav'
wavfile.write(str(WAV),SR,(np.clip(audio,-1,1)*32767).astype(np.int16))
MP3=ROOT/'Second_Light_Original_Piano_30s.mp3'
r=subprocess.run(['ffmpeg','-v','error','-y','-i',str(WAV),
 '-af','loudnorm=I=-17:TP=-2.4:LRA=11,volume=-1.2dB,alimiter=limit=0.87:attack=5:release=90',
 '-c:a','libmp3lame','-b:a','256k',str(MP3)],capture_output=True,text=True,timeout=48)
if r.returncode:raise RuntimeError(r.stderr[-300:])
MP4=ROOT/'Second_Light_Original_Piano_30s.mp4'
mod.render_video(event,DUR,WAV,MP4)
probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate','-of','json',str(MP4)],capture_output=True,text=True,timeout=14)
assert probe.returncode==0
vmeta=json.loads(probe.stdout)
assert abs(float(vmeta['format']['duration'])-30)<.01
assert any(x.get('codec_name')=='h264' and x.get('width')==720 for x in vmeta['streams'])
assert any(x.get('codec_name')=='aac' for x in vmeta['streams'])
manifest={'title':'SECOND LIGHT','bpm':128,'tonality':'B minor / relative D major','duration':30.,
 'type':'Original piano music, Flow Piano Music v1.2 Concert A+',
 'not_derived_from_tiktok_note_events':True,
 'composition_intent':'5–3 note melodic hook integrated into chord expression, call and response with rests, 2-bar harmonic rhythm',
 'chords':[{'bar':i+1,'name':ch,'start':round(i*BAR,4)} for i,(ch,*_) in enumerate(score)],
 'melody':melodies,'note_events':event,'fps':30,'resolution':[720,1280],
 'user_review':'PENDING','creator_credit':'Salamander Grand Piano sample by Alexander Holm, CC BY 3.0'}
MAN=ROOT/'Second_Light_Original_Piano_30s_manifest.json'
MAN.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'PASS','title':'SECOND LIGHT','events':len(event),'melody_events':len(mel),
 'chord_changes':len(set(s[0] for s in score)),
 'files':{f.name:{'size':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in [MP4,MP3,MID,MAN,vp]},'probe':vmeta},ensure_ascii=False))
