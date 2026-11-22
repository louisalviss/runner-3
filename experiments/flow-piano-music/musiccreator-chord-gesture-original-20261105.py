#!/usr/bin/env python3
"""Chord Gesture No.1 — original 10s sampled-piano research audition.

Pattern inspiration only from 2026-11-05 user-positive MusicCreator TikTok
7704419790449904926: 102-BPM quarterbeat inferred from 63 transient candidates
and phase-grid fit, chord-led texture, syncopated 0.75-beat gestures.
The source MIDI, source pitch order, source audio and full transcription
are NOT used here. This is an original A-major chord sequence
F#m11 -> Dmaj9 -> Aadd9/C# -> E7sus4/E7 -> Aadd9.
No modification of approved Concert A+ or older rejected 30s outputs.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,subprocess,re
from pathlib import Path

PARENT_BLOB="d23091c87d0a396fb244a82973e665988715e679"
PARENT_NAME="musicvae-original-hook-20261104.py"
STEM="Chord_Gesture_102BPM_Original_10s"
BPM=102
BEAT=60/BPM
BAR=4*BEAT
MUSICAL_DURATION=10.05
RENDER_DURATION=10.77
SOURCE_REFERENCE="https://www.tiktok.com/@official_musiccreator/video/7704419790449904926"

def parent():
 p=Path(__file__).with_name(PARENT_NAME)
 raw=p.read_bytes()
 blob=hashlib.sha1(b"blob "+str(len(raw)).encode()+bytes((0,))+raw).hexdigest()
 if blob!=PARENT_BLOB:raise RuntimeError("Pinned renderer source mismatch")
 spec=importlib.util.spec_from_file_location("original_piano_renderer",str(p))
 module=importlib.util.module_from_spec(spec)
 spec.loader.exec_module(module)
 return module

# Each chord is performed as a multidimensional piano gesture; NOT as
# a synthetic monophonic melody with generic backing.
# Start, harmonic name, root, main voicing, soft restroke(s), secondary bass.
BARS=[
 (0.0,"F#m11",42,[57,61,64,69],[(.75,[61,64,69],.31,62),(1.50,[57,64,68],.42,59),(3.25,[61,64,68],.29,63)],49),
 (BAR,"Dmaj9",50,[54,57,61,64],[(1.0,[57,61,64],.26,60),(2.50,[61,64,69],.39,65),(3.50,[57,61,64],.27,55)],45),
 (2*BAR,"Aadd9/C#",49,[52,57,59,64],[(1.5,[57,64,71],.36,63),(3.0,[59,64,69],.45,62)],52),
 (3*BAR,"E7sus4",40,[52,57,62,69],[(.75,[57,62,69],.29,65),(2.0,[52,56,62,68],.42,66),(3.25,[56,62,71],.24,59)],47),
]

def make_score(m):
 m.BEAT_BPM=BPM;m.SECONDS=MUSICAL_DURATION;m.RENDER_SECONDS=RENDER_DURATION
 m.NOTES.clear();m.CONTROL.clear()
 beats=[];starts=[]
 def add(t,d,p,v,ch,tag):
  if t<0 or t>=MUSICAL_DURATION:raise RuntimeError("Bad onset")
  m.n(round(t,4),min(d,MUSICAL_DURATION-t),p,int(v),ch,tag)
 for bar_index,(base,name,bass,voicing,strikes,second_bass) in enumerate(BARS):
  main=base+.012
  add(main,1.48,bass,52 if bar_index==3 else 56,0,name+":bass-root")
  add(base+2*BEAT+.015,.58,second_bass,46,0,name+":bass-response")
  beats.extend([round(base,3),round(base+2*BEAT,3)])
  starts.append(round(base,3))
  # Grand performance: low notes lead by 5-13ms and inner tones connect.
  for i,pitch in enumerate(voicing):
   add(base+.027+i*.009,1.70,pitch,66-(i%3)*3,1,name+":long-voice")
  for beat_index,pitches,duration,velocity in strikes:
   attack=base+beat_index*BEAT
   starts.append(round(attack,3))
   for i,pitch in enumerate(pitches):
    add(attack+.015+i*.007,duration,pitch,velocity-i*3,1,name+":chord-pulse")
 # Dominant's 4 -> 3 movement is one intentional point of tension.
 add(3*BAR+2.0*BEAT+.028,.65,68,62,2,"E7:Gsharp4-sus-resolution")
 # Clear cadence anticipates the loop with a new Aadd9 chord at end.
 finish=4*BAR-.17
 add(finish+.005,.62,45,52,0,"Aadd9-final-bass")
 for i,pitch in enumerate([52,57,59,64,69]):
  add(finish+.028+i*.008,.64,pitch,65-i*2,1,"Aadd9-final-chord")
 starts.append(round(finish,3))
 # Pedal releases just after the next chord starts, not before its attack.
 for idx,(base,*_) in enumerate(BARS):
  if idx==0:
   for ch in (0,1,2):m.CONTROL.append((base+.065,ch,64,77))
  else:
   for ch in (0,1,2):
    m.CONTROL.extend([(base+.055,ch,64,0),(base+.115,ch,64,74)])
 for ch in (0,1,2):
  m.CONTROL.extend([(finish+.052,ch,64,0),(finish+.12,ch,64,68),(10.0,ch,64,0)])
 # No overlapping same-pitch note-on/off on the same MIDI channel.
 bykey={}
 for i,(start,d,pitch,velocity,ch,label) in enumerate(m.NOTES):
  bykey.setdefault((ch,pitch),[]).append(i)
 shortened=0
 for ids in bykey.values():
  ids.sort(key=lambda i:m.NOTES[i][0])
  for left,right in zip(ids,ids[1:]):
   t,d,p,v,ch,name=m.NOTES[left]
   next_t=m.NOTES[right][0]
   if t+d>=next_t-.009:
    new_d=round(next_t-t-.014,4)
    if new_d<=.06:raise RuntimeError("Conflicting same-pitch strikes")
    m.NOTES[left]=(t,new_d,p,v,ch,name)
    shortened+=1
 if len(m.NOTES)<55 or len(m.NOTES)>92:raise RuntimeError("Unexpected score length")
 if len(BARS)!=4:raise RuntimeError("Expected four bars")
 return {"bass_grid":beats,"chord_gesture_onsets":starts,"same_pitch_shortened":shortened}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def integrated_lufs(path):
 p=subprocess.run(["ffmpeg","-nostdin","-hide_banner","-i",str(path),
   "-filter_complex","ebur128=peak=true","-f","null","-"],
   capture_output=True,text=True,timeout=25)
 v=re.findall(r"I:\s*(-?\d+(?:\.\d+)?) LUFS",p.stderr)
 if p.returncode or not v:raise RuntimeError("LUFS measurement failed")
 return float(v[-1])

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--output-dir",required=True)
 args=ap.parse_args()
 out=Path(args.output_dir)
 if out.exists() and any(out.iterdir()):raise RuntimeError("Cannot overwrite previous results")
 out.mkdir(parents=True,exist_ok=True)
 m=parent();grid=make_score(m)
 midi=out/(STEM+".mid")
 data=m.midi_bytes()
 old=b"\xff\x51\x03"+(500000).to_bytes(3,"big")
 new=b"\xff\x51\x03"+round(60000000/BPM).to_bytes(3,"big")
 if data.count(old)!=1:raise RuntimeError("Unexpected original MIDI tempo map")
 midi.write_bytes(data.replace(old,new,1))
 wav,mp3,qa=m.render_audio(out,m.SF2)
 final=out/(STEM+".mp3");mp3.rename(final);wav.unlink()
 report={
  "status":"ORIGINAL_HOOK_10S_HUMAN_LISTENING_PENDING",
  "reference_source":"MusicCreator TikTok clip 7704419790449904926, copyright not copied",
  "reference_url":SOURCE_REFERENCE,
  "reference_media_sha256":"127c55a4cfd0f6f97770c13a59361a185aa10954cfb2f5bc9928ad6a91d0813c",
  "measured_reference_onsets":63,
  "reference_phase_fit_best_bpm":102,
  "reference_analysis_caveat":"transient detector and rhythm grid, not original BPM/MIDI",
  "music_authorship":"all chords, voicings, pitches, timings new and hand-composed",
  "chord_sequence":["F#m11","Dmaj9","Aadd9/C#","E7sus4-E7","Aadd9"],
  "bpm":BPM,"meter":"4/4","musical_seconds":MUSICAL_DURATION,"render_seconds":RENDER_DURATION,
  "note_count":len(m.NOTES),"bass_notes":sum(x[4]==0 for x in m.NOTES),
  "chord_notes":sum(x[4]==1 for x in m.NOTES),"suspension_notes":sum(x[4]==2 for x in m.NOTES),
  "rhythm_grid":grid,"sf2_source":"SalamanderGrandPiano-V3+20200602.sf2",
  "piano_only":True,"qa_audio":qa,"integrated_lufs":integrated_lufs(final),
  "files":{p.name:{"bytes":p.stat().st_size,"sha256":sha(p)} for p in (midi,final)},
  "music_quality":"NOT_APPROVED_UNTIL_USER_LISTENS",
  "production_changes":False
 }
 manifest=out/(STEM+"_manifest.json")
 manifest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
