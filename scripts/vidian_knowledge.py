#!/usr/bin/env python3
import argparse,collections,gzip,json,math,re,sqlite3,unicodedata,zipfile
from pathlib import Path

STOP=set('và là của có cho trong một những các được với này đó khi thì đã đang sẽ nhưng mà hay về từ đến ra vào ở trên dưới theo như nên cũng rất không chỉ lại còn hơn sau trước nếu do bởi vì để tại người thứ nào nhiều ít qua làm bị đi thấy nói vẫn thể phải thật tôi bạn chúng ta hắn cô nó họ đây đó gì đâu sao phần bài viết nguồn thông tin tóm tắt tác giả ngày tháng năm link vidian vn'.split())
BAD=set('Trong Đây Một Hai Ba Bốn Năm Sáu Bảy Tám Chín Mười Người Điều Sự Kẻ Bạn Tôi Hắn Cô Nó Ta Chúng Họ Hãy Nhưng Mà Với Theo Tại Vì Nếu Khi Sau Trước Đến Được Có Là Không Các Những Tháng Ngày Năm Tổng Hội Tác Link Top Rank Review Tin Thông Tin Nguồn Chẳng Chính Thánh Tiếng Hoàng Huyền Trạch'.split())
GEN=re.compile(r'^(?:moi quan he(?: nhan vat)?|trai nghiem(?: nhan vat)?|hinh tuong(?: nhan vat)?|thiet lap(?: hinh tuong)?|nang luc(?: nhan vat)?|thong tin(?: nhan vat)?|dac diem|boi canh|tieu diem|gioi thieu|tom tat|danh gia|ket luan|nguon|tu khoa|nhan vat|cac moi quan he nhan(?: vat)?)$',re.I)
TYPES=[('technique',r'(?:Thần Công|Chân Kinh|Bảo Điển|Kiếm Pháp|Đao Pháp|Tâm Pháp|Bí Pháp|Công Pháp|Pháp Tắc|Dị Thuật|Thần Chưởng|Thần Thông|Thuật|Quyết)$'),('faction',r'(?:Tông|Môn|Giáo|Cung|Điện|Các|Viện|Bang|Hội|Gia Tộc|Thánh Địa|Vương Triều|Đế Quốc|Tộc)$'),('world',r'(?:Giới|Đại Lục|Tinh Vực|Vực|Thiên Vực|Hạ Giới|Thượng Giới|Tiên Giới|Ma Giới)$'),('item',r'(?:Kiếm|Đao|Thương|Đỉnh|Tháp|Ấn|Châu|Kính|Lô|Đan|Dược|Cổ|Pháp Bảo|Bảo Vật)$')]
TYPES=[(t,re.compile(x,re.I)) for t,x in TYPES]
RELS=[('MEMBER_OF',r'^(?:thuộc|gia nhập|đầu quân|bái nhập)$'),('HAS',r'^(?:có|sở hữu|nắm|nắm giữ|mang|dùng|sử dụng)$'),('IS_A',r'^(?:là|trở thành|được gọi)$'),('CONFLICT_WITH',r'^(?:đánh|giết|chiến|đấu|đối đầu|tấn công|địch)$'),('CULTIVATES',r'^(?:tu luyện|luyện|đột phá|đạt|tấn thăng|tiến giai)$'),('CREATES',r'^(?:tạo|sáng tạo|luyện chế|rèn|viết)$'),('KNOWS',r'^(?:biết|nhận ra|gặp|quen)$'),('LIKES',r'^(?:yêu|thích|ái mộ)$')]
RELS=[(t,re.compile(x,re.I)) for t,x in RELS]
TOK=re.compile(r'[0-9A-Za-zÀ-ỹĐđ]+')

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def unaccent(s): return ''.join(c for c in unicodedata.normalize('NFD',s) if unicodedata.category(c)!='Mn').replace('đ','d').replace('Đ','D')
def norm(s): return clean(re.sub(r'[^0-9a-zđ]+',' ',unaccent(clean(s)).lower()))
def toks(s): return [x.lower() for x in TOK.findall(s or '')]
def display(s):
    s=clean(s); out=[]; prev=''
    for c in s:
        if prev and prev.islower() and c.isupper(): out.append(' ')
        out.append(c); prev=c
    return clean(''.join(out))
def valid_entity(s):
    s=display(s).strip(' .,:;!?()[]{}\"\'“”‘’|-_'); n=norm(s)
    if len(s)<2 or len(s)>90 or s in BAD or s.lower() in STOP or not n or GEN.match(n): return False
    if re.search(r'(?:moi quan he|trai nghiem|hinh tuong|thiet lap|nang luc|thong tin)\s+(?:nhan vat)?$',n): return False
    a=next((c for c in s if c.isalpha()),'')
    if not a or not a.isupper(): return False
    if ' ' not in s and len(s)<=4 and not re.search(r'(?:Tông|Môn|Cung|Giới|Kiếm|Đao|Đan|Cổ)$',s,re.I): return False
    return True
def etype(s,ctx=''):
    for t,r in TYPES:
        if r.search(s): return t
    n=norm(ctx)
    if any(x in n for x in ('nhan vat','nam chinh','nu chinh')): return 'character'
    if 'tac gia' in n: return 'author'
    return 'unknown'
def rtype(p):
    for t,r in RELS:
        if r.search(clean(p)): return t
    return 'RELATED_BY'
def records(src):
    src=Path(src)
    if src.is_file():
        with zipfile.ZipFile(src) as z:
            for n in sorted(x for x in z.namelist() if x.endswith('.jsonl.gz')):
                with z.open(n) as raw,gzip.open(raw,'rt',encoding='utf-8') as f:
                    for line in f:
                        if line.strip(): yield json.loads(line)
    else:
        for p in sorted(src.glob('chunks/*.jsonl.gz')):
            with gzip.open(p,'rt',encoding='utf-8') as f:
                for line in f:
                    if line.strip(): yield json.loads(line)
def frames(r):
    for s in r.get('sections') or []:
        for p in s.get('paragraphs') or []:
            yield from (x for x in p.get('sentences') or [] if isinstance(x,dict))
def surface(f):
    w=[clean(str(e.get('dependent') or '')) for e in f.get('dependency_edges') or [] if isinstance(e,dict)]
    if any(w): return ' '.join(x for x in w if x)
    return clean(' '.join([*(map(str,f.get('subjects') or [])),str(f.get('predicate_root') or ''),*(map(str,f.get('objects') or []))]))
def best(phrase,lookup):
    p=norm(phrase)
    if p in lookup:return lookup[p]
    if len(p)>=5:
        c=[(len(k),v) for k,v in lookup.items() if p in k or k in p]
        if c:return max(c)[1]

def extract(r):
    title=re.sub(r'\s*-\s*vidian\.vn\s*$','',clean(r.get('title') or r.get('listing_title') or ''),flags=re.I)
    ents=collections.Counter(); ty=collections.defaultdict(collections.Counter); lex=collections.Counter(); pred=collections.Counter(); sub=collections.Counter(); obj=collections.Counter(); raw=[]
    for f in frames(r):
        sf=surface(f); fe=[]
        for e in f.get('entities') or []:
            name=display(str(e.get('name') if isinstance(e,dict) else e)); cnt=int(e.get('count',1)) if isinstance(e,dict) else 1
            if valid_entity(name): ents[name]+=max(1,cnt); ty[name][etype(name,sf)]+=max(1,cnt); fe.append(name)
        p=clean(str(f.get('predicate_root') or ''))
        if p:pred[p]+=1
        sub.update(clean(str(x)) for x in f.get('subjects') or [] if clean(str(x))); obj.update(clean(str(x)) for x in f.get('objects') or [] if clean(str(x)))
        for x in f.get('residual_lexicon') or []:
            if isinstance(x,dict):
                t=clean(str(x.get('term') or '')).lower()
                if len(t)>=2 and t not in STOP and not t.isdigit():lex[t]+=max(1,int(x.get('count') or 1))
        raw.append((f,fe))
    profile=None
    if ':' in title:
        left,right=map(display,title.split(':',1)); looks=any('nhan vat' in norm(x) for x in list(pred)+list(sub))
        if looks and valid_entity(left) and valid_entity(right) and len(right.split())<=7:
            ents[left]+=3; ents[right]+=4; ty[left]['work']+=20; ty[right]['character']+=20; profile=(right,left)
    for seg in re.split(r'[:|]',title):
        seg=display(seg)
        if 2<=len(seg)<=70 and len(seg.split())<=8 and valid_entity(seg): ents[seg]+=3
    canon={}
    for name,c in ents.most_common():
        n=norm(name)
        if n not in canon or (c,len(name))>(ents[canon[n]],len(canon[n])):canon[n]=name
    me=collections.Counter(); mt=collections.defaultdict(collections.Counter)
    for name,c in ents.items(): me[canon[norm(name)]]+=c; mt[canon[norm(name)]].update(ty[name])
    ents,ty=me,mt; lookup={norm(n):n for n in ents}
    rel=collections.Counter(); evid=collections.defaultdict(list)
    for f,fe in raw:
        p=clean(str(f.get('predicate_root') or '')); typ=rtype(p)
        ss=[best(x,lookup) for x in f.get('subjects') or []]; oo=[best(x,lookup) for x in f.get('objects') or []]
        pairs=[(a,b,.9) for a in dict.fromkeys(x for x in ss if x) for b in dict.fromkeys(x for x in oo if x) if a!=b]
        if not pairs:
            u=list(dict.fromkeys(x for x in fe if x in ents))
            if len(u)==2:pairs=[(u[0],u[1],.35)]
        for a,b,c in pairs:
            k=(a,typ,b,p); rel[k]+=1
            if len(evid[k])<5:evid[k].append((str(f.get('source_sentence_sha256') or ''),c))
    if profile:
        a,b=canon.get(norm(profile[0]),profile[0]),canon.get(norm(profile[1]),profile[1]); k=(a,'APPEARS_IN',b,'title_profile'); rel[k]+=1; evid[k].append(('TITLE',.97))
    top=[n for n,c in ents.most_common(16) if c>=2]
    for i,a in enumerate(top):
        for b in top[i+1:]: rel[(a,'CO_OCCURS',b,'')]+=min(ents[a],ents[b])
    concept=clean(' '.join([title,*[n for n,c in ents.most_common(80) for _ in range(min(3,max(1,int(math.log2(c+1)))))],*[t for t,c in lex.most_common(320) for _ in range(min(2,max(1,int(math.log2(c+1)))))],*[x for x,_ in pred.most_common(70)],*[x for x,_ in sub.most_common(70)],*[x for x,_ in obj.most_common(70)]]))
    return {'url':r['url'],'title':title,'concept':concept,'ents':ents,'types':ty,'rel':rel,'evid':evid,'sentences':int(r.get('sentence_count') or 0)}

def build(src,out,dim=160,features=60000):
    out=Path(out);out.mkdir(parents=True,exist_ok=True); data=[]; names=collections.defaultdict(collections.Counter); types=collections.defaultdict(collections.Counter); df=collections.Counter(); total=collections.Counter(); titles=set()
    for i,r in enumerate(records(src),1):
        x=extract(r);data.append(x);seen=set()
        for n,c in x['ents'].items():
            z=norm(n);names[z][n]+=c;types[z].update(x['types'][n]);total[z]+=c
            if z not in seen:df[z]+=1;seen.add(z)
        for s in re.split(r'[:|]',x['title']):
            if valid_entity(display(s)):titles.add(norm(display(s)))
        if i%500==0:print(json.dumps({'phase':'extract','articles':i}),flush=True)
    keep=set()
    for z,ns in names.items():
        n=max(ns,key=lambda x:(ns[x],len(x)));multi=' ' in n
        if z in titles or (multi and (df[z]>=2 or total[z]>=4)) or (not multi and total[z]>=8 and df[z]<=25):keep.add(z)
    db=out/'vidian_knowledge.sqlite'; db.unlink(missing_ok=True); con=sqlite3.connect(db)
    con.executescript('''CREATE TABLE articles(id INTEGER PRIMARY KEY,url TEXT UNIQUE,title TEXT,concept TEXT);CREATE VIRTUAL TABLE fts USING fts5(title,concept,content='articles',content_rowid='id',tokenize='unicode61 remove_diacritics 2');CREATE TRIGGER ai AFTER INSERT ON articles BEGIN INSERT INTO fts(rowid,title,concept) VALUES(new.id,new.title,new.concept);END;CREATE TABLE entities(id INTEGER PRIMARY KEY,name TEXT,norm TEXT UNIQUE,type TEXT,doc_freq INT,total_mentions INT);CREATE TABLE article_entities(article_id INT,entity_id INT,mentions INT,salience REAL,PRIMARY KEY(article_id,entity_id));CREATE TABLE relations(id INTEGER PRIMARY KEY,subject_id INT,type TEXT,object_id INT,raw TEXT,evidence_count INT,confidence REAL,UNIQUE(subject_id,type,object_id,raw));CREATE TABLE relation_evidence(relation_id INT,article_id INT,sentence_sha TEXT,confidence REAL,PRIMARY KEY(relation_id,article_id,sentence_sha));CREATE INDEX ae_e ON article_entities(entity_id,salience DESC);CREATE INDEX rs ON relations(subject_id,confidence DESC);CREATE INDEX ro ON relations(object_id,confidence DESC);''')
    eid={}
    for z in sorted(keep):
        n=max(names[z],key=lambda x:(names[z][x],len(x))); tt=types[z].most_common(); typ=tt[0][0] if tt else 'unknown'; eid[z]=con.execute('INSERT INTO entities(name,norm,type,doc_freq,total_mentions) VALUES(?,?,?,?,?)',(n,z,typ,df[z],total[z])).lastrowid
    aid={}; local={}
    for i,x in enumerate(data,1):
        a=con.execute('INSERT INTO articles(url,title,concept) VALUES(?,?,?)',(x['url'],x['title'],x['concept'])).lastrowid;aid[x['url']]=a;local[a]={}
        for n,c in x['ents'].items():
            z=norm(n)
            if z in eid:
                sal=float(c)*(1+math.log1p(len(data)/max(1,df[z])));con.execute('INSERT OR REPLACE INTO article_entities VALUES(?,?,?,?)',(a,eid[z],c,sal));local[a][n]=eid[z]
        if i%500==0:con.commit();print(json.dumps({'phase':'db','articles':i}),flush=True)
    agg=collections.Counter();cs=collections.Counter();ev=collections.defaultdict(list)
    for x in data:
        a=aid[x['url']]
        for (s,t,o,raw),n in x['rel'].items():
            se,oe=eid.get(norm(s)),eid.get(norm(o))
            if not se or not oe or se==oe:continue
            if t=='CO_OCCURS' and se>oe:se,oe=oe,se
            k=(se,t,oe,raw);agg[k]+=n;ee=x['evid'].get((s,t,o,raw),[]);cs[k]+=sum(c for _,c in ee) if ee else (.2*n if t=='CO_OCCURS' else .45*n)
            ev[k].extend((a,h,c) for h,c in ee[:5])
    for k,n in agg.items():
        se,t,oe,raw=k;conf=min(.99,cs[k]/max(1,n));rid=con.execute('INSERT INTO relations(subject_id,type,object_id,raw,evidence_count,confidence) VALUES(?,?,?,?,?,?)',(se,t,oe,raw,n,conf)).lastrowid
        for a,h,c in ev[k][:20]:con.execute('INSERT OR IGNORE INTO relation_evidence VALUES(?,?,?,?)',(rid,a,h,c))
    con.commit();con.execute('PRAGMA optimize')
    sem={'enabled':False}
    try:
        import joblib,numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import TruncatedSVD
        from sklearn.preprocessing import Normalizer
        v=TfidfVectorizer(strip_accents='unicode',ngram_range=(1,2),min_df=2,max_df=.92,max_features=features,sublinear_tf=True);X=v.fit_transform([x['concept'] for x in data]);d=min(dim,X.shape[0]-1,X.shape[1]-1);svd=TruncatedSVD(d,random_state=17,n_iter=7);nm=Normalizer(copy=False);D=nm.fit_transform(svd.fit_transform(X)).astype('float32');np.save(out/'vectors.npy',D,allow_pickle=False);joblib.dump({'v':v,'svd':svd,'nm':nm},out/'semantic.joblib',compress=3);sem={'enabled':True,'method':'TF-IDF + TruncatedSVD + cosine','dimensions':d,'features':X.shape[1]}
    except Exception as e:sem={'enabled':False,'error':f'{type(e).__name__}:{e}'}
    c={'articles':con.execute('select count(*) from articles').fetchone()[0],'entities':con.execute('select count(*) from entities').fetchone()[0],'article_entity_edges':con.execute('select count(*) from article_entities').fetchone()[0],'relations':con.execute('select count(*) from relations').fetchone()[0],'factual_relations':con.execute("select count(*) from relations where type<>'CO_OCCURS'").fetchone()[0],'fts_rows':con.execute('select count(*) from fts').fetchone()[0]};con.close()
    m={'schema':'vidian-knowledge-v1','source_prose_persisted':False,'retrieval':{'lexical':'SQLite FTS5 BM25','semantic':sem,'graph':'entity-document + typed relations + co-occurrence'},'counts':c,'limitations':['No raw source prose is persisted; evidence is URL + sentence SHA + parsed frame fields.','Parser-derived typed relations are evidence candidates, not ground truth.','CO_OCCURS is association only.']};(out/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(m,ensure_ascii=False,indent=2))

def scale(xs):
    if not xs:return {}
    lo=min(v for _,v in xs);hi=max(v for _,v in xs)
    return {i:(1 if hi==lo else (v-lo)/(hi-lo)) for i,v in xs}
def query(idx,q,limit=10,mode='hybrid'):
    idx=Path(idx);con=sqlite3.connect(idx/'vidian_knowledge.sqlite');con.row_factory=sqlite3.Row;score=collections.defaultdict(dict);ts=[t for t in toks(q) if len(t)>=2 and t not in STOP] or toks(q);fq=(' AND ' if len(ts)<=4 else ' OR ').join(f'\"{t}\"' for t in ts[:16])
    if fq:
        rr=con.execute('SELECT a.id,-bm25(fts,5.0,1.0) s FROM fts JOIN articles a ON a.id=fts.rowid WHERE fts MATCH ? ORDER BY bm25(fts,5.0,1.0) LIMIT 120',(fq,)).fetchall()
        for a,s in scale([(int(r['id']),float(r['s'])) for r in rr]).items():score[a]['lexical']=s
    nq=norm(q);er=con.execute("SELECT id FROM entities WHERE norm=? OR norm LIKE ? OR ? LIKE '%'||norm||'%' LIMIT 20",(nq,f'%{nq}%',nq)).fetchall() if nq else [];qe=[int(x[0]) for x in er]
    for e in qe:
        for r in con.execute('SELECT article_id FROM article_entities WHERE entity_id=? ORDER BY salience DESC LIMIT 80',(e,)):score[int(r[0])]['entity']=1
    if qe:
        m=','.join('?'*len(qe));sql=f'''SELECT CASE WHEN subject_id IN ({m}) THEN object_id ELSE subject_id END eid,MAX(confidence) c,SUM(evidence_count) n FROM relations WHERE subject_id IN ({m}) OR object_id IN ({m}) GROUP BY eid ORDER BY c DESC,n DESC LIMIT 30''';p=qe+qe+qe
        for r in con.execute(sql,p):
            for a in con.execute('SELECT article_id FROM article_entities WHERE entity_id=? ORDER BY salience DESC LIMIT 30',(int(r['eid']),)):score[int(a[0])]['graph']=max(score[int(a[0])].get('graph',0),.35*float(r['c']))
    if mode!='lexical' and (idx/'semantic.joblib').exists():
        import joblib,numpy as np
        m=joblib.load(idx/'semantic.joblib');D=np.load(idx/'vectors.npy',mmap_mode='r');v=m['nm'].transform(m['svd'].transform(m['v'].transform([q])))[0].astype('float32');ss=D@v;k=min(120,len(ss));ix=np.argpartition(ss,-k)[-k:];sem=scale([(int(i)+1,float(ss[i])) for i in ix if ss[i]>0])
        for a,s in sem.items():score[a]['semantic']=s
    w={'lexical':.42,'semantic':.4,'entity':.13,'graph':.05} if mode=='hybrid' else ({'lexical':1} if mode=='lexical' else {'semantic':.85,'entity':.1,'graph':.05});rank=sorted(((sum(w.get(k,0)*v for k,v in p.items()),a,p) for a,p in score.items()),reverse=True)[:limit];out=[]
    for s,a,p in rank:
        ar=con.execute('select title,url from articles where id=?',(a,)).fetchone();en=con.execute('select e.name,e.type,ae.mentions from article_entities ae join entities e on e.id=ae.entity_id where ae.article_id=? order by ae.salience desc limit 8',(a,)).fetchall();out.append({'score':round(s,6),'components':{k:round(v,5) for k,v in p.items()},'title':ar['title'],'url':ar['url'],'entities':[dict(x) for x in en]})
    print(json.dumps(out,ensure_ascii=False,indent=2));con.close()
def entity(idx,name,limit=20):
    con=sqlite3.connect(Path(idx)/'vidian_knowledge.sqlite');con.row_factory=sqlite3.Row;e=con.execute('select * from entities where norm=?',(norm(name),)).fetchone()
    if not e:print('[]');return
    i=int(e['id']);a=con.execute('select a.title,a.url,ae.mentions from article_entities ae join articles a on a.id=ae.article_id where ae.entity_id=? order by ae.salience desc limit ?',(i,limit)).fetchall();r=con.execute("select s.name subject,r.type,r.raw,o.name object,r.evidence_count,r.confidence from relations r join entities s on s.id=r.subject_id join entities o on o.id=r.object_id where (r.subject_id=? or r.object_id=?) and r.type<>'CO_OCCURS' order by r.confidence desc,r.evidence_count desc limit ?",(i,i,limit)).fetchall();print(json.dumps({'entity':dict(e),'articles':[dict(x) for x in a],'relations':[dict(x) for x in r]},ensure_ascii=False,indent=2));con.close()
def main():
    ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='cmd',required=True);b=sp.add_parser('build');b.add_argument('--corpus',required=True);b.add_argument('--out',required=True);b.add_argument('--semantic-dim',type=int,default=160);b.add_argument('--max-features',type=int,default=60000);q=sp.add_parser('query');q.add_argument('--index',required=True);q.add_argument('--q',required=True);q.add_argument('--limit',type=int,default=10);q.add_argument('--mode',choices=['hybrid','semantic','lexical'],default='hybrid');e=sp.add_parser('entity');e.add_argument('--index',required=True);e.add_argument('--name',required=True);e.add_argument('--limit',type=int,default=20);s=sp.add_parser('stats');s.add_argument('--index',required=True);a=ap.parse_args()
    if a.cmd=='build':build(a.corpus,a.out,a.semantic_dim,a.max_features)
    elif a.cmd=='query':query(a.index,a.q,a.limit,a.mode)
    elif a.cmd=='entity':entity(a.index,a.name,a.limit)
    else:print(Path(a.index,'manifest.json').read_text(encoding='utf-8'))
if __name__=='__main__':main()
