#!/usr/bin/env python3
import argparse, collections, hashlib, json, math, re, sqlite3, unicodedata
from pathlib import Path

CANONICAL_TOPICS = [
    'hook_opening','plot_structure_arc','outline','pacing_tension','cliffhanger',
    'character_design','motivation_conflict','villain_antagonist','progression_power','reward_payoff',
    'worldbuilding','system_design','foreshadow_payoff','mystery_reveal','stakes',
    'dialogue_voice','description_scene','combat_action','emotion_immersion','romance_relationship',
    'style_prose','editing_consistency','serialization_reader','theme_meaning',
    'title_blurb_packaging','genre_pattern','craft_general'
]

MOXING_MAP = {
    'hook_opening':'hook_opening','plot_structure':'plot_structure_arc','outline':'outline',
    'pacing_tension':'pacing_tension','character_design':'character_design','motivation_conflict':'motivation_conflict',
    'progression_power':'progression_power','reward_payoff':'reward_payoff','worldbuilding':'worldbuilding',
    'dialogue_voice':'dialogue_voice','description_scene':'description_scene','romance_relationship':'romance_relationship',
    'style_prose':'style_prose','market_retention':'serialization_reader','title_blurb_packaging':'title_blurb_packaging',
    'pitfalls_editing':'editing_consistency','genre_pattern':'genre_pattern','serialization':'serialization_reader',
    'craft_general':'craft_general'
}

TOPIC_TERMS = {
 'hook_opening':['mở đầu','mở truyện','chương đầu','hook','thu hút độc giả','开头','开篇','第一章','黄金三章','吸引读者'],
 'plot_structure_arc':['cốt truyện','kết cấu','cấu trúc','arc','mạch truyện','主线','情节','剧情','结构','故事线'],
 'outline':['đại cương','dàn ý','outline','大纲','细纲','纲要','框架'],
 'pacing_tension':['tiết tấu','nhịp truyện','nhịp độ','cao trào','căng thẳng','节奏','张力','高潮','拖沓','紧凑'],
 'cliffhanger':['cliffhanger','cuối chương','kết chương','treo','断章','章末'],
 'character_design':['nhân vật','tính cách','nhân thiết','main','nhân vật chính','人物','主角','人设','性格','角色'],
 'motivation_conflict':['động cơ','mục tiêu','xung đột','mâu thuẫn','目标','动机','欲望','冲突','矛盾'],
 'villain_antagonist':['phản diện','đối thủ','kẻ địch','boss','反派','对手','敌人'],
 'progression_power':['progression','thăng cấp','tu luyện','cảnh giới','đột phá','升级','修炼','境界','突破','实力'],
 'reward_payoff':['sảng','payoff','phần thưởng','tài nguyên','kỳ ngộ','thu hoạch','爽点','打脸','奖励','资源','机缘','收获'],
 'worldbuilding':['worldbuilding','thế giới quan','bối cảnh','thế lực','世界观','背景设定','势力','设定'],
 'system_design':['hệ thống','cơ chế','quy tắc sức mạnh','系统','机制','等级','规则'],
 'foreshadow_payoff':['foreshadow','phục bút','gieo','thu hồi','伏笔','铺垫','回收'],
 'mystery_reveal':['bí ẩn','huyền niệm','mystery','reveal','悬念','谜团','揭秘'],
 'stakes':['nguy cơ','hậu quả','cái giá','stakes','风险','后果','危机','代价'],
 'dialogue_voice':['thoại','đối thoại','lời thoại','dialogue','对话','对白','台词'],
 'description_scene':['miêu tả','mô tả','cảnh vật','scene','描写','场景','环境'],
 'combat_action':['chiến đấu','trận chiến','combat','战斗','打斗','动作戏'],
 'emotion_immersion':['cảm xúc','đồng cảm','nhập vai','emotion','情绪','共鸣','代入感'],
 'romance_relationship':['tình cảm','tình yêu','romance','quan hệ','感情','爱情','恋爱','关系'],
 'style_prose':['văn phong','câu văn','hành văn','prose','文笔','文风','叙述','语言'],
 'editing_consistency':['logic','nhất quán','sửa','biên tập','editing','逻辑','修改','自检','错误'],
 'serialization_reader':['độc giả','giữ chân','retention','đăng chương','追读','读者','留存','订阅','更新','连载'],
 'theme_meaning':['chủ đề','thông điệp','ý nghĩa','theme','主题','立意','意义'],
 'title_blurb_packaging':['tên truyện','giới thiệu','bìa','packaging','书名','简介','封面','包装'],
 'genre_pattern':['thể loại','tiên hiệp','huyền huyễn','đô thị','genre','仙侠','玄幻','都市','悬疑','科幻','历史'],
 'craft_general':['kỹ thuật viết','phương pháp viết','writing craft','写作技巧','写作方法','创作技巧']
}

QUERY_ALIASES = {
 'tiên hiệp':'仙侠 修炼 升级 progression tu luyện cảnh giới',
 'huyền huyễn':'玄幻 世界观 升级',
 'mở đầu':'开头 开篇 第一章 黄金三章 hook',
 'thu hút':'吸引 读者 追读 retention',
 'nhân vật chính':'主角 人设 性格 main',
 'main':'主角 人设 性格 nhân vật chính',
 'kỳ ngộ':'机缘 收获 奖励 tài nguyên payoff',
 'tài nguyên':'资源 收获 升级 progression',
 'sảng':'爽点 打脸 期待感 payoff',
 'progression':'升级 修炼 境界 thăng cấp tu luyện',
 'cao trào':'高潮 张力 节奏 pacing',
 'bí ẩn':'悬念 谜团 伏笔 mystery',
 'cliffhanger':'断章 章末 悬念 cuối chương',
 'đại cương':'大纲 细纲 框架 outline',
 'worldbuilding':'世界观 背景设定 势力 thế giới quan',
 'thoại':'对话 台词 对白 dialogue',
 'văn phong':'文笔 文风 叙述 prose',
 'độc giả':'读者 追读 留存 retention',
 'tên truyện':'书名 简介 封面 title blurb',
 'tránh lỗi':'错误 避坑 自检 editing',
}

ATOM_TERMS = {
 'opening':['mở đầu','mở truyện','chương đầu','thu hút','开头','开篇','第一章','黄金三章','吸引'],
 'goal':['mục tiêu','động cơ','mong muốn','目标','动机','欲望'],
 'conflict':['xung đột','mâu thuẫn','冲突','矛盾'],
 'character':['nhân vật','tính cách','main','人物','主角','人设','性格'],
 'pacing':['nhịp','tiết tấu','cao trào','张力','节奏','高潮'],
 'progression':['thăng cấp','tu luyện','cảnh giới','đột phá','升级','修炼','境界','突破'],
 'reward':['phần thưởng','tài nguyên','kỳ ngộ','thu hoạch','sảng','奖励','资源','机缘','收获','爽点'],
 'world':['thế giới quan','bối cảnh','thế lực','世界观','背景','势力','设定'],
 'foreshadow':['phục bút','gợi trước','gieo','伏笔','铺垫'],
 'mystery':['bí ẩn','huyền niệm','悬念','谜团','揭秘'],
 'dialogue':['thoại','đối thoại','对话','对白','台词'],
 'description':['miêu tả','mô tả','cảnh vật','描写','场景','环境'],
 'reader':['độc giả','giữ chân','retention','读者','追读','留存','订阅'],
 'outline':['đại cương','dàn ý','大纲','细纲','框架'],
 'style':['văn phong','câu văn','hành văn','文笔','文风','叙述','语言'],
 'editing':['logic','nhất quán','sửa','biên tập','逻辑','修改','自检','错误'],
 'romance':['tình cảm','tình yêu','感情','爱情','恋爱'],
 'cliffhanger':['cuối chương','kết chương','treo','断章','章末'],
 'stakes':['nguy cơ','hậu quả','cái giá','风险','后果','危机','代价'],
 'system':['hệ thống','cơ chế','quy tắc','系统','机制','等级','规则'],
 'combat':['chiến đấu','trận chiến','战斗','打斗'],
 'emotion':['cảm xúc','đồng cảm','nhập vai','情绪','共鸣','代入感'],
 'theme':['chủ đề','thông điệp','ý nghĩa','主题','立意','意义'],
 'packaging':['tên truyện','giới thiệu','bìa','书名','简介','封面'],
 'genre':['tiên hiệp','huyền huyễn','đô thị','仙侠','玄幻','都市','悬疑','科幻','历史'],
}

SOURCE_QUALITY={'vidian':0.84,'moxing':0.74}
DIRECTION={'dont':'negative','warning':'negative','do':'positive','technique':'technique','diagnostic':'technique','principle':'principle'}


def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def unaccent(s): return ''.join(c for c in unicodedata.normalize('NFD',s or '') if unicodedata.category(c)!='Mn')
def norm(s): return clean(re.sub(r'[^0-9a-z\u4e00-\u9fff]+',' ',unaccent((s or '').lower())))
def phrase_hit(text,phrase):
    if not phrase: return False
    if re.search(r'[\u4e00-\u9fff]',phrase): return phrase in text
    return f' {norm(phrase)} ' in f' {norm(text)} '

def canonical_moxing(topic,text):
    if topic=='foreshadow_mystery':
        if any(x in text for x in ['谜','揭秘','悬念']): return 'mystery_reveal'
        return 'foreshadow_payoff'
    return MOXING_MAP.get(topic,topic if topic in CANONICAL_TOPICS else 'craft_general')

def atoms(text):
    out=[]
    for a,terms in ATOM_TERMS.items():
        if any(phrase_hit(text,t) for t in terms): out.append(a)
    return out

def direction(kind): return DIRECTION.get(kind,'principle')

def simhash64(text):
    s=norm(text).replace(' ','_')
    if len(s)<3: return 0
    grams=[s[i:i+3] for i in range(len(s)-2)]
    vec=[0]*64
    for g in grams:
        h=int.from_bytes(hashlib.blake2b(g.encode('utf-8'),digest_size=8).digest(),'big')
        for i in range(64): vec[i]+=1 if (h>>i)&1 else -1
    out=0
    for i,v in enumerate(vec):
        if v>=0: out|=1<<i
    return out

def hamming(a,b): return (a^b).bit_count()

def expanded(q):
    low=q.lower(); extra=[]
    for k,v in QUERY_ALIASES.items():
        if k in low: extra.append(v)
    for topic,terms in TOPIC_TERMS.items():
        if any(phrase_hit(q,t) for t in terms): extra += terms[:6]
    return clean(q+' '+' '.join(extra))

def detect_topics(text,limit=8):
    scored=[]
    for topic,terms in TOPIC_TERMS.items():
        hit=[t for t in terms if phrase_hit(text,t)]
        if hit: scored.append((topic,len(hit),hit))
    return sorted(scored,key=lambda x:(-x[1],CANONICAL_TOPICS.index(x[0])))[:limit]

def read_vidian(index):
    db=Path(index)/'vidian_writing.sqlite'; con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    for r in con.execute('''SELECT p.id,p.topic,p.kind,p.confidence,p.rule_text,p.surface,p.sentence_sha,p.section,a.title,a.url FROM passages p JOIN articles a ON a.id=p.article_id'''):
        yield {'source':'vidian','source_id':int(r['id']),'source_topic':r['topic'],'topic':r['topic'],'kind':r['kind'],'confidence':float(r['confidence'] or 0.5),'text':clean(r['rule_text'] or r['surface']),'evidence_surface':clean(r['surface']),'evidence_id':r['sentence_sha'],'section':r['section'] or '','title':r['title'],'url':r['url'],'verbatim':False}
    con.close()

def read_moxing(index):
    db=Path(index)/'moxing_writing.sqlite'; con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    for r in con.execute('''SELECT p.id,p.topic,p.kind,p.confidence,p.text,p.sentence_sha,a.title,a.url FROM passages p JOIN articles a ON a.id=p.article_id'''):
        txt=clean(r['text']); topic=canonical_moxing(r['topic'],txt)
        yield {'source':'moxing','source_id':int(r['id']),'source_topic':r['topic'],'topic':topic,'kind':r['kind'],'confidence':float(r['confidence'] or 0.5),'text':txt,'evidence_surface':txt,'evidence_id':r['sentence_sha'],'section':'','title':r['title'],'url':r['url'],'verbatim':True}
    con.close()

def dedup_rows(rows):
    kept=[]; exact=set(); buckets=collections.defaultdict(list); dup=0
    for r in sorted(rows,key=lambda x:(x['source'],x['topic'],-x['confidence'],x['source_id'])):
        n=norm(r['text'])
        if len(n)<12: dup+=1; continue
        ek=(r['source'],r['topic'],n)
        if ek in exact: dup+=1; continue
        exact.add(ek)
        sh=simhash64(r['text']); b=(r['source'],r['topic'],sh>>48)
        near=None
        for j,oldsh in buckets[b][-40:]:
            if hamming(sh,oldsh)<=5:
                near=j; break
        if near is not None:
            dup+=1; continue
        r['simhash']=sh; r['atoms']=atoms(r['text']); r['direction']=direction(r['kind'])
        buckets[b].append((len(kept),sh)); kept.append(r)
    return kept,dup

def build(vidian,moxing,outdir,dims=96,max_features=50000):
    out=Path(outdir); out.mkdir(parents=True,exist_ok=True)
    raw=list(read_vidian(vidian))+list(read_moxing(moxing))
    raw_counts=collections.Counter(x['source'] for x in raw)
    rows,dup=dedup_rows(raw)
    clusters=collections.defaultdict(list)
    for i,r in enumerate(rows):
        if len(r['atoms'])>=2:
            key=(r['topic'],r['direction'],tuple(sorted(r['atoms'])[:3]))
            clusters[key].append(i)
    supported=0; cluster_count=0
    for key,idxs in clusters.items():
        src={rows[i]['source'] for i in idxs}
        if len(src)<2: continue
        cluster_count+=1
        bysrc=collections.Counter(rows[i]['source'] for i in idxs)
        for i in idxs:
            other=sum(v for s,v in bysrc.items() if s!=rows[i]['source'])
            rows[i]['cross_source_support']=min(12,other); rows[i]['support_key']='|'.join([key[0],key[1],','.join(key[2])]); supported+=1
    for r in rows:
        r.setdefault('cross_source_support',0); r.setdefault('support_key','')

    db=out/'writing_brain.sqlite'; db.unlink(missing_ok=True); con=sqlite3.connect(db)
    con.executescript('''
      CREATE TABLE passages(id INTEGER PRIMARY KEY, source TEXT, source_id INT, source_topic TEXT, topic TEXT, kind TEXT, direction TEXT, confidence REAL, source_quality REAL, cross_source_support INT, support_key TEXT, text TEXT, evidence_surface TEXT, evidence_id TEXT, section TEXT, title TEXT, url TEXT, verbatim INT, atoms_json TEXT, simhash TEXT);
      CREATE VIRTUAL TABLE passage_fts USING fts5(title,topic,kind,text,content='',tokenize='unicode61 remove_diacritics 2');
      CREATE INDEX idx_topic ON passages(topic,confidence DESC);
      CREATE INDEX idx_source ON passages(source,topic);
      CREATE INDEX idx_support ON passages(cross_source_support DESC,topic);
    ''')
    for r in rows:
        pid=con.execute('''INSERT INTO passages(source,source_id,source_topic,topic,kind,direction,confidence,source_quality,cross_source_support,support_key,text,evidence_surface,evidence_id,section,title,url,verbatim,atoms_json,simhash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
            r['source'],r['source_id'],r['source_topic'],r['topic'],r['kind'],r['direction'],r['confidence'],SOURCE_QUALITY[r['source']],r['cross_source_support'],r['support_key'],r['text'],r['evidence_surface'],r['evidence_id'],r['section'],r['title'],r['url'],1 if r['verbatim'] else 0,json.dumps(r['atoms'],ensure_ascii=False),str(r['simhash'])
        )).lastrowid
        r['id']=pid
        con.execute('INSERT INTO passage_fts(rowid,title,topic,kind,text) VALUES(?,?,?,?,?)',(pid,r['title'],r['topic'],r['kind'],r['text']))
    con.commit(); con.execute('PRAGMA optimize')

    semantic={}
    try:
        import joblib, numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import TruncatedSVD
        from sklearn.preprocessing import Normalizer
        for source in ('vidian','moxing'):
            subset=[r for r in rows if r['source']==source]
            docs=[clean(' '.join([r['topic'],r['kind'],r['title'],r['text']])) for r in subset]
            if source=='vidian':
                v=TfidfVectorizer(strip_accents='unicode',ngram_range=(1,2),min_df=2,max_df=.97,max_features=max_features,sublinear_tf=True)
            else:
                v=TfidfVectorizer(analyzer='char',ngram_range=(2,4),min_df=2,max_df=.98,max_features=max_features,sublinear_tf=True)
            X=v.fit_transform(docs); d=min(dims,X.shape[0]-1,X.shape[1]-1)
            svd=TruncatedSVD(d,random_state=17,n_iter=7); nm=Normalizer(copy=False)
            D=nm.fit_transform(svd.fit_transform(X)).astype('float32')
            np.save(out/f'{source}_vectors.npy',D,allow_pickle=False)
            np.save(out/f'{source}_ids.npy',np.array([r['id'] for r in subset],dtype='int64'),allow_pickle=False)
            joblib.dump({'vectorizer':v,'svd':svd,'normalizer':nm},out/f'{source}_semantic.joblib',compress=3)
            semantic[source]={'enabled':True,'method':('word TF-IDF(1,2)+SVD+cosine' if source=='vidian' else 'char TF-IDF(2,4)+SVD+cosine'),'dimensions':d,'features':X.shape[1],'vectors':len(subset)}
    except Exception as e:
        semantic={'error':f'{type(e).__name__}:{e}'}

    retained=collections.Counter(x['source'] for x in rows)
    topic_counts=[{'topic':r[0],'passages':r[1],'vidian':r[2],'moxing':r[3],'supported':r[4]} for r in con.execute("SELECT topic,count(*),sum(source='vidian'),sum(source='moxing'),sum(cross_source_support>0) FROM passages GROUP BY topic ORDER BY count(*) DESC")]
    con.close()
    manifest={
      'schema':'webnovel-writing-brain-v1','taxonomy_version':'fusion-27-topics-v1','sources':{
        'vidian':{'input':'vidian-writing-v1-2026-08-17','raw_passages':raw_counts['vidian'],'retained':retained['vidian'],'evidence':'parser-reconstructed; not verbatim source prose'},
        'moxing':{'input':'moxing-writing-v1-2026-08-17 quality v1.1','raw_passages':raw_counts['moxing'],'retained':retained['moxing'],'evidence':'capped source excerpts; source site may include reposted/member-uploaded material'}},
      'counts':{'raw_passages':len(raw),'retained_passages':len(rows),'deduplicated_within_source':dup,'cross_source_supported_passages':supported,'cross_source_support_clusters':cluster_count,'topics':len({r['topic'] for r in rows})},
      'topic_counts':topic_counts,'retrieval':{'lexical':'unified SQLite FTS5 BM25','semantic':semantic,'fusion':'normalized lexical + per-language latent semantic + confidence/source-quality + conservative cross-source-theme boost'},
      'consensus_policy':'Cross-source support is thematic evidence only: same canonical topic, same directive direction, and >=2 bilingual concept atoms. It is not proof that two passages state the same rule.',
      'dedup_policy':'Exact/SimHash near-dedup is performed only within the same source and canonical topic. Cross-language passages are never collapsed as duplicates.',
      'interfaces':['query','direct','review','checklist','stats'],
      'limitations':['No multilingual LLM embeddings are used. Semantic models are separate latent TF-IDF/SVD spaces bridged by bilingual query expansion.','Vidian evidence is reconstructed parser-token surface and must not be represented as verbatim quotation.','Moxing excerpts should be paraphrased in generated answers when possible; open the source URL for exact-context verification.']}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


def _scale(pairs):
    if not pairs:return {}
    vals=[v for _,v in pairs]; lo=min(vals); hi=max(vals)
    return {i:(1.0 if hi==lo else (v-lo)/(hi-lo)) for i,v in pairs}

def _fts_terms(q):
    ex=expanded(q)
    zh=re.findall(r'[\u4e00-\u9fff]{2,}',ex)
    lat=[x for x in re.findall(r'[0-9A-Za-zÀ-ỹĐđ]+',ex) if len(x)>=2]
    terms=[]; seen=set()
    for x in lat+zh:
        y=x.strip()
        if y and y not in seen: seen.add(y);terms.append(y)
    return ex,terms[:50]

def search(index,q,limit=12,topic=None,source='all',consensus_only=False):
    idx=Path(index); con=sqlite3.connect(idx/'writing_brain.sqlite'); con.row_factory=sqlite3.Row
    scores=collections.defaultdict(dict); ex,terms=_fts_terms(q)
    filt=[]; fparams=[]
    if topic: filt.append('p.topic=?'); fparams.append(topic)
    if source!='all': filt.append('p.source=?'); fparams.append(source)
    if consensus_only: filt.append('p.cross_source_support>0')
    where=(' AND '+' AND '.join(filt)) if filt else ''
    if terms:
        fts=' OR '.join('"'+t.replace('"','')+'"' for t in terms)
        try:
            rows=con.execute(f'''SELECT p.id,-bm25(passage_fts,2.0,1.2,0.8,2.6) s FROM passage_fts JOIN passages p ON p.id=passage_fts.rowid WHERE passage_fts MATCH ? {where} ORDER BY bm25(passage_fts,2.0,1.2,0.8,2.6) LIMIT 500''',[fts]+fparams).fetchall()
            for pid,s in _scale([(int(r['id']),float(r['s'])) for r in rows]).items(): scores[pid]['lexical']=s
        except sqlite3.OperationalError:
            pass
    try:
        import joblib, numpy as np
        for src in ('vidian','moxing'):
            if source!='all' and source!=src: continue
            modelp=idx/f'{src}_semantic.joblib'; vecp=idx/f'{src}_vectors.npy'; idp=idx/f'{src}_ids.npy'
            if not modelp.exists(): continue
            m=joblib.load(modelp); D=np.load(vecp,mmap_mode='r'); ids=np.load(idp,mmap_mode='r')
            v=m['normalizer'].transform(m['svd'].transform(m['vectorizer'].transform([ex])))[0].astype('float32')
            sims=D@v; k=min(350,len(sims))
            if k<=0: continue
            ix=np.argpartition(sims,-k)[-k:]
            pairs=[]
            for j in ix:
                if sims[j]<=0: continue
                pid=int(ids[j])
                if topic or consensus_only:
                    r=con.execute('SELECT topic,cross_source_support FROM passages WHERE id=?',(pid,)).fetchone()
                    if topic and r['topic']!=topic: continue
                    if consensus_only and not r['cross_source_support']: continue
                pairs.append((pid,float(sims[j])))
            for pid,s in _scale(pairs).items(): scores[pid]['semantic']=s
    except Exception:
        pass
    ranked=[]
    for pid,c in scores.items():
        r=con.execute('SELECT confidence,source_quality,cross_source_support FROM passages WHERE id=?',(pid,)).fetchone()
        base=.47*c.get('lexical',0)+.43*c.get('semantic',0)
        base+=.055*float(r['confidence'])+.025*float(r['source_quality'])+min(.06,.008*int(r['cross_source_support']))
        ranked.append((base,pid,c))
    ranked.sort(reverse=True)
    out=[]; seen_urls=collections.Counter(); seen_sim=set(); source_counts=collections.Counter()
    for base,pid,c in ranked:
        r=con.execute('SELECT * FROM passages WHERE id=?',(pid,)).fetchone(); sim=(r['source'],r['simhash'])
        if sim in seen_sim: continue
        if seen_urls[r['url']]>=2: continue
        diversity=0.018 if source_counts[r['source']]==0 else 0
        item={'score':round(base+diversity,6),'components':{k:round(v,5) for k,v in c.items()},'passage_id':pid,'source':r['source'],'source_passage_id':r['source_id'],'topic':r['topic'],'source_topic':r['source_topic'],'kind':r['kind'],'confidence':r['confidence'],'cross_source_support':r['cross_source_support'],'support_key':r['support_key'],'text':r['text'],'evidence_surface':r['evidence_surface'],'evidence_id':r['evidence_id'],'title':r['title'],'url':r['url'],'verbatim_source_excerpt':bool(r['verbatim']),'atoms':json.loads(r['atoms_json'] or '[]')}
        out.append(item); seen_sim.add(sim); seen_urls[r['url']]+=1; source_counts[r['source']]+=1
        if len(out)>=limit: break
    con.close(); return out

def evidence_for_topic(index,text,topic,limit,used):
    terms=' '.join(TOPIC_TERMS[topic][:8]); pool=search(index,text+' '+terms,max(limit*5,30),topic)
    keep=[]
    pool.sort(key=lambda x:(x['cross_source_support']>0,x['score']),reverse=True)
    for preferred in ('vidian','moxing','any'):
        for x in pool:
            if x['passage_id'] in used: continue
            if preferred!='any' and x['source']!=preferred: continue
            used.add(x['passage_id']); keep.append(x)
            if len(keep)>=limit: return keep
    return keep

def direct(index,brief,limit=40):
    scored=detect_topics(brief,10); selected=[x[0] for x in scored[:8]]
    core=['hook_opening','plot_structure_arc','pacing_tension','character_design','motivation_conflict','progression_power','worldbuilding','reward_payoff']
    for t in core:
        if len(selected)>=8: break
        if t not in selected:selected.append(t)
    per=max(4,math.ceil(limit/max(1,len(selected)))); used=set(); sections=[]
    for t in selected:
        hits=evidence_for_topic(index,brief,t,per,used)
        if hits: sections.append({'topic':t,'must_do':[x for x in hits if x['kind'] in ('do','principle')],'avoid':[x for x in hits if x['kind'] in ('dont','warning')],'techniques':[x for x in hits if x['kind'] in ('technique','diagnostic')],'all':hits,'sources':sorted({x['source'] for x in hits}),'consensus_items':sum(x['cross_source_support']>0 for x in hits)})
    return {'schema':'webnovel-writing-directive-v1','brief_sha256':hashlib.sha256(brief.encode()).hexdigest(),'detected_topics':[{'topic':t,'score':s,'matches':m} for t,s,m in scored],'directive_topics':[s['topic'] for s in sections],'sections':sections,'protocol':['Use cross-source support as corroborating craft signal, not proof of an identical rule.','Prefer paraphrase over copying source excerpts.','For Vidian exact wording, open the source URL because stored evidence is reconstructed.','After drafting, run review and targeted checklist.']}

def review(index,text,limit=28):
    scored=detect_topics(text,8); selected=[x[0] for x in scored[:6]] or ['plot_structure_arc','pacing_tension','character_design','style_prose']
    per=max(4,math.ceil(limit/max(1,len(selected)))); used=set(); buckets=[]
    for t in selected:
        hits=evidence_for_topic(index,text,t,per,used)
        if hits:buckets.append({'topic':t,'hits':hits,'sources':sorted({x['source'] for x in hits}),'consensus_items':sum(x['cross_source_support']>0 for x in hits)})
    return {'schema':'webnovel-writing-review-v1','draft_sha256':hashlib.sha256(text.encode()).hexdigest(),'detected_topics':[{'topic':t,'score':s,'matches':m} for t,s,m in scored],'review_dimensions':[b['topic'] for b in buckets],'evidence_buckets':buckets}

def checklist(index,topic,limit=20):
    hits=search(index,' '.join(TOPIC_TERMS[topic]),limit*4,topic)
    hits.sort(key=lambda x:(x['cross_source_support']>0,x['score']),reverse=True)
    keep=[]; src=collections.Counter()
    for x in hits:
        if len(keep)>=limit:break
        if src[x['source']] > max(3,len(keep)*.75): continue
        keep.append(x);src[x['source']]+=1
    return {'schema':'webnovel-writing-checklist-v1','topic':topic,'items':keep,'sources':dict(src),'consensus_items':sum(x['cross_source_support']>0 for x in keep)}

def dump(x,path=None):
    raw=json.dumps(x,ensure_ascii=False,indent=2);print(raw)
    if path:Path(path).write_text(raw,encoding='utf-8')

def main():
    ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='cmd',required=True)
    b=sp.add_parser('build');b.add_argument('--vidian',required=True);b.add_argument('--moxing',required=True);b.add_argument('--out',required=True);b.add_argument('--dims',type=int,default=96);b.add_argument('--max-features',type=int,default=50000)
    q=sp.add_parser('query');q.add_argument('--index',required=True);q.add_argument('--q',required=True);q.add_argument('--limit',type=int,default=12);q.add_argument('--topic',choices=CANONICAL_TOPICS);q.add_argument('--source',choices=['all','vidian','moxing'],default='all');q.add_argument('--consensus-only',action='store_true');q.add_argument('--json-out')
    d=sp.add_parser('direct');d.add_argument('--index',required=True);g=d.add_mutually_exclusive_group(required=True);g.add_argument('--brief');g.add_argument('--file');d.add_argument('--limit',type=int,default=40);d.add_argument('--json-out')
    r=sp.add_parser('review');r.add_argument('--index',required=True);g=r.add_mutually_exclusive_group(required=True);g.add_argument('--text');g.add_argument('--file');r.add_argument('--limit',type=int,default=28);r.add_argument('--json-out')
    c=sp.add_parser('checklist');c.add_argument('--index',required=True);c.add_argument('--topic',required=True,choices=CANONICAL_TOPICS);c.add_argument('--limit',type=int,default=20);c.add_argument('--json-out')
    s=sp.add_parser('stats');s.add_argument('--index',required=True)
    a=ap.parse_args()
    if a.cmd=='build':build(a.vidian,a.moxing,a.out,a.dims,a.max_features)
    elif a.cmd=='query':dump({'schema':'webnovel-writing-query-v1','query':a.q,'expanded_query':expanded(a.q),'topic_filter':a.topic,'source_filter':a.source,'consensus_only':a.consensus_only,'hits':search(a.index,a.q,a.limit,a.topic,a.source,a.consensus_only)},a.json_out)
    elif a.cmd=='direct':
        text=a.brief if a.brief is not None else Path(a.file).read_text(encoding='utf-8');dump(direct(a.index,text,a.limit),a.json_out)
    elif a.cmd=='review':
        text=a.text if a.text is not None else Path(a.file).read_text(encoding='utf-8');dump(review(a.index,text,a.limit),a.json_out)
    elif a.cmd=='checklist':dump(checklist(a.index,a.topic,a.limit),a.json_out)
    else:print((Path(a.index)/'manifest.json').read_text(encoding='utf-8'))
if __name__=='__main__':main()
