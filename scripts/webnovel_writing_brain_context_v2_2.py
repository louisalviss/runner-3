#!/usr/bin/env python3
"""Build a context/conflict resolution layer on top of Semantic Canonical V2.1."""
from __future__ import annotations
import argparse, collections, json, re, shutil, sqlite3, unicodedata
from pathlib import Path

NEG_PHRASES=('không nên','không được','không cần','không phải','không thể','đừng','tránh','hạn chế','tuyệt đối không','chớ','không ','chẳng ','không bao giờ')
POS_PHRASES=('nên ','cần ','phải ','hãy ','ưu tiên','tốt nhất','có thể ','nên dùng','nên cho','nên để','cố gắng','đảm bảo','bắt buộc')
CTX_PHRASES=('khi ','nếu ','trong trường hợp','đối với','tùy ','tuỳ ','trừ khi','chỉ khi','sau khi','trước khi','ở giai đoạn','giai đoạn ','lúc ','khi nào','tùy theo','tuỳ theo','trong lúc')
ABS_PHRASES=('luôn ','nhất định','bắt buộc','mọi ','không bao giờ','tuyệt đối','chỉ cần','duy nhất','bất kỳ','bất cứ','mọi lúc')
STOP_CORE={'nen','can','phai','hay','uu','tien','tot','nhat','khong','duoc','dung','tranh','han','che','khi','neu','trong','truong','hop','doi','voi','tuy','tru','chi','sau','truoc','luc','co','the','la','va','cua','mot','nhung','thi','de','cho','nay','do','ra','vao','ve'}

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def unaccent(s): return ''.join(c for c in unicodedata.normalize('NFD',s or '') if unicodedata.category(c)!='Mn')
def norm(s): return clean(re.sub(r'[^0-9a-z]+',' ',unaccent((s or '').lower())))
def toks(s): return {x for x in norm(s).split() if len(x)>=3}
def core_toks(s): return {x for x in norm(s).split() if len(x)>=3 and x not in STOP_CORE}
def jac(a,b): return len(a&b)/len(a|b) if a and b else 0.0

def markers(text,phrases):
    low=' '+clean(text).lower()+' '; return [p.strip() for p in phrases if p in low]

def infer_context(text,legacy_direction):
    neg=markers(text,NEG_PHRASES);pos=markers(text,POS_PHRASES);ctx=markers(text,CTX_PHRASES);ab=markers(text,ABS_PHRASES)
    stance='negative' if neg else ('directive' if pos else 'neutral')
    mode='contextual' if ctx else ('avoid' if stance=='negative' else ('recommended' if stance=='directive' else ('technique' if legacy_direction=='technique' else 'principle')))
    return {'stance':stance,'mode':mode,'neg':neg,'pos':pos,'ctx':ctx,'abs':ab,'legacy_mismatch':int(legacy_direction=='negative' and stance!='negative')}

def confidence(sim,core,base=.45): return round(min(.99,base+.34*max(0,min(1,(sim-.86)/.14))+.21*min(1,core/.40)),6)
def classify(a,b,sim):
    ca,cb=a['ctx'],b['ctx'];ta,tb=a['text'],b['text'];na,nb=norm(ta),norm(tb);core=jac(core_toks(ta),core_toks(tb));lex=jac(toks(ta),toks(tb));ctxa=set(ca['ctx']);ctxb=set(cb['ctx']);co=jac(ctxa,ctxb)
    opposite={ca['stance'],cb['stance']}=={'negative','directive'};same=(na==nb) or (sim>=.965 and core>=.72)
    if same and not opposite: rel,conf,reason='direction_error',confidence(sim,core,.60),'Near-identical proposition with different legacy direction labels; no semantic opposition detected.'
    elif opposite:
        contextual=bool(ctxa or ctxb)
        if contextual and (co<.50 or bool(ctxa)!=bool(ctxb)) and sim>=.89: rel,conf,reason='conditional',confidence(sim,core,.48),'Opposing stances appear under different or asymmetric application context; preserve both as conditional guidance.'
        elif (sim>=.94 and core>=.15) or (sim>=.90 and core>=.24): rel,conf,reason='true_conflict',confidence(sim,core,.54),'Explicit positive/negative stance opposition on a highly similar proposition.'
        elif contextual and sim>=.88: rel,conf,reason='conditional',confidence(sim,core,.43),'Potential opposition is context-scoped rather than universal.'
        else: rel,conf,reason='review',confidence(sim,core,.30),'Opposite stance cues exist, but proposition overlap is insufficient for an automatic contradiction decision.'
    else:
        if (ca['legacy_mismatch'] or cb['legacy_mismatch']) and sim>=.93 and core>=.30: rel,conf,reason='direction_error',confidence(sim,core,.55),'Legacy negative direction conflicts with the Vietnamese surface text; pair is semantically aligned.'
        elif (ctxa or ctxb) and sim>=.92 and core>=.18 and co<.50: rel,conf,reason='conditional',confidence(sim,core,.42),'Related guidance applies under different contexts; treat as conditional variants, not contradiction.'
        else: rel,conf,reason='complementary',confidence(sim,core,.50),'Different legacy direction labels but no explicit opposite textual stance; guidance is complementary/adjacent.'
    return rel,conf,reason,round(core,6),round(lex,6),round(co,6)

def build(srcdir,outdir):
    src=Path(srcdir);out=Path(outdir)
    if out.exists():shutil.rmtree(out)
    shutil.copytree(src,out);con=sqlite3.connect(out/'writing_brain.sqlite');con.row_factory=sqlite3.Row
    rules=[dict(r) for r in con.execute('SELECT id,topic,direction,canonical_text FROM canonical_rules ORDER BY id')];raw=[dict(r) for r in con.execute('SELECT * FROM canonical_conflicts ORDER BY id')]
    assert len(rules)==16697 and len(raw)==26320
    con.executescript('''DROP TABLE IF EXISTS canonical_rule_context;DROP TABLE IF EXISTS canonical_relations;CREATE TABLE canonical_rule_context(rule_id INTEGER PRIMARY KEY,inferred_stance TEXT NOT NULL,application_mode TEXT NOT NULL,context_markers_json TEXT NOT NULL,absolute_markers_json TEXT NOT NULL,negative_markers_json TEXT NOT NULL,positive_markers_json TEXT NOT NULL,legacy_direction_mismatch INTEGER NOT NULL,context_summary TEXT NOT NULL);CREATE TABLE canonical_relations(relation_id INTEGER PRIMARY KEY,raw_conflict_id INTEGER NOT NULL UNIQUE,rule_a INTEGER NOT NULL,rule_b INTEGER NOT NULL,topic TEXT NOT NULL,similarity REAL NOT NULL,relation TEXT NOT NULL,confidence REAL NOT NULL,core_jaccard REAL NOT NULL,lexical_jaccard REAL NOT NULL,context_overlap REAL NOT NULL,stance_a TEXT NOT NULL,stance_b TEXT NOT NULL,reason TEXT NOT NULL);CREATE INDEX idx_cr_rel ON canonical_relations(relation,confidence DESC);CREATE INDEX idx_cr_rulea ON canonical_relations(rule_a,relation);CREATE INDEX idx_cr_ruleb ON canonical_relations(rule_b,relation);''')
    ctx={};mismatch=0
    for r in rules:
        c=infer_context(r['canonical_text'] or '',r['direction'] or 'principle');ctx[r['id']]={'text':r['canonical_text'] or '','ctx':c};mismatch+=c['legacy_mismatch'];summary=f"mode={c['mode']}; stance={c['stance']}"+(f"; context={', '.join(c['ctx'])}" if c['ctx'] else '')+(f"; absolute={', '.join(c['abs'])}" if c['abs'] else '')
        con.execute('INSERT INTO canonical_rule_context VALUES(?,?,?,?,?,?,?,?,?)',(r['id'],c['stance'],c['mode'],json.dumps(c['ctx'],ensure_ascii=False),json.dumps(c['abs'],ensure_ascii=False),json.dumps(c['neg'],ensure_ascii=False),json.dumps(c['pos'],ensure_ascii=False),c['legacy_mismatch'],summary))
    counts=collections.Counter();by_topic=collections.Counter();rid=0
    for x in raw:
        a=ctx[x['rule_a']];b=ctx[x['rule_b']];rel,conf,reason,core,lex,co=classify(a,b,float(x['similarity']));rid+=1;counts[rel]+=1;by_topic[(x['topic'],rel)]+=1
        con.execute('INSERT INTO canonical_relations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,x['id'],x['rule_a'],x['rule_b'],x['topic'],x['similarity'],rel,conf,core,lex,co,a['ctx']['stance'],b['ctx']['stance'],reason))
    con.commit();total=len(raw);resolved=con.execute("SELECT count(*) FROM canonical_relations WHERE relation!='review'").fetchone()[0];truec=counts['true_conflict'];cond=counts['conditional'];falsec=counts['complementary']+counts['direction_error'];review=counts['review'];bad_exact=con.execute("SELECT count(*) FROM canonical_relations cr JOIN canonical_rules a ON a.id=cr.rule_a JOIN canonical_rules b ON b.id=cr.rule_b WHERE cr.relation='true_conflict' AND lower(trim(a.canonical_text))=lower(trim(b.canonical_text))").fetchone()[0];promotion=(bad_exact==0 and resolved/total>=.85 and falsec/total>=.50 and review/total<=.15)
    topic_summary={}
    for (t,rel),n in sorted(by_topic.items()):topic_summary.setdefault(t,{})[rel]=n
    qa={'schema':'webnovel-writing-brain-context-v2.2-qa','rules_total':len(rules),'raw_conflict_candidates':total,'classified':dict(counts),'resolved_non_review':resolved,'resolved_rate':round(resolved/total,6),'false_conflict_total':falsec,'false_conflict_rate':round(falsec/total,6),'true_conflict_total':truec,'conditional_total':cond,'review_total':review,'review_rate':round(review/total,6),'legacy_negative_direction_mismatches':mismatch,'exact_true_conflict_sanity_failures':bad_exact,'topic_relations':topic_summary,'promotion_pass':bool(promotion),'contract':'V2.2 preserves all V2.1 rules/evidence and raw conflict candidates, infers Vietnamese textual stance/context, and resolves candidate relations without treating legacy direction-label differences as contradictions.'}
    (out/'context_v2_2_qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');mp=out/'manifest.json';man=json.loads(mp.read_text(encoding='utf-8'));man['schema']='webnovel-writing-brain-context-v2.2';man['knowledge_mode']='semantic-canonical-context-first';man['context_v2_2']={'promotion_pass':bool(promotion),'raw_conflicts':total,'classified':dict(counts),'legacy_direction_mismatches':mismatch};mp.write_text(json.dumps(man,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');con.execute('PRAGMA optimize');con.close();print(json.dumps(qa,ensure_ascii=False,indent=2))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();build(a.source,a.out)
if __name__=='__main__':main()
