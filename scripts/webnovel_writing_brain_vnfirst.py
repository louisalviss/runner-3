#!/usr/bin/env python3
import argparse, hashlib, json, re, shutil, sqlite3
from pathlib import Path

ZH = re.compile(r'[\u3400-\u9fff]')
ZH_RUN = re.compile(r'[\u3400-\u9fff]+')
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

def sha(s):
    return hashlib.sha256((s or '').encode('utf-8')).hexdigest()

def clean(s):
    return re.sub(r'\s+',' ',s or '').strip()

def vn_display(text):
    """Guarantee no CJK glyphs leak into default display/search fields."""
    return clean(ZH_RUN.sub(' thuật ngữ nguồn ', text or ''))

def load_translations(path):
    out = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            x = json.loads(line)
            pid = int(x['passage_id'])
            if pid in out:
                raise AssertionError(f'duplicate translation passage_id={pid}')
            out[pid] = x
    return out

def ensure_columns(con):
    cols = {r[1] for r in con.execute('PRAGMA table_info(passages)')}
    additions = {
        'text_zh':'TEXT', 'evidence_surface_zh':'TEXT', 'title_zh':'TEXT',
        'text_vi_raw':'TEXT','language':'TEXT', 'translation_model':'TEXT',
        'translation_sha256':'TEXT','translation_residual_zh_chars':'INT'
    }
    for name, typ in additions.items():
        if name not in cols:
            con.execute(f'ALTER TABLE passages ADD COLUMN {name} {typ}')

def rebuild_fts(con):
    con.execute('DROP TABLE IF EXISTS passage_fts')
    con.execute("CREATE VIRTUAL TABLE passage_fts USING fts5(title,topic,kind,text,content='',tokenize='unicode61 remove_diacritics 2')")
    rows = con.execute('SELECT id,title,topic,kind,text FROM passages ORDER BY id').fetchall()
    con.executemany('INSERT INTO passage_fts(rowid,title,topic,kind,text) VALUES(?,?,?,?,?)', rows)
    con.commit()

def rebuild_semantic(out, con, dims=96, max_features=50000):
    import joblib, numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    from sklearn.preprocessing import Normalizer
    semantic = {}
    con.row_factory = sqlite3.Row
    for source in ('vidian','moxing'):
        rows = con.execute('SELECT id,topic,kind,title,text FROM passages WHERE source=? ORDER BY id',(source,)).fetchall()
        docs = [' '.join([r['topic'] or '',r['kind'] or '',r['title'] or '',r['text'] or '']) for r in rows]
        v = TfidfVectorizer(strip_accents='unicode',ngram_range=(1,2),min_df=2,max_df=.97,max_features=max_features,sublinear_tf=True)
        X = v.fit_transform(docs)
        d = min(dims, X.shape[0]-1, X.shape[1]-1)
        svd = TruncatedSVD(d, random_state=17, n_iter=7)
        nm = Normalizer(copy=False)
        D = nm.fit_transform(svd.fit_transform(X)).astype('float32')
        np.save(out/f'{source}_vectors.npy', D, allow_pickle=False)
        np.save(out/f'{source}_ids.npy', np.array([r['id'] for r in rows],dtype='int64'), allow_pickle=False)
        joblib.dump({'vectorizer':v,'svd':svd,'normalizer':nm}, out/f'{source}_semantic.joblib', compress=3)
        semantic[source] = {
            'enabled':True,'method':'Vietnamese word TF-IDF(1,2)+SVD+cosine',
            'dimensions':d,'features':int(X.shape[1]),'vectors':len(rows)
        }
    return semantic

def build(base, translations, outdir, model_id, model_revision, source_sha256):
    base = Path(base); out = Path(outdir)
    if out.exists(): shutil.rmtree(out)
    shutil.copytree(base, out)
    tr = load_translations(translations)
    assert len(tr) == 9538, len(tr)
    db = out/'writing_brain.sqlite'
    con = sqlite3.connect(db); con.row_factory = sqlite3.Row
    ensure_columns(con)
    rows = con.execute("SELECT id,evidence_id,text,evidence_surface,title,topic FROM passages WHERE source='moxing' ORDER BY id").fetchall()
    assert len(rows) == 9538, len(rows)
    missing=[]; sha_bad=[]; evidence_bad=[]; empty=[]
    raw_zh_chars=0; raw_chars=0; sanitized_rows=0
    for r in rows:
        pid=int(r['id']); x=tr.get(pid)
        if x is None:
            missing.append(pid); continue
        if x.get('evidence_id') != r['evidence_id']: evidence_bad.append(pid)
        if x.get('text_zh_sha256') != sha(r['text']): sha_bad.append(pid)
        text_vi_raw=(x.get('text_vi') or '').strip()
        if not text_vi_raw: empty.append(pid)
        residual=len(ZH.findall(text_vi_raw)); raw_zh_chars += residual; raw_chars += len(text_vi_raw)
        text_vi=vn_display(text_vi_raw)
        sanitized_rows += int(text_vi != clean(text_vi_raw))
        assert not ZH.search(text_vi), pid
        label = TOPIC_VI.get(r['topic'],'Kỹ thuật viết')
        title_vi = f'Moxing — {label}'
        con.execute('''UPDATE passages SET text_zh=?,evidence_surface_zh=?,title_zh=?,text_vi_raw=?,text=?,evidence_surface=?,title=?,language='vi',translation_model=?,translation_sha256=?,translation_residual_zh_chars=?,verbatim=0 WHERE id=?''',(
            r['text'],r['evidence_surface'],r['title'],text_vi_raw,text_vi,text_vi,title_vi,
            f'{model_id}@{model_revision}',x.get('text_vi_sha256') or sha(text_vi_raw),residual,pid))
    assert not missing, ('missing',len(missing),missing[:10])
    assert not sha_bad, ('sha_bad',len(sha_bad),sha_bad[:10])
    assert not evidence_bad, ('evidence_bad',len(evidence_bad),evidence_bad[:10])
    assert not empty, ('empty',len(empty),empty[:10])
    con.execute("UPDATE passages SET language='vi' WHERE source='vidian'")
    con.commit()
    rebuild_fts(con)
    semantic = rebuild_semantic(out, con)
    counts = dict(con.execute("SELECT source,count(*) FROM passages GROUP BY source").fetchall())
    raw_zh_ratio = raw_zh_chars/max(raw_chars,1)
    default_cjk = con.execute("SELECT count(*) FROM passages WHERE source='moxing' AND (text GLOB '*[一-龥]*' OR title GLOB '*[一-龥]*')").fetchone()[0]
    assert counts.get('moxing') == 9538 and counts.get('vidian') == 11672, counts
    assert raw_zh_ratio < .08, raw_zh_ratio
    assert default_cjk == 0, default_cjk
    con.execute('PRAGMA optimize'); con.close()

    manifest_path = out/'manifest.json'
    old = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    old.update({
        'schema':'webnovel-writing-brain-vnfirst-v1',
        'language_mode':'vi-first',
        'default_display_language':'vi',
        'default_retrieval_language':'vi',
        'source_language_policy':{
            'vidian':'Vietnamese source/reconstructed evidence',
            'moxing':'Vietnamese machine-translation used for default retrieval/display. Chinese originals and raw MT are retained only in provenance/audit columns.'
        },
        'moxing_translation':{
            'rows':9538,'model_id':model_id,'model_revision':model_revision,
            'source_writing_brain_sha256':source_sha256,
            'raw_mt_zh_char_ratio':round(raw_zh_ratio,6),
            'rows_with_residual_cjk_sanitized_for_default_display':sanitized_rows,
            'default_display_rows_with_cjk':default_cjk,
            'provenance_preserved':True
        },
        'retrieval':{
            'lexical':'Unified Vietnamese SQLite FTS5 BM25 over default display text',
            'semantic':semantic,
            'fusion':'Vietnamese lexical + Vietnamese per-source latent semantic + confidence/source-quality + conservative cross-source-theme boost'
        },
        'vnfirst_contract':'Default user-facing Moxing evidence text and titles contain no CJK glyphs. Chinese source text/title and unsanitized machine translation remain audit-only provenance and are not returned by standard query/direct/review/checklist interfaces.',
    })
    manifest_path.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    qa={
        'schema':'webnovel-writing-brain-vnfirst-qa-v1','passages_total':sum(counts.values()),
        'vidian':counts.get('vidian',0),'moxing':counts.get('moxing',0),
        'moxing_translated':len(tr),'missing':len(missing),'sha_bad':len(sha_bad),
        'evidence_bad':len(evidence_bad),'empty_vi':len(empty),'raw_mt_zh_char_ratio':round(raw_zh_ratio,6),
        'sanitized_rows':sanitized_rows,'default_moxing_rows_with_cjk':default_cjk,
        'default_text_language':'vi','provenance_columns':['text_zh','evidence_surface_zh','title_zh','text_vi_raw']
    }
    (out/'vnfirst_qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(qa,ensure_ascii=False,indent=2))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--base',required=True); ap.add_argument('--translations',required=True); ap.add_argument('--out',required=True)
    ap.add_argument('--model-id',default='DanVP/MoxhiMT-60')
    ap.add_argument('--model-revision',default='3ae60c790cf21deebeab8e1a82f4024fbdc1fc87')
    ap.add_argument('--source-sha256',required=True)
    a=ap.parse_args(); build(a.base,a.translations,a.out,a.model_id,a.model_revision,a.source_sha256)
if __name__=='__main__': main()
