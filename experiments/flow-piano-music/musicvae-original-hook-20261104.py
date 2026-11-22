#!/usr/bin/env python3
"""Isolated MusicVAE topline + hand-harmonized solo-piano audition.

Composer research only. The upper melodic phrase below is one of 14 authentic
Magenta MusicVAE mel_4bar_med_lokl_q2 CPU samples, selected by phrase structure.
It is NOT the melody from the accepted 30s piano-roll benchmark.
Manual harmony/voicing is disclosed. No sample or original master is changed.
"""
from __future__ import annotations

import argparse
import ctypes as ct
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

CHECKPOINT = "https://storage.googleapis.com/magentadata/js/checkpoints/music_vae/mel_4bar_med_lokl_q2"
MODEL_SAMPLES_SHA = "c9935a1887ce5a181384ef521ec5db3a4f665f4e83d5e77dba251cd93e438c26"
MODEL_SAMPLE_INDEX = 12
BEAT_BPM = 120
PPQ = 480
SECONDS = 8.0
RENDER_SECONDS = 8.65
SF2 = "/opt/flow-piano-music/assets/SalamanderGrandPiano-SF2-V3+20200602/SalamanderGrandPiano-V3+20200602.sf2"

# Generated 4-bar 64-step MusicVAE melody. Preserve model pitch/time
# intervals; octave shift (+12) only places it in the piano upper register.
TOPLINE = [
    (62,0,2),(60,2,4),(57,4,6),(55,6,12),
    (57,12,14),(55,14,32),(53,32,36),(57,36,38),
    (55,38,40),(57,40,44),(60,44,46),(57,46,64),
]
MELODY_VELOCITIES = [98,88,84,79,87,77,78,89,81,91,104,89]
assert len(TOPLINE) == len(MELODY_VELOCITIES)
# Each event: start seconds, duration seconds, MIDI pitch, velocity, channel, source.
NOTES: list[tuple[float,float,int,int,int,str]] = []
CONTROL: list[tuple[float,int,int,int]] = []

def n(t, d, p, v, ch, source):
    assert 0 <= t < SECONDS and .04 < d <= SECONDS and 24 <= p <= 100
    NOTES.append((round(t,4),round(min(d,SECONDS-t),4),p,v,ch,source))

def chord(start, duration, bass, inner, label, *,
          vel=57, bassvel=48):
    # Bass and inner piano voices are spread, not dense low-mid chord blocks.
    n(start+.008,min(duration,1.7),bass,bassvel,0,label)
    for i,p in enumerate(inner):
        n(start+.032+i*.014,min(duration-.1,1.65),p,
          vel+((i%3)-1)*3,1,label)

def make_score():
    NOTES.clear()
    CONTROL.clear()
    for i,(pitch,st,ed) in enumerate(TOPLINE):
        t=st*.125
        dur=max(.10,(ed-st)*.125-.025)
        n(t+.025,dur,pitch+12,MELODY_VELOCITIES[i],2,"MusicVAE-topline")

    # Intentional chord-scale voice-leading around D minor; independently
    # designed accompaniment under the model's D–C–A–G / F–A–G–A–C–A melody.
    chord(0,2,38,[53,57,60,64],"Dm9",vel=58,bassvel=51)
    # Restrikes inside a long-held harmony, creating pulse without drums.
    n(1.05,.36,57,48,1,"Dm9-restroke")
    n(1.05,.36,60,47,1,"Dm9-restroke")
    n(1.51,.29,53,51,1,"Dm9-restroke")
    n(1.51,.29,64,49,1,"Dm9-restroke")

    # Bbmaj13: G4 held by the model is 13th; common F3/A3 move little.
    chord(2,2,46,[53,57,62,65],"Bbmaj13",vel=55,bassvel=49)
    n(2.93,.36,57,47,1,"Bbmaj13-restroke")
    n(2.93,.36,62,49,1,"Bbmaj13-restroke")

    # Gm11: F4 (seventh), A4 (ninth), C5 (eleventh) in the model melody.
    chord(4,2,43,[50,58,62],"Gm11",vel=61,bassvel=51)
    n(4.92,.34,58,49,1,"Gm11-restroke")
    n(4.92,.34,62,52,1,"Gm11-restroke")

    # Dominant suspension followed by inner-voice 4->3 resolution.
    chord(6,1.15,45,[52,55,62],"A7sus4",vel=54,bassvel=50)
    n(6.63,.39,61,59,1,"A7-3rd-resolution")

    # D minor release, while the model's held A4 resolves as the fifth.
    chord(7.15,.85,38,[53,57,62,65],"Dm-resolution",vel=55,bassvel=48)

    for st,en in ((.045,1.87),(2.045,3.88),(4.045,5.89),
                  (6.045,7.08),(7.19,7.82)):
        for ch in (0,1,2):
            CONTROL.extend(((st,ch,64,85),(en,ch,64,0)))
    # Repeated strikes of the SAME pitch/channel must release the previous
    # voice first. Otherwise a later note_off can cut the newly struck note.
    # Pedal CC64 preserves the intended sustain across this humanized re-strike.
    by_key={}
    for i,(t,d,p,v,ch,source) in enumerate(NOTES):
        by_key.setdefault((ch,p),[]).append(i)
    for indices in by_key.values():
        indices.sort(key=lambda i:NOTES[i][0])
        for previous,current in zip(indices,indices[1:]):
            t,d,p,v,ch,label=NOTES[previous]
            next_start=NOTES[current][0]
            if t+d>=next_start-.005:
                safe_d=round(next_start-t-.011,4)
                if safe_d<.06:
                    raise RuntimeError("Repeated same-pitch attacks are too close")
                NOTES[previous]=(t,safe_d,p,v,ch,label)
    return NOTES

def vlq(n):
    if n < 0:raise ValueError("Negative delta time")
    b=[n&0x7f];n>>=7
    while n:
        b.insert(0,(n&0x7f)|0x80);n>>=7
    return bytes(b)

def midi_bytes():
    tracks=[]
    meta=(b"\x00\xff\x51\x03"+(500000).to_bytes(3,"big")
          +b"\x00\xff\x58\x04\x04\x02\x18\x08"
          +b"\x00\xff\x2f\x00")
    tracks.append(meta)
    for ch in (0,1,2):
        events=[(0,1,bytes([0xC0+ch,0]))]
        for t,d,p,v,c,_ in NOTES:
            if c!=ch:continue
            start=round(t*PPQ*BEAT_BPM/60)
            end=round((t+d)*PPQ*BEAT_BPM/60)
            events.extend(((start,3,bytes([0x90+ch,p,v])),
                           (end,0,bytes([0x80+ch,p,0]))))
        for t,c,cc,val in CONTROL:
            if c==ch:events.append((round(t*PPQ*BEAT_BPM/60),2,bytes([0xB0+ch,cc,val])))
        events.sort(key=lambda x:(x[0],x[1]))
        data=bytearray()
        prev=0
        for tick,_,message in events:
            data+=vlq(tick-prev)+message;prev=tick
        data+=b"\x00\xff\x2f\x00"
        tracks.append(bytes(data))
    raw=b"MThd"+struct.pack(">IHHH",6,1,len(tracks),PPQ)
    for track in tracks:raw+=b"MTrk"+struct.pack(">I",len(track))+track
    return raw

def render_audio(output, sf2):
    import numpy as np
    sample_rate=44100
    length=round(RENDER_SECONDS*sample_rate)
    library=ct.CDLL(ctypes.util.find_library("fluidsynth"))
    P=ct.c_void_p; I=ct.c_int; D=ct.c_double
    def api(name, ret, argtypes):
        f=getattr(library,name);f.restype=ret;f.argtypes=argtypes;return f
    settings=api("new_fluid_settings",P,[])()
    api("fluid_settings_setnum",I,[P,ct.c_char_p,D])(settings,b"synth.sample-rate",float(sample_rate))
    api("fluid_settings_setnum",I,[P,ct.c_char_p,D])(settings,b"synth.gain",0.30)
    setint=api("fluid_settings_setint",I,[P,ct.c_char_p,I])
    setint(settings,b"synth.polyphony",96)
    setint(settings,b"synth.reverb.active",1)
    setint(settings,b"synth.chorus.active",0)
    synth=api("new_fluid_synth",P,[P])(settings)
    sfid=api("fluid_synth_sfload",I,[P,ct.c_char_p,I])(synth,str(sf2).encode(),1)
    if sfid < 0:raise RuntimeError("sampled piano not loaded")
    select=api("fluid_synth_program_select",I,[P,I,I,I,I])
    for channel in (0,1,2):
        if select(synth,channel,sfid,0,0)!=0:raise RuntimeError("Piano program unavailable")
    noteon=api("fluid_synth_noteon",I,[P,I,I,I])
    noteoff=api("fluid_synth_noteoff",I,[P,I,I])
    cc=api("fluid_synth_cc",I,[P,I,I,I])
    write=api("fluid_synth_write_float",I,[P,I,P,I,I,P,I,I])

    events=[]
    for t,d,p,v,ch,_ in NOTES:
        events.append((round(t*sample_rate),2,ch,p,v))
        events.append((round((t+d)*sample_rate),0,ch,p,0))
    for t,ch,num,value in CONTROL:
        events.append((round(t*sample_rate),1,ch,num,value))
    events.sort(key=lambda e:(e[0],e[1]))
    left=np.zeros(length,dtype=np.float32)
    right=np.zeros(length,dtype=np.float32)
    cursor=j=0
    while cursor<length:
        while j<len(events) and events[j][0]<=cursor:
            _,typ,ch,p,v=events[j]
            if typ==0:noteoff(synth,ch,p)
            elif typ==1:cc(synth,ch,p,v)
            else:noteon(synth,ch,p,v)
            j+=1
        end=min(length,cursor+4096,events[j][0] if j<len(events) else length)
        if end<=cursor:end=cursor+1
        l=left[cursor:end];r=right[cursor:end]
        if write(synth,end-cursor,P(l.ctypes.data),0,1,P(r.ctypes.data),0,1)!=0:
            raise RuntimeError("Failed rendering sampled piano")
        cursor=end

    peak=float(np.max(np.abs(np.r_[left,right])))
    rms=float(np.sqrt(np.mean((left.astype(np.float64)**2+right.astype(np.float64)**2)/2)))
    if peak < .01 or rms<.0005:raise RuntimeError("Silent/near-silent piano render")
    import wave
    wav=output/"New_Hook_MusicVAE_Dm_8s.wav"
    interleaved=np.column_stack((left,right))
    pcm=(np.clip(interleaved,-.99,.99)*32767).astype(np.int16)
    with wave.open(str(wav),"wb") as w:
        w.setnchannels(2);w.setsampwidth(2)
        w.setframerate(sample_rate);w.writeframes(pcm.tobytes())
    mp3=output/"New_Hook_MusicVAE_Dm_8s.mp3"
    subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
                    "-i",str(wav),"-af","highpass=f=40,lowpass=f=12000,"
                    "loudnorm=I=-16:TP=-2:LRA=8","-ar","44100",
                    "-c:a","libmp3lame","-b:a","192k",str(mp3)],
                   capture_output=True,text=True,check=True,timeout=45)
    return wav,mp3,{"raw_audio_peak":round(peak,6),"raw_audio_rms":round(rms,6)}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output-dir",required=True)
    ap.add_argument("--sf2",default=SF2)
    args=ap.parse_args()
    output=Path(args.output_dir)
    if output.exists() and any(output.iterdir()):
        raise RuntimeError("Output folder is not empty; refusing to overwrite")
    output.mkdir(parents=True,exist_ok=True)
    make_score()
    mid=output/"New_Hook_MusicVAE_Dm_8s.mid"
    mid.write_bytes(midi_bytes())
    wav,mp3,audio=render_audio(output,args.sf2)
    import wave
    with wave.open(str(wav),"rb") as w:
        audioduration=w.getnframes()/w.getframerate()
    report={
        "status":"AUDITION_PENDING_USER_LISTENING",
        "source_model":"Magenta MusicVAE mel_4bar_med_lokl_q2",
        "source_sample_index":MODEL_SAMPLE_INDEX,
        "source_14_samples_sha256":MODEL_SAMPLES_SHA,
        "melody_authorship":"model-sampled motif; octave+12; no original benchmark notes used",
        "harmony_authorship":"new authored accompaniment under model motif",
        "bpm":BEAT_BPM,"motif_beats":16,
        "motif_seconds":SECONDS,"render_seconds":audioduration,
        "melody_notes":len(TOPLINE),
        "bass_notes":sum(n[4]==0 for n in NOTES),
        "inner_notes":sum(n[4]==1 for n in NOTES),
        "piano_only":True,
        "source_notes":[{"pitch":p,"start_step":st,"end_step":ed} for p,st,ed in TOPLINE],
        "files":{p.name:{"sha256":sha(p),"bytes":p.stat().st_size} for p in (mid,wav,mp3)},
        "audio_qa":audio,
        "musical_quality":"NOT_APPROVED; listening feedback required",
        "production_changes":"NONE",
    }
    manifest=output/"New_Hook_MusicVAE_Dm_manifest.json"
    manifest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__":
    main()
