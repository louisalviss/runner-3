#!/usr/bin/env python3
import collections, hashlib, json, re, sqlite3
from pathlib import Path
import vidian_writing as w

DIRECTIVE_KINDS={'do','dont','warning','technique','diagnostic'}
STRONG_TITLE_CUES=['viết','sáng tác','cốt truyện','văn phong','kỹ xảo','đại cương','thế giới quan','hình tượng','tình tiết','nhịp','hội thoại','bàn tay vàng','goldfinger','kinh nghiệm','hướng dẫn','lý luận','phương pháp','chiến lược','bí quyết','tips','định hướng','cấu trúc','thiết lập','xây dựng','phục bút','mâu thuẫn','xung đột','kỳ ngộ','giữ chân độc giả','sảng điểm','nhập vai','tạo hình']
CRAFT_TERMS=STRONG_TITLE_CUES+['nhân vật','độc giả','tác giả','chương','truyện','tiểu thuyết','mở đầu','kết chương','cao trào','mục tiêu','động cơ','phản diện','cảnh giới','tu luyện','tài nguyên','bảo vật','hệ thống','bối cảnh','cảnh','miêu tả','đối thoại','lời thoại','cảm xúc','logic','nhất quán','chủ đề','nguyên tắc','arc','foreshadow','payoff','cliffhanger']
BAD_TITLE_CUES=['bộ tiểu thuyết mới hoàn thành','bộ tiểu thuyết huyễn tưởng','sơ lược','review truyện','danh sách truyện']


def marker_norm(text):
    return ' '.join(re.findall(r'[0-9A-Za-zÀ-ỹĐđ]+',(text or '').lower()))

def marker_has(text,phrases):
    n=' '+marker_norm(text)+' '
    return any((lambda z: bool(z) and f' {z} ' in n)(marker_norm(x)) for x in phrases)

def strict_kind(text):
    if marker_has(text,w.NEG): return 'dont',.92
    if marker_has(text,w.WARN): return 'warning',.82
    if marker_has(text,w.POS): return 'do',.88
    if marker_has(text,w.TECH): return 'technique',.76
    if marker_has(text,w.EXAMPLE): return 'example',.68
    if marker_has(text,w.DIAG): return 'diagnostic',.64
    return 'principle',.52

def title_craft_score(title):
    t=(title or '').lower()
    return sum(1 for x in STRONG_TITLE_CUES if x in t)-2*sum(1 for x in BAD_TITLE_CUES if x in t)

def has_craft_signal(rule):
    return marker_has(rule,CRAFT_TERMS)

def actionable(item):
    rule=item.get('rule',''); kind=item.get('kind',''); title=item.get('title','')
    if len(marker_norm(rule).split())<7 or not has_craft_signal(rule): return False
    if kind in DIRECTIVE_KINDS: return True
    if kind=='principle': return title_craft_score(title)>0
    return False

def evidence_score(item):
    kind=item.get('kind','')
    kw={'do':1.0,'dont':.98,'warning':.88,'technique':.86,'diagnostic':.72,'principle':.55}.get(kind,.3)
    base=float(item.get('score',0) or 0)
    conf=float(item.get('confidence',0) or 0)
    ts=max(-2,min(4,title_craft_score(item.get('title',''))))
    length=len(marker_norm(item.get('rule','')).split())
    length_bonus=.08 if 10<=length<=90 else 0
    return base+.24*kw+.12*conf+.035*ts+length_bonus

def rank_actionable(items,limit):
    out=[]; seen=set()
    for x in sorted((dict(x) for x in items if actionable(x)),key=evidence_score,reverse=True):
        z=marker_norm(x.get('rule',''))
        if not z or z in seen: continue
        seen.add(z); out.append(x)
        if len(out)>=limit: break
    return out

def strict_extract(record):
    title=w.vk.clean(record.get('title') or record.get('listing_title') or '')
    rows=[]; counts=collections.Counter()
    for frame in w.vk.frames(record):
        surface=w.vk.clean(w.vk.surface(frame))
        if len(w.vk.toks(surface))<7: continue
        topics=w.topic_scores(title+' '+surface)
        if not topics: continue
        topic,score,matches=topics[0]
        rule=surface[:420]
        k,conf=strict_kind(rule)
        if k in {'do','dont','warning','technique'}: conf=min(.98,conf+.06)
        counts[topic]+=score
        rows.append({'sentence_sha':str(frame.get('source_sentence_sha256') or hashlib.sha256(surface.encode()).hexdigest()),'topic':topic,'topic_score':score,'topic_matches':matches,'kind':k,'confidence':conf,'surface':surface,'rule':rule})
    title_strong=title_craft_score(title)>0
    directive=sum(1 for x in rows if x['kind'] in DIRECTIVE_KINDS)
    if not title_strong and directive<2:
        rows=[x for x in rows if x['kind'] in DIRECTIVE_KINDS and has_craft_signal(x['rule'])]
        counts=collections.Counter()
        for x in rows: counts[x['topic']]+=x['topic_score']
    return {'url':record['url'],'title':title,'passages':rows,'topics':counts}

def refine_checklists(index,limit=25):
    idx=Path(index); con=sqlite3.connect(idx/'vidian_writing.sqlite'); con.row_factory=sqlite3.Row; data={}
    for topic in w.TOPICS:
        rr=con.execute("select p.id passage_id,p.kind,p.confidence,p.rule,p.sentence_sha,a.title,a.url from passages p join articles a on a.id=p.article_id where p.topic=? and p.kind in ('do','dont','warning','technique','diagnostic','principle') order by p.confidence desc limit 500",(topic,)).fetchall()
        data[topic]=rank_actionable([dict(x) for x in rr],limit)
    con.close(); (idx/'checklists.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); return data

def apply():
    w.kind=strict_kind
    w.extract=strict_extract
    return w
