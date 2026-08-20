#!/usr/bin/env python3
import argparse, collections, hashlib, json, math, re, sqlite3
from pathlib import Path
import webnovel_writing_brain as brain


def _scale(pairs):
    if not pairs:return {}
    vals=[v for _,v in pairs];lo=min(vals);hi=max(vals)
    return {i:(1.0 if hi==lo else (v-lo)/(hi-lo)) for i,v in pairs}

def _terms(q):
    ex=brain.expanded(q)
    toks=[];seen=set()
    for x in re.findall(r'[0-9A-Za-zÀ-ỹĐđ]+',ex):
        x=x.strip()
        if len(x)>=2 and x not in seen:seen.add(x);toks.append(x)
    return ex,toks[:60]

def has_canonical(index):
    p=Path(index)/'writing_brain.sqlite'
    if not p.exists():return False
    con=sqlite3.connect(p)
    ok=con.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='canonical_rules'").fetchone()[0]>0
    con.close();return ok

def _evidence(con,rule_id,limit=4):
    rows=con.execute('''SELECT e.evidence_rank,e.similarity_to_rule,p.id passage_id,p.source,p.source_id,p.topic,p.kind,p.confidence,p.text,p.evidence_id,p.title,p.url FROM canonical_evidence e JOIN passages p ON p.id=e.passage_id WHERE e.rule_id=? ORDER BY e.evidence_rank LIMIT ?''',(rule_id,limit)).fetchall()
    return [dict(r) for r in rows]

def search(index,q,limit=12,topic=None,direction=None,cross_source_only=False,evidence_limit=4):
    import joblib,numpy as np
    idx=Path(index);con=sqlite3.connect(idx/'writing_brain.sqlite');con.row_factory=sqlite3.Row
    scores=collections.defaultdict(dict);ex,terms=_terms(q);where=[];params=[]
    if topic:where.append('r.topic=?');params.append(topic)
    if direction:where.append('r.direction=?');params.append(direction)
    if cross_source_only:where.append('r.cross_source=1')
    filt=(' AND '+' AND '.join(where)) if where else ''
    if terms:
        fts=' OR '.join('"'+t.replace('"','')+'"' for t in terms)
        try:
            rs=con.execute(f'''SELECT r.id,-bm25(canonical_fts,2.2,1.0,1.2,3.0) s FROM canonical_fts JOIN canonical_rules r ON r.id=canonical_fts.rowid WHERE canonical_fts MATCH ? {filt} ORDER BY bm25(canonical_fts,2.2,1.0,1.2,3.0) LIMIT 600''',[fts]+params).fetchall()
            for rid,s in _scale([(int(r['id']),float(r['s'])) for r in rs]).items():scores[rid]['lexical']=s
        except sqlite3.OperationalError:pass
    try:
        m=joblib.load(idx/'canonical_semantic.joblib');D=np.load(idx/'canonical_vectors.npy',mmap_mode='r');ids=np.load(idx/'canonical_ids.npy',mmap_mode='r')
        v=m['normalizer'].transform(m['svd'].transform(m['vectorizer'].transform([ex])))[0].astype('float32');sims=D@v;k=min(500,len(sims));ix=np.argpartition(sims,-k)[-k:] if k else []
        pairs=[]
        for j in ix:
            if sims[j]<=0:continue
            rid=int(ids[j]);r=con.execute('SELECT topic,direction,cross_source FROM canonical_rules WHERE id=?',(rid,)).fetchone()
            if topic and r['topic']!=topic:continue
            if direction and r['direction']!=direction:continue
            if cross_source_only and not r['cross_source']:continue
            pairs.append((rid,float(sims[j])))
        for rid,s in _scale(pairs).items():scores[rid]['semantic']=s
    except Exception:pass
    ranked=[]
    for rid,c in scores.items():
        r=con.execute('SELECT confidence,evidence_count,cross_source,source_count FROM canonical_rules WHERE id=?',(rid,)).fetchone()
        sc=.49*c.get('lexical',0)+.43*c.get('semantic',0)+.045*float(r['confidence'])+min(.05,.012*math.log2(max(1,r['evidence_count'])))+(.04 if r['cross_source'] else 0)
        ranked.append((sc,rid,c))
    ranked.sort(reverse=True)
    out=[];topic_count=collections.Counter()
    for sc,rid,c in ranked:
        r=con.execute('SELECT * FROM canonical_rules WHERE id=?',(rid,)).fetchone()
        if topic_count[r['topic']]>=max(3,math.ceil(limit*.55)):continue
        ev=_evidence(con,rid,evidence_limit);sources=sorted({x['source'] for x in ev})
        out.append({'score':round(sc,6),'components':{k:round(v,5) for k,v in c.items()},'rule_id':rid,'topic':r['topic'],'direction':r['direction'],'kind':r['kind'],'title':r['title'],'canonical_text':r['canonical_text'],'confidence':r['confidence'],'evidence_count':r['evidence_count'],'vidian_count':r['vidian_count'],'moxing_count':r['moxing_count'],'cross_source':bool(r['cross_source']),'sources':sources,'representative_passage_id':r['representative_passage_id'],'evidence':ev})
        topic_count[r['topic']]+=1
        if len(out)>=limit:break
    con.close();return out

def direct(index,brief,limit=32):
    scored=brain.detect_topics(brief,10);topics=[x[0] for x in scored[:8]]
    for t in ['hook_opening','plot_structure_arc','pacing_tension','character_design','motivation_conflict','progression_power','worldbuilding','reward_payoff']:
        if len(topics)>=8:break
        if t not in topics:topics.append(t)
    per=max(3,math.ceil(limit/max(1,len(topics))));sections=[];used=set()
    for t in topics:
        pool=search(index,brief+' '+' '.join(brain.TOPIC_TERMS[t][:8]),per*3,t,evidence_limit=3);keep=[]
        for x in pool:
            if x['rule_id'] in used:continue
            used.add(x['rule_id']);keep.append(x)
            if len(keep)>=per:break
        if keep:sections.append({'topic':t,'must_do':[x for x in keep if x['direction'] in ('positive','principle')],'avoid':[x for x in keep if x['direction']=='negative'],'techniques':[x for x in keep if x['direction']=='technique'],'all':keep,'cross_source_rules':sum(x['cross_source'] for x in keep)})
    return {'schema':'webnovel-writing-directive-canonical-v1','brief_sha256':hashlib.sha256(brief.encode()).hexdigest(),'detected_topics':[{'topic':t,'score':s,'matches':m} for t,s,m in scored],'sections':sections,'knowledge_layer':'canonical_rules','protocol':['Draft from canonical rules first.','Use linked evidence for nuance/provenance, not as duplicate instructions.','Cross-source rules receive a corroboration boost but are not automatically treated as universal laws.']}

def review(index,text,limit=24):
    scored=brain.detect_topics(text,8);topics=[x[0] for x in scored[:6]] or ['plot_structure_arc','pacing_tension','character_design','style_prose'];per=max(3,math.ceil(limit/max(1,len(topics))));b=[]
    for t in topics:
        hits=search(index,text+' '+' '.join(brain.TOPIC_TERMS[t][:8]),per,t,evidence_limit=3)
        if hits:b.append({'topic':t,'rules':hits,'cross_source_rules':sum(x['cross_source'] for x in hits)})
    return {'schema':'webnovel-writing-review-canonical-v1','draft_sha256':hashlib.sha256(text.encode()).hexdigest(),'detected_topics':[{'topic':t,'score':s,'matches':m} for t,s,m in scored],'review_dimensions':[x['topic'] for x in b],'rule_buckets':b,'knowledge_layer':'canonical_rules'}

def checklist(index,topic,limit=18):
    hits=search(index,' '.join(brain.TOPIC_TERMS[topic][:10]),limit,topic,evidence_limit=3)
    return {'schema':'webnovel-writing-checklist-canonical-v1','topic':topic,'items':hits,'cross_source_rules':sum(x['cross_source'] for x in hits),'knowledge_layer':'canonical_rules'}
def dump(x,path=None):
    raw=json.dumps(x,ensure_ascii=False,indent=2);print(raw)
    if path:Path(path).write_text(raw,encoding='utf-8')
def main():
    ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='cmd',required=True)
    q=sp.add_parser('query');q.add_argument('--index',required=True);q.add_argument('--q',required=True);q.add_argument('--limit',type=int,default=12);q.add_argument('--topic',choices=brain.CANONICAL_TOPICS);q.add_argument('--direction',choices=['negative','positive','technique','principle']);q.add_argument('--cross-source-only',action='store_true');q.add_argument('--json-out')
    d=sp.add_parser('direct');d.add_argument('--index',required=True);g=d.add_mutually_exclusive_group(required=True);g.add_argument('--brief');g.add_argument('--file');d.add_argument('--limit',type=int,default=32);d.add_argument('--json-out')
    r=sp.add_parser('review');r.add_argument('--index',required=True);g=r.add_mutually_exclusive_group(required=True);g.add_argument('--text');g.add_argument('--file');r.add_argument('--limit',type=int,default=24);r.add_argument('--json-out')
    c=sp.add_parser('checklist');c.add_argument('--index',required=True);c.add_argument('--topic',required=True,choices=brain.CANONICAL_TOPICS);c.add_argument('--limit',type=int,default=18);c.add_argument('--json-out')
    s=sp.add_parser('stats');s.add_argument('--index',required=True)
    a=ap.parse_args()
    if a.cmd=='query':dump({'schema':'webnovel-writing-query-canonical-v1','query':a.q,'hits':search(a.index,a.q,a.limit,a.topic,a.direction,a.cross_source_only)},a.json_out)
    elif a.cmd=='direct':dump(direct(a.index,a.brief if a.brief is not None else Path(a.file).read_text(encoding='utf-8'),a.limit),a.json_out)
    elif a.cmd=='review':dump(review(a.index,a.text if a.text is not None else Path(a.file).read_text(encoding='utf-8'),a.limit),a.json_out)
    elif a.cmd=='checklist':dump(checklist(a.index,a.topic,a.limit),a.json_out)
    else:print((Path(a.index)/'canonical_qa.json').read_text(encoding='utf-8'))
if __name__=='__main__':main()
