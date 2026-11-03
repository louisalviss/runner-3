#!/usr/bin/env python3
"""Flow Piano Music v1: render an existing note-level manifest to MP4/MP3/MIDI.
Replays the user-approved 30-second visual style; no chord guessing or network calls.
The source manifest is an explicit input and is never overwritten.
"""
import argparse
import ctypes as C
import ctypes.util
import json
import math
import struct
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import signal
from scipy.io import wavfile

SR = 44100
FPS = 30
WIDTH, HEIGHT = 720, 1280
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_REGULAR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
DEFAULT_SF2 = '/opt/flow-piano-music/assets/UprightPianoKW-20220221.sf2'
ORIGINAL_APPROVED = ('Emotional_Piano_Roll_30s', 283, 30.0)

def midi_var(n):
    out=[n&127];n >>= 7
    while n:
        out.insert(0, (n&127)|128);n >>= 7
    return bytes(out)

def smf_chunk(tag, body):
    return tag+struct.pack('>I',len(body))+body

def validate(manifest):
    assert int(manifest['fps']) == 30
    assert manifest['resolution']==[WIDTH,HEIGHT]
    duration=float(manifest['duration'])
    assert 4<=duration<=180
    notes=manifest['note_events']
    assert len(notes)>0
    for n in notes:
        assert 0<=float(n['start'])<duration
        assert 0<float(n['duration']) and float(n['start'])+float(n['duration'])<=duration+.12
        assert 21<=int(n['pitch'])<=108
        assert 1<=int(n['velocity'])<=127
        assert int(n['channel']) in (0,1,2,3)
    return duration,notes

def write_midi(notes, output):
    tracks=[]
    for channel in range(4):
        ev=[]
        for n in notes:
            if int(n['channel'])!=channel:
                continue
            begin=round(float(n['start'])*960)
            stop=round((float(n['start'])+float(n['duration']))*960)
            ev.extend(((begin,1,int(n['pitch']),int(n['velocity'])),(stop,0,int(n['pitch']),0)))
        ev.sort(key=lambda a:(a[0],a[1]))
        body=(b'\x00\xff\x51\x03\x07\xa1\x20' if channel==0 else b'')
        body+=b'\x00'+bytes([0xc0|channel,0])
        prev=0
        for tick,on,pitch,velocity in ev:
            body+=midi_var(tick-prev)+bytes([(0x90 if on else 0x80)|channel,pitch,velocity])
            prev=tick
        body+=b'\x00\xff\x2f\x00'
        tracks.append(smf_chunk(b'MTrk',body))
    out=smf_chunk(b'MThd',struct.pack('>HHH',1,4,480))+b''.join(tracks)
    Path(output).write_bytes(out)

def fluid_api(lib,name,return_type,args):
    proc=getattr(lib,name);proc.restype=return_type;proc.argtypes=args
    return proc

def render_audio(notes,duration,sf2,wavpath,mp3path):
    lib=C.CDLL(ctypes.util.find_library('fluidsynth'))
    VP=C.c_void_p;I=C.c_int;D=C.c_double
    settings=fluid_api(lib,'new_fluid_settings',VP,[])()
    fluid_api(lib,'fluid_settings_setnum',I,[VP,C.c_char_p,D])(settings,b'synth.sample-rate',SR)
    fluid_api(lib,'fluid_settings_setnum',I,[VP,C.c_char_p,D])(settings,b'synth.gain',.36)
    setint=fluid_api(lib,'fluid_settings_setint',I,[VP,C.c_char_p,I])
    setint(settings,b'synth.polyphony',200)
    setint(settings,b'synth.reverb.active',0)
    setint(settings,b'synth.chorus.active',0)
    synth=fluid_api(lib,'new_fluid_synth',VP,[VP])(settings)
    sid=fluid_api(lib,'fluid_synth_sfload',I,[VP,C.c_char_p,I])(synth,str(sf2).encode(),1)
    assert sid>=0, 'Soundfont load failed'
    prog=fluid_api(lib,'fluid_synth_program_select',I,[VP,I,I,I,I])
    for channel in range(4):
        prog(synth,channel,sid,0,0)
    on=fluid_api(lib,'fluid_synth_noteon',I,[VP,I,I,I])
    off=fluid_api(lib,'fluid_synth_noteoff',I,[VP,I,I])
    write=fluid_api(lib,'fluid_synth_write_float',I,[VP,I,VP,I,I,VP,I,I])
    timeline=[]
    for n in notes:
        start=round(float(n['start'])*SR)
        stop=min(round((float(n['start'])+float(n['duration']))*SR),round(duration*SR)-1)
        ch=int(n['channel']);pitch=int(n['pitch'])
        timeline.append((start,1,pitch,int(n['velocity']),ch))
        timeline.append((stop,0,pitch,0,ch))
    timeline.sort(key=lambda x:(x[0],x[1]))
    samples=round(duration*SR)
    left=np.zeros(samples,dtype=np.float32)
    right=np.zeros(samples,dtype=np.float32)
    pos=idx=0
    while pos<samples:
        while idx<len(timeline) and timeline[idx][0]<=pos:
            _,state,pitch,vel,ch=timeline[idx]
            if state:on(synth,ch,pitch,vel)
            else:off(synth,ch,pitch)
            idx+=1
        limit=min(samples,pos+4096,timeline[idx][0] if idx<len(timeline) else samples)
        if limit<=pos:limit=pos+1
        write(synth,limit-pos,C.c_void_p(left[pos:limit].ctypes.data),0,1,C.c_void_p(right[pos:limit].ctypes.data),0,1)
        pos=limit
    audio=np.stack((left,right),axis=1)
    audio=signal.sosfilt(signal.butter(2,38,btype='highpass',fs=SR,output='sos'),audio,axis=0).astype(np.float32)
    dry=audio.copy()
    for channel in range(2):
        for delay,gain in ((.040,.07),(.091,.056),(.158,.033)):
            shift=round((delay+channel*.004)*SR)
            audio[shift:,channel]+=dry[:-shift,channel]*gain
    peak=float(abs(audio).max())
    audio*=min(2.1,.78/max(.001,peak))
    fade_n=round(.78*SR)
    audio[-fade_n:]*=np.linspace(1.,0.,fade_n,dtype=np.float32)[:,None]**1.3
    wavfile.write(str(wavpath),SR,(np.clip(audio,-1,1)*32767).astype(np.int16))
    result=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
      '-i',str(wavpath),'-c:a','libmp3lame','-b:a','224k',str(mp3path)],
      capture_output=True,text=True,timeout=100)
    if result.returncode:
        raise RuntimeError('ffmpeg MP3 error: '+result.stderr[-500:])

def labels_from_time(moment):
    chord_timeline=[(0.0, 'C#m9'), (1.875, 'Aadd9'), (3.75, 'Eadd9/G#'), (5.625, 'Bsus4-to-B'), (7.5, 'F#m9'), (9.375, 'Amaj9'), (11.25, 'Eadd9/G#'), (13.125, 'Bsus4-to-B'), (15.0, 'C#m9'), (16.875, 'Aadd9'), (18.75, 'Eadd9/G#'), (20.625, 'Bsus4-to-B'), (22.5, 'F#m11'), (24.375, 'Aadd9'), (26.25, 'G#7sus4'), (28.125, 'G#7')]
    title=chord_timeline[0][1]
    for t,label in chord_timeline:
        if moment>=t:title=label
    return title

def render_video(notes,duration,wavpath,mp4path):
    pps=116
    origin=312
    roll_top=306
    roll_height=710
    roll_width=round(origin+pps*duration+WIDTH+100)
    lane=16.0
    def y_pitch(p):
        return round(24+(83-p)*lane)
    world=Image.new('RGB',(roll_width,roll_height),'#252E36')
    dw=ImageDraw.Draw(world)
    for pitch in range(41,84):
        y=y_pitch(pitch)
        color=('#263038' if pitch%12 in (0,5,7)
                else '#222A32' if pitch%12 in (1,3,6,8,10) else '#2A333C')
        dw.rectangle((0,y,roll_width,y+round(lane)-1),fill=color)
        dw.line((0,y,roll_width,y),fill='#43505A' if pitch%12==0 else '#35404A',width=2 if pitch%12==0 else 1)
    for k in range(int(duration*2)+1):
        x=round(origin+(k/2)*pps)
        major=k%4==0
        dw.line((x,0,x,roll_height),fill='#58626B' if major else '#3C4751',width=2 if major else 1)
    dw.line((round(origin+15*pps),0,round(origin+15*pps),roll_height),fill='#9B7B44',width=3)
    for note in notes:
        start=origin+round(float(note['start'])*pps)
        stop=origin+round((float(note['start'])+float(note['duration']))*pps)
        y=y_pitch(int(note['pitch']))+2
        if y<10 or y>roll_height-15:continue
        if stop<=start:stop=start+2
        layer=note.get('layer','SOURCE_ROLL')
        color={'SOURCE_ROLL':'#CCA052','VARIATION':'#DFB260','VARIATION_ECHO':'#B78A3F'}.get(layer,'#CCA052')
        accent='#F5D489' if layer=='SOURCE_ROLL' else '#F8DCA0'
        dw.rounded_rectangle((start+1,y+2,stop+1,y+15),radius=2,fill='#141C21')
        dw.rounded_rectangle((start,y,stop,y+13),radius=2,fill=color,outline=accent,width=1)
        if stop-start>=31:dw.line((start+4,y+2,stop-3,y+2),fill=accent,width=1)
    font_label=ImageFont.truetype(FONT_BOLD,17)
    font_title=ImageFont.truetype(FONT_BOLD,43)
    font_regular=ImageFont.truetype(FONT_REGULAR,20)
    font_song=ImageFont.truetype(FONT_BOLD,28)
    font_chord=ImageFont.truetype(FONT_BOLD,48)
    font_small=ImageFont.truetype(FONT_REGULAR,16)
    font_semitone=ImageFont.truetype(FONT_REGULAR,15)
    base=Image.new('RGB',(WIDTH,HEIGHT),'#0F151E')
    d=ImageDraw.Draw(base)
    for y in range(298):
        v=y/298
        d.line((0,y,WIDTH,y),fill=(round(16+8*v),round(22+12*v),round(32+11*v)))
    for y in range(1035,HEIGHT):
        v=(y-1035)/(HEIGHT-1035)
        d.line((0,y,WIDTH,y),fill=(round(18-3*v),round(26-4*v),round(35-5*v)))
    d.rounded_rectangle((38,38,200,70),radius=16,fill='#594626')
    d.line((38,91,682,91),fill='#40505E',width=2)
    d.text((55,44),'PIANO CHORDS',font=font_label,fill='#F5D38B')
    d.text((37,106),'ELECTRIC MEMORY',font=font_title,fill='#F8F5EC')
    d.text((39,172),'30s MIDI PERFORMANCE',font=font_song,fill='#D2B67A')
    d.text((39,225),'Original hook development / Concert Grand',font=font_regular,fill='#A5B0BD')
    d.line((38,281,682,281),fill='#3D4B59',width=2)
    d.rectangle((0,roll_top,47,roll_top+roll_height),fill='#1B242D')
    for pitch in range(41,84):
        if pitch%12 not in (0,5,7):continue
        y=roll_top+y_pitch(pitch)+1
        if 315<=y<=1015:
            name=['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B'][pitch%12]+str(pitch//12-1)
            d.text((8,y),name,font=font_semitone,fill='#8F9DA8')
    d.line((0,1032,WIDTH,1032),fill='#42515E',width=2)
    d.text((39,1062),'CHORD PROGRESSION',font=font_label,fill='#C9A969')
    d.rounded_rectangle((36,1118,684,1204),radius=12,fill='#222D36',outline='#34424D',width=2)
    d.text((40,1225),'PIANO ONLY  /  MIDI + AUDIO SYNC',font=font_small,fill='#8997A4')
    d.rounded_rectangle((39,1262,681,1270),radius=4,fill='#35404A')
    args=['ffmpeg','-hide_banner','-loglevel','error','-y',
      '-f','rawvideo','-pixel_format','rgb24','-video_size',f'{WIDTH}x{HEIGHT}',
      '-framerate',str(FPS),'-i','pipe:0','-i',str(wavpath),'-t',str(duration),
      '-map','0:v:0','-map','1:a:0',
      '-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p',
      '-c:a','aac','-b:a','192k','-ar','44100','-movflags','+faststart',
      '-shortest',str(mp4path)]
    proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        for index in range(round(duration*FPS)):
            moment=index/FPS
            offset=round(moment*pps)
            frame=base.copy()
            frame.paste(world.crop((offset,0,offset+WIDTH,roll_height)),(0,roll_top))
            draw=ImageDraw.Draw(frame)
            draw.rectangle((0,roll_top,47,roll_top+roll_height),fill='#1B242D')
            for pitch in range(41,84):
                if pitch%12 not in (0,5,7):continue
                y=roll_top+y_pitch(pitch)+1
                if roll_top+8<=y<=roll_top+roll_height-17:
                    name=['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B'][pitch%12]+str(pitch//12-1)
                    draw.text((7,y),name,font=font_semitone,fill='#96A3AC')
            draw.rectangle((origin-4,roll_top,origin+5,roll_top+roll_height),fill='#66502C')
            draw.line((origin,roll_top,origin,roll_top+roll_height),fill='#FFF0C3',width=3)
            draw.polygon(((origin-9,roll_top-10),(origin+9,roll_top-10),(origin,roll_top+6)),fill='#FFE49F')
            second=moment>=15
            phase=('HOOK' if moment<7.5 else 'ANSWER' if moment<15 else 'HOOK RETURN' if moment<22.5 else 'ENDING')
            draw.rounded_rectangle((512,42,678,72),radius=14,fill='#303B45')
            draw.text((525,46),phase,font=font_label,fill='#F1D392')
            draw.rounded_rectangle((492,222,680,255),radius=14,fill='#273440')
            tm=f'{int(moment)//60:02d}:{int(moment)%60:02d}'
            draw.text((511,226),tm+' / 00:30',font=font_small,fill='#DFE5EA')
            draw.text((67,1134),labels_from_time(moment),font=font_chord,fill='#FFE2A1')
            draw.text((488,1137),str(int(moment//7.5)+1),font=font_chord,fill='#B9C8D2')
            progress=round(moment/duration*642)
            if progress>0:draw.rounded_rectangle((39,1262,39+progress,1270),radius=4,fill='#E8BD6C')
            if moment>duration-.32:
                alpha=min(1.,(moment-(duration-.32))/.32)
                frame=Image.blend(frame,Image.new('RGB',frame.size,'#0E151E'),alpha*.83)
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        result=proc.wait(timeout=120)
        if result:raise RuntimeError('ffmpeg MP4 error: '+proc.stderr.read().decode('utf-8','replace')[-600:])
    finally:
        if proc.poll() is None:proc.kill()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--manifest',required=True)
    p.add_argument('--output-dir',required=True)
    p.add_argument('--soundfont',default=DEFAULT_SF2)
    p.add_argument('--basename',default='Emotional_Piano_Roll_30s')
    p.add_argument('--skip-video',action='store_true')
    args=p.parse_args()
    path=Path(args.manifest)
    manifest=json.loads(path.read_text(encoding='utf8'))
    duration,notes=validate(manifest)
    sf2=Path(args.soundfont)
    if not sf2.is_file():raise FileNotFoundError('Missing SoundFont: '+str(sf2))
    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    mid=out/(args.basename+'.mid')
    mp3=out/(args.basename+'.mp3')
    wav=out/(args.basename+'.wav')
    mp4=out/(args.basename+'.mp4')
    write_midi(notes,mid)
    render_audio(notes,duration,sf2,wav,mp3)
    if not args.skip_video:render_video(notes,duration,wav,mp4)
    probe={'notes':len(notes),'duration':duration,'files':{
      item.name:item.stat().st_size for item in (mid,mp3,wav,mp4) if item.exists()}}
    print(json.dumps(probe,ensure_ascii=False))

if __name__=='__main__':
    main()
