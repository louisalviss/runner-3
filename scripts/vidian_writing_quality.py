#!/usr/bin/env python3
import collections, hashlib, json, re, sqlite3
from pathlib import Path
import vidian_writing as w

DIRECTIVE_KINDS={'do','dont','warning','technique','diagnostic'}
STRONG_TITLE_CUES=['viết','sáng tác','cốt truyện','văn phong','kỹ xảo','đại cương','thế giới quan','hình tượng','tình tiết','nhịp','hội thoại','bàn tay vàng','goldfinger','kinh nghiệm','hướng dẫn','lý luận','phương pháp','chiến lược','bí quyết','tips','định hướng','cấu trúc','thiết lập','xây dựng','phục bút','mâu thuẫn','xung đột','kỳ ngộ','cơ duyên','giữ chân độc giả','sảng điểm','nhập vai','tạo hình']
STRONG_RULE_CUES=['viết','sáng tác','cốt truyện','văn phong','độc giả','nhân vật','nhân vật chính','mở đầu','kết chương','cao trào','nhịp truyện','nhịp độ','arc','mục tiêu','động cơ','phản diện','mâu thuẫn','xung đột','tu luyện','cảnh giới','chiến lực','công pháp','tài nguyên','bảo vật','kỳ ngộ','cơ duyên','thế giới quan','bối cảnh','hệ thống sức mạnh','đối thoại','lời thoại','miêu tả','cảm xúc','logic','nhất quán','chủ đề','phục bút','foreshadow','payoff','cliffhanger','sảng','giữ chân','tỷ lệ đọc','đọc hết']
BAD_TITLE_CUES=['bộ tiểu thuyết mới hoàn thành','bộ tiểu thuyết huyễn tưởng','sơ lược','review truyện','danh sách truyện']

# Avoid ambiguous single-word/phrase markers that frequently appear in names or story facts.
STRICT_NEG=[x for x in w.NEG if x!='không được']+['không được viết','không được để','không được cho','không được dùng','không được sử dụng','không được miêu tả','không được mô tả','không được tạo','không được xây dựng','không được thiết lập','không được lạm dụng']
STRICT_WARN=[x for x in w.WARN if x!='kỵ']+['đại kỵ','tối kỵ','kiêng kỵ']
STRICT_POS=[x for x in w.POS if x not in {'quan trọng','tốt nhất'}]
STRICT_TECH=[x for x in w.TECH if x!='cách']+['cách viết','cách xây dựng','cách tạo','cách miêu tả','cách mô tả','cách thiết kế','cách xử lý','cách triển khai']
STRICT_EXAMPLE=list(w.EXAMPLE)
STRICT_DIAG=[x for x in w.DIAG if x!='khi']

# Lower weights for broad terms and boost craft-specific terms. This resolves ties such as
# `cơ duyên ... nhân vật chính`: reward/payoff should win over generic character mention.
TERM_WEIGHT={
    ('character_design','nhân vật'):.60,
    ('serialization_reader','độc giả'):.70,('serialization_reader','đọc giả'):.70,
    ('system_design','hệ thống'):.70,('system_design','thiết lập'):.55,('system_design','cảnh giới'):.55,
    ('description_scene','hành động'):.65,('description_scene','chi tiết'):.65,
    ('romance_relationship','quan hệ'):.60,
    ('worldbuilding','bối cảnh'):.80,('worldbuilding','xã hội'):.65,('worldbuilding','lịch sử'):.65,
    ('progression_power','năng lực'):.65,('progression_power','tu luyện'):1.55,('progression_power','cảnh giới'):1.35,
    ('reward_payoff','cơ duyên'):1.90,('reward_payoff','kỳ ngộ'):1.90,('reward_payoff','tài nguyên'):1.30,('reward_payoff','bảo vật'):1.30,
    ('hook_opening','mở đầu'):1.90,('pacing_tension','cao trào'):1.55,
    ('motivation_conflict','động cơ'):1.55,('plot_structure_arc','arc'):1.25,
}


def marker_norm(text):
    # Preserve Vietnamese diacritics. Accent stripping would collapse chớ→cho and kỵ→kỳ.
    return ' '.join(re.findall(r'[0-9A-Za-zÀ-ỹĐđ]+',(text or '').lower()))

def marker_has(text,phrases):
    n=' '+marker_norm(text)+' '
    for raw in phrases:
        z=marker_norm(raw)
        if z and f' {z} ' in n:
            return True
    return False

def _patch_topic_map():
    reward=w.TOPICS['reward_payoff']
    if 'cơ duyên' not in reward: reward.append('cơ duyên')
    serial=[x for x in w.TOPICS['serialization_reader'] if x!='chương']
    for x in ['tỷ lệ đọc','đọc hết','lưu lượng','giữ chân độc giả']:
        if x not in serial: serial.append(x)
    w.TOPICS['serialization_reader']=serial

def quality_topic_scores(text):
    n=w.vk.norm(text); out=[]
    for topic,keys in w.TOPICS.items():
        matches=[]; seen=set(); score=0.0; best=0.0
        for raw in keys:
            z=w.vk.norm(raw)
            if not z or z in seen: continue
            seen.add(z)
            if f' {z} ' not in f' {n} ': continue
            words=len(z.split())
            base=1.0 if words==1 else 1.0+.55*(words-1)
            weight=TERM_WEIGHT.get((topic,raw),base)
            matches.append(raw); score+=weight; best=max(best,weight)
        if matches: out.append((topic,round(score,4),matches,best))
    out.sort(key=lambda x:(-x[1],-x[3],x[0]))
    return [(t,s,m) for t,s,m,_ in out]

def strict_kind(text):
    if marker_has(text,STRICT_NEG): return 'dont',.92
    if marker_has(text,STRICT_WARN): return 'warning',.82
    if marker_has(text,STRICT_POS): return 'do',.88
    if marker_has(text,STRICT_TECH): return 'technique',.76
    if marker_has(text,STRICT_EXAMPLE): return 'example',.68
    if marker_has(text,STRICT_DIAG): return 'diagnostic',.64
    return 'principle',.52

def title_craft_score(title):
    t=(title or '').lower()
    return sum(1 for x in STRONG_TITLE_CUES if x in t)-2*sum(1 for x in BAD_TITLE_CUES if x in t)

def has_strong_craft_signal(rule):
    return marker_has(rule,STRONG_RULE_CUES)

def topic_aligned(item):
    topic=item.get('topic')
    return bool(topic and topic in w.TOPICS and marker_has(item.get('rule',''),w.TOPICS[topic]))

def actionable(item):
    rule=item.get('rule',''); kind=item.get('kind',''); title=item.get('title','')
    if len(marker_norm(rule).split())<7: return False
    if not has_strong_craft_signal(rule) or not topic_aligned(item): return False
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
    title_topics=w.topic_scores(title)
    title_strong=title_craft_score(title)>0
    rows=[]; counts=collections.Counter()
    for frame in w.vk.frames(record):
        surface=w.vk.clean(w.vk.surface(frame))
        if len(w.vk.toks(surface))<7: continue
        rule=surface[:420]
        k,conf=strict_kind(rule)
        # Prefer topic evidence in the sentence itself. Title-only topic inheritance is allowed
        # only for explicit directive sentences from clearly craft-oriented articles.
        topics=w.topic_scores(surface)
        inherited=False
        if not topics:
            if not (title_strong and title_topics and k in DIRECTIVE_KINDS and has_strong_craft_signal(rule)):
                continue
            topics=title_topics
            inherited=True
        topic,score,matches=topics[0]
        if inherited: score=max(.25,float(score)*.25)
        if k in {'do','dont','warning','technique'}: conf=min(.98,conf+.06)
        counts[topic]+=score
        rows.append({'sentence_sha':str(frame.get('source_sentence_sha256') or hashlib.sha256(surface.encode()).hexdigest()),'topic':topic,'topic_score':score,'topic_matches':matches,'kind':k,'confidence':conf,'surface':surface,'rule':rule,'topic_inherited_from_title':inherited})
    if not title_strong:
        rows=[x for x in rows if x['kind'] in DIRECTIVE_KINDS and has_strong_craft_signal(x['rule'])]
        counts=collections.Counter()
        for x in rows: counts[x['topic']]+=x['topic_score']
    return {'url':record['url'],'title':title,'passages':rows,'topics':counts}

def refine_checklists(index,limit=25):
    idx=Path(index); con=sqlite3.connect(idx/'vidian_writing.sqlite'); con.row_factory=sqlite3.Row; data={}
    for topic in w.TOPICS:
        rr=con.execute("select p.id passage_id,p.topic,p.kind,p.confidence,p.rule,p.sentence_sha,a.title,a.url from passages p join articles a on a.id=p.article_id where p.topic=? and p.kind in ('do','dont','warning','technique','diagnostic','principle') order by p.confidence desc limit 800",(topic,)).fetchall()
        data[topic]=rank_actionable([dict(x) for x in rr],limit)
    con.close(); (idx/'checklists.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); return data

def apply():
    _patch_topic_map()
    w.topic_scores=quality_topic_scores
    w.kind=strict_kind
    w.extract=strict_extract
    return w
