#!/usr/bin/env python3
"""User-facing quality/balance layer for the fused Vidian + Moxing Writing Brain."""
import collections, math
import webnovel_writing_brain as brain

LOW_QUALITY_MOXING = ('天生的嫉妒心理','女性天生','男性天生','女人天生','男人天生')


def acceptable(x):
    text=(x.get('title','')+' '+x.get('text',''))
    if x.get('source')=='moxing' and any(z in text for z in LOW_QUALITY_MOXING):
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
        # Retrieve independently so one source cannot crowd the other out before balancing.
        got=brain.search(index,text+' '+terms,per_source,topic,src)
        if not got:
            got=brain.search(index,terms,per_source,topic,src)
        pool.extend(got)
    # Mixed retrieval supplies additional high-scoring candidates and consensus-rich items.
    pool.extend(brain.search(index,text+' '+terms,max(24,per_source//2),topic))
    return _dedup_pool(pool)


def balanced_take(pool,limit,used=None):
    used=used if used is not None else set()
    pool=[x for x in pool if acceptable(x) and x.get('passage_id') not in used]
    pool.sort(key=lambda x:(x.get('cross_source_support',0)>0,x.get('score',0),x.get('confidence',0)),reverse=True)
    available={x['source'] for x in pool}
    keep=[]; counts=collections.Counter()
    # First take the strongest item from each available source.
    for src in ('vidian','moxing'):
        for x in pool:
            if x['source']==src and x['passage_id'] not in used:
                keep.append(x); used.add(x['passage_id']); counts[src]+=1; break
    # Then fill with a soft 65% per-source ceiling while both sources have candidates.
    cap=max(2,math.ceil(limit*.65))
    for x in pool:
        if len(keep)>=limit: break
        if x['passage_id'] in used: continue
        if len(available)>1 and counts[x['source']]>=cap: continue
        keep.append(x);used.add(x['passage_id']);counts[x['source']]+=1
    # Relax the ceiling only when needed to fill the packet.
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

# Patch the base module globals used by direct/review/main.
brain.evidence_for_topic=evidence_for_topic
brain.checklist=checklist

if __name__=='__main__':
    brain.main()
