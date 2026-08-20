#!/usr/bin/env python3
"""Conservative canonical-rule builder for the VN-first Writing Brain."""
import argparse, collections, hashlib, json, math, re, shutil, sqlite3, unicodedata
from pathlib import Path

TOPIC_VI={'hook_opening':'Mở đầu và hook','plot_structure_arc':'Cấu trúc cốt truyện','outline':'Đại cương','pacing_tension':'Nhịp truyện và căng thẳng','cliffhanger':'Kết chương và cliffhanger','character_design':'Thiết kế nhân vật','motivation_conflict':'Động cơ và xung đột','villain_antagonist':'Phản diện và đối thủ','progression_power':'Tiến triển sức mạnh','reward_payoff':'Phần thưởng và payoff','worldbuilding':'Xây dựng thế giới','system_design':'Thiết kế hệ thống','foreshadow_payoff':'Phục bút và thu hồi','mystery_reveal':'Bí ẩn và hé lộ','stakes':'Nguy cơ và cái giá','dialogue_voice':'Đối thoại và giọng nhân vật','description_scene':'Miêu tả và cảnh','combat_action':'Chiến đấu và hành động','emotion_immersion':'Cảm xúc và nhập vai','romance_relationship':'Tình cảm và quan hệ','style_prose':'Văn phong và câu chữ','editing_consistency':'Biên tập và nhất quán','serialization_reader':'Độc giả và giữ chân','theme_meaning':'Chủ đề và ý nghĩa','title_blurb_packaging':'Tên truyện và giới thiệu','genre_pattern':'Mẫu thể loại','craft_general':'Kỹ thuật viết chung'}
ZH=re.compile(r'[\u3400-\u9fff]')
def clean(s):return re.sub(r'\s+',' ',s or '').strip()
def unaccent(s):return ''.join(c for c in unicodedata.normalize('NFD',s or '') if unicodedata.category(c)!='Mn')
def norm(s):return clean(re.sub(r'[^0-9a-z]+',' ',unaccent((s or '').lower())))
def h(s):return hashlib.sha256((s or '').encode()).hexdigest()
def atoms(raw):
    try:return set(json.loads(raw or '[]'))
    except Exception:return set()
def aover(a,b):return 0.0 if not a or not b else len(a&b)/max(1,min(len(a),len(b)))
class DSU:
    def __init__(self,n):self.p=list(range(n));self.sz=[1]*n
    def find(self,x):
        while self.p[x]!=x:self.p[x]=self.p[self.p[x]];x=self.p[x]
        return x
    def union(self,a,b,cap=24):
        a,b=self.find(a),self.find(b)
        if a==b or self.sz[a]+self.sz[b]>cap:return False
        if self.sz[a]<self.sz[b]:a,b=b,a
        self.p[b]=a;self.sz[a]+=self.sz[b];return True

def cconf(ms):
    best=max(float(x['confidence'] or .5)*float(x['source_quality'] or .7) for x in ms)
    bonus=(.065 if len({x['source'] for x in ms})>1 else 0)+min(.055,.018*math.log2(max(1,len(ms))))
    return round(min(.99,best+bonus),6)

def build(base,outdir,max_neighbors=12):
    import joblib,numpy as np
    from scipy.sparse import hstack
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import normalize,Normalizer
    from sklearn.decomposition import TruncatedSVD
    base=Path(base);out=Path(outdir)
    if out.exists():shutil.rmtree(out)
    shutil.copytree(base,out)
    con=sqlite3.connect(out/'writing_brain.sqlite');con.row_factory=sqlite3.Row
    rs=[dict(r) for r in con.execute('SELECT id,source,source_id,topic,kind,direction,confidence,source_quality,cross_source_support,text,evidence_surface,evidence_id,title,url,atoms_json FROM passages ORDER BY id')]
    assert len(rs)==21210 and sum(x['source']=='vidian' for x in rs)==11672 and sum(x['source']=='moxing' for x in rs)==9538
    assert not any(ZH.search(x['text'] or '') for x in rs if x['source']=='moxing')
    dsu=DSU(len(rs));groups=collections.defaultdict(list);edge_sim={};accepted=0
    for i,x in enumerate(rs):groups[(x['topic'],x['direction'])].append(i)
    for _,idxs in groups.items():
        if len(idxs)<2:continue
        docs=[rs[i]['text'] or '' for i in idxs]
        w=TfidfVectorizer(strip_accents='unicode',ngram_range=(1,2),min_df=1,max_df=.995,max_features=36000,sublinear_tf=True).fit_transform(docs)
        try:c=TfidfVectorizer(strip_accents='unicode',analyzer='char_wb',ngram_range=(3,5),min_df=2,max_df=.995,max_features=30000,sublinear_tf=True).fit_transform(docs)
        except ValueError:c=None
        xmat=normalize(hstack([w*.74,c*.26],format='csr') if c is not None else w)
        k=min(max_neighbors,len(idxs));dist,nei=NearestNeighbors(metric='cosine',algorithm='brute',n_neighbors=k,n_jobs=-1).fit(xmat).kneighbors(xmat)
        aset=[atoms(rs[i]['atoms_json']) for i in idxs];ns=[norm(rs[i]['text']) for i in idxs];ls=[max(1,len(z)) for z in ns]
        for a in range(len(idxs)):
            for p in range(1,k):
                b=int(nei[a,p])
                if b<=a:continue
                sim=1-float(dist[a,p]);gi,gj=idxs[a],idxs[b];ra,rb=rs[gi],rs[gj]
                lr=min(ls[a],ls[b])/max(ls[a],ls[b]);ao=aover(aset[a],aset[b]);exact=bool(ns[a]) and ns[a]==ns[b];cross=ra['source']!=rb['source']
                if exact:ok=True
                elif cross:ok=(lr>=.42 and ao>=.34 and sim>=.70) or (lr>=.55 and ao>=.50 and sim>=.65)
                else:ok=(lr>=.55 and ao>=.34 and sim>=.82)
                if ok:
                    edge_sim[tuple(sorted((gi,gj)))]=sim
                    if dsu.union(gi,gj):accepted+=1
    cls=collections.defaultdict(list)
    for i in range(len(rs)):cls[dsu.find(i)].append(i)
    clusters=sorted(cls.values(),key=lambda xs:min(rs[i]['id'] for i in xs))
    con.executescript('''DROP TABLE IF EXISTS canonical_rules;DROP TABLE IF EXISTS canonical_evidence;DROP TABLE IF EXISTS canonical_fts;
    CREATE TABLE canonical_rules(id INTEGER PRIMARY KEY,topic TEXT,direction TEXT,kind TEXT,title TEXT,canonical_text TEXT,confidence REAL,evidence_count INT,vidian_count INT,moxing_count INT,source_count INT,cross_source INT,atoms_json TEXT,representative_passage_id INT,rule_hash TEXT UNIQUE,merge_method TEXT,max_pair_similarity REAL);
    CREATE TABLE canonical_evidence(rule_id INT NOT NULL,passage_id INT NOT NULL UNIQUE,source TEXT NOT NULL,evidence_id TEXT,url TEXT,confidence REAL,similarity_to_rule REAL,evidence_rank INT,PRIMARY KEY(rule_id,passage_id));
    CREATE VIRTUAL TABLE canonical_fts USING fts5(title,topic,direction,text,content='',tokenize='unicode61 remove_diacritics 2');
    CREATE INDEX idx_canonical_topic ON canonical_rules(topic,direction,confidence DESC);CREATE INDEX idx_canonical_cross ON canonical_rules(cross_source DESC,evidence_count DESC);CREATE INDEX idx_canonical_evidence_rule ON canonical_evidence(rule_id,evidence_rank);''')
    cdocs=[];cids=[];cross_rules=0;max_cluster=0
    for rid,midx in enumerate(clusters,1):
        ms=[rs[i] for i in midx];topic=ms[0]['topic'];direction=ms[0]['direction'];assert all(x['topic']==topic and x['direction']==direction for x in ms)
        src=collections.Counter(x['source'] for x in ms);cross_rules+=len(src)>1;max_cluster=max(max_cluster,len(ms));all_atoms=sorted(set().union(*(atoms(x['atoms_json']) for x in ms)))
        def score(gi):
            x=rs[gi];ln=len(clean(x['text']));concise=1/(1+max(0,ln-360)/720);central=sum(edge_sim.get(tuple(sorted((gi,j))),0.0) for j in midx if j!=gi)/max(1,len(midx)-1)
            return .42*float(x['confidence'] or .5)+.23*float(x['source_quality'] or .7)+.12*min(1,float(x['cross_source_support'] or 0)/4)+.08*concise+.15*central
        rep_i=max(midx,key=score);rep=rs[rep_i];text=clean(rep['text']);title=TOPIC_VI.get(topic,'Kỹ thuật viết');kind=collections.Counter(x['kind'] for x in ms).most_common(1)[0][0]
        mx=max([edge_sim.get(tuple(sorted((a,b))),0.0) for ai,a in enumerate(midx) for b in midx[ai+1:]] or [1.0]);rulehash=h('|'.join([topic,direction,norm(text),str(rep['id']),str(min(rs[i]['id'] for i in midx))]))
        con.execute('INSERT INTO canonical_rules VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,topic,direction,kind,title,text,cconf(ms),len(ms),src['vidian'],src['moxing'],len(src),int(len(src)>1),json.dumps(all_atoms,ensure_ascii=False),rep['id'],rulehash,'conservative-vietnamese-tfidf-v2.1',round(mx,6)))
        con.execute('INSERT INTO canonical_fts(rowid,title,topic,direction,text) VALUES(?,?,?,?,?)',(rid,title,topic,direction,text))
        ranked=[]
        for gi in midx:
            x=rs[gi];sim=1.0 if gi==rep_i else edge_sim.get(tuple(sorted((gi,rep_i))),0.0);es=.62*float(x['confidence'] or .5)+.28*float(x['source_quality'] or .7)+.10*sim;ranked.append((es,sim,x))
        for rank,(_,sim,x) in enumerate(sorted(ranked,reverse=True,key=lambda z:z[0]),1):con.execute('INSERT INTO canonical_evidence VALUES(?,?,?,?,?,?,?,?)',(rid,x['id'],x['source'],x['evidence_id'],x['url'],x['confidence'],round(float(sim),6),rank))
        cdocs.append(' '.join([topic,direction,title,text]));cids.append(rid)
    con.commit()
    v=TfidfVectorizer(strip_accents='unicode',ngram_range=(1,2),min_df=2,max_df=.98,max_features=60000,sublinear_tf=True);X=v.fit_transform(cdocs);dims=min(96,X.shape[0]-1,X.shape[1]-1);svd=TruncatedSVD(dims,random_state=23,n_iter=7);nm=Normalizer(copy=False);D=nm.fit_transform(svd.fit_transform(X)).astype('float32')
    np.save(out/'canonical_vectors.npy',D,allow_pickle=False);np.save(out/'canonical_ids.npy',np.array(cids,dtype='int64'),allow_pickle=False);joblib.dump({'vectorizer':v,'svd':svd,'normalizer':nm},out/'canonical_semantic.joblib',compress=3)
    rules=con.execute('SELECT count(*) FROM canonical_rules').fetchone()[0];mapped=con.execute('SELECT count(*) FROM canonical_evidence').fetchone()[0];distinct=con.execute('SELECT count(distinct passage_id) FROM canonical_evidence').fetchone()[0];single=con.execute('SELECT count(*) FROM canonical_rules WHERE evidence_count=1').fetchone()[0]
    cjk=sum(bool(ZH.search(r[0] or '')) for r in con.execute('SELECT canonical_text FROM canonical_rules'));assert mapped==21210 and distinct==21210 and cjk==0 and 10000<rules<=21210 and max_cluster<=24
    tstats=[dict(r) for r in con.execute('SELECT topic,count(*) rules,sum(evidence_count) evidence,sum(cross_source) cross_source_rules FROM canonical_rules GROUP BY topic ORDER BY rules DESC')]
    qa={'schema':'webnovel-writing-brain-canonical-qa-v2.1','passages_total':21210,'canonical_rules':rules,'evidence_mapped':mapped,'singleton_rules':single,'multi_evidence_rules':rules-single,'evidence_collapsed':21210-rules,'cross_source_rules':cross_rules,'accepted_merge_edges':accepted,'max_cluster_size':max_cluster,'canonical_cjk_rows':cjk,'semantic_dimensions':dims,'semantic_features':int(X.shape[1]),'topic_stats':tstats,'contract':'Every evidence passage maps to exactly one conservative canonical rule; evidence is preserved; canonical rules are the default retrieval layer.'}
    (out/'canonical_qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    mp=out/'manifest.json';man=json.loads(mp.read_text(encoding='utf-8'));man.update({'schema':'webnovel-writing-brain-canonical-v1','knowledge_mode':'canonical-first','default_retrieval_layer':'canonical_rules','evidence_fallback':'passages','canonical_layer':{'rules':rules,'evidence_passages':21210,'evidence_collapsed':21210-rules,'cross_source_rules':cross_rules,'merge_policy':'Conservative semantic clustering only inside identical canonical topic + directive direction. Cross-source merges require Vietnamese TF-IDF similarity plus shared craft atoms; thematic support_key alone is never treated as equivalence.','representative_policy':'Canonical text is an extractive Vietnamese formulation chosen from the strongest/most-central linked evidence; all evidence is retained.','tables':['canonical_rules','canonical_evidence','canonical_fts'],'semantic':'Vietnamese word TF-IDF(1,2)+SVD+cosine, up to 96d'}});mp.write_text(json.dumps(man,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    con.execute('PRAGMA optimize');con.close();print(json.dumps(qa,ensure_ascii=False,indent=2))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base',required=True);ap.add_argument('--out',required=True);ap.add_argument('--max-neighbors',type=int,default=12);a=ap.parse_args();build(a.base,a.out,a.max_neighbors)
if __name__=='__main__':main()
