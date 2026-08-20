#!/usr/bin/env python3
"""User-facing quality/balance layer for the fused Vidian + Moxing Writing Brain."""
import collections, math
import webnovel_writing_brain as brain

LOW_QUALITY_MOXING = (
    '天生的嫉妒心理','女性天生','男性天生','女人天生','男人天生',
    'tâm lý ghen tị bẩm sinh','phụ nữ bẩm sinh','nam giới bẩm sinh','đàn ông bẩm sinh','phụ nữ vốn dĩ','đàn ông vốn dĩ'
)


def acceptable(x):
    text=(x.get('title','')+' '+x.get('text','')).lower()
    if x.get('source')=='moxing' and any(z.lower() in text for z in LOW_QUALITY_MOXING):
        return False
    return True


def _dedup_pool(pool):
    best={}
    for x in pool:
        pid=x.get('passage_id')
        if pid is None: continue
        old=best.get(pid)
        if old is None or x.get('score',0)>old.get('score',0): best[pid]=x
    return list(best.values())


def source_balanced_pool(index,text,topic,per_source=40):
    terms=' '.join(brain.TOPIC_TERMS[topic][:10])
    pool=[]
    for src in ('vidian','moxing'):
        got=brain.search(index,text+' '+terms,per_source,topic,src)
        if not got:
            got=brain.search(index,terms,per_source,topic,src)
        pool.extend(got)
    pool.extend(brain.search(index,text+' '+terms,max(24,per_source//2),topic))
    return _dedup_pool(pool)


def balanced_take(pool,limit,used=None):
    used=used if used is not None else set()
    pool=[x for x in pool if acceptable(x) and x.get('passage_id') not in used]
    pool.sort(key=lambda x:(x.get('cross_source_support',0)>0,x.get('score',0),x.get('confidence',0)),reverse=True)
    available={x['source'] for x in pool}
    keep=[]; counts=collections.Counter()
    for src in ('vidian','moxing'):
        for x in pool:
            if x['source']==src and x['passage_id'] not in used:
                keep.append(x); used.add(x['passage_id']); counts[src]+=1; break
    cap=max(2,math.ceil(limit*.65))
    for x in pool:
        if len(keep)>=limit: break
        if x['passage_id'] in used: continue
        if len(available)>1 and counts[x['source']]>=cap: continue
        keep.append(x);used.add(x['passage_id']);counts[x['source']]+=1
    if len(keep)<limit:
        for x in pool:
            if len(keep)>=limit: break
            if x['passage_id'] in used: continue
            keep.append(x);used.add(x['passage_id']);counts[x['source']]+=1
    return keep


def evidence_for_topic(index,text,topic,limit,used):
    pool=source_balanced_pool(index,text,topic,max(40,limit*8))
    return balanced_take(pool,limit,used)


def checklist(index,topic,limit=20):
    terms=' '.join(brain.TOPIC_TERMS[topic][:10])
    pool=[]
    for src in ('vidian','moxing'):
        pool.extend(brain.search(index,terms,max(50,limit*5),topic,src))
    pool.extend(brain.search(index,terms,max(40,limit*3),topic))
    keep=balanced_take(_dedup_pool(pool),limit,set())
    src=collections.Counter(x['source'] for x in keep)
    return {'schema':'webnovel-writing-checklist-v1.2','topic':topic,'items':keep,'sources':dict(src),'consensus_items':sum(x.get('cross_source_support',0)>0 for x in keep),'quality_layer':'balanced-per-source-retrieval-v1.2'}

brain.evidence_for_topic=evidence_for_topic
brain.checklist=checklist

if __name__=='__main__':
    import sys
    idx=None
    if '--index' in sys.argv:
        try: idx=sys.argv[sys.argv.index('--index')+1]
        except Exception: idx=None
    if idx:
        try:
            import webnovel_writing_brain_canonical_agent as canonical
            if canonical.has_canonical(idx):
                canonical.main()
                raise SystemExit(0)
        except SystemExit:
            raise
        except Exception:
            pass
    brain.main()
