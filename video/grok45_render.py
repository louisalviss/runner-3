from PIL import Image, ImageDraw, ImageFont
import os, math

W,H,FPS,DUR=1280,720,24,18
N=FPS*DUR
OUT='work/grok45_frames'
os.makedirs(OUT,exist_ok=True)

FONT_REG='/usr/share/fonts/truetype/inter/Inter-Regular.otf'
FONT_MED='/usr/share/fonts/truetype/inter/Inter-Medium.otf'
FONT_BOLD='/usr/share/fonts/truetype/inter/Inter-Bold.otf'
if not os.path.exists(FONT_REG):
    FONT_REG='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    FONT_MED=FONT_REG
    FONT_BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

def F(path,size): return ImageFont.truetype(path,size)
def ease(x):
    x=max(0,min(1,x)); return 3*x*x-2*x*x*x
def mix(a,b,t): return int(a+(b-a)*t)

BG=(8,9,11); PANEL=(15,17,21); PANEL2=(20,23,28); TEXT=(242,244,247); MUTED=(142,150,162); LINE=(47,52,61)
ACC=(126,153,255); GOOD=(112,208,157); GOLD=(236,195,104)

# precomputed background grid
def base_frame(t):
    im=Image.new('RGB',(W,H),BG); d=ImageDraw.Draw(im)
    # quiet radial glow using concentric ellipses
    for r in range(460,80,-40):
        a=(460-r)/380
        col=(mix(9,18,a),mix(10,20,a),mix(12,28,a))
        d.ellipse((W-530-r/2,80-r/2,W-530+r/2,80+r/2),fill=col)
    off=int((t*12)%72)
    for x in range(-72+off,W,72): d.line((x,0,x,H),fill=(18,20,24),width=1)
    for y in range(-72+off,H,72): d.line((0,y,W,y),fill=(18,20,24),width=1)
    return im

def rr(d,box,r=18,fill=PANEL,outline=LINE,w=1): d.rounded_rectangle(box,radius=r,fill=fill,outline=outline,width=w)
def txt(d,xy,s,size,col=TEXT,bold=False,anchor=None):
    d.text(xy,s,font=F(FONT_BOLD if bold else FONT_REG,size),fill=col,anchor=anchor)

def fade(t,a,b,fi=.25,fo=.25):
    if t<a or t>b:return 0
    v=1
    if t<a+fi:v*=(t-a)/fi
    if t>b-fo:v*=(b-t)/fo
    return max(0,min(1,v))

def article_scene(t):
    im=Image.new('RGBA',(W,H),(0,0,0,0));d=ImageDraw.Draw(im)
    p=ease((t-.1)/2.6)
    txt(d,(86,74),'xAI  /  OFFICIAL ANNOUNCEMENT',16,MUTED,bold=True)
    txt(d,(86,110),'JUL 16, 2026',14,(96,104,116))
    y=175+int(18*(1-p))
    txt(d,(86,y),'Introducing',54,TEXT,bold=True)
    txt(d,(86,y+64),'Grok 4.5',72,TEXT,bold=True)
    txt(d,(86,y+158),'Coding. Agentic tasks. Knowledge work.',23,MUTED)
    # editorial pull quote, not fake screenshot
    x=760; yy=180
    rr(d,(x,yy,x+430,yy+340),24,PANEL,LINE,1)
    txt(d,(x+28,yy+28),'WHAT xAI CLAIMS',14,MUTED,bold=True)
    lines=[('“smartest model”',32,TEXT,True),('built for coding,',23,MUTED,False),('agentic tasks, and',23,MUTED,False),('knowledge work',23,MUTED,False)]
    cy=yy+85
    for s,sz,c,b in lines:
        txt(d,(x+28,cy),s,sz,c,bold=b);cy+=46
    txt(d,(x+28,yy+290),'Source: x.ai · Grok 4.5',13,(98,106,117))
    # terminal strip
    bx,by,bw,bh=86,560,1104,100
    rr(d,(bx,by,bx+bw,by+bh),18,(12,14,17),LINE,1)
    txt(d,(bx+22,by+18),'agent run',13,MUTED,bold=True)
    cmds=['$ inspect repo','→ plan changes','→ run tests','✓ patch ready']
    n=max(1,min(len(cmds),int(1+p*len(cmds))))
    xcur=bx+22
    for i,s in enumerate(cmds[:n]):
        c=GOOD if '✓' in s else (ACC if '→' in s else TEXT)
        txt(d,(xcur,by+50),s,16,c,bold=False);xcur+=190 if i<3 else 0
    return im

def benchmark_scene(t):
    im=Image.new('RGBA',(W,H),(0,0,0,0));d=ImageDraw.Draw(im);p=ease((t-3.3)/2.8)
    txt(d,(86,70),'ENGINEERING BENCHMARK',15,MUTED,bold=True)
    txt(d,(86,108),'Fast is only useful if it still solves the task.',34,TEXT,bold=True)
    txt(d,(86,155),'SWE Marathon · pass@1 · xAI-reported',17,MUTED)
    vals=[('Grok 4.5',29),('Opus 4.8',26),('Fable',24),('Opus 4.7',16)]
    x0=300; maxw=760
    for i,(name,val) in enumerate(vals):
        y=245+i*90
        txt(d,(86,y+4),name,20,TEXT if i==0 else MUTED,bold=i==0)
        d.rounded_rectangle((x0,y,x0+maxw,y+34),radius=17,fill=(24,27,32))
        bw=int(maxw*(val/32)*p)
        d.rounded_rectangle((x0,y,x0+bw,y+34),radius=17,fill=ACC if i==0 else (72,78,89))
        txt(d,(x0+maxw+26,y+3),str(val),20,TEXT if i==0 else MUTED,bold=True)
    rr(d,(86,610,1190,670),16,(12,14,17),LINE,1)
    txt(d,(106,629),'80 TPS',20,TEXT,bold=True);txt(d,(210,629),'served at “fast-model speeds” · xAI claim',17,MUTED)
    return im

def pricing_scene(t):
    im=Image.new('RGBA',(W,H),(0,0,0,0));d=ImageDraw.Draw(im);p=ease((t-6.9)/2.5)
    txt(d,(86,72),'COST-PERFORMANCE',15,MUTED,bold=True)
    txt(d,(86,112),'The pricing attack',48,TEXT,bold=True)
    txt(d,(86,174),'Frontier AI is becoming an economics game.',22,MUTED)
    # two big price blocks
    for i,(price,label,sub) in enumerate([('$2','INPUT','per 1M tokens'),('$6','OUTPUT','per 1M tokens')]):
        x=86+i*560;y=265
        rr(d,(x,y,x+500,y+300),28,PANEL if i==0 else PANEL2,LINE,1)
        txt(d,(x+28,y+26),label,15,MUTED,bold=True)
        shift=int(20*(1-p))
        txt(d,(x+28,y+82+shift),price,88,TEXT,bold=True)
        txt(d,(x+30,y+207),sub,19,MUTED)
        d.line((x+30,y+255,x+470,y+255),fill=LINE,width=1)
        txt(d,(x+30,y+270),'xAI API price · Jul 2026',13,(96,104,116))
    return im

def distribution_scene(t):
    im=Image.new('RGBA',(W,H),(0,0,0,0));d=ImageDraw.Draw(im);p=ease((t-10.5)/2.8)
    txt(d,(86,72),'DISTRIBUTION',15,MUTED,bold=True)
    txt(d,(86,112),'A model is also where it shows up.',42,TEXT,bold=True)
    txt(d,(86,171),'Grok 4.5 moved into developer workflows, not just a chat box.',20,MUTED)
    cards=[('Grok Build','default model','xAI'),('Cursor','trained alongside','Cursor'),('GitHub Copilot','available Jul 28','GitHub')]
    for i,(name,sub,tag) in enumerate(cards):
        local=ease(max(0,min(1,p*1.35-i*.16)))
        x=86+int(55*(1-local));y=260+i*115
        rr(d,(x,y,1110,y+86),20,PANEL if i<2 else PANEL2,LINE,1)
        txt(d,(x+25,y+17),name,25,TEXT,bold=True)
        txt(d,(x+25,y+51),sub,15,MUTED)
        rr(d,(1000,y+22,1085,y+62),14,(27,31,38),LINE,1)
        txt(d,(1042,y+42),tag,13,ACC,bold=True,anchor='mm')
    txt(d,(86,640),'Distribution = part of the product.',20,(182,188,198),bold=True)
    return im

def end_scene(t):
    im=Image.new('RGBA',(W,H),(0,0,0,0));d=ImageDraw.Draw(im);p=ease((t-14.4)/2.5)
    txt(d,(86,88),'THE REAL AI WAR',15,MUTED,bold=True)
    items=[('CAPABILITY',86,185,TEXT),('×  SPEED',86,300,ACC),('×  COST',86,415,(194,205,236))]
    for i,(s,x,y,c) in enumerate(items):
        xx=x+int(36*(1-ease(max(0,min(1,p+i*.06)))))
        txt(d,(xx,y),s,72,c,bold=True)
    txt(d,(86,585),'Not “who is smartest?” — who is strong enough, fast enough, cheap enough.',21,MUTED)
    txt(d,(86,636),'Sources: xAI · Grok 4.5 announcement · GitHub Copilot announcement',13,(93,101,112))
    return im

for i in range(N):
    t=i/FPS
    im=base_frame(t).convert('RGBA')
    for (a,b,fn) in [(0,3.8,article_scene),(3.3,7.3,benchmark_scene),(6.8,11.1,pricing_scene),(10.5,14.9,distribution_scene),(14.4,18,end_scene)]:
        al=fade(t,a,b,.25,.28)
        if al:
            layer=fn(t); layer.putalpha(int(255*al)); im.alpha_composite(layer)
    # subtle vignette using translucent border gradients
    d=ImageDraw.Draw(im)
    for k in range(18):
        a=int(3+k*1.2); d.rectangle((k,k,W-1-k,H-1-k),outline=(0,0,0,a),width=2)
    im.convert('RGB').save(f'{OUT}/{i:05d}.jpg',quality=92)
print('frames',N)
