
"""Original composition and 30s piano-roll video: AFTERGLOW.
Created with Flow Piano Music v1.2 (Concert A+); original authored MIDI pitches,
beats and progression. No use of TikTok source melody/recording.
"""
import os,sys,json,math,hashlib,struct,ctypes as C,ctypes.util,subprocess,importlib.util
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile

BPM=128
BEAT=60/BPM
BAR=BEAT*4
DURATION=BAR*16
SR=44100
assert DURATION==30
ROOT=Path('/tmp/flow-piano-music-original-afterglow-20261029')
ROOT.mkdir(parents=True,exist_ok=True)
SOUNDFONT='/opt/flow-piano-music/assets/SalamanderGrandPiano-SF2-V3+20200602/SalamanderGrandPiano-V3+20200602.sf2'
assert Path(SOUNDFONT).is_file()

# Hand-composed changes of harmony; piano-roll notes entirely new.
# ch=name, bass root MIDI, fifth MIDI, right hand voicing mid-register, allowed chroma.
SCORE=[
 ('Dadd9',38,45,[50,57,62,64,66],{2,4,6,9}),
 ('A/C#',37,45,[52,57,61,64],{1,4,9}),
 ('Bm7',35,42,[47,54,57,62,66],{11,2,6,9}),
 ('Gadd9',43,50,[55,59,62,67],{7,11,2,9}),
 ('D/F#',42,45,[50,57,62,66],{2,6,9}),
 ('Asus4/A',45,52,[52,57,62,64],{9,2,4,1}),
 ('Bm7',35,42,[47,54,57,62,66],{11,2,6,9}),
 ('Gadd9',43,50,[55,59,62,67],{7,11,2,9}),
 ('Dadd9',38,45,[50,57,62,64,66],{2,4,6,9}),
 ('A/C#',37,45,[52,57,61,64],{1,4,9}),
 ('Bm7',35,42,[47,54,57,62,66],{11,2,6,9}),
 ('Gmaj7',43,50,[55,59,62,66],{7,11,2,6}),
 ('Em7',40,47,[52,55,59,62],{4,7,11,2}),
 ('G/A',45,52,[55,59,62,67],{9,7,11,2,4}),
 ('Asus4/A',45,52,[52,57,62,64],{9,2,4,1}),
 ('Dadd9',38,45,[50,57,62,64,66],{2,4,6,9}),
]
# Every melody note explicitly authored, 4/4 bars at 128 BPM. Beat offset, MIDI, held beats.
TOP=[
 [(0.06,78,.58),(.82,76,.36),(1.51,74,.76),(2.70,69,.29),(3.31,71,.54)],
 [(0.05,76,.58),(.82,78,.33),(1.54,76,.44),(2.30,73,.53),(3.31,71,.52)],
 [(0.06,78,.60),(.84,76,.34),(1.51,74,.73),(2.63,71,.34),(3.29,69,.54)],
 [(0.06,74,.58),(.88,71,.34),(1.57,69,.47),(2.42,67,.38),(3.28,69,.55)],
 [(0.08,74,.63),(.88,76,.36),(1.52,78,.59),(2.46,81,.51),(3.43,78,.44)],
 [(0.06,79,.53),(.84,76,.33),(1.59,74,.47),(2.56,73,.43),(3.32,76,.57)],
 [(0.07,78,.57),(.78,74,.32),(1.40,76,.48),(2.24,74,.48),(3.20,71,.64)],
 [(0.07,74,.59),(.86,71,.33),(1.52,69,.44),(2.35,67,.45),(3.17,69,.59)],
 [(0.06,78,.60),(.82,76,.36),(1.51,74,.75),(2.70,69,.29),(3.31,71,.54)],
 [(0.06,76,.60),(.80,78,.36),(1.55,76,.39),(2.34,73,.48),(3.30,74,.57)],
 [(0.04,78,.65),(.85,76,.35),(1.58,74,.65),(2.65,71,.31),(3.27,74,.60)],
 [(0.06,79,.81),(1.09,78,.46),(1.87,74,.40),(2.58,71,.47),(3.31,74,.49)],
 [(0.06,79,.56),(.87,78,.37),(1.61,76,.47),(2.51,74,.47),(3.34,71,.51)],
 [(0.06,81,.58),(.85,79,.36),(1.58,78,.45),(2.43,76,.41),(3.22,74,.64)],
 [(0.07,79,.59),(.85,76,.36),(1.60,74,.53),(2.52,73,.44),(3.35,76,.53)],
 [(0.05,78,.64),(.91,76,.38),(1.60,74,1.12),(3.23,69,.57)]
]
assert len(TOP)==len(SCORE)==16

events=[]
def add_note(start,duration,pitch,velocity,channel,role,section):
 if not 0<=start<30 or not .03<duration<=4.5:raise ValueError((start,duration,pitch))
 assert 34<=pitch<=85
 if start+duration>29.98:duration=max(.06,29.98-start)
 events.append({'start':round(start,5),'duration':round(duration,5),'pitch':pitch,
   'velocity':int(velocity),'channel':channel,'layer':role,'role':role,'section':section})
express=[.92,.96,1.00,.83,.96,1.05,.98,.81,1.04,1.10,1.11,.99,1.13,1.17,1.09,.96]
# Drive emotion with notewise expression and breathing, not randomizing MIDI.
for bar,(name,root,fifth,voicing,chroma) in enumerate(SCORE):
 base=bar*BAR;mul=express[bar]
 section='HOOK' if bar<4 else 'LIFT' if bar<8 else 'HOOK_RETURN' if bar<12 else 'RESOLVE'
 assert {root%12,fifth%12}|{p%12 for p in voicing}<=chroma
 # Left-hand: quiet rounded roots and carefully placed up-register bass answers.
 add_note(base+.012,BEAT*3.20,root,round(49*mul),0,'BASS',section)
 add_note(base+BEAT*2.10,BEAT*1.35,fifth,round(39*mul),0,'BASS',section)
 # Most bars only 2 bass notes; avoid robotic pumping.
 if bar in (4,8,12,15):
  octave=root+12
  add_note(base+BEAT*3.19,BEAT*.62,octave,round(36*mul),0,'BASS',section)
 # Independent inner voices: piano-like staggered attack, sustained harmony
 stagger=[.053,.087,.112,.141,.168]
 for ix,p in enumerate(voicing):
  duration=BEAT*(3.33 if ix<2 else 3.06)
  if p==62 and bar in (5,14):duration=BEAT*2.35
  v=round((55+ix*2.7)*mul)
  add_note(base+stagger[ix],duration,p,v,1,'HARMONY',section)
 # Suspended fourth falls to third only on the two dedicated dominant bars
 if bar in (5,14):
  add_note(base+BEAT*2.57,BEAT*1.06,61,round(59*mul),1,'HARMONY',section)
 # Hook part: separate MIDI channel to preserve independent rearticulation.
 for j,(at,pitch,held) in enumerate(TOP[bar]):
  accent=[94,80,89,76,82][j]
  v=round(accent*mul+(5 if pitch>=79 and bar>=11 else 0))
  add_note(base+BEAT*at,BEAT*held,pitch,max(52,min(112,v)),2,'MELODY',section)
 # Light two-note chords between melody beats. Omit when silence is intentional.
 if bar in (0,2,3,4,6,8,9,10,12,13,14):
  t=base+BEAT*(2.92 if bar in (0,8,12) else 3.03)
  group=sorted(set(voicing))[-3:-1]
  for k,p in enumerate(group):
   add_note(t+.012*k,BEAT*.28,p,round((41+4*k)*mul),3,'PULSE',section)

events.sort(key=lambda e:(e['start'],e['pitch'],e['channel']))
assert len(events)>175
assert all(a['pitch']>=67 for a in events if a['role']=='MELODY')
assert all(0<n['velocity']<=127 for n in events)
assert sum(n['role']=='MELODY' for n in events)==sum(len(b) for b in TOP)
# Make sure source's 15s optical notes have not been reused as a sequence.
source_manifest=Path('/tmp/flow-piano-music-popular-20261029/popular_30s_manifest.json')
if source_manifest.is_file():
 old=json.loads(source_manifest.read_text())
 old_mel=[(round(x['start'],2),x['pitch']) for x in old['note_events'] if x['channel']==2 and x['start']<15]
 new_mel=[(round(x['start'],2),x['pitch']) for x in events if x['channel']==2 and x['start']<15]
 assert old_mel!=new_mel

# Bring in the exact Flow Piano Music visual renderer + MIDI SMF Type 1 writer,
# locally modifying only the label, visible register and highlight colors.
render_source=Path('/opt/flow-piano-music/render.py').read_text()
original_idx=render_source.index('def labels_from_time(')
stop=render_source.index('def render_video(')
def_labels='CHORDS='+repr([(round(i*BAR,5),chord[0]) for i,chord in enumerate(SCORE)])+'''
def labels_from_time(moment):
    current=CHORDS[0][1]
    for begin,label in CHORDS:
        if moment>=begin:current=label
    return current

'''
visual_source=render_source[:original_idx]+def_labels+render_source[stop:]
visual_source=visual_source.replace('lane=17.5','lane=13.2')
visual_source=visual_source.replace('26+(70-p)*lane','26+(84-p)*lane')
visual_source=visual_source.replace('range(33,72)','range(34,85)')
visual_source=visual_source.replace('range(36,71)','range(36,85)')
visual_source=visual_source.replace("'EMOTIONAL',font=font_title","'AFTERGLOW',font=font_title")
visual_source=visual_source.replace("'30s MIDI PERFORMANCE',font=font_song","'ORIGINAL PIANO HOOK',font=font_song")
visual_source=visual_source.replace("'A piano-roll composition study',font=font_regular","'An original melody in D major',font=font_regular")
visual_source=visual_source.replace("'PIANO CHORDS',font=font_label","'ORIGINAL MUSIC',font=font_label")
visual_source=visual_source.replace("'CHORD PROGRESSION',font=font_label","'MELODY & CHORDS',font=font_label")
visual_source=visual_source.replace("'ORIGINAL'","'HOOK'")
visual_source=visual_source.replace("'VARIATION'","'LIFT'")
# Current text second selector only checks moment>=15; "LIFT" here denotes second chorus uplift
visual_source=visual_source.replace("color={'SOURCE_ROLL':'#CCA052','VARIATION':'#DFB260','VARIATION_ECHO':'#B78A3F'}.get(layer,'#CCA052')",
"""color='#E3B768' if note.get('channel')==2 else '#B98748' if note.get('channel')==0 else '#C59E5B' if note.get('channel')==1 else '#A98044'""")
visual_source=visual_source.replace("accent='#F5D489' if layer=='SOURCE_ROLL' else '#F8DCA0'",
"""accent='#FFE7A8' if note.get('channel')==2 else '#E6C38B'""")
vp=ROOT/'afterglow_visual_renderer.py'
vp.write_text(visual_source)
spec=importlib.util.spec_from_file_location('afterglow_visual',str(vp))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
midi=ROOT/'Afterglow_Original_Piano_30s.mid'
module.write_midi(events,midi)

# Concert A+ like sample dynamics, piano-only fluid synth, note/pedal timing.
lib=C.CDLL(ctypes.util.find_library('fluidsynth'))
VP=C.c_void_p;I=C.c_int;D=C.c_double
def api(name,ret,args):
 fn=getattr(lib,name);fn.restype=ret;fn.argtypes=args;return fn
settings=api('new_fluid_settings',VP,[])()
api('fluid_settings_setnum',I,[VP,C.c_char_p,D])(settings,b'synth.sample-rate',SR)
api('fluid_settings_setnum',I,[VP,C.c_char_p,D])(settings,b'synth.gain',.34)
setting_int=api('fluid_settings_setint',I,[VP,C.c_char_p,I])
for name,val in [(b'synth.polyphony',256),(b'synth.reverb.active',0),(b'synth.chorus.active',0)]:
 setting_int(settings,name,val)
synth=api('new_fluid_synth',VP,[VP])(settings)
sfid=api('fluid_synth_sfload',I,[VP,C.c_char_p,I])(synth,SOUNDFONT.encode(),1)
assert sfid>=0
program=api('fluid_synth_program_select',I,[VP,I,I,I,I])
for ch in range(4):program(synth,ch,sfid,0,0)
on=api('fluid_synth_noteon',I,[VP,I,I,I])
off=api('fluid_synth_noteoff',I,[VP,I,I])
cc=api('fluid_synth_cc',I,[VP,I,I,I])
write=api('fluid_synth_write_float',I,[VP,I,VP,I,I,VP,I,I])

timeline=[]
for i in range(16):
 bar=i*BAR;last=(i+1)*BAR
 for ch in range(4):
  timeline.append((round((bar+.028)*SR),2,64,92,ch))
  timeline.append((round((last-.078)*SR),2,64,0,ch))
for n in events:
 st=n['start']+(0.003 if n['channel']==0 else 0.006 if n['channel']==1 else .010 if n['channel']==2 else .005)
 stop=min(29.999,st+n['duration'])
 timeline.append((round(st*SR),1,n['pitch'],n['velocity'],n['channel']))
 timeline.append((round(stop*SR),0,n['pitch'],0,n['channel']))
timeline.sort(key=lambda e:(e[0],e[1]))
N=round(DURATION*SR)
L=np.zeros(N,dtype=np.float32);R=np.zeros(N,dtype=np.float32)
pos=idx=0
while pos<N:
 while idx<len(timeline) and timeline[idx][0]<=pos:
  _,kind,p,v,ch=timeline[idx]
  if kind==0:off(synth,ch,p)
  elif kind==1:on(synth,ch,p,v)
  else:cc(synth,ch,p,v)
  idx+=1
 until=min(N,pos+4096,timeline[idx][0] if idx<len(timeline) else N)
 if until<=pos:until=pos+1
 write(synth,until-pos,VP(L[pos:until].ctypes.data),0,1,VP(R[pos:until].ctypes.data),0,1)
 pos=until

audio=np.stack((L,R),axis=1).astype(np.float64)
audio=signal.sosfilt(signal.butter(2,46,fs=SR,btype='highpass',output='sos'),audio,axis=0)
def bell(x,center,q,db):
 A=10**(db/40);w=2*np.pi*center/SR;alpha=np.sin(w)/(2*q)
 b=np.array([1+alpha*A,-2*np.cos(w),1-alpha*A])
 a=np.array([1+alpha/A,-2*np.cos(w),1-alpha/A])
 return signal.lfilter(b/a[0],a/a[0],x,axis=0)
audio=bell(audio,150,1.,-1.9)
audio=bell(audio,2100,.83,1.15)
audio=bell(audio,5800,1.,.5)
dry=audio.copy()
for c in range(2):
 for delay,gain in [(.027,.06),(.064,.045),(.118,.027),(.181,.018)]:
  d=round(SR*(delay+.006*c))
  audio[d:,c]+=dry[:-d,1-c]*gain
rng=np.random.default_rng(24102026)
ir_len=round(.82*SR)
kernel=rng.normal(0,1,(ir_len,2))*np.exp(-np.arange(ir_len)[:,None]/(SR*.15))
kernel[:round(.039*SR),:]=0
kernel*=.0010/max(abs(kernel).max(),.001)
for c in range(2):
 audio[:,c]+=signal.fftconvolve(dry[:,c],kernel[:,c],mode='full')[:N]
fade=round(.49*SR)
audio[-fade:]*=np.linspace(1,0,fade)[:,None]
peak=max(float(abs(audio).max()),.001)
audio*=.73/peak
assert np.isfinite(audio).all()
wav=ROOT/'Afterglow_Original_Piano_30s.wav'
wavfile.write(str(wav),SR,(np.clip(audio,-1,1)*32767).astype(np.int16))
mp3=ROOT/'Afterglow_Original_Piano_30s.mp3'
ff=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
 '-i',str(wav),'-af','loudnorm=I=-17:TP=-2.8:LRA=10,volume=-1.2dB,alimiter=limit=0.87:attack=5:release=100',
 '-codec:a','libmp3lame','-b:a','256k',str(mp3)],capture_output=True,text=True,timeout=50)
if ff.returncode:raise RuntimeError('mp3 error:'+ff.stderr[-330:])
mp4=ROOT/'Afterglow_Original_Piano_30s.mp4'
module.render_video(events,DURATION,wav,mp4)
probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate','-of','json',str(mp4)],capture_output=True,text=True,timeout=15)
assert probe.returncode==0
meta=json.loads(probe.stdout)
assert abs(float(meta['format']['duration'])-30)<.01
assert any(x.get('codec_name')=='h264' and x.get('width')==720 for x in meta['streams'])
assert any(x.get('codec_name')=='aac' for x in meta['streams'])

manifest={
 'title':'AFTERGLOW','composer':'original composition created by ChatGPT on user request',
 'copyright':'new original note sequence, not a transcription or copy of reference video',
 'genre':'Emotional piano hook / cinematic dance piano study',
 'influences':'Berklee hook repetition+contrast; broad pop harmonic movement; Flow Piano Music v1.2 visual/audio production',
 'key':'D major','bpm':BPM,'duration':DURATION,'fps':30,'resolution':[720,1280],
 'soundfont_profile':'Concert A+ Salamander sampled piano','source_audio_used':False,
 'signature_motif_first_bar':TOP[0],
 'hook_return_bar':8,
 'arrangement':'Four 4-bar phrases: hook, lift, hook return, tension/resolution. Piano only.',
 'chord_timeline':[{'bar':i+1,'start':round(i*BAR,5),'chord':name} for i,(name,*_) in enumerate(SCORE)],
 'note_events':events,'qa_approval':'not yet user evaluated',
 'music_theory_references':['Berklee Andrea Stolpe hooks','Hooktheory popular chord progressions','Earworm empirical research'],
}
mp=ROOT/'Afterglow_Original_Piano_30s_manifest.json'
mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'RENDERED_ORIGINAL','title':'AFTERGLOW','duration':DURATION,
 'n_notes':len(events),'melody_events':sum(n['channel']==2 for n in events),
 'chords':[row[0] for row in SCORE],'distinct_melody_pitches':len(set(n['pitch'] for n in events if n['channel']==2)),
 'video':meta,'files':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [mp4,mp3,midi,mp,vp]},'render_sha':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},ensure_ascii=False))
