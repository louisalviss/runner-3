#!/usr/bin/env python3
"""AFTER RAIN — 14-second, original chord-led solo piano study.

Composition, not a transcription or continuation of M2. Deliberate motif:
D5-C5-A4 is a descending question, returning as E5-C5-A4 with a different
ending. An expanding response peaks over A7, then resolves to D minor.

Research-only: sound is sampled Salamander Grand; no changes to masters.
Audio/video publication requires independent listener approval.
The M2 source module is imported ONLY to reuse the vetted FluidSynth,
MIDI type-1 and audio renderer, never its MusicVAE notes.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json
from pathlib import Path

PARENT_BLOB="d23091c87d0a396fb244a82973e665988715e679"
PARENT_NAME="musicvae-original-hook-20261104.py"
STEM="After_Rain_Original_Piano_14s"
PITCH_A=(74,72,69)
PITCH_A_VARIANT=(76,72,69)
HARMONY=[
    (0.0,2.0,"Dm9",38,[53,57,60,64],52,62),
    (2.0,2.0,"Dm7/C",48,[53,57,60,62],49,60),
    (4.0,2.0,"Bbadd9",46,[53,58,62,65],54,62),
    (6.0,2.0,"Fadd9/A",45,[53,57,60,67],51,60),
    (8.0,2.0,"Gm7",43,[50,55,58,65],52,63),
    (10.0,2.0,"A7sus4-A7",45,[52,55,62,64],51,61),
    (12.0,2.0,"Dm(add9)",38,[53,57,62,64],50,59),
]
# Local starts and durations are semantically composed; never randomly generated.
# Onsets are *not* one-event-per-beat except for selected musical stresses.
TOP=[
    (.15,.28,74,85,"A:call"),
    (.52,.28,72,80,"A:short-answer"),
    (.99,.77,69,88,"A:landing"),
    (1.82,.28,72,74,"pickup"),
    (2.30,.25,74,85,"A:recall"),
    (2.64,.35,77,92,"A:expand"),
    (3.21,.27,76,80,"sigh"),
    (3.60,.31,74,81,"D:cadence"),
    (4.17,.28,72,79,"B:start"),
    (4.62,.31,74,84,"B:rising"),
    (5.09,.68,77,93,"B:arrival"),
    (6.23,.25,76,80,"A:variant"),
    (6.56,.31,72,80,"A:variant2"),
    (7.03,.65,69,88,"A:variant3"),
    (8.30,.32,70,80,"C:question"),
    (8.85,.31,74,89,"C:upward"),
    (9.36,.43,72,82,"C:hold-back"),
    (10.15,.26,73,83,"dominant-third"),
    (10.59,.34,76,88,"dominant-rise"),
    (11.16,.31,79,92,"single-climax"),
    (11.61,.25,76,80,"drop"),
    (12.17,.27,77,84,"resolution-start"),
    (12.57,.27,76,77,"resolution-sigh"),
    (13.07,.78,74,88,"tonic-rest"),
]
# Syncopated inner-voice responses, with deliberately missing pulses.
RESPONSES=[
    (1.51,[57,60],.31,51,"A:echo"),
    (3.50,[53,57],.24,49,"A:quiet-echo"),
    (5.44,[58,62],.33,50,"B:lift"),
    (9.53,[55,58],.24,51,"C:anacrusis"),
    (11.49,[52,55],.22,52,"dominant:turn"),
]
# Sustain is released AFTER next new harmonic attack (45 ms), then repedaled.
PEDAL=[(0.06,4.04),(4.09,6.045),(6.10,8.04),
       (8.10,10.04),(10.09,12.04),(12.10,13.88)]

def parent():
    p=Path(__file__).with_name(PARENT_NAME)
    b=p.read_bytes()
    blob=hashlib.sha1(b"blob "+str(len(b)).encode()+bytes((0,))+b).hexdigest()
    if blob != PARENT_BLOB:
        raise RuntimeError("Pinned piano renderer source changed")
    spec=importlib.util.spec_from_file_location("piano_renderer_m2",str(p))
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def build(m):
    m.SECONDS=14.0
    m.RENDER_SECONDS=14.65
    m.NOTES.clear();m.CONTROL.clear()
    def add(t,d,p,v,ch,label):
        m.n(t,d,p,v,ch,label)
    for start,secs,name,bass,voicing,bvel,ivel in HARMONY:
        add(start+.010,min(1.82,secs-.18),bass,bvel,0,name+":bass")
        for j,p in enumerate(voicing):
            add(start+.033+j*.007,1.69,p,ivel-2*(j%3),1,name+":voicing")
    # Phrasal human piano accents are narrowly varied by design, not random jitter.
    for t,d,p,v,label in TOP:
        add(t,d,p,v,2,label)
    for t,tones,d,v,label in RESPONSES:
        for j,p in enumerate(tones):
            add(t+.008*j,d,p,v-2*j,1,label)
    # One clear A7sus4→A7 voice resolution BEFORE the D minor return.
    add(11.08,.59,61,63,1,"A7:Csharp4-third-resolution")
    for st,en in PEDAL:
        for ch in (0,1,2):
            m.CONTROL.extend([(st,ch,64,76),(en,ch,64,0)])
    # Note-off ordering: no same-pitch overlap at a restrike; CC64 holds sound.
    by={}
    for i,(t,d,p,v,ch,name) in enumerate(m.NOTES):
        by.setdefault((ch,p),[]).append(i)
    shortened=0
    for idxs in by.values():
        idxs.sort(key=lambda i:m.NOTES[i][0])
        for i,j in zip(idxs,idxs[1:]):
            t,d,p,v,ch,label=m.NOTES[i]
            nt=m.NOTES[j][0]
            if t+d>=nt-.008:
                nd=round(nt-t-.019,4)
                if nd<.06:
                    raise RuntimeError("Same-key notes too close for safe retrigger")
                m.NOTES[i]=(t,nd,p,v,ch,label)
                shortened+=1
    # Note count/phrase logic gates. These cannot certify perceptual quality.
    assert len(TOP)==24
    assert [p for _,_,p,_,_ in TOP[:3]]==list(PITCH_A)
    assert [p for _,_,p,_,_ in TOP[11:14]]==list(PITCH_A_VARIANT)
    assert [x[0] for x in RESPONSES]!=[1.5,3.5,5.5,7.5,9.5]
    assert max(TOP,key=lambda e:e[2])[2]==79
    return shortened

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",required=True)
    args=p.parse_args()
    out=Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise RuntimeError("Non-empty output folder; refusing to overwrite research")
    out.mkdir(parents=True,exist_ok=True)
    m=parent()
    shortened=build(m)
    mid=out/(STEM+".mid")
    mid.write_bytes(m.midi_bytes())
    wav,mp3,rawqa=m.render_audio(out,m.SF2)
    clean=out/(STEM+".mp3")
    mp3.rename(clean)
    wav.unlink()
    report={
       "status":"RESEARCH_AUDITION_PENDING",
       "title":"After Rain — original chord-led solo piano",
       "purpose":"New original composition after two rejected M2 longer developments",
       "musical_provenance":"24 hand-composed soprano events; no benchmark or M2 melody copied",
       "composition_principles":["three-note descending motif","recall with augmentation","phrased rests","inner-voice common tones","intentional sparse syncopation","one dominant climax and tonic resolution"],
       "bpm":120,"bar_count":7,"duration_musical_s":14.0,"rendered_s":14.65,
       "harmony":[{"start":row[0],"name":row[2],"bass":row[3],"inner":row[4]} for row in HARMONY],
       "melody":[{"start":t,"duration":d,"pitch":pitch,"velocity":vel,"motif":tag} for t,d,pitch,vel,tag in TOP],
       "top_note_count":len(TOP),
       "inner_note_count":sum(x[4]==1 for x in m.NOTES),
       "bass_note_count":sum(x[4]==0 for x in m.NOTES),
       "same_key_truncation_count":shortened,
       "sf2_source":"SalamanderGrandPiano-V3+20200602.sf2",
       "soundfont_author":"Alexander Holm (CC BY 3.0); sample not redistributed",
       "audio_qa":rawqa,
       "artifacts":{x.name:{"sha256":sha(x),"bytes":x.stat().st_size} for x in (mid,clean)},
       "human_music_quality":"PENDING; user's listening overrides structural QA",
       "production_changes":False
    }
    manifest=out/(STEM+"_manifest.json")
    manifest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+chr(10))
    print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
