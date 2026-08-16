#!/usr/bin/env python3
import argparse,collections,hashlib,json,math,re,shutil,sqlite3
from pathlib import Path

TOPIC_VI={'character_design':'xây dựng nhân vật','serialization_reader':'giữ chân độc giả & đăng dài kỳ','craft_general':'kỹ thuật sáng tác tổng quát','plot_structure_arc':'cốt truyện & cấu trúc arc','description_scene':'miêu tả & dựng cảnh','reward_payoff':'phần thưởng & payoff','emotion_immersion':'cảm xúc & nhập vai','editing_consistency':'biên tập & nhất quán','motivation_conflict':'động cơ & xung đột','hook_opening':'mở đầu & hook','pacing_tension':'tiết tấu & căng thẳng','style_prose':'văn phong','progression_power':'progression & hệ sức mạnh','genre_pattern':'mô thức thể loại','worldbuilding':'xây dựng thế giới','romance_relationship':'tình cảm & quan hệ','dialogue_voice':'đối thoại & giọng nhân vật','outline':'đại cương','system_design':'thiết kế hệ thống','title_blurb_packaging':'tiêu đề & giới thiệu truyện','villain_antagonist':'phản diện & đối thủ','theme_meaning':'chủ đề & ý nghĩa','mystery_reveal':'bí ẩn & tiết lộ','combat_action':'chiến đấu & hành động','foreshadow_payoff':'phục bút & thu hồi','stakes':'nguy cơ & cái giá','cliffhanger':'cliffhanger & kết chương'}
KIND_VI={'do':'nên làm','dont':'cần tránh','warning':'cảnh báo','technique':'kỹ thuật','diagnostic':'chẩn đoán','principle':'nguyên tắc','example':'ví dụ'}
STOP=set('và là của có cho trong một những các được với này đó khi thì đã đang sẽ nhưng mà hay về từ đến ra vào ở trên dưới theo như nên cũng rất không chỉ lại còn hơn sau trước nếu do bởi vì để tại người thứ nào nhiều ít qua làm bị đi thấy nói vẫn thể phải thật tôi bạn chúng ta hắn cô nó họ đây đó gì đâu sao'.split())
TOK=re.compile(r'[0-9A-Za-zÀ-ỹĐđ]+')

def clean(s):return re.sub(r'\s+',' ',s or '').strip()
def sha(s):return hashlib.sha256((s or '').encode()).hexdigest()
def toks(s):return [x.lower() for x in TOK.findall(s or '') if len(x)>1 and x.lower() not in STOP]
def load_jsonl(path):return [json.loads(x) for x in open(path,encoding='utf-8') if x.strip()]
def _cols(con,table):return {r[1] for r in con.execute(f'pragma table_info({table})')}

def build(source,translations,titles,out,dims=128,max_features=80000):
    src=Path(source); dst=Path(out);dst.mkdir(parents=True,exist_ok=True)
    db=dst/'writing_brain_vi.sqlite';shutil.copy2(src/'writing_brain.sqlite',db)
    con=sqlite3.connect(db);con.row_factory=sqlite3.Row
    cols=_cols(con,'passages')
    for name,typ in [('text_vi','TEXT'),('text_zh','TEXT'),('title_vi','TEXT'),('title_zh','TEXT'),('concepts_vi','TEXT'),('translation_model','TEXT'),('translation_revision','TEXT')]:
      if name not in cols:con.execute(f'alter table passages add column {name} {typ}')
    trans={int(x['passage_id']):x for x in load_jsonl(translations)}
    title_map={x['title_zh']:x for x in load_jsonl(titles)}
    rows=con.execute('select id,source,text,evidence_id,title from passages').fetchall();mox=vid=0
    for r in rows:
      if r['source']=='moxing':
        x=trans.get(int(r['id']));assert x and x['evidence_id']==r['evidence_id'],r['id'];assert x['text_zh_sha256']==sha(r['text']),r['id']
        ti=title_map.get(r['title']);assert ti and ti['title_zh_sha256']==sha(r['title']),r['title']
        con.execute('update passages set text_vi=?,text_zh=?,title_vi=?,title_zh=?,concepts_vi=?,translation_model=?,translation_revision=? where id=?',(x['text_vi'],r['text'],ti['title_vi'],r['title'],' '.join(x.get('concepts_vi') or []),x['model_id'],x['model_revision'],r['id']));mox+=1
      else:
        con.execute("update passages set text_vi=text,text_zh='',title_vi=title,title_zh='',concepts_vi='',translation_model='source-vietnamese',translation_revision='' where id=?",(r['id'],));vid+=1
    assert mox==9538 and vid==11672,(mox,vid)
    con.execute('drop table if exists passages_vi_fts')
    con.execute("create virtual table passages_vi_fts using fts5(title_vi,topic_vi,kind_vi,text_vi,concepts_vi,content='',tokenize='unicode61 remove_diacritics 2')")
    docs=[];ids=[]
    for r in con.execute('select id,topic,kind,title_vi,text_vi,concepts_vi from passages order by id'):
      tv=TOPIC_VI.get(r['topic'],r['topic']);kv=KIND_VI.get(r['kind'],r['kind']);con.execute('insert into passages_vi_fts(rowid,title_vi,topic_vi,kind_vi,text_vi,concepts_vi) values(?,?,?,?,?,?)',(r['id'],r['title_vi'],tv,kv,r['text_vi'],r['concepts_vi'] or ''));docs.append(clean(' '.join([r['title_vi'] or '',tv,kv,r['text_vi'] or '',r['concepts_vi'] or ''])));ids.append(int(r['id']))
    con.commit();con.execute('pragma optimize');con.close()
    import joblib,numpy as np
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import Normalizer
    vec=TfidfVectorizer(strip_accents='unicode',ngram_range=(1,2),min_df=2,max_df=.96,max_features=max_features,sublinear_tf=True);X=vec.fit_transform(docs);d=min(dims,X.shape[0]-1,X.shape[1]-1);svd=TruncatedSVD(d,random_state=17,n_iter=7);nm=Normalizer(copy=False);D=nm.fit_transform(svd.fit_transform(X)).astype('float32')
    np.save(dst/'vi_vectors.npy',D,allow_pickle=False);np.save(dst/'vi_ids.npy',np.array(ids,dtype='int64'),allow_pickle=False);joblib.dump({'v':vec,'svd':svd,'nm':nm},dst/'vi_semantic.joblib',compress=3)
    source_manifest=json.loads((src/'manifest.json').read_text(encoding='utf-8'));tm=json.loads((Path(translations).parent/'manifest.json').read_text(encoding='utf-8')) if (Path(translations).parent/'manifest.json').exists() else {}
    manifest={'schema':'webnovel-writing-brain-vi-v1','language_mode':'vi-first','counts':{'passages':len(ids),'vidian_native_vi':vid,'moxing_machine_translated_vi':mox,'moxing_translation_coverage':round(mox/9538,6),'moxing_title_translation_count':len(title_map)},'translation':{'model_id':tm.get('model_id','Helsinki-NLP/opus-mt-zh-vi'),'model_revision':tm.get('model_revision','e048b2d21aebc6da81d050a4bac4e5b5178bba58'),'policy':'Vietnamese machine translation is the display/retrieval layer; Chinese remains canonical provenance for Moxing.'},'retrieval':{'lexical':'Vietnamese-first SQLite FTS5','semantic':{'method':'single Vietnamese TF-IDF(1,2)+SVD+cosine','dimensions':d,'features':X.shape[1],'vectors':len(ids)}},'source_brain':source_manifest.get('schema'),'topics':TOPIC_VI,'interfaces':['query','direct','review','checklist','stats'],'limitations':['Moxing Vietnamese is machine translation and may contain terminology errors.','Use source_text_zh/source_title_zh and URL when exact Chinese meaning matters.','Semantic retrieval is latent TF-IDF/SVD, not an LLM embedding model.']}
    (dst/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(manifest,ensure_ascii=False,indent=2))

def _scale(pairs):
    if not pairs:return {}
    vals=[v for _,v in pairs];lo,hi=min(vals),max(vals);return {i:(1 if hi==lo else (v-lo)/(hi-lo)) for i,v in pairs}

def search(index,q,limit=20,topic=None,source=None):
    idx=Path(index);con=sqlite3.connect(idx/'writing_brain_vi.sqlite');con.row_factory=sqlite3.Row;score=collections.defaultdict(dict);terms=toks(q);fq=' OR '.join(f'"{x}"' for x in terms[:24]);filters=[];params=[]
    if topic:filters.append('p.topic=?');params.append(topic)
    if source:filters.append('p.source=?');params.append(source)
    filt=(' AND '+' AND '.join(filters)) if filters else ''
    if fq:
      rows=con.execute(f'''select p.id,-bm25(passages_vi_fts,2.0,1.0,.8,1.3,.7) s from passages_vi_fts join passages p on p.id=passages_vi_fts.rowid where passages_vi_fts match ? {filt} order by bm25(passages_vi_fts,2.0,1.0,.8,1.3,.7) limit 300''',[fq]+params).fetchall()
      for i,s in _scale([(int(r['id']),float(r['s'])) for r in rows]).items():score[i]['lexical']=s
    import joblib,numpy as np
    m=joblib.load(idx/'vi_semantic.joblib');D=np.load(idx/'vi_vectors.npy',mmap_mode='r');ids=np.load(idx/'vi_ids.npy',mmap_mode='r');v=m['nm'].transform(m['svd'].transform(m['v'].transform([q])))[0].astype('float32');sims=D@v;k=min(500,len(sims));ix=np.argpartition(sims,-k)[-k:];pairs=[]
    for j in ix:
      if sims[j]<=0:continue
      pid=int(ids[j]);r=con.execute('select topic,source from passages where id=?',(pid,)).fetchone()
      if topic and r['topic']!=topic:continue
      if source and r['source']!=source:continue
      pairs.append((pid,float(sims[j])))
    for i,s in _scale(pairs).items():score[i]['semantic']=s
    ranked=[]
    for pid,c in score.items():
      r=con.execute('select * from passages where id=?',(pid,)).fetchone();base=.45*c.get('lexical',0)+.55*c.get('semantic',0);base+=.04*float(r['confidence'] or 0)+.03*float(r['source_quality'] or 0)+(.04 if int(r['cross_source_support'] or 0)>0 else 0);ranked.append((base,pid,c))
    ranked.sort(reverse=True);out=[]
    for s,pid,c in ranked[:limit]:
      r=con.execute('select * from passages where id=?',(pid,)).fetchone();out.append({'score':round(s,6),'passage_id':pid,'source':r['source'],'topic':r['topic'],'topic_vi':TOPIC_VI.get(r['topic'],r['topic']),'kind':r['kind'],'kind_vi':KIND_VI.get(r['kind'],r['kind']),'confidence':r['confidence'],'cross_source_support':r['cross_source_support'],'text':r['text_vi'],'title':r['title_vi'],'url':r['url'],'evidence_id':r['evidence_id'],'provenance':{'source_text_zh':r['text_zh'] if r['source']=='moxing' else '','source_title_zh':r['title_zh'] if r['source']=='moxing' else '','source_language':'zh' if r['source']=='moxing' else 'vi'}})
    con.close();return out

def balanced(pool,limit,used=None):
    used=used if used is not None else set();pool=[x for x in pool if x['passage_id'] not in used];keep=[];counts=collections.Counter();pool.sort(key=lambda x:(x.get('cross_source_support',0)>0,x['score'],x['confidence'] or 0),reverse=True)
    for src in ('vidian','moxing'):
      x=next((z for z in pool if z['source']==src and z['passage_id'] not in used),None)
      if x:keep.append(x);used.add(x['passage_id']);counts[src]+=1
    cap=max(2,math.ceil(limit*.65))
    for x in pool:
      if len(keep)>=limit:break
      if x['passage_id'] in used or counts[x['source']]>=cap:continue
      keep.append(x);used.add(x['passage_id']);counts[x['source']]+=1
    for x in pool:
      if len(keep)>=limit:break
      if x['passage_id'] in used:continue
      keep.append(x);used.add(x['passage_id']);counts[x['source']]+=1
    return keep

def detect_topics(text):
    low=text.lower();alias={'nhân vật':'character_design','main':'character_design','cốt truyện':'plot_structure_arc','arc':'plot_structure_arc','mở đầu':'hook_opening','hook':'hook_opening','tiết tấu':'pacing_tension','cao trào':'pacing_tension','tu luyện':'progression_power','cảnh giới':'progression_power','thăng cấp':'progression_power','tài nguyên':'reward_payoff','cơ duyên':'reward_payoff','phần thưởng':'reward_payoff','sảng':'reward_payoff','thế giới':'worldbuilding','tông môn':'worldbuilding','đối thoại':'dialogue_voice','phục bút':'foreshadow_payoff','bí ẩn':'mystery_reveal','phản diện':'villain_antagonist','đại cương':'outline','tình cảm':'romance_relationship','văn phong':'style_prose','chiến đấu':'combat_action','cliffhanger':'cliffhanger'};sc=collections.Counter()
    for k,t in alias.items():
      if k in low:sc[t]+=1
    return [t for t,_ in sc.most_common(8)]

def evidence_topic(index,text,topic,limit,used):
    pool=[]
    for src in ('vidian','moxing'):pool+=search(index,text+' '+TOPIC_VI.get(topic,''),max(30,limit*8),topic,src)
    return balanced(pool,limit,used)

def direct(index,brief,limit=40):
    selected=detect_topics(brief);core=['hook_opening','plot_structure_arc','pacing_tension','character_design','motivation_conflict','progression_power','worldbuilding','reward_payoff']
    for t in core:
      if len(selected)>=8:break
      if t not in selected:selected.append(t)
    per=max(4,math.ceil(limit/max(1,len(selected))));used=set();sections=[]
    for t in selected:
      keep=evidence_topic(index,brief,t,per,used)
      if keep:sections.append({'topic':t,'topic_vi':TOPIC_VI.get(t,t),'sources':sorted(set(x['source'] for x in keep)),'must_do':[x for x in keep if x['kind'] in {'do','principle'}],'avoid':[x for x in keep if x['kind'] in {'dont','warning'}],'techniques':[x for x in keep if x['kind'] in {'technique','diagnostic'}],'all':keep})
    return {'schema':'webnovel-writing-directive-vi-v1','language':'vi','brief_sha256':sha(brief),'sections':sections}

def review(index,text,limit=28):
    selected=detect_topics(text)[:6] or ['plot_structure_arc','pacing_tension','character_design','style_prose'];per=max(3,math.ceil(limit/len(selected)));used=set();b=[]
    for t in selected:
      h=evidence_topic(index,text,t,per,used)
      if h:b.append({'topic':t,'topic_vi':TOPIC_VI.get(t,t),'sources':sorted(set(x['source'] for x in h)),'hits':h})
    return {'schema':'webnovel-writing-review-vi-v1','language':'vi','draft_sha256':sha(text),'evidence_buckets':b}

def checklist(index,topic,limit=20):
    pool=[]
    for src in ('vidian','moxing'):pool+=search(index,TOPIC_VI.get(topic,topic),max(60,limit*6),topic,src)
    h=balanced(pool,limit,set());return {'schema':'webnovel-writing-checklist-vi-v1','language':'vi','topic':topic,'topic_vi':TOPIC_VI.get(topic,topic),'sources':dict(collections.Counter(x['source'] for x in h)),'items':h}

def dump(x,path=None):
    raw=json.dumps(x,ensure_ascii=False,indent=2);print(raw)
    if path:Path(path).write_text(raw,encoding='utf-8')

def main():
    ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='cmd',required=True)
    b=sp.add_parser('build');b.add_argument('--source',required=True);b.add_argument('--translations',required=True);b.add_argument('--titles',required=True);b.add_argument('--out',required=True);b.add_argument('--dims',type=int,default=128);b.add_argument('--max-features',type=int,default=80000)
    q=sp.add_parser('query');q.add_argument('--index',required=True);q.add_argument('--q',required=True);q.add_argument('--limit',type=int,default=20);q.add_argument('--topic');q.add_argument('--source');q.add_argument('--json-out')
    d=sp.add_parser('direct');d.add_argument('--index',required=True);d.add_argument('--brief',required=True);d.add_argument('--limit',type=int,default=40);d.add_argument('--json-out')
    r=sp.add_parser('review');r.add_argument('--index',required=True);r.add_argument('--text',required=True);r.add_argument('--limit',type=int,default=28);r.add_argument('--json-out')
    c=sp.add_parser('checklist');c.add_argument('--index',required=True);c.add_argument('--topic',required=True,choices=sorted(TOPIC_VI));c.add_argument('--limit',type=int,default=20);c.add_argument('--json-out')
    s=sp.add_parser('stats');s.add_argument('--index',required=True);a=ap.parse_args()
    if a.cmd=='build':build(a.source,a.translations,a.titles,a.out,a.dims,a.max_features)
    elif a.cmd=='query':dump({'schema':'webnovel-writing-query-vi-v1','language':'vi','query':a.q,'hits':search(a.index,a.q,a.limit,a.topic,a.source)},a.json_out)
    elif a.cmd=='direct':dump(direct(a.index,a.brief,a.limit),a.json_out)
    elif a.cmd=='review':dump(review(a.index,a.text,a.limit),a.json_out)
    elif a.cmd=='checklist':dump(checklist(a.index,a.topic,a.limit),a.json_out)
    else:print((Path(a.index)/'manifest.json').read_text(encoding='utf-8'))
if __name__=='__main__':main()
