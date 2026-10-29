
from __future__ import annotations
import os,subprocess,json,hashlib,math,ctypes as C,ctypes.util,importlib.util,sys
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile

ROOT=Path('/tmp/flow-piano-music-popular-20261029')
OUT=ROOT/'concert_a_plus';OUT.mkdir(parents=True,exist_ok=True)
SOURCE=json.loads((ROOT/'popular_30s_manifest.json').read_text())
ORIGINAL=SOURCE['note_events']
SF2='/opt/flow-piano-music/assets/SalamanderGrandPiano-SF2-V3+20200602/SalamanderGrandPiano-V3+20200602.sf2'
SOURCE_VIDEO=str(ROOT/'top_musiccreator_reference.mp4')
SHIFT=0.144 # seconds, source/audio transient analysis (source to A)
SR=44100;DURATION=30.0
assert len(ORIGINAL)==111
# All pitches unchanged; all note starts advanced by ~0.144s to match reference.
# Extend the isolated very short high grace notes just enough to be audible.
notes=[]
for q in ORIGINAL:
 n=dict(q)
 n['start']=max(0.0,round(q['start']-SHIFT,5))
 d=q['duration']
 if q['pitch']>=57 and d<.135:
  d=min(.165,max(d*1.22,.092))
 # avoid a micro gap when octaves change, but do not create new notes
 n['duration']=round(min(d,30.0-n['start']),5)
 notes.append(n)
notes.sort(key=lambda q:(q['start'],q['pitch']))
assert len(notes)==len(ORIGINAL)
assert all(a['pitch']==b['pitch'] for a,b in zip(sorted(ORIGINAL,key=lambda n:(n['start'],n['pitch'])),notes))

# Group-level musical expression follows the phrase shape of the reference.
CONTOUR=[(0,.87),(.6,.91),(1.4,.94),(2.7,.86),(3.55,1.12),(4.45,1.09),
 (5.15,1.01),(6.65,.79),(7.5,1.08),(8.2,1.06),(9.3,.90),(10.65,.80),
 (11.15,1.12),(12.5,1.07),(14.6,.79),(14.98,.85)]
def contour(t):
 t=t%15.
 return float(np.interp(t,[x[0] for x in CONTOUR],[x[1] for x in CONTOUR]))
def dynamic(n):
 p=n['pitch'];v=n['velocity']
 # Grand soundfont has much more transient color as MIDI velocity rises.
 # Preserve high melodic voices, avoid G1/B1 bass overpowering everything.
 if p<=38:base=48;v=(v-75)*.22
 elif p<=47:base=54;v=(v-75)*.37
 elif p<=55:base=64;v=(v-73)*.52
 elif p<=60:base=76;v=(v-66)*.67
 else:base=87;v=(v-67)*.77
 val=(base+v)*contour(n['start'])
 if n['start']>=15:val*=1.035
 # lead motifs each eighth segment have a gentle arrival accent
 if p>=62 and n['duration']>.35:val+=3
 return round(max(34,min(112,val)))

manifest=dict(SOURCE)
manifest.update({'version':'Flow Piano Music 1.1 experimental Concert A+',
 'method':'pitches and optical note structure remain identical to MusicCreator source; phrase-level dynamics and reference-audio 144ms onset correction',
 'note_events':notes,
 'soundfont':str(SF2),
 'source_offset_seconds_corrected':SHIFT,
 'reference_audio_transient_crosscorr_peak_at_offset_s':SHIFT,
 'feedback':'Concert A preferred over Warm B; A+ NOT yet user approved',
 'renderer':'/opt/flow-piano-music/experiments/musiccreator-concert-Aplus.py',
 'visual_frames':'same Flow Piano Music visual style, rerendered with corrected note timings' })
M=OUT/'MusicCreator_Concert_Aplus_30s_manifest.json'
M.write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')

# Render sample-based Salamander Grand Piano, no synthetic lead/drums.
lib=C.CDLL(ctypes.util.find_library('fluidsynth'))
VP=C.c_void_p;I=C.c_int;D=C.c_double
def api(name,ret,args):
 f=getattr(lib,name);f.restype=ret;f.argtypes=args;return f
settings=api('new_fluid_settings',VP,[])()
api('fluid_settings_setnum',I,[VP,C.c_char_p,D])(settings,b'synth.sample-rate',SR)
api('fluid_settings_setnum',I,[VP,C.c_char_p,D])(settings,b'synth.gain',.34)
setint=api('fluid_settings_setint',I,[VP,C.c_char_p,I])
for name,val in [(b'synth.polyphony',256),(b'synth.reverb.active',0),(b'synth.chorus.active',0)]:
 setint(settings,name,val)
synth=api('new_fluid_synth',VP,[VP])(settings)
sfid=api('fluid_synth_sfload',I,[VP,C.c_char_p,I])(synth,str(SF2).encode(),1)
assert sfid>=0
program=api('fluid_synth_program_select',I,[VP,I,I,I,I])
for ch in range(4):program(synth,ch,sfid,0,0)
on=api('fluid_synth_noteon',I,[VP,I,I,I])
off=api('fluid_synth_noteoff',I,[VP,I,I])
cc=api('fluid_synth_cc',I,[VP,I,I,I])
write=api('fluid_synth_write_float',I,[VP,I,VP,I,I,VP,I,I])
# Sustain pedal release before each new harmony, half-damped only when transition is close.
changes=[0,.83,1.53,3.82,4.49,5.20,7.55,8.23,8.91,11.2,11.9,12.6,
 15,15.83,16.53,18.82,19.49,20.20,22.55,23.23,23.91,26.2,26.9,27.6,30]
changes=[max(0,t-SHIFT) for t in changes]
events=[]
for k,a in enumerate(changes[:-1]):
 b=changes[k+1]
 if b-a<.33:continue
 # Release 60ms before chord and reapply gently 32ms after attack.
 for ch in range(4):
  events.append((round((a+.030)*SR),2,64,85,ch))
  events.append((round((b-.064)*SR),2,64,0,ch))
for n in notes:
 p=n['pitch'];st=n['start'];dur=n['duration'];ch=n['channel']
 # A human piano chord is a low-to-high 9ms roll, not every note quantized exactly.
 delay=.003 if p<44 else .007 if p<57 else .012
 # Don't create first-note delays after loop starts; apply same visual source event +/-12ms.
 first=min(DURATION-.002,st+delay)
 stop=min(DURATION-.001,first+dur)
 events += [(round(first*SR),1,p,dynamic(n),ch),
            (round(stop*SR),0,p,0,ch)]
events.sort(key=lambda q:(q[0],q[1]))
N=int(DURATION*SR)
L=np.zeros(N,dtype=np.float32);R=np.zeros(N,dtype=np.float32)
pos=i=0
while pos<N:
 while i<len(events) and events[i][0]<=pos:
  _,kind,p,v,ch=events[i]
  if kind==0:off(synth,ch,p)
  elif kind==1:on(synth,ch,p,v)
  else:cc(synth,ch,p,v)
  i+=1
 bound=min(N,pos+4096,events[i][0] if i<len(events) else N)
 if bound<=pos:bound=pos+1
 write(synth,bound-pos,VP(L[pos:bound].ctypes.data),0,1,VP(R[pos:bound].ctypes.data),0,1)
 pos=bound
audio=np.stack((L,R),axis=1).astype(np.float64)
audio=signal.sosfilt(signal.butter(2,46,fs=SR,btype='highpass',output='sos'),audio,axis=0)
def bell(x,center,q,db):
 A=10**(db/40);w=2*np.pi*center/SR;alpha=np.sin(w)/(2*q)
 b=np.array([1+alpha*A,-2*np.cos(w),1-alpha*A])
 a=np.array([1+alpha/A,-2*np.cos(w),1-alpha/A])
 return signal.lfilter(b/a[0],a/a[0],x,axis=0)
audio=bell(audio,150,1.,-1.9)
audio=bell(audio,2100,.83,1.2)
audio=bell(audio,5800,1.,.7)
dry=audio.copy()
for c in range(2):
 for delay,gain in [(0.027,.06),(0.064,.044),(0.118,.029),(0.181,.018)]:
  d=round(SR*(delay+.006*c))
  audio[d:,c]+=dry[:-d,1-c]*gain
# Subtle reverb tail; use independent deterministic airy late reflections.
rng=np.random.default_rng(1251)
k=round(.8*SR)
kernel=rng.normal(0,1,(k,2))*np.exp(-np.arange(k)[:,None]/(SR*.145))
kernel[:round(.04*SR),:]=0
kernel*=.0009/max(abs(kernel).max(),.001)
for c in range(2):
 audio[:,c]+=signal.fftconvolve(dry[:,c],kernel[:,c],mode='full')[:N]
fade=int(.8*SR);audio[-fade:]*=np.linspace(1,0,fade)[:,None]
peak=max(abs(audio).max(),.001)
audio*=.74/peak
assert np.isfinite(audio).all()
W=OUT/'MusicCreator_Concert_Aplus_30s.wav'
wavfile.write(str(W),SR,(np.clip(audio,-1,1)*32767).astype(np.int16))
P=OUT/'MusicCreator_Concert_Aplus_30s.mp3'
ff=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(W),
 '-af','loudnorm=I=-17.3:TP=-2.3:LRA=11,volume=-0.8dB,alimiter=limit=0.89:attack=5:release=95',
 '-c:a','libmp3lame','-b:a','256k',str(P)],capture_output=True,text=True,timeout=55)
assert ff.returncode==0,ff.stderr[-450:]

# MIDI and video use exactly the corrected 111 note events.
rpath=ROOT/'render_popular.py'
spec=importlib.util.spec_from_file_location('piano_visual_renderer',str(rpath))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.CHORD_TIMELINE=[(max(0,round(t-SHIFT,4)),name) for t,name in module.CHORD_TIMELINE]
MID=OUT/'MusicCreator_Concert_Aplus_30s.mid'
VID=OUT/'MusicCreator_Concert_Aplus_30s.mp4'
module.write_midi(notes,MID)
module.render_video(notes,DURATION,W,VID)

for filename in (W,P,MID,VID,M):
 assert filename.is_file()
probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate','-of','json',str(VID)],capture_output=True,text=True,timeout=15)
assert probe.returncode==0
p=json.loads(probe.stdout)
assert abs(float(p['format']['duration'])-30)<.01
assert any(x.get('codec_name')=='h264' and x.get('width')==720 for x in p['streams'])
assert any(x.get('codec_name')=='aac' for x in p['streams'])

print(json.dumps({'status':'COMPLETE','source_event_count':len(ORIGINAL),'polished_event_count':len(notes),
 'source_offset_corrected_s':SHIFT,'video_probe':p,
 'files':{f.name:{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in (P,VID,MID,M,W)}},ensure_ascii=False))
