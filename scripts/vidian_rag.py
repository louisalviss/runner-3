#!/usr/bin/env python3
import argparse, collections, json, re, sqlite3, unicodedata
from pathlib import Path

STOP=set('và là của có cho trong một những các được với này đó khi thì đã đang sẽ nhưng mà hay về từ đến ra vào ở trên dưới theo như nên cũng rất không chỉ lại còn hơn sau trước nếu do bởi vì để tại người thứ nào nhiều ít qua làm bị đi thấy nói vẫn thể phải thật tôi bạn chúng ta hắn cô nó họ đây đó gì đâu sao phần bài viết nguồn thông tin tóm tắt tác giả ngày tháng năm link vidian vn'.split())
TOK=re.compile(r'[0-9A-Za-zÀ-ỹĐđ]+')
GENERIC_MATCH={'cong phap','phap bao','nhan vat','tu luyen','phap mon','ky nang','nang luc','the gioi','tac gia','truyen','tieu thuyet','quan he'}

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def unaccent(s): return ''.join(c for c in unicodedata.normalize('NFD',s) if unicodedata.category(c)!='Mn').replace('đ','d').replace('Đ','D')
def norm(s): return clean(re.sub(r'[^0-9a-z]+',' ',unaccent(clean(s)).lower()))
def norm_native(s): return clean(re.sub(r'[^0-9a-zà-ỹđ]+',' ',clean(s).lower()))
def toks(s): return [x.lower() for x in TOK.findall(s or '')]
def scale(xs):
    if not xs:return {}
    lo=min(v for _,v in xs); hi=max(v for _,v in xs)
    return {i:(1.0 if hi==lo else (v-lo)/(hi-lo)) for i,v in xs}

def matched_entities(con,q,limit=12):
    nq=norm(q); nnq=norm_native(q); short_query=len(toks(q))<=4
    proper_tokens=[x for x in re.findall(r'[0-9A-Za-zÀ-ỹĐđ]+',q or '') if x and x[0].isupper()]
    if not short_query and not proper_tokens: return []
    rows=con.execute('select id,name,norm,type,doc_freq,total_mentions from entities').fetchall()
    cand=[]
    for r in rows:
        en=r['norm']; nen=norm_native(r['name'])
        if not en or len(en)<4: continue
        if en in GENERIC_MATCH and en!=nq: continue
        exact=(nen==nnq) or (short_query and en==nq)
        inq=(f' {nen} ' in f' {nnq} ') or (short_query and f' {en} ' in f' {nq} ')
        if exact or inq:
            score=(100 if exact else 50)+min(len(nen),40)-min(int(r['doc_freq']),200)/50
            cand.append((score,dict(r)))
    cand.sort(key=lambda x:x[0],reverse=True)
    out=[]; seen=set()
    for _,r in cand:
        if r['norm'] in seen: continue
        seen.add(r['norm']); out.append(r)
        if len(out)>=limit: break
    return out

def retrieve(idx,q,limit=10,mode='hybrid'):
    idx=Path(idx); con=sqlite3.connect(idx/'vidian_knowledge.sqlite');con.row_factory=sqlite3.Row
    score=collections.defaultdict(dict)
    ts=[t for t in toks(q) if len(t)>=2 and t not in STOP] or toks(q)
    fq=(' AND ' if len(ts)<=4 else ' OR ').join(f'\"{t}\"' for t in ts[:16])
    if fq:
        try:
            rr=con.execute('SELECT a.id,-bm25(fts,5.0,1.0) s FROM fts JOIN articles a ON a.id=fts.rowid WHERE fts MATCH ? ORDER BY bm25(fts,5.0,1.0) LIMIT 160',(fq,)).fetchall()
        except sqlite3.OperationalError:
            rr=[]
        for a,s in scale([(int(r['id']),float(r['s'])) for r in rr]).items():score[a]['lexical']=s
    mes=matched_entities(con,q)
    qe=[int(x['id']) for x in mes]
    for e in qe:
        for r in con.execute('SELECT article_id,salience FROM article_entities WHERE entity_id=? ORDER BY salience DESC LIMIT 100',(e,)):
            score[int(r['article_id'])]['entity']=max(score[int(r['article_id'])].get('entity',0),1.0)
    if qe:
        m=','.join('?'*len(qe)); sql=f'''SELECT CASE WHEN subject_id IN ({m}) THEN object_id ELSE subject_id END eid,MAX(confidence) c,SUM(evidence_count) n FROM relations WHERE (subject_id IN ({m}) OR object_id IN ({m})) AND type<>'CO_OCCURS' GROUP BY eid ORDER BY c DESC,n DESC LIMIT 50''';p=qe+qe+qe
        for r in con.execute(sql,p):
            for a in con.execute('SELECT article_id FROM article_entities WHERE entity_id=? ORDER BY salience DESC LIMIT 40',(int(r['eid']),)):
                score[int(a['article_id'])]['graph']=max(score[int(a['article_id'])].get('graph',0),.35*float(r['c']))
    if mode!='lexical' and (idx/'semantic.joblib').exists():
        import joblib,numpy as np
        m=joblib.load(idx/'semantic.joblib'); D=np.load(idx/'vectors.npy',mmap_mode='r')
        v=m['nm'].transform(m['svd'].transform(m['v'].transform([q])))[0].astype('float32');ss=D@v;k=min(160,len(ss));ix=np.argpartition(ss,-k)[-k:]
        sem=scale([(int(i)+1,float(ss[i])) for i in ix if ss[i]>0])
        for a,s in sem.items():score[a]['semantic']=s
    weights={'lexical':.42,'semantic':.4,'entity':.13,'graph':.05} if mode=='hybrid' else ({'lexical':1.0} if mode=='lexical' else {'semantic':.85,'entity':.1,'graph':.05})
    rank=sorted(((sum(weights.get(k,0)*v for k,v in parts.items()),a,parts) for a,parts in score.items()),reverse=True)[:limit]
    hits=[]
    for s,a,parts in rank:
        ar=con.execute('select title,url from articles where id=?',(a,)).fetchone()
        ens=con.execute('select e.id,e.name,e.type,ae.mentions,ae.salience from article_entities ae join entities e on e.id=ae.entity_id where ae.article_id=? order by ae.salience desc limit 12',(a,)).fetchall()
        hits.append({'article_id':a,'score':round(s,6),'components':{k:round(v,5) for k,v in parts.items()},'title':ar['title'],'url':ar['url'],'entities':[dict(x) for x in ens]})
    top_ids={h['article_id'] for h in hits}; rels=[]
    if qe:
        m=','.join('?'*len(qe));
        sql=f'''select r.id,s.name subject,r.type,r.raw,o.name object,r.evidence_count,r.confidence from relations r join entities s on s.id=r.subject_id join entities o on o.id=r.object_id where (r.subject_id in ({m}) or r.object_id in ({m})) and r.type<>'CO_OCCURS' order by r.confidence desc,r.evidence_count desc limit 200'''
        for r in con.execute(sql,qe+qe):
            ev=con.execute('select re.article_id,a.title,a.url,re.sentence_sha,re.confidence from relation_evidence re join articles a on a.id=re.article_id where re.relation_id=? order by re.confidence desc limit 8',(int(r['id']),)).fetchall()
            evidence=[dict(x) for x in ev]
            support_top=sum(1 for x in evidence if int(x['article_id']) in top_ids)
            d=dict(r); d['top_hit_support']=support_top; d['evidence']=evidence
            rels.append(d)
        rels.sort(key=lambda x:(x['top_hit_support'],x['confidence'],x['evidence_count']),reverse=True)
        rels=rels[:30]
    manifest=json.loads((idx/'manifest.json').read_text(encoding='utf-8')) if (idx/'manifest.json').exists() else {}
    con.close()
    return {'question':q,'mode':mode,'matched_entities':mes,'top_hits':hits,'candidate_relations':rels,'source_prose_persisted':manifest.get('source_prose_persisted',False),'limitations':manifest.get('limitations',[]),'usage_note':'Use this packet for retrieval/ranking. For factual claims that require exact wording or context, fetch the original source URL; parser-derived relations are candidates, not ground truth.'}

def markdown(pkt):
    lines=['# Vidian evidence packet','',f"Question: {pkt['question']}",f"Mode: {pkt['mode']}",'']
    if pkt['matched_entities']:
        lines+=['## Matched entities']+[f"- {e['name']} [{e['type']}] — docs {e['doc_freq']}, mentions {e['total_mentions']}" for e in pkt['matched_entities']]
    lines+=['','## Top retrieval hits']
    for i,h in enumerate(pkt['top_hits'],1):
        es=', '.join(e['name'] for e in h['entities'][:6])
        lines += [f"{i}. {h['title']}",f"   URL: {h['url']}",f"   Score: {h['score']} | {h['components']}",f"   Entities: {es}"]
    if pkt['candidate_relations']:
        lines+=['','## Candidate relations (verify before asserting as fact)']
        for r in pkt['candidate_relations'][:20]:
            pred=f" / predicate={r['raw']}" if r.get('raw') else ''
            lines.append(f"- {r['subject']} --{r['type']}--> {r['object']} | conf={r['confidence']:.2f}, evidence={r['evidence_count']}{pred}")
            for ev in r['evidence'][:2]:lines.append(f"  - {ev['title']} | {ev['url']} | sentence_sha={ev['sentence_sha']}")
    lines+=['','## Limits']+[f"- {x}" for x in pkt['limitations']]+['- '+pkt['usage_note']]
    return '\n'.join(lines)+'\n'

def main():
    ap=argparse.ArgumentParser(description='Create a compact retrieval/evidence packet from Vidian Knowledge Layer.')
    ap.add_argument('--index',required=True);ap.add_argument('--q',required=True);ap.add_argument('--limit',type=int,default=10);ap.add_argument('--mode',choices=['hybrid','semantic','lexical'],default='hybrid');ap.add_argument('--json-out');ap.add_argument('--md-out')
    a=ap.parse_args();pkt=retrieve(a.index,a.q,a.limit,a.mode);js=json.dumps(pkt,ensure_ascii=False,indent=2)
    if a.json_out:Path(a.json_out).write_text(js,encoding='utf-8')
    if a.md_out:Path(a.md_out).write_text(markdown(pkt),encoding='utf-8')
    print(js)
if __name__=='__main__':main()
