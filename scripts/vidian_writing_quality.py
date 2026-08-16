#!/usr/bin/env python3
import collections, hashlib, re
import vidian_writing as w

DIRECTIVE_KINDS={'do','dont','warning','technique','diagnostic'}
STRONG_TITLE_CUES=['viết','sáng tác','cốt truyện','văn phong','kỹ xảo','đại cương','thế giới quan','hình tượng','tình tiết','nhịp','hội thoại','bàn tay vàng','goldfinger','kinh nghiệm','hướng dẫn','lý luận','phương pháp','chiến lược','bí quyết','tips','định hướng','cấu trúc','thiết lập','xây dựng','phục bút','mâu thuẫn','xung đột','kỳ ngộ','giữ chân độc giả','sảng điểm','nhập vai']

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
    title_strong=any(cue in title.lower() for cue in STRONG_TITLE_CUES)
    directive=sum(1 for x in rows if x['kind'] in DIRECTIVE_KINDS)
    if not title_strong and directive<2:
        rows=[x for x in rows if x['kind'] in DIRECTIVE_KINDS]
        counts=collections.Counter()
        for x in rows: counts[x['topic']]+=x['topic_score']
    return {'url':record['url'],'title':title,'passages':rows,'topics':counts}

def apply():
    w.kind=strict_kind
    w.extract=strict_extract
    return w
