#!/usr/bin/env python3
import argparse, hashlib, json, math
from pathlib import Path
import vidian_writing as w
import vidian_writing_quality as quality

# Keep runtime topic detection and evidence validation identical to the build-time quality layer.
w=quality.apply()


def _checklist_items(index,topic,limit):
    data=json.loads((Path(index)/'checklists.json').read_text(encoding='utf-8'))
    return [dict(x) for x in data.get(topic,[])[:limit]]

def search(index,q,limit=12,mode='hybrid',topic=None,kind=None):
    raw=w.search(index,q,max(160,limit*16),mode,topic,kind)
    return quality.rank_actionable(raw,limit)


def _topic_evidence(index,text,topic,limit,used):
    pool=w.search(index,text,max(120,limit*24),'hybrid',topic)
    pool+=w.search(index,' '.join(w.TOPICS[topic][:10]),max(100,limit*20),'hybrid',topic)
    ranked=quality.rank_actionable(pool,limit*4)
    # Durable fallback: refined checklist is itself QA-gated actionable evidence.
    ranked+=_checklist_items(index,topic,limit*3)
    keep=[]
    for x in ranked:
        pid=x.get('passage_id')
        if pid in used: continue
        if not quality.actionable(x): continue
        used.add(pid); keep.append(x)
        if len(keep)>=limit: break
    return keep


def direct(index,brief,limit=36):
    scored=w.topic_scores(brief)
    selected=[x[0] for x in scored[:8]]
    core=['hook_opening','plot_structure_arc','pacing_tension','character_design','motivation_conflict','progression_power','worldbuilding','reward_payoff']
    for t in core:
        if len(selected)>=8: break
        if t not in selected: selected.append(t)
    per=max(4,math.ceil(limit/max(1,len(selected))))
    sections=[]; used=set()
    for topic in selected:
        keep=_topic_evidence(index,brief,topic,per,used)
        if not keep: continue
        sections.append({'topic':topic,'must_do':[x for x in keep if x['kind'] in {'do','principle'}],'avoid':[x for x in keep if x['kind'] in {'dont','warning'}],'techniques':[x for x in keep if x['kind'] in {'technique','diagnostic'}],'all':keep})
    return {'schema':'vidian-writing-directive-packet-v1.2','brief_sha256':hashlib.sha256(brief.encode()).hexdigest(),'brief_chars':len(brief),'detected_topics':[{'topic':t,'score':s,'matches':m} for t,s,m in scored[:12]],'directive_topics':[x['topic'] for x in sections],'sections':sections,'composition_protocol':['Treat retrieved rules as craft constraints, not prose to copy.','Evidence must be topic-aligned in the sentence itself and pass actionable-quality filters.','Convert selected rules into scene and arc checks before drafting.','After drafting, run review and repair only weaknesses actually present.','Evidence surfaces are reconstructed parser tokens, never verbatim quotations.']}


def review(index,text,limit=24):
    scored=w.topic_scores(text)
    selected=[x[0] for x in scored[:6]] or ['plot_structure_arc','pacing_tension','character_design','style_prose']
    per=max(3,math.ceil(limit/max(1,len(selected))))
    buckets=[]; used=set()
    for topic in selected:
        keep=_topic_evidence(index,text,topic,per,used)
        if not keep: continue
        buckets.append({'topic':topic,'hits':keep})
    return {'schema':'vidian-writing-review-packet-v1.2','draft_sha256':hashlib.sha256(text.encode()).hexdigest(),'draft_chars':len(text),'detected_topics':[{'topic':t,'score':s,'matches':m} for t,s,m in scored[:10]],'review_dimensions':[x['topic'] for x in buckets],'evidence_buckets':buckets,'instruction':'Use actionable, topic-aligned craft rules as review criteria. Do not treat reconstructed evidence surfaces as verbatim source prose.'}


def checklist(index,topic,limit=20):
    return {'schema':'vidian-writing-checklist-v1.2','topic':topic,'items':_checklist_items(index,topic,limit)}


def dump(packet,json_out=None,md_out=None):
    raw=json.dumps(packet,ensure_ascii=False,indent=2); print(raw)
    if json_out: Path(json_out).write_text(raw,encoding='utf-8')
    if md_out: Path(md_out).write_text(w.md(packet),encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest='cmd',required=True)
    q=sp.add_parser('query');q.add_argument('--index',required=True);q.add_argument('--q',required=True);q.add_argument('--limit',type=int,default=12);q.add_argument('--mode',choices=['hybrid','semantic','lexical'],default='hybrid');q.add_argument('--topic',choices=sorted(w.TOPICS));q.add_argument('--kind',choices=['do','dont','warning','technique','diagnostic','principle']);q.add_argument('--json-out');q.add_argument('--md-out')
    d=sp.add_parser('direct');d.add_argument('--index',required=True);g=d.add_mutually_exclusive_group(required=True);g.add_argument('--brief');g.add_argument('--file');d.add_argument('--limit',type=int,default=36);d.add_argument('--json-out');d.add_argument('--md-out')
    r=sp.add_parser('review');r.add_argument('--index',required=True);g=r.add_mutually_exclusive_group(required=True);g.add_argument('--text');g.add_argument('--file');r.add_argument('--limit',type=int,default=24);r.add_argument('--json-out');r.add_argument('--md-out')
    c=sp.add_parser('checklist');c.add_argument('--index',required=True);c.add_argument('--topic',required=True,choices=sorted(w.TOPICS));c.add_argument('--limit',type=int,default=20);c.add_argument('--json-out');c.add_argument('--md-out')
    a=ap.parse_args()
    if a.cmd=='query': dump({'schema':'vidian-writing-query-packet-v1.2','query':a.q,'mode':a.mode,'topic_filter':a.topic,'kind_filter':a.kind,'hits':search(a.index,a.q,a.limit,a.mode,a.topic,a.kind)},a.json_out,a.md_out)
    elif a.cmd=='direct':
        text=a.brief if a.brief is not None else Path(a.file).read_text(encoding='utf-8'); dump(direct(a.index,text,a.limit),a.json_out,a.md_out)
    elif a.cmd=='review':
        text=a.text if a.text is not None else Path(a.file).read_text(encoding='utf-8'); dump(review(a.index,text,a.limit),a.json_out,a.md_out)
    else: dump(checklist(a.index,a.topic,a.limit),a.json_out,a.md_out)
if __name__=='__main__':main()
