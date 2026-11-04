#!/usr/bin/env python3
"""M2 chord-led piano groove repair, research only.

Preserves the exact previous 12-note M2 soprano (pitch, onset and duration);
rebuilds only accompaniment to a stable 4/4 pulse at 120 BPM.
Expected one-bar pattern: bass beat 1; soft chord 2&; bass beat 3;
soft chord beat 4. Bass/inner chords and pedal remain piano-only.

Prior M2/chord-led artifacts and Concert A+ masters stay immutable.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

PARENT_NAME = "musicvae-original-hook-20261104.py"
PARENT_BLOB = "d23091c87d0a396fb244a82973e665988715e679"
BPM = 120
BEAT_SECONDS = 0.5
CHORDS = (
    (0.0,"Dm7",38,45,(53,57,60),(57,60,62)),
    (2.0,"Bb6",46,53,(53,58,62),(53,58,62)),
    (4.0,"Gm7",43,50,(50,55,58,62),(55,58,62)),
    (6.0,"A7sus4",45,52,(52,55,62),(52,55,62)),
)

def load_parent():
    path=Path(__file__).with_name(PARENT_NAME)
    b=path.read_bytes()
    git_blob=hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
    if git_blob != PARENT_BLOB:
        raise RuntimeError("Unexpected parent M2 source. Reproducibility gate failed.")
    spec=importlib.util.spec_from_file_location("m2_piano_parent",str(path))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def build(m):
    m.make_score()
    top=[n for n in m.NOTES if n[4]==2]
    if len(top)!=12:
        raise RuntimeError("Unexpected M2 melody")
    m.NOTES[:] = top
    m.CONTROL.clear()
    def add(t,d,p,v,ch,tag):
        m.n(round(t,4),round(d,4),p,v,ch,tag)
    rhythm=[]
    for bar,(t,name,root,fifth,held,pulsed) in enumerate(CHORDS):
        # Bass 1-3: create an audible repeated meter without drums.
        add(t+.012,1.55,root,54 if bar in (0,2) else 51,0,name+"-beat1")
        add(t+1.012,.68,fifth,47 if bar in (0,2) else 45,0,name+"-beat3")
        rhythm.extend((("bass",round(t,2)),("bass",round(t+1,2))))
        # Voice-leading across long notes; do not re-strike all notes at random times.
        for j,p in enumerate(held):
            add(t+.016+.008*j,1.76,p,62-(j%2)*2,1,name+"-long")
        # Same 4/4 pattern in each full 2s harmonic bar.
        # 2& (0.75 seconds), 4 (1.50 seconds).
        # The fourth bar replaces 4th-beat strike with the Dm landing.
        for offset,vel in ((.75,51),(1.5,53)):
            if bar==3 and offset==1.5:
                continue
            for j,p in enumerate(pulsed):
                add(t+offset+.015+.004*j,.41,p,vel-j*2,1,name+"-groove")
            rhythm.append(("chord_pulse",round(t+offset,2)))
    # A7sus4's third resolves on beat 3 before the final Dm landing.
    add(7.013,.39,61,57,1,"A7-Csharp-resolution")
    # Final D minor lands squarely on beat 4; piano-only bass and chord.
    for j,p in enumerate((53,57,62)):
        add(7.514+j*.009,.46,p,58-2*j,1,"Dm-final-landing")
    add(7.511,.46,38,54,0,"Dm-final-bass")
    rhythm.extend((("resolution",7.0),("final_chord",7.5)))

    # Pedal change *just after* the new chord attack, then repedal.
    # This avoids a dry 100-140 ms hole at each bar boundary.
    pedal_times=[(0.,78),(2.035,0),(2.085,78),
                 (4.035,0),(4.085,78),
                 (6.035,0),(6.085,78),
                 (7.535,0),(7.575,72),(8.055,0)]
    for at,val in pedal_times:
        for ch in (0,1,2):
            m.CONTROL.append((at,ch,64,val))

    # Re-strike on same pitch+channel must not have stacked note-ons;
    # old voice is still held acoustically by sustain controller.
    by_key={}
    for idx,(t,d,p,v,ch,src) in enumerate(m.NOTES):
        by_key.setdefault((ch,p),[]).append(idx)
    adjusted=0
    for idxs in by_key.values():
        idxs.sort(key=lambda i:m.NOTES[i][0])
        for older,newer in zip(idxs,idxs[1:]):
            t,d,p,v,ch,name=m.NOTES[older]
            next_t=m.NOTES[newer][0]
            if t+d>=next_t-.006:
                new_d=round(next_t-t-.014,4)
                if new_d<=.045:
                    raise RuntimeError("Unresolvable overlapping same-pitch attack")
                m.NOTES[older]=(t,new_d,p,v,ch,name)
                adjusted+=1
    beats=[n[1] for n in rhythm if n[0]=="bass"]
    pulses=[n[1] for n in rhythm if n[0]=="chord_pulse"]
    assert beats==[0.,1.,2.,3.,4.,5.,6.,7.],beats
    assert pulses==[.75,1.5,2.75,3.5,4.75,5.5,6.75],pulses
    return top, adjusted, rhythm

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",required=True)
    p.add_argument("--previous-mp3",required=True)
    args=p.parse_args()
    dest=Path(args.output_dir)
    if dest.exists() and any(dest.iterdir()):
        raise RuntimeError("No overwrite: the output directory is not empty")
    dest.mkdir(parents=True,exist_ok=True)
    previous=Path(args.previous_mp3)
    if sha(previous)!="b45a58238b6cef5b6ad81cb6b75083163648005e6cf74ca419303f809843196d":
        raise RuntimeError("Old chord-led B reference SHA changed")
    m=load_parent()
    melody,shortened,rhythm=build(m)
    stem="M2_ChordLed_GrooveSmooth_8s"
    midi=dest/(stem+".mid")
    midi.write_bytes(m.midi_bytes())
    wav,intermediate,audio=m.render_audio(dest,m.SF2)

    # Use the exact same loudness gate as previous M2 A/B.
    from importlib.util import spec_from_file_location,module_from_spec
    # EBU R128 integrated measurement using ffmpeg, not a loudness estimate.
    import re
    def lufs(x):
        q=subprocess.run(["ffmpeg","-nostdin","-hide_banner","-i",str(x),
          "-filter_complex","ebur128=peak=true","-f","null","-"],
          capture_output=True,text=True,timeout=20)
        match=re.findall(r"I:\s*(-?\d+(?:\.\d+)?) LUFS",q.stderr)
        if q.returncode or not match:
            raise RuntimeError("ffmpeg loudness analysis failed")
        return float(match[-1])
    old_lufs=lufs(previous)
    raw_lufs=lufs(intermediate)
    gain=round(old_lufs-raw_lufs,2)
    if abs(gain)>3:raise RuntimeError("Unreasonable loudness correction")
    final=dest/(stem+".mp3")
    q=subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error",
        "-y","-i",str(wav),"-af","highpass=f=40,lowpass=f=12000,"
        "loudnorm=I=-16:TP=-2:LRA=8,volume="+str(gain)+"dB",
        "-ar","44100","-c:a","libmp3lame","-b:a","192k",str(final)],
        capture_output=True,text=True,timeout=45)
    if q.returncode:
        raise RuntimeError("Final ffmpeg render failed "+q.stderr[-400:])
    got=lufs(final)
    if abs(got-old_lufs)>.31:
        raise RuntimeError("Failed loudness match: "+str(got-old_lufs))
    wav.unlink()
    intermediate.unlink()
    result={
        "classification":"GROOVE_4_4_TECHNICAL_PASS_HUMAN_REVIEW_PENDING",
        "bpm":BPM,"beats_per_bar":4,"seconds_per_beat":BEAT_SECONDS,
        "melody_notes":len(melody),
        "soprano_event_data":[list(x[:5]) for x in melody],
        "bass_notes":sum(x[4]==0 for x in m.NOTES),
        "inner_voice_notes":sum(x[4]==1 for x in m.NOTES),
        "same_key_shortened_voices":shortened,
        "rhythm_pattern":rhythm,
        "pedal_change_strategy":"new chord starts, then brief pedal-up/re-pedal",
        "previous_version_B_sha256":sha(previous),
        "previous_version_B_lufs":old_lufs,
        "new_version_lufs":got,
        "new_minus_previous_lufs":round(got-old_lufs,3),
        "files":{file.name:{"bytes":file.stat().st_size,"sha256":sha(file)}
                 for file in (midi,final)},
        "user_quality_verdict":"PENDING",
        "production_changes":False
    }
    mf=dest/(stem+"_manifest.json")
    mf.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":main()
