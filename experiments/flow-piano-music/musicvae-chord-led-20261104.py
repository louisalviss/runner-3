#!/usr/bin/env python3
"""Research-only chord-led piano arrangement of prior M2 MusicVAE melody.

Read-only parent: musicvae-original-hook-20261104.py at known Git blob.
Preserves all twelve soprano pitches/times, rewrites accompaniment and rhythmic
structure. No reference TikTok note sequences copied. Never alters v1.2 masters.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

BASE_BLOB = "d23091c87d0a396fb244a82973e665988715e679"
BASE_NAME = "musicvae-original-hook-20261104.py"

def _load_base():
    path = Path(__file__).with_name(BASE_NAME)
    raw = path.read_bytes()
    git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()
    if git_blob != BASE_BLOB:
        raise RuntimeError("Unexpected source M2 Git blob; fail closed")
    spec = importlib.util.spec_from_file_location("musicvae_parent_m2",path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def make_score(m):
    m.make_score()
    original_top = [event for event in m.NOTES if event[4] == 2]
    if len(original_top) != 12:
        raise RuntimeError("Expected original 12-note M2 topline")
    m.NOTES[:] = original_top
    m.CONTROL.clear()
    notes = m.NOTES
    def put(t,d,p,v,ch,desc):
        m.n(t,d,p,v,ch,desc)
    def chord(t,root,pitches,*,sustain=1.75,vel=62,rootvel=53,name):
        put(t+.009,min(sustain,7.99-t),root,rootvel,0,name+"-bass")
        for j,p in enumerate(pitches):
            put(t+.013,min(sustain-.08,7.99-t),p,vel-(j%2)*3,1,name+"-inner")
    def stroke(t,pitches,*,duration=.28,vel=59,name):
        for i,p in enumerate(pitches):
            put(t+.012+i*.004,duration,p,vel-i*2,1,name+"-restroke")

    # Chord-led with individual upper soprano notes already playing inside
    # the simultaneously voiced chords. Use full voices plus selective strikes,
    # not automatic every-16th plucks or chord extensions as a complexity quota.
    chord(0.00,38,[53,57,60,62],sustain=1.78,vel=63,rootvel=54,name="Dm7")
    stroke(.25,[57,60],duration=.21,vel=54,name="Dm7")
    stroke(.50,[53,60,62],duration=.29,vel=57,name="Dm11")
    stroke(1.50,[53,57,62],duration=.22,vel=54,name="Dm11")

    # Bb2 -> F3 -> Bb3 -> D4: major triad/6th supporting held G4.
    chord(2.00,46,[53,58,62],sustain=1.78,vel=63,rootvel=55,name="Bb6")
    stroke(2.70,[53,58,62],duration=.27,vel=55,name="Bb6")
    stroke(3.15,[58,62],duration=.27,vel=51,name="Bb6")

    # Gm7: clear dark chord, repeats aligned with top F4->A4->G4->A4->C5
    chord(4.00,43,[50,55,58,62],sustain=1.78,vel=67,rootvel=55,name="Gm7")
    stroke(4.50,[55,58,62],duration=.24,vel=56,name="Gm9")
    stroke(5.00,[50,58,62],duration=.28,vel=59,name="Gm9")
    stroke(5.50,[55,58,62],duration=.24,vel=58,name="Gm11")

    # Tension and purposeful cadence: D4 suspension resolves to C#4,
    # finally pivot to Dm. Held model A4 remains an audible common tone.
    chord(6.00,45,[52,55,62],sustain=1.13,vel=65,rootvel=53,name="A7sus4")
    stroke(6.50,[52,55],duration=.24,vel=55,name="A7sus4")
    put(6.79,.37,61,61,1,"A7-third-resolution")
    chord(7.24,38,[53,57,62],sustain=.72,vel=59,rootvel=51,name="Dm-arrival")

    # Avoid overlapping note-on of identical pitch/channel which makes
    # its paired note_off terminate the newer strike in sampled SF2 engines.
    by_key={}
    for i,(start,dur,pitch,velocity,ch,source) in enumerate(notes):
        by_key.setdefault((ch,pitch),[]).append(i)
    truncated_count=0
    for indices in by_key.values():
        indices.sort(key=lambda i:notes[i][0])
        for previous,current in zip(indices,indices[1:]):
            t,d,p,v,ch,label=notes[previous]
            next_t=notes[current][0]
            if t+d >= next_t-.005:
                adjusted=round(next_t-t-.012,4)
                if adjusted <=.04:
                    raise RuntimeError("Impossible same-note re-strike separation")
                notes[previous]=(t,adjusted,p,v,ch,label)
                truncated_count+=1
    for ped_on,ped_off in ((.045,1.88),(2.045,3.88),(4.045,5.88),
                           (6.045,7.15),(7.27,7.96)):
        for ch in (0,1,2):
            m.CONTROL.extend(((ped_on,ch,64,76),(ped_off,ch,64,0)))
    return original_top, truncated_count

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def measure_lufs(path):
    import re
    p=subprocess.run(["ffmpeg","-nostdin","-hide_banner","-i",str(path),
                      "-filter_complex","ebur128=peak=true","-f","null","-"],
                     capture_output=True,text=True,timeout=18)
    matches=re.findall(r"I:\s*(-?\d+(?:\.\d+)?) LUFS",p.stderr)
    if p.returncode or not matches:
        raise RuntimeError("Failed integrated loudness analysis")
    return float(matches[-1])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output-dir",required=True)
    ap.add_argument("--original-mp3",required=True)
    args=ap.parse_args()
    output=Path(args.output_dir)
    if output.exists() and any(output.iterdir()):
        raise RuntimeError("Refusing overwrite of nonempty output folder")
    output.mkdir(parents=True,exist_ok=True)
    base=_load_base()
    top,shorten=make_score(base)
    prefix="New_Hook_M2_ChordLed_8s"
    (output/(prefix+".mid")).write_bytes(base.midi_bytes())
    wav,initial,qa=base.render_audio(output,base.SF2)
    reference=Path(args.original_mp3)
    reference_integrated=measure_lufs(reference)
    initial_integrated=measure_lufs(initial)
    gain=round(reference_integrated-initial_integrated,2)
    if abs(gain)>3:
        raise RuntimeError("Gross loudness mismatch")
    final=output/(prefix+".mp3")
    # Create final from original uncompressed WAV rather than recompress MP3.
    p=subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
                      "-i",str(wav),"-af",("highpass=f=40,lowpass=f=12000,"
                      "loudnorm=I=-16:TP=-2:LRA=8,volume="+str(gain)+"dB"),
                      "-ar","44100","-c:a","libmp3lame","-b:a","192k",str(final)],
                     capture_output=True,text=True,timeout=35)
    if p.returncode:
        raise RuntimeError("Final MP3 render failed: "+p.stderr[-500:])
    final_lufs=measure_lufs(final)
    if abs(final_lufs-reference_integrated)>.31:
        raise RuntimeError("Failed A/B perceived-loudness match")
    initial.unlink()  # no duplicate candidate preview in output scope
    wav.unlink()  # sampled raw backing is reproducible from script/SF2
    report={
        "status":"CHORD_LED_AB_AUDITION_PENDING",
        "base_source_git_blob":BASE_BLOB,
        "note_count":len(base.NOTES),
        "topline_count":len(top),
        "bass_notes":sum(x[4]==0 for x in base.NOTES),
        "inner_voice_notes":sum(x[4]==1 for x in base.NOTES),
        "same_pitch_overlap_truncated":shorten,
        "soprano_pitches":[e[2] for e in top],
        "soprano_times":[e[0] for e in top],
        "reference_baseline_sha256":sha(reference),
        "reference_integrated_lufs":reference_integrated,
        "raw_candidate_lufs":initial_integrated,
        "match_gain_db":gain,
        "candidate_integrated_lufs":final_lufs,
        "lufs_delta":round(final_lufs-reference_integrated,2),
        "artifact_files":{p.name:{"sha256":sha(p),"bytes":p.stat().st_size}
                          for p in [output/(prefix+".mid"),final]},
        "human_music_review":"PENDING",
        "production_change":False,
    }
    (output/(prefix+"_manifest.json")).write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__":
    main()
