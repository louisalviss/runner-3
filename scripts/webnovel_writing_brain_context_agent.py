#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sqlite3
from pathlib import Path
import webnovel_writing_brain as brain
import webnovel_writing_brain_canonical_agent as canonical


def _load_context(con,rule_id,relation_limit=6):
    try:
        r=con.execute('SELECT * FROM canonical_rule_context WHERE rule_id=?',(rule_id,)).fetchone()
    except sqlite3.OperationalError:
        return None,[]
    if not r:return None,[]
    c=dict(r)
    for k in ('context_markers_json','absolute_markers_json','negative_markers_json','positive_markers_json'):
        try:c[k[:-5]]=json.loads(c.pop(k) or '[]')
        except Exception:c[k[:-5]]=[]
    rels=[]
    try:
        rows=con.execute('''SELECT relation_id,rule_a,rule_b,topic,similarity,relation,confidence,core_jaccard,context_overlap,stance_a,stance_b,reason
          FROM canonical_relations WHERE rule_a=? OR rule_b=?
          ORDER BY CASE relation WHEN 'true_conflict' THEN 0 WHEN 'conditional' THEN 1 WHEN 'direction_error' THEN 2 ELSE 3 END,
                   confidence DESC LIMIT ?''',(rule_id,rule_id,relation_limit)).fetchall()
        for x in rows:
            d=dict(x);d['other_rule_id']=d['rule_b'] if d['rule_a']==rule_id else d['rule_a'];rels.append(d)
    except sqlite3.OperationalError:pass
    return c,rels

def _effective(hit,ctx):
    if not ctx:return hit.get('direction')
    if ctx['inferred_stance']=='negative':return 'negative'
    if ctx['application_mode']=='technique':return 'technique'
    if hit.get('direction')=='negative' and ctx.get('legacy_direction_mismatch'):
        return 'principle'
    if hit.get('direction') in ('positive','principle','technique'):return hit.get('direction')
    return 'principle'

def enrich_hits(index,hits):
    con=sqlite3.connect(Path(index)/'writing_brain.sqlite');con.row_factory=sqlite3.Row
    out=[]
    for h in hits:
        x=dict(h);ctx,rels=_load_context(con,x['rule_id']);x['context']=ctx;x['relations']=rels;x['effective_direction']=_effective(x,ctx)
        x['true_conflict_relations']=sum(r['relation']=='true_conflict' for r in rels)
        x['conditional_relations']=sum(r['relation']=='conditional' for r in rels)
        out.append(x)
    con.close();return out

def search(index,q,limit=12,topic=None,direction=None,cross_source_only=False,evidence_limit=4):
    hits=canonical.search(index,q,limit*2 if direction else limit,topic,None,cross_source_only,evidence_limit)
    hits=enrich_hits(index,hits)
    if direction:
        hits=[x for x in hits if x['effective_direction']==direction]
    return hits[:limit]

def direct(index,brief,limit=32):
    d=canonical.direct(index,brief,limit)
    for sec in d.get('sections',[]):
        hits=enrich_hits(index,sec.get('all',[]));sec['all']=hits
        sec['must_do']=[x for x in hits if x['effective_direction'] in ('positive','principle')]
        sec['avoid']=[x for x in hits if x['effective_direction']=='negative']
        sec['techniques']=[x for x in hits if x['effective_direction']=='technique']
        sec['conditional']=[x for x in hits if x.get('context',{}).get('application_mode')=='contextual']
        sec['true_conflict_relations']=sum(x['true_conflict_relations'] for x in hits)
    d['schema']='webnovel-writing-directive-context-v2.2';d['knowledge_layer']='canonical_rules+context_relations'
    d['protocol']=['Draft from semantic canonical rules first.','Use effective_direction inferred from Vietnamese text; legacy direction labels are provenance only when they disagree.','Treat conditional relations as context-dependent alternatives, not universal contradictions.','Surface true-conflict relations when two explicit opposing rules target the same proposition.','Use linked evidence for nuance/provenance.']
    return d

def review(index,text,limit=24):
    d=canonical.review(index,text,limit)
    for bucket in d.get('rule_buckets',[]):bucket['rules']=enrich_hits(index,bucket.get('rules',[]))
    d['schema']='webnovel-writing-review-context-v2.2';d['knowledge_layer']='canonical_rules+context_relations';return d

def checklist(index,topic,limit=18):
    hits=search(index,' '.join(brain.TOPIC_TERMS[topic][:10]),limit,topic,evidence_limit=3)
    return {'schema':'webnovel-writing-checklist-context-v2.2','topic':topic,'items':hits,
      'cross_source_rules':sum(x['cross_source'] for x in hits),'conditional_items':sum(x.get('context',{}).get('application_mode')=='contextual' for x in hits),
      'knowledge_layer':'canonical_rules+context_relations'}

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
    if a.cmd=='query':dump({'schema':'webnovel-writing-query-context-v2.2','query':a.q,'hits':search(a.index,a.q,a.limit,a.topic,a.direction,a.cross_source_only)},a.json_out)
    elif a.cmd=='direct':dump(direct(a.index,a.brief if a.brief is not None else Path(a.file).read_text(encoding='utf-8'),a.limit),a.json_out)
    elif a.cmd=='review':dump(review(a.index,a.text if a.text is not None else Path(a.file).read_text(encoding='utf-8'),a.limit),a.json_out)
    elif a.cmd=='checklist':dump(checklist(a.index,a.topic,a.limit),a.json_out)
    else:print((Path(a.index)/'context_v2_2_qa.json').read_text(encoding='utf-8'))
if __name__=='__main__':main()
