#!/usr/bin/env python3
"""Build a conservative canonical-rule layer over the VN-first Writing Brain.

Evidence passages are never deleted. Every passage maps to exactly one canonical rule.
Only passages with the same canonical topic + directive direction are eligible to merge.
"""
import argparse, collections, hashlib, json, math, re, shutil, sqlite3, unicodedata
from pathlib import Path

TOPIC_VI = {
    'hook_opening':'Mở đầu và hook','plot_structure_arc':'Cấu trúc cốt truyện','outline':'Đại cương',
    'pacing_tension':'Nhịp truyện và căng thẳng','cliffhanger':'Kết chương và cliffhanger',
    'character_design':'Thiết kế nhân vật','motivation_conflict':'Động cơ và xung đột',
    'villain_antagonist':'Phản diện và đối thủ','progression_power':'Tiến triển sức mạnh',
    'reward_payoff':'Phần thưởng và payoff','worldbuilding':'Xây dựng thế giới','system_design':'Thiết kế hệ thống',
    'foreshadow_payoff':'Phục bút và thu hồi','mystery_reveal':'Bí ẩn và hé lộ','stakes':'Nguy cơ và cái giá',
    'dialogue_voice':'Đối thoại và giọng nhân vật','description_scene':'Miêu tả và cảnh',
    'combat_action':'Chiến đấu và hành động','emotion_immersion':'Cảm xúc và nhập vai',
    'romance_relationship':'Tình cảm và quan hệ','style_prose':'Văn phong và câu chữ',
    'editing_consistency':'Biên tập và nhất quán','serialization_reader':'Độc giả và giữ chân',
    'theme_meaning':'Chủ đề và ý nghĩa','title_blurb_packaging':'Tên truyện và giới thiệu',
    'genre_pattern':'Mẫu thể loại','craft_general':'Kỹ thuật viết chung',
}
ZH = re.compile(r'[\u3400-\u9fff]')


def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def unaccent(s): return ''.join(c for c in unicodedata.normalize('NFD',s or '') if unicodedata.category(c)!='Mn')
def norm(s): return clean(re.sub(r'[^0-9a-z]+',' ',unaccent((s or '').lower())))
def sha(s): return hashlib.sha256((s or '').encode('utf-8')).hexdigest()


class DSU:
    def __init__(self,n): self.p=list(range(n)); self.sz=[1]*n
    def find(self,x):
        while self.p[x]!=x:
            self.p[x]=self.p[self.p[x]]; x=self.p[x]
        return x
    def union(self,a,b,max_size=24):
        a,b=self.find(a),self.find(b)
        if a==b:return False
        if self.sz[a]+self.sz[b] > max_size:return False
        if self.sz[a] < self.sz[b]: a,b=b,a
        self.p[b]=a; self.sz[a]+=self.sz[b]
        return True


def atomset(raw):
    try:return set(json.loads(raw or '[]'))
    except Exception:return set()


def atom_overlap(a,b):
    if not a or not b:return 0.0
    return len(a & b) / max(1, min(len(a),len(b)))


def canonical_confidence(members):
    best=max(float(x['confidence'] or 0.5)*float(x['source_quality'] or 0.7) for x in members)
    sources={x['source'] for x in members}
    bonus=(0.065 if len(sources)>1 else 0.0) + min(0.055,0.018*math.log2(max(1,len(members))))
    return round(min(.99,best+bonus),6)


def build(base,outdir,max_neighbors=12):
    import joblib, numpy as np
    from scipy.sparse import hstack
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import normalize, Normalizer
    from sklearn.decomposition import TruncatedSVD

    base=Path(base); out=Path(outdir)
    if out.exists(): shutil.rmtree(out)
    shutil.copytree(base,out)
    db=out/'writing_brain.sqlite'
    con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    rows=[dict(r) for r in con.execute('''SELECT id,source,source_id,topic,kind,direction,confidence,source_quality,cross_source_support,support_key,text,evidence_surface,evidence_id,title,url,atoms_json FROM passages ORDER BY id''')]
    assert len(rows)==21210,len(rows)
    assert sum(r['source']=='vidian' for r in rows)==11672
    assert sum(r['source']=='moxing' for r in rows)==9538
    assert not any(ZH.search(r['text'] or '') for r in rows if r['source']=='moxing')

    dsu=DSU(len(rows)); by_group=collections.defaultdict(list)
    for i,r in enumerate(rows): by_group[(r['topic'],r['direction'])].append(i)
    pair_similarity={}; accepted_pairs=0

    for (topic,direction),idxs in by_group.items():
        if len(idxs)<2: continue
        docs=[rows[i]['text'] or '' for i in idxs]
        # Word signal captures semantic overlap; char signal stabilizes Vietnamese paraphrase / terminology variants.
        wv=TfidfVectorizer(strip_accents='unicode',ngram_range=(1,2),min_df=1,max_df=.995,max_features=42000,sublinear_tf=True)
        cv=TfidfVectorizer(strip_accents='unicode',analyzer='char_wb',ngram_range=(3,5),min_df=2,max_df=.995,max_features=36000,sublinear_tf=True)
        W=wv.fit_transform(docs)
        try:C=cv.fit_transform(docs)
        except ValueError:C=None
        X=normalize(hstack([W*.72,C*.28],format='csr') if C is not None else W)
        k=min(max_neighbors,len(idxs))
        nn=NearestNeighbors(metric='cosine',algorithm='brute',n_neighbors=k,n_jobs=-1).fit(X)
        dist,nei=nn.kneighbors(X,return_distance=True)
        atoms=[atomset(rows[i]['atoms_json']) for i in idxs]
        normalized=[norm(rows[i]['text']) for i in idxs]
        lengths=[max(1,len(x)) for x in normalized]
        for li in range(len(idxs)):
            for pos in range(1,k):
                lj=int(nei[li,pos]); sim=1.0-float(dist[li,pos])
                if lj<=li: continue
                gi,gj=idxs[li],idxs[lj]
                a,b=rows[gi],rows[gj]
                lr=min(lengths[li],lengths[lj])/max(lengths[li],lengths[lj])
                ao=atom_overlap(atoms[li],atoms[lj])
                exact=normalized[li] and normalized[li]==normalized[lj]
                cross=a['source']!=b['source']
                # Conservative gates: cross-source paraphrases may differ more lexically, but must share a craft atom.
                if exact:
                    ok=True
                elif cross:
                    ok=(lr>=.42 and ao>=.34 and sim>=.70) or (lr>=.55 and ao>=.50 and sim>=.65)
                else:
                    ok=(lr>=.55 and ao>=.34 and sim>=.82)
                if ok and dsu.union(gi,gj,max_size=24):
                    accepted_pairs+=1
                if ok:
                    pair_similarity[tuple(sorted((gi,gj)))]=sim

    clusters=collections.defaultdict(list)
    for i in range(len(rows)): clusters[dsu.find(i)].append(i)
    cluster_list=sorted(clusters.values(),key=lambda xs:min(rows[i]['id'] for i in xs))

    con.executescript('''
      DROP TABLE IF EXISTS canonical_rules;
      DROP TABLE IF EXISTS canonical_evidence;
      DROP TABLE IF EXISTS canonical_fts;
      CREATE TABLE canonical_rules(
        id INTEGER PRIMARY KEY, topic TEXT, direction TEXT, kind TEXT, title TEXT, canonical_text TEXT,
        confidence REAL, evidence_count INT, vidian_count INT, moxing_count INT, source_count INT,
        cross_source INT, atoms_json TEXT, representative_passage_id INT, rule_hash TEXT UNIQUE,
        merge_method TEXT, max_pair_similarity REAL
      );
      CREATE TABLE canonical_evidence(
        rule_id INT NOT NULL, passage_id INT NOT NULL UNIQUE, source TEXT NOT NULL, evidence_id TEXT,
        url TEXT, confidence REAL, similarity_to_rule REAL, evidence_rank INT,
        PRIMARY KEY(rule_id,passage_id)
      );
      CREATE VIRTUAL TABLE canonical_fts USING fts5(title,topic,direction,text,content='',tokenize='unicode61 remove_diacritics 2');
      CREATE INDEX idx_canonical_topic ON canonical_rules(topic,direction,confidence DESC);
      CREATE INDEX idx_canonical_cross ON canonical_rules(cross_source DESC,evidence_count DESC);
      CREATE INDEX idx_canonical_evidence_rule ON canonical_evidence(rule_id,evidence_rank);
    ''')

    canonical_docs=[]; canonical_ids=[]; merged_rules=0; cross_rules=0; max_cluster=0
    for rid,midx in enumerate(cluster_list,1):
        members=[rows[i] for i in midx]; max_cluster=max(max_cluster,len(members))
        topic=members[0]['topic']; direction=members[0]['direction']
        assert all(x['topic']==topic and x['direction']==direction for x in members)
        src=collections.Counter(x['source'] for x in members)
        if len(members)>1: merged_rules+=1
        if len(src)>1: cross_rules+=1
        atoms=sorted(set().union(*(atomset(x['atoms_json']) for x in members)))
        # Pick the strongest concise evidence as the canonical formulation.
        def rep_score(x):
            length=len(clean(x['text']))
            concise=1.0/(1.0+max(0,length-360)/720)
            return .50*float(x['confidence'] or .5)+.28*float(x['source_quality'] or .7)+.14*min(1,float(x['cross_source_support'] or 0)/4)+.08*concise
        rep=max(members,key=rep_score); rep_i=rows.index(rep)
        # If cluster has multiple items, prefer a member central to the cluster when similarity evidence is available.
        if len(midx)>1:
            central=[]
            for gi in midx:
                sims=[]
                for gj in midx:
                    if gi==gj:continue
                    sims.append(pair_similarity.get(tuple(sorted((gi,gj))),0.0))
                central.append((sum(sims)/max(1,len(sims))+.12*rep_score(rows[gi]),gi))
            _,rep_i=max(central); rep=rows[rep_i]
        text=clean(rep['text']); title=TOPIC_VI.get(topic,'Kỹ thuật viết')
        conf=canonical_confidence(members)
        maxsim=max([pair_similarity.get(tuple(sorted((a,b))),0.0) for ai,a in enumerate(midx) for b in midx[ai+1:]] or [1.0])
        rule_hash=sha('|'.join([topic,direction,norm(text)]))
        kind=collections.Counter(x['kind'] for x in members).most_common(1)[0][0]
        con.execute('''INSERT INTO canonical_rules(id,topic,direction,kind,title,canonical_text,confidence,evidence_count,vidian_count,moxing_count,source_count,cross_source,atoms_json,representative_passage_id,rule_hash,merge_method,max_pair_similarity) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
            rid,topic,direction,kind,title,text,conf,len(members),src['vidian'],src['moxing'],len(src),1 if len(src)>1 else 0,
            json.dumps(atoms,ensure_ascii=False),rep['id'],rule_hash,'conservative-vietnamese-tfidf-v1',round(maxsim,6)))
        con.execute('INSERT INTO canonical_fts(rowid,title,topic,direction,text) VALUES(?,?,?,?,?)',(rid,title,topic,direction,text))
        ranked=[]
        for gi in midx:
            x=rows[gi]
            sim=1.0 if gi==rep_i else pair_similarity.get(tuple(sorted((gi,rep_i))),0.0)
            e_score=.62*float(x['confidence'] or .5)+.28*float(x['source_quality'] or .7)+.10*sim
            ranked.append((e_score,sim,x))
        ranked.sort(reverse=True,key=lambda z:z[0])
        for rank,(_,sim,x) in enumerate(ranked,1):
            con.execute('INSERT INTO canonical_evidence(rule_id,passage_id,source,evidence_id,url,confidence,similarity_to_rule,evidence_rank) VALUES(?,?,?,?,?,?,?,?)',(
                rid,x['id'],x['source'],x['evidence_id'],x['url'],x['confidence'],round(float(sim),6),rank))
        canonical_docs.append(' '.join([topic,direction,title,text])); canonical_ids.append(rid)
    con.commit()

    # Canonical semantic index: one vector per rule, all Vietnamese.
    v=TfidfVectorizer(strip_accents='unicode',ngram_range=(1,2),min_df=2,max_df=.98,max_features=60000,sublinear_tf=True)
    X=v.fit_transform(canonical_docs); dims=min(96,X.shape[0]-1,X.shape[1]-1)
    svd=TruncatedSVD(dims,random_state=23,n_iter=7); nm=Normalizer(copy=False)
    D=nm.fit_transform(svd.fit_transform(X)).astype('float32')
    np.save(out/'canonical_vectors.npy',D,allow_pickle=False)
    np.save(out/'canonical_ids.npy',np.array(canonical_ids,dtype='int64'),allow_pickle=False)
    joblib.dump({'vectorizer':v,'svd':svd,'normalizer':nm},out/'canonical_semantic.joblib',compress=3)

    rules=con.execute('SELECT count(*) FROM canonical_rules').fetchone()[0]
    mapped=con.execute('SELECT count(*) FROM canonical_evidence').fetchone()[0]
    distinct_mapped=con.execute('SELECT count(distinct passage_id) FROM canonical_evidence').fetchone()[0]
    cjk_rules=con.execute("SELECT count(*) FROM canonical_rules WHERE canonical_text GLOB '*[㐀-鿿]*'").fetchone()[0]
    singleton=con.execute('SELECT count(*) FROM canonical_rules WHERE evidence_count=1').fetchone()[0]
    multi=rules-singleton
    assert mapped==21210 and distinct_mapped==21210,(mapped,distinct_mapped)
    assert cjk_rules==0,cjk_rules
    assert rules<=21210 and rules>10000,rules
    assert max_cluster<=24,max_cluster

    topic_stats=[dict(r) for r in con.execute('''SELECT topic,count(*) rules,sum(evidence_count) evidence,sum(cross_source) cross_source_rules FROM canonical_rules GROUP BY topic ORDER BY rules DESC''')]
    qa={
      'schema':'webnovel-writing-brain-canonical-qa-v1','passages_total':21210,'canonical_rules':rules,
      'evidence_mapped':mapped,'singleton_rules':singleton,'multi_evidence_rules':multi,
      'evidence_collapsed':21210-rules,'cross_source_rules':cross_rules,'accepted_merge_edges':accepted_pairs,
      'max_cluster_size':max_cluster,'canonical_cjk_rows':cjk_rules,'semantic_dimensions':dims,'semantic_features':int(X.shape[1]),
      'topic_stats':topic_stats,
      'contract':'Every evidence passage maps to exactly one conservative canonical rule; evidence is preserved and standard retrieval should prefer canonical rules.'
    }
    (out/'canonical_qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    mp=out/'manifest.json'; manifest=json.loads(mp.read_text(encoding='utf-8'))
    manifest.update({
      'schema':'webnovel-writing-brain-canonical-v1','knowledge_mode':'canonical-first',
      'canonical_layer':{
        'rules':rules,'evidence_passages':21210,'evidence_collapsed':21210-rules,'cross_source_rules':cross_rules,
        'merge_policy':'Conservative semantic clustering only inside identical canonical topic + directive direction. Cross-source merges require Vietnamese TF-IDF similarity plus shared craft atoms; support_key alone never proves equivalence.',
        'representative_policy':'Canonical text is an extractive Vietnamese formulation chosen from the strongest/most-central evidence; all supporting evidence remains linked.',
        'tables':['canonical_rules','canonical_evidence','canonical_fts'],
        'semantic':'Vietnamese word TF-IDF(1,2)+SVD+cosine, 96d maximum'
      },
      'default_retrieval_layer':'canonical_rules',
      'evidence_fallback':'passages'
    })
    mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    con.execute('PRAGMA optimize');con.close()
    print(json.dumps(qa,ensure_ascii=False,indent=2))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base',required=True);ap.add_argument('--out',required=True);ap.add_argument('--max-neighbors',type=int,default=12)
    a=ap.parse_args();build(a.base,a.out,a.max_neighbors)
if __name__=='__main__':main()
