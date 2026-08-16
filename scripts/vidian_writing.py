#!/usr/bin/env python3
import argparse, collections, hashlib, json, math, sqlite3
from pathlib import Path
import vidian_pipeline as vp
import vidian_knowledge as vk

CATEGORY='chi-dao-sang-tac'
TOPICS={
'hook_opening':['mở đầu','mở truyện','chương đầu','hook','thu hút độc giả','ấn tượng đầu'],
'plot_structure_arc':['cốt truyện','kết cấu','cấu trúc','mạch truyện','tuyến truyện','arc','đại cương','dàn ý','chủ tuyến','phó tuyến'],
'pacing_tension':['tiết tấu','nhịp truyện','nhịp độ','cao trào','căng thẳng','kịch tính','xung đột','tension'],
'cliffhanger':['cliffhanger','cuối chương','kết chương','treo','móc câu cuối'],
'character_design':['nhân vật','tính cách','hình tượng','thiết lập nhân vật','nhân thiết','vai chính','nam chính','nữ chính','nhân vật phụ'],
'motivation_conflict':['động cơ','mục tiêu nhân vật','mong muốn','mâu thuẫn','xung đột nội tâm','lựa chọn','quyết định'],
'villain_antagonist':['phản diện','đối thủ','kẻ địch','boss','địch nhân'],
'progression_power':['thăng cấp','tiến giai','đột phá','tu luyện','cảnh giới','hệ thống sức mạnh','chiến lực','công pháp','năng lực','level'],
'reward_payoff':['sảng','thoả mãn','thỏa mãn','payoff','phần thưởng','thu hoạch','tài nguyên','bảo vật','kỳ ngộ','đánh mặt'],
'worldbuilding':['thế giới quan','worldbuilding','bối cảnh','địa lý','tông môn','thế lực','xã hội','lịch sử','thiết lập thế giới'],
'system_design':['hệ thống','quy tắc','cơ chế','thiết lập','cảnh giới','đẳng cấp','cấp bậc','hệ thống tu luyện'],
'foreshadow_payoff':['foreshadow','phục bút','gợi trước','ám chỉ','gieo','thu hồi','payoff'],
'mystery_reveal':['bí ẩn','bí mật','huyền niệm','suspense','tiết lộ','reveal','giải đáp','ẩn giấu'],
'stakes':['nguy cơ','cái giá','hậu quả','sống chết','đe dọa','rủi ro','stake'],
'dialogue_voice':['đối thoại','thoại','lời thoại','khẩu khí','giọng nói','xưng hô'],
'description_scene':['miêu tả','mô tả','cảnh vật','khung cảnh','hành động','chi tiết','show dont tell'],
'combat_action':['chiến đấu','đánh nhau','giao chiến','trận chiến','combat','động tác'],
'emotion_immersion':['cảm xúc','đồng cảm','nhập vai','đại nhập cảm','trải nghiệm độc giả','cộng hưởng'],
'romance_relationship':['tình cảm','tình yêu','romance','quan hệ','nữ chính','nam nữ'],
'style_prose':['văn phong','câu văn','ngôn ngữ','cách viết','hành văn','giọng văn','từ ngữ'],
'editing_consistency':['logic','nhất quán','lỗ hổng','bug','sạn','kiểm tra','sửa','biên tập','continuity'],
'serialization_reader':['độc giả','đọc giả','theo dõi','đặt mua','chương','đăng chương','webnovel','truyện mạng','giữ chân'],
'theme_meaning':['chủ đề','tư tưởng','thông điệp','ý nghĩa','giá trị quan']}
POS=['nên','cần','phải','hãy','tốt nhất','quan trọng','cần phải','nên để','nên cho','có thể dùng','có thể sử dụng']
NEG=['không nên','không được','tránh','đừng','hạn chế','không cần','chớ','tuyệt đối không']
WARN=['lỗi','sai lầm','vấn đề','nhược điểm','dễ khiến','dễ làm','nguy hiểm','phản tác dụng','kỵ']
TECH=['cách','phương pháp','kỹ thuật','mẹo','bí quyết','thủ pháp','biện pháp','làm thế nào']
EXAMPLE=['ví dụ','chẳng hạn','thí dụ','có thể lấy','như trong','ví như']
DIAG=['nếu','khi','trường hợp','dấu hiệu','kiểm tra','xem xét','đánh giá']

def inventory(out=None):
    last=vp.last_page(CATEGORY)
    if last<1: raise SystemExit('cannot resolve chi-dao-sang-tac pages')
    by={}; failures=[]
    for p in range(1,last+1):
        c,page,d,err=vp.fetch_listing(CATEGORY,p)
        if err: failures.append({'page':page,'error':err})
        for u,t in d.items(): by[u]=max(by.get(u,''),t,key=len)
    if failures: raise SystemExit('listing failures: '+json.dumps(failures,ensure_ascii=False))
    x={'schema':'vidian-writing-category-inventory-v1','category':CATEGORY,'last_page':last,'urls':len(by),'rows':[{'url':u,'listing_title':by[u]} for u in sorted(by)]}
    if out: Path(out).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
    return x

def _phrase_present(norm_text,norm_phrase):
    return bool(norm_phrase) and f' {norm_phrase} ' in f' {norm_text} '

def _matched_phrases(text,phrases):
    n=vk.norm(text); out=[]; seen=set()
    for raw in phrases:
        z=vk.norm(raw)
        if not z or z in seen: continue
        seen.add(z)
        if _phrase_present(n,z): out.append((raw,z))
    return out

def topic_scores(text):
    out=[]
    for topic,keys in TOPICS.items():
        matches=_matched_phrases(text,keys)
        if not matches: continue
        score=sum(2 if ' ' in z else 1 for _,z in matches)
        specificity=max(len(z.split()) for _,z in matches)
        out.append((topic,float(score),[raw for raw,_ in matches],specificity))
    out.sort(key=lambda x:(-x[1],-x[3],x[0]))
    return [(t,s,h) for t,s,h,_ in out]

def kind(text):
    has=lambda xs:bool(_matched_phrases(text,xs))
    if has(NEG): return 'dont',.92
    if has(WARN): return 'warning',.82
    if has(POS): return 'do',.88
    if has(TECH): return 'technique',.76
    if has(EXAMPLE): return 'example',.68
    if has(DIAG): return 'diagnostic',.64
    return 'principle',.52

def extract(r):
    title=vk.clean(r.get('title') or r.get('listing_title') or '')
    out=[]; counts=collections.Counter()
    for f in vk.frames(r):
        text=vk.surface(f)
        if len(vk.toks(text))<5: continue
        ts=topic_scores(title+' '+text)
        if not ts: continue
        topic,score,matches=ts[0]; k,conf=kind(text)
        if k in {'do','dont','warning','technique'}: conf=min(.98,conf+.06)
        counts[topic]+=score
        out.append({'sentence_sha':str(f.get('source_sentence_sha256') or hashlib.sha256(text.encode()).hexdigest()),'topic':topic,'topic_score':score,'topic_matches':matches,'kind':k,'confidence':conf,'surface':vk.clean(text),'rule':vk.clean(text)[:420]})
    return {'url':r['url'],'title':title,'passages':out,'topics':counts}

def build(corpus,outdir,semantic_dim=96,max_features=40000):
    out=Path(outdir); out.mkdir(parents=True,exist_ok=True); inv=inventory(out/'category_inventory.json'); wanted={x['url'] for x in inv['rows']}; found={}; scanned=0
    for r in vk.records(corpus):
        scanned+=1
        if r.get('url') in wanted: found[r['url']]=extract(r)
    missing=sorted(wanted-set(found)); (out/'missing_urls.json').write_text(json.dumps(missing,ensure_ascii=False,indent=2),encoding='utf-8')
    if not found: raise SystemExit('no category records matched corpus')
    db=out/'vidian_writing.sqlite'; db.unlink(missing_ok=True); con=sqlite3.connect(db)
    con.executescript("""CREATE TABLE articles(id INTEGER PRIMARY KEY,url TEXT UNIQUE,title TEXT,category TEXT);CREATE TABLE passages(id INTEGER PRIMARY KEY,article_id INT,sentence_sha TEXT,topic TEXT,kind TEXT,confidence REAL,surface TEXT,rule TEXT,UNIQUE(article_id,sentence_sha));CREATE TABLE article_topics(article_id INT,topic TEXT,score REAL,PRIMARY KEY(article_id,topic));CREATE VIRTUAL TABLE passage_fts USING fts5(title,topic,kind,rule,surface,content='',tokenize='unicode61 remove_diacritics 2');CREATE INDEX pt ON passages(topic,confidence DESC);CREATE INDEX pk ON passages(kind,confidence DESC);""")
    vecrows=[]
    for u in sorted(found):
        x=found[u]; aid=con.execute('INSERT INTO articles(url,title,category) VALUES(?,?,?)',(u,x['title'],CATEGORY)).lastrowid
        for t,s in x['topics'].items(): con.execute('INSERT INTO article_topics VALUES(?,?,?)',(aid,t,float(s)))
        for p in x['passages']:
            pid=con.execute('INSERT OR IGNORE INTO passages(article_id,sentence_sha,topic,kind,confidence,surface,rule) VALUES(?,?,?,?,?,?,?)',(aid,p['sentence_sha'],p['topic'],p['kind'],p['confidence'],p['surface'],p['rule'])).lastrowid
            if pid:
                con.execute('INSERT INTO passage_fts(rowid,title,topic,kind,rule,surface) VALUES(?,?,?,?,?,?)',(pid,x['title'],p['topic'],p['kind'],p['rule'],p['surface'])); vecrows.append((pid,x['title'],p))
    con.commit()
    seen=set(); rules=[]
    for pid,title,p in sorted(vecrows,key=lambda x:-x[2]['confidence']):
        z=vk.norm(p['rule'])
        if len(z)<20 or z in seen: continue
        seen.add(z); rules.append({'passage_id':pid,'title':title,**p})
    (out/'rule_bank.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rules),encoding='utf-8')
    checklist={}
    for t in TOPICS:
        rr=con.execute("SELECT p.id,p.kind,p.confidence,p.rule,a.title,a.url,p.sentence_sha FROM passages p JOIN articles a ON a.id=p.article_id WHERE p.topic=? AND p.kind IN ('do','dont','warning','technique','principle') ORDER BY p.confidence DESC,length(p.rule) ASC LIMIT 25",(t,)).fetchall()
        checklist[t]=[{'passage_id':r[0],'kind':r[1],'confidence':r[2],'rule':r[3],'title':r[4],'url':r[5],'sentence_sha':r[6]} for r in rr]
    (out/'checklists.json').write_text(json.dumps(checklist,ensure_ascii=False,indent=2),encoding='utf-8')
    sem={'enabled':False}
    try:
        import joblib,numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import TruncatedSVD
        from sklearn.preprocessing import Normalizer
        docs=[vk.clean(' '.join([title,p['topic'],p['kind'],p['rule'],p['surface']])) for _,title,p in vecrows]; v=TfidfVectorizer(strip_accents='unicode',ngram_range=(1,2),min_df=2,max_df=.95,max_features=max_features,sublinear_tf=True); X=v.fit_transform(docs); d=min(semantic_dim,X.shape[0]-1,X.shape[1]-1)
        if d>=2:
            svd=TruncatedSVD(d,random_state=17,n_iter=7); nm=Normalizer(copy=False); D=nm.fit_transform(svd.fit_transform(X)).astype('float32'); np.save(out/'vectors.npy',D,allow_pickle=False); np.save(out/'passage_ids.npy',np.array([x[0] for x in vecrows],dtype='int64'),allow_pickle=False); joblib.dump({'v':v,'svd':svd,'nm':nm},out/'semantic.joblib',compress=3); sem={'enabled':True,'method':'TF-IDF + TruncatedSVD + cosine','dimensions':d,'features':X.shape[1],'vectors':len(vecrows)}
    except Exception as e: sem={'enabled':False,'error':f'{type(e).__name__}:{e}'}
    counts={'canonical_articles_scanned':scanned,'category_urls':len(wanted),'matched_articles':len(found),'missing_category_urls':len(missing),'passages':con.execute('select count(*) from passages').fetchone()[0],'directive_rules':con.execute("select count(*) from passages where kind in ('do','dont','warning','technique')").fetchone()[0],'do_rules':con.execute("select count(*) from passages where kind='do'").fetchone()[0],'dont_rules':con.execute("select count(*) from passages where kind='dont'").fetchone()[0],'warnings':con.execute("select count(*) from passages where kind='warning'").fetchone()[0],'topics_with_rules':con.execute('select count(distinct topic) from passages').fetchone()[0]}
    tops=[{'topic':r[0],'passages':r[1],'avg_confidence':round(r[2],3)} for r in con.execute('select topic,count(*),avg(confidence) from passages group by topic order by count(*) desc')]; con.close()
    m={'schema':'vidian-writing-knowledge-v1','source_category':CATEGORY,'source_prose_persisted':False,'evidence_surface':'reconstructed from dependency-edge token order; not verbatim source prose','taxonomy_version':'1.1','topics':list(TOPICS),'counts':counts,'top_topics':tops,'retrieval':{'lexical':'SQLite FTS5 BM25','semantic':sem,'filters':['topic','kind']},'limitations':['Original source prose is not persisted in the canonical semantic corpus.','Rule text is reconstructed from parser token order and must not be represented as a verbatim quotation.','Directive/topic labels are heuristic candidates; source URL + sentence SHA are retained for verification.']}
    (out/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(m,ensure_ascii=False,indent=2))

def scale(xs):
    if not xs:return {}
    lo=min(v for _,v in xs); hi=max(v for _,v in xs); return {i:(1 if hi==lo else (v-lo)/(hi-lo)) for i,v in xs}

def search(index,q,limit=12,mode='hybrid',topic=None,kind_filter=None):
    idx=Path(index); con=sqlite3.connect(idx/'vidian_writing.sqlite'); con.row_factory=sqlite3.Row; score=collections.defaultdict(dict); ts=[t for t in vk.toks(q) if len(t)>=2 and t not in vk.STOP] or vk.toks(q); fq=' OR '.join(f'"{t}"' for t in ts[:20]); where=[]; params=[]
    if topic: where.append('p.topic=?'); params.append(topic)
    if kind_filter: where.append('p.kind=?'); params.append(kind_filter)
    filt=(' AND '+' AND '.join(where)) if where else ''
    if fq and mode!='semantic':
        try: rr=con.execute(f"SELECT p.id,-bm25(passage_fts,2.5,1,1,2,1) s FROM passage_fts JOIN passages p ON p.id=passage_fts.rowid WHERE passage_fts MATCH ? {filt} ORDER BY bm25(passage_fts,2.5,1,1,2,1) LIMIT 200",[fq]+params).fetchall()
        except sqlite3.OperationalError: rr=[]
        for i,s in scale([(int(r['id']),float(r['s'])) for r in rr]).items(): score[i]['lexical']=s
    if mode!='lexical' and (idx/'semantic.joblib').exists():
        import joblib,numpy as np
        m=joblib.load(idx/'semantic.joblib'); D=np.load(idx/'vectors.npy',mmap_mode='r'); ids=np.load(idx/'passage_ids.npy',mmap_mode='r'); v=m['nm'].transform(m['svd'].transform(m['v'].transform([q])))[0].astype('float32');ss=D@v;k=min(250,len(ss));ix=np.argpartition(ss,-k)[-k:] if k else [];pairs=[]
        for j in ix:
            if ss[j]<=0: continue
            pid=int(ids[j]); r=con.execute('select topic,kind from passages where id=?',(pid,)).fetchone()
            if topic and r['topic']!=topic: continue
            if kind_filter and r['kind']!=kind_filter: continue
            pairs.append((pid,float(ss[j])))
        for i,s in scale(pairs).items(): score[i]['semantic']=s
    w={'lexical':.48,'semantic':.52} if mode=='hybrid' else ({'lexical':1} if mode=='lexical' else {'semantic':1}); ranked=sorted(((sum(w.get(k,0)*v for k,v in c.items()),pid,c) for pid,c in score.items()),reverse=True)[:limit]; out=[]
    for s,pid,c in ranked:
        r=con.execute('select p.*,a.title,a.url from passages p join articles a on a.id=p.article_id where p.id=?',(pid,)).fetchone(); out.append({'score':round(s,6),'components':{k:round(v,5) for k,v in c.items()},'passage_id':pid,'topic':r['topic'],'kind':r['kind'],'confidence':r['confidence'],'rule':r['rule'],'evidence_surface':r['surface'],'sentence_sha':r['sentence_sha'],'title':r['title'],'url':r['url'],'evidence_note':'reconstructed parser-token surface; not verbatim source prose'})
    con.close(); return out

def review(index,text,limit=24):
    scored=topic_scores(text); selected=[x[0] for x in scored[:6]] or ['plot_structure_arc','pacing_tension','character_design','style_prose']; per=max(3,math.ceil(limit/len(selected))); buckets=[]; used=set()
    for t in selected:
        keep=[]
        for x in search(index,text,per*3,'hybrid',t):
            if x['passage_id'] in used: continue
            used.add(x['passage_id']); keep.append(x)
            if len(keep)>=per: break
        buckets.append({'topic':t,'hits':keep})
    return {'schema':'vidian-writing-review-packet-v1','draft_sha256':hashlib.sha256(text.encode()).hexdigest(),'draft_chars':len(text),'detected_topics':[{'topic':t,'score':s,'matches':m} for t,s,m in scored[:10]],'review_dimensions':selected,'evidence_buckets':buckets,'instruction':'Use retrieved rules as craft criteria; evidence surfaces are reconstructed, not verbatim quotes.'}

def direct(index,brief,limit=36):
    scored=topic_scores(brief); selected=[x[0] for x in scored[:8]]; core=['hook_opening','plot_structure_arc','pacing_tension','character_design','motivation_conflict','progression_power','worldbuilding','reward_payoff']
    for t in core:
        if len(selected)>=8: break
        if t not in selected:selected.append(t)
    per=max(4,math.ceil(limit/len(selected))); sections=[]; used=set()
    for t in selected:
        hits=search(index,brief,per*4,'hybrid',t)
        if len(hits)<per: hits+=search(index,' '.join(TOPICS[t][:8]),per*3,'hybrid',t)
        keep=[]
        for x in hits:
            if x['passage_id'] in used:continue
            used.add(x['passage_id']);keep.append(x)
            if len(keep)>=per:break
        sections.append({'topic':t,'must_do':[x for x in keep if x['kind'] in {'do','principle'}],'avoid':[x for x in keep if x['kind'] in {'dont','warning'}],'techniques':[x for x in keep if x['kind'] in {'technique','diagnostic','example'}],'all':keep})
    return {'schema':'vidian-writing-directive-packet-v1','brief_sha256':hashlib.sha256(brief.encode()).hexdigest(),'brief_chars':len(brief),'detected_topics':[{'topic':t,'score':s,'matches':m} for t,s,m in scored[:12]],'directive_topics':selected,'sections':sections,'composition_protocol':['Treat rules as craft constraints, not prose to copy.','Prefer higher-confidence rules that fit the brief and genre when rules conflict.','Convert selected rules into scene/arc checks before drafting.','After drafting, run review and repair evidenced weaknesses.','Never represent evidence_surface as a verbatim quotation.']}

def md(packet):
    lines=['# Vidian Writing Evidence Packet','']
    groups=packet.get('sections') or packet.get('evidence_buckets')
    if groups:
        for g in groups:
            lines += [f"## {g['topic']}",'']
            items=g.get('all') or g.get('hits') or []
            for x in items: lines += [f"- **{x['kind']}** ({x['confidence']:.2f}) — {x['rule']}",f"  - {x['title']} — {x['url']}",f"  - sentence_sha: `{x['sentence_sha']}`"]
            lines.append('')
    else:
        for x in packet.get('hits',[]): lines += [f"- **{x['topic']} / {x['kind']}** ({x['confidence']:.2f}) — {x['rule']}",f"  - {x['title']} — {x['url']}",f"  - sentence_sha: `{x['sentence_sha']}`"]
    lines += ['','> Evidence surfaces are reconstructed from parser tokens, not verbatim source prose.']; return '\n'.join(lines)+'\n'

def dump(packet,json_out=None,md_out=None):
    raw=json.dumps(packet,ensure_ascii=False,indent=2); print(raw)
    if json_out:Path(json_out).write_text(raw,encoding='utf-8')
    if md_out:Path(md_out).write_text(md(packet),encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest='cmd',required=True)
    b=sp.add_parser('build');b.add_argument('--corpus',required=True);b.add_argument('--out',required=True);b.add_argument('--semantic-dim',type=int,default=96);b.add_argument('--max-features',type=int,default=40000)
    q=sp.add_parser('query');q.add_argument('--index',required=True);q.add_argument('--q',required=True);q.add_argument('--limit',type=int,default=12);q.add_argument('--mode',choices=['hybrid','semantic','lexical'],default='hybrid');q.add_argument('--topic',choices=sorted(TOPICS));q.add_argument('--kind',choices=['do','dont','warning','technique','example','diagnostic','principle']);q.add_argument('--json-out');q.add_argument('--md-out')
    r=sp.add_parser('review');r.add_argument('--index',required=True);g=r.add_mutually_exclusive_group(required=True);g.add_argument('--text');g.add_argument('--file');r.add_argument('--limit',type=int,default=24);r.add_argument('--json-out');r.add_argument('--md-out')
    d=sp.add_parser('direct');d.add_argument('--index',required=True);g=d.add_mutually_exclusive_group(required=True);g.add_argument('--brief');g.add_argument('--file');d.add_argument('--limit',type=int,default=36);d.add_argument('--json-out');d.add_argument('--md-out')
    c=sp.add_parser('checklist');c.add_argument('--index',required=True);c.add_argument('--topic',required=True,choices=sorted(TOPICS));c.add_argument('--limit',type=int,default=20);c.add_argument('--json-out')
    s=sp.add_parser('stats');s.add_argument('--index',required=True);i=sp.add_parser('inventory');i.add_argument('--out',required=True);a=ap.parse_args()
    if a.cmd=='build':build(a.corpus,a.out,a.semantic_dim,a.max_features)
    elif a.cmd=='inventory':print(json.dumps(inventory(a.out),ensure_ascii=False,indent=2))
    elif a.cmd=='stats':print((Path(a.index)/'manifest.json').read_text(encoding='utf-8'))
    elif a.cmd=='query':dump({'schema':'vidian-writing-query-packet-v1','query':a.q,'mode':a.mode,'topic_filter':a.topic,'kind_filter':a.kind,'hits':search(a.index,a.q,a.limit,a.mode,a.topic,a.kind)},a.json_out,a.md_out)
    elif a.cmd=='checklist':
        data=json.loads((Path(a.index)/'checklists.json').read_text(encoding='utf-8'));dump({'schema':'vidian-writing-checklist-v1','topic':a.topic,'items':data.get(a.topic,[])[:a.limit]},a.json_out,None)
    elif a.cmd=='review':
        text=a.text if a.text is not None else Path(a.file).read_text(encoding='utf-8');dump(review(a.index,text,a.limit),a.json_out,a.md_out)
    elif a.cmd=='direct':
        text=a.brief if a.brief is not None else Path(a.file).read_text(encoding='utf-8');dump(direct(a.index,text,a.limit),a.json_out,a.md_out)
if __name__=='__main__':main()
