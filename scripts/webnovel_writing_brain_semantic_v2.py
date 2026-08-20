#!/usr/bin/env python3
"""Semantic atomic-rule canonicalizer for the VN-first Webnovel Writing Brain.

V2 goals:
- preserve every source passage as evidence/provenance;
- split passages into compact atomic craft statements;
- embed Vietnamese atoms with multilingual-e5-small;
- merge semantic equivalents only inside the same topic + direction;
- detect high-similarity opposite-direction rule conflicts;
- keep canonical_rules/canonical_evidence compatible with the existing canonical agent;
- benchmark V2 against Canonical V1 before promotion.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math, re, shutil, sqlite3, unicodedata
from pathlib import Path

ZH = re.compile(r"[\u3400-\u9fff]")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n+")
CLAUSE_SPLIT = re.compile(
    r"\s+(?:nhưng|tuy nhiên|đồng thời|trong khi|thay vì|vì vậy|do đó|mặt khác|ngược lại)\s+",
    re.I,
)
DIRECTIVE_HINTS = (
    "nên", "không nên", "cần", "phải", "tránh", "hãy", "đừng", "nên tránh",
    "ưu tiên", "hạn chế", "đảm bảo", "không được", "tốt nhất", "quan trọng",
    "có thể", "để", "khi", "nếu",
)

TOPIC_VI = {
    'hook_opening':'Mở đầu và hook','plot_structure_arc':'Cấu trúc cốt truyện','outline':'Đại cương',
    'pacing_tension':'Nhịp truyện và căng thẳng','cliffhanger':'Kết chương và cliffhanger',
    'character_design':'Thiết kế nhân vật','motivation_conflict':'Động cơ và xung đột',
    'villain_antagonist':'Phản diện và đối thủ','progression_power':'Tiến triển sức mạnh',
    'reward_payoff':'Phần thưởng và payoff','worldbuilding':'Xây dựng thế giới',
    'system_design':'Thiết kế hệ thống','foreshadow_payoff':'Phục bút và thu hồi',
    'mystery_reveal':'Bí ẩn và hé lộ','stakes':'Nguy cơ và cái giá',
    'dialogue_voice':'Đối thoại và giọng nhân vật','description_scene':'Miêu tả và cảnh',
    'combat_action':'Chiến đấu và hành động','emotion_immersion':'Cảm xúc và nhập vai',
    'romance_relationship':'Tình cảm và quan hệ','style_prose':'Văn phong và câu chữ',
    'editing_consistency':'Biên tập và nhất quán','serialization_reader':'Độc giả và giữ chân',
    'theme_meaning':'Chủ đề và ý nghĩa','title_blurb_packaging':'Tên truyện và giới thiệu',
    'genre_pattern':'Mẫu thể loại','craft_general':'Kỹ thuật viết chung',
}

BENCH_QUERIES = [
    ("hook_opening","mở đầu truyện tiên hiệp thế nào để giữ độc giả ngay chương đầu"),
    ("hook_opening","hook đầu truyện nên đưa xung đột hay mục tiêu nhân vật trước"),
    ("plot_structure_arc","cách thiết kế arc truyện dài không bị rời rạc"),
    ("plot_structure_arc","nhịp tăng tiến của đại cốt truyện nên chia thế nào"),
    ("outline","đại cương webnovel cần chi tiết đến mức nào"),
    ("pacing_tension","cách giữ nhịp truyện nhanh mà không thành vội"),
    ("pacing_tension","làm sao tăng căng thẳng trước cao trào"),
    ("cliffhanger","kết chương cliffhanger thế nào không bị gượng"),
    ("character_design","thiết kế nhân vật chính thận trọng nhưng không nhạt"),
    ("character_design","nhân vật phụ làm sao có chức năng và cá tính riêng"),
    ("motivation_conflict","động cơ nhân vật phải gắn với xung đột ra sao"),
    ("villain_antagonist","phản diện thế nào để có sức ép mà không ngu"),
    ("progression_power","progression sức mạnh cần cost và giới hạn thế nào"),
    ("progression_power","làm sao tránh power creep phá cân bằng"),
    ("reward_payoff","phần thưởng sau arc nên đủ đã nhưng không phá truyện"),
    ("worldbuilding","worldbuilding nên lộ dần thay vì dump thông tin thế nào"),
    ("worldbuilding","xây hệ thống tông môn thế giới tiên hiệp có chiều sâu"),
    ("system_design","thiết kế hệ thống kỹ năng sao cho có lựa chọn và tradeoff"),
    ("foreshadow_payoff","phục bút nên cài và thu hồi như thế nào"),
    ("mystery_reveal","hé lộ bí ẩn theo lớp để độc giả vẫn đoán được"),
    ("stakes","nâng stakes mà không lạm dụng đe dọa tính mạng"),
    ("dialogue_voice","đối thoại làm sao phân biệt giọng từng nhân vật"),
    ("description_scene","miêu tả cảnh đủ hình ảnh nhưng không làm chậm nhịp"),
    ("combat_action","viết combat rõ vị trí chiến thuật và payoff"),
    ("emotion_immersion","làm sao tăng nhập vai cảm xúc mà không melodrama"),
    ("romance_relationship","romance trong webnovel phát triển tự nhiên thế nào"),
    ("style_prose","văn phong webnovel gọn dễ đọc nhưng không nhạt"),
    ("editing_consistency","kiểm soát continuity tên kỹ năng cảnh giới nhân vật"),
    ("serialization_reader","giữ chân độc giả serial qua nhiều chương thế nào"),
    ("serialization_reader","mỗi chương nên có promise progress payoff gì"),
    ("theme_meaning","chủ đề truyện nên hiện qua lựa chọn nhân vật thay vì giảng"),
    ("title_blurb_packaging","title và blurb webnovel nên hứa điều gì"),
    ("genre_pattern","dùng trope thể loại mà không thành sáo"),
    ("craft_general","khi review một chương nên ưu tiên lỗi nào trước"),
]
BENCH_QUERIES = BENCH_QUERIES + [(t, q + " cho truyện dài đăng chương liên tục") for t, q in BENCH_QUERIES]


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def unaccent(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def norm(s: str | None) -> str:
    return clean(re.sub(r"[^0-9a-z]+", " ", unaccent((s or "").lower())))


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def json_set(raw: str | None) -> set[str]:
    try:
        v = json.loads(raw or "[]")
        return {str(x) for x in v if str(x).strip()}
    except Exception:
        return set()


def token_set(s: str) -> set[str]:
    return {x for x in norm(s).split() if len(x) >= 3}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def strip_cjk(s: str) -> str:
    return clean(ZH.sub("", s or ""))


def atomicize(text: str, title: str, topic: str) -> list[str]:
    """Extract up to 3 compact, non-overlapping atomic craft statements."""
    text = strip_cjk(text)
    chunks: list[str] = []
    for sent in SENTENCE_SPLIT.split(text):
        sent = clean(sent.strip(" -•\t"))
        if not sent:
            continue
        parts = CLAUSE_SPLIT.split(sent) if len(sent) > 240 else [sent]
        for part in parts:
            p = clean(part.strip(" -•\t"))
            if 24 <= len(p) <= 420:
                chunks.append(p)
            elif len(p) > 420:
                buf = ""
                for x in re.split(r"(?<=[,，])\s*", p):
                    cand = clean((buf + " " + x).strip())
                    if len(cand) > 320 and buf:
                        if len(buf) >= 24:
                            chunks.append(clean(buf))
                        buf = x
                    else:
                        buf = cand
                if len(clean(buf)) >= 24:
                    chunks.append(clean(buf))
    if not chunks:
        fallback = strip_cjk(text)
        if fallback:
            chunks = [fallback[:420].rstrip()]
        else:
            chunks = [f"{TOPIC_VI.get(topic, 'Kỹ thuật viết')}: xem evidence nguồn để kiểm tra chi tiết."]

    scored = []
    for p in chunks:
        low = p.lower()
        hint = sum(h in low for h in DIRECTIVE_HINTS)
        score = hint * 2.0 + min(len(p), 220) / 220 - max(0, len(p) - 280) / 280
        scored.append((score, p))
    out, seen = [], set()
    for _, p in sorted(scored, key=lambda z: z[0], reverse=True):
        n = norm(p)
        if len(n) < 12 or n in seen:
            continue
        seen.add(n)
        out.append(p)
        if len(out) >= 3:
            break
    return out or [strip_cjk(text)[:420]]


class DSU:
    def __init__(self, n: int):
        self.p = list(range(n)); self.sz = [1] * n
    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a: int, b: int, cap: int = 32) -> bool:
        a, b = self.find(a), self.find(b)
        if a == b or self.sz[a] + self.sz[b] > cap:
            return False
        if self.sz[a] < self.sz[b]: a, b = b, a
        self.p[b] = a; self.sz[a] += self.sz[b]; return True


def canonical_confidence(members: list[dict]) -> float:
    base = max(float(x["confidence"] or 0.5) * float(x["source_quality"] or 0.7) for x in members)
    source_bonus = 0.07 if len({x["source"] for x in members}) > 1 else 0.0
    evidence_bonus = min(0.07, 0.02 * math.log2(max(1, len(members))))
    return round(min(0.99, base + source_bonus + evidence_bonus), 6)


def encode(model, texts, batch_size=128):
    import numpy as np
    arr = model.encode(["passage: " + clean(t) for t in texts], batch_size=batch_size,
        normalize_embeddings=True, show_progress_bar=True, convert_to_numpy=True)
    return np.asarray(arr, dtype="float32")


def query_encode(model, texts, batch_size=64):
    import numpy as np
    arr = model.encode(["query: " + clean(t) for t in texts], batch_size=batch_size,
        normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True)
    return np.asarray(arr, dtype="float32")


def build(base: str, v1: str, outdir: str, model_id: str, neighbors: int = 24):
    import faiss, joblib, numpy as np
    from sentence_transformers import SentenceTransformer

    base = Path(base); v1 = Path(v1); out = Path(outdir)
    if out.exists(): shutil.rmtree(out)
    shutil.copytree(base, out)
    con = sqlite3.connect(out / "writing_brain.sqlite"); con.row_factory = sqlite3.Row
    passages = [dict(r) for r in con.execute("""SELECT id,source,source_id,topic,kind,direction,confidence,source_quality,
                  cross_source_support,text,evidence_surface,evidence_id,title,url,atoms_json FROM passages ORDER BY id""")]
    assert len(passages) == 21210
    assert sum(x["source"] == "vidian" for x in passages) == 11672
    assert sum(x["source"] == "moxing" for x in passages) == 9538

    atomic = []; aid = 0
    for p in passages:
        for order, text in enumerate(atomicize(p["text"] or "", p["title"] or "", p["topic"]), 1):
            aid += 1
            atomic.append({"id":aid,"passage_id":p["id"],"source":p["source"],"topic":p["topic"],
                "kind":p["kind"],"direction":p["direction"] or "neutral","text":strip_cjk(text),
                "confidence":float(p["confidence"] or 0.5),"source_quality":float(p["source_quality"] or 0.7),
                "evidence_id":p["evidence_id"],"url":p["url"],"atoms":json_set(p["atoms_json"]),
                "cross_support":int(p["cross_source_support"] or 0),"order":order})
    passage_atomic_coverage = len({x["passage_id"] for x in atomic}); assert passage_atomic_coverage == 21210

    model = SentenceTransformer(model_id, device="cpu")
    emb = encode(model, [x["text"] for x in atomic]); dim = emb.shape[1]
    dsu = DSU(len(atomic)); edge_sim = {}; merge_edges = cross_edges = candidates = 0
    groups = collections.defaultdict(list)
    for i, a in enumerate(atomic): groups[(a["topic"], a["direction"])].append(i)

    for _, idxs in groups.items():
        if len(idxs) < 2: continue
        local = emb[np.asarray(idxs, dtype="int64")]
        index = faiss.IndexHNSWFlat(dim, 32, faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efConstruction = 80; index.hnsw.efSearch = 64; index.add(local)
        k = min(neighbors, len(idxs)); sims, neigh = index.search(local, k)
        for a_pos, gi in enumerate(idxs):
            a = atomic[gi]
            for rank in range(1, k):
                b_pos = int(neigh[a_pos, rank])
                if b_pos < 0: continue
                gj = idxs[b_pos]
                if gj <= gi: continue
                b = atomic[gj]; sim = float(sims[a_pos, rank]); candidates += 1
                exact = norm(a["text"]) == norm(b["text"]); cross = a["source"] != b["source"]
                lex = jaccard(token_set(a["text"]), token_set(b["text"])); atom_overlap = jaccard(a["atoms"], b["atoms"])
                la, lb = max(1,len(norm(a["text"]))), max(1,len(norm(b["text"])))
                lr = min(la,lb)/max(la,lb); corroborated = bool(a["cross_support"] and b["cross_support"])
                if exact: ok = True
                elif cross:
                    ok = ((sim>=0.83 and lr>=0.42 and (lex>=0.10 or atom_overlap>=0.25))
                          or (sim>=0.87 and lr>=0.50)
                          or (corroborated and sim>=0.79 and lr>=0.55 and atom_overlap>=0.25))
                else:
                    ok = ((sim>=0.88 and lr>=0.45 and (lex>=0.12 or atom_overlap>=0.25))
                          or (sim>=0.92 and lr>=0.55))
                if ok:
                    edge_sim[(min(gi,gj),max(gi,gj))] = sim
                    if dsu.union(gi,gj): merge_edges += 1; cross_edges += int(cross)

    cls = collections.defaultdict(list)
    for i in range(len(atomic)): cls[dsu.find(i)].append(i)
    clusters = sorted(cls.values(), key=lambda xs:min(atomic[i]["id"] for i in xs))

    con.executescript("""DROP TABLE IF EXISTS canonical_rules; DROP TABLE IF EXISTS canonical_evidence;
    DROP TABLE IF EXISTS canonical_fts; DROP TABLE IF EXISTS atomic_rules; DROP TABLE IF EXISTS canonical_atomic_evidence;
    DROP TABLE IF EXISTS canonical_conflicts;
    CREATE TABLE atomic_rules(id INTEGER PRIMARY KEY,passage_id INT NOT NULL,source TEXT NOT NULL,topic TEXT NOT NULL,
      kind TEXT,direction TEXT NOT NULL,atomic_text TEXT NOT NULL,confidence REAL,source_quality REAL,extraction_order INT,
      atomic_hash TEXT UNIQUE);
    CREATE INDEX idx_atomic_passage ON atomic_rules(passage_id); CREATE INDEX idx_atomic_topic_direction ON atomic_rules(topic,direction);
    CREATE TABLE canonical_rules(id INTEGER PRIMARY KEY,topic TEXT,direction TEXT,kind TEXT,title TEXT,canonical_text TEXT,
      confidence REAL,evidence_count INT,vidian_count INT,moxing_count INT,source_count INT,cross_source INT,atoms_json TEXT,
      representative_passage_id INT,rule_hash TEXT UNIQUE,merge_method TEXT,max_pair_similarity REAL);
    CREATE TABLE canonical_evidence(rule_id INT NOT NULL,passage_id INT NOT NULL,source TEXT NOT NULL,evidence_id TEXT,url TEXT,
      confidence REAL,similarity_to_rule REAL,evidence_rank INT,PRIMARY KEY(rule_id,passage_id));
    CREATE INDEX idx_canonical_evidence_rule ON canonical_evidence(rule_id,evidence_rank);
    CREATE TABLE canonical_atomic_evidence(rule_id INT NOT NULL,atomic_id INT NOT NULL UNIQUE,passage_id INT NOT NULL,
      source TEXT NOT NULL,similarity_to_rule REAL,evidence_rank INT,PRIMARY KEY(rule_id,atomic_id));
    CREATE INDEX idx_cae_rule ON canonical_atomic_evidence(rule_id,evidence_rank);
    CREATE TABLE canonical_conflicts(id INTEGER PRIMARY KEY,rule_a INT NOT NULL,rule_b INT NOT NULL,topic TEXT NOT NULL,
      similarity REAL NOT NULL,direction_a TEXT NOT NULL,direction_b TEXT NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL,
      UNIQUE(rule_a,rule_b));
    CREATE VIRTUAL TABLE canonical_fts USING fts5(title,topic,direction,text,content='',tokenize='unicode61 remove_diacritics 2');
    CREATE INDEX idx_canonical_topic ON canonical_rules(topic,direction,confidence DESC);
    CREATE INDEX idx_canonical_cross ON canonical_rules(cross_source DESC,evidence_count DESC);""")

    for a in atomic:
        con.execute("INSERT INTO atomic_rules VALUES(?,?,?,?,?,?,?,?,?,?,?)", (a["id"],a["passage_id"],a["source"],a["topic"],
          a["kind"],a["direction"],a["text"],a["confidence"],a["source_quality"],a["order"],
          sha("|".join([str(a["passage_id"]),str(a["order"]),norm(a["text"])]))))

    canon_ids=[]; cross_rules=max_cluster=multi_rules=0
    for rid,mids in enumerate(clusters,1):
        members=[atomic[i] for i in mids]; topic=members[0]["topic"]; direction=members[0]["direction"]
        assert all(x["topic"]==topic and x["direction"]==direction for x in members)
        unique_passages={}
        for x in members: unique_passages.setdefault(x["passage_id"],x)
        src=collections.Counter(x["source"] for x in unique_passages.values()); cross=int(len(src)>1)
        cross_rules+=cross; max_cluster=max(max_cluster,len(mids)); multi_rules+=int(len(mids)>1)
        def rep_score(gi):
            x=atomic[gi]; central=sum(edge_sim.get((min(gi,j),max(gi,j)),0.0) for j in mids if j!=gi)/max(1,len(mids)-1)
            concise=1.0/(1.0+max(0,len(x["text"])-220)/320)
            return 0.38*x["confidence"]+0.24*x["source_quality"]+0.23*central+0.15*concise
        rep_i=max(mids,key=rep_score); rep=atomic[rep_i]; text=strip_cjk(rep["text"]); title=TOPIC_VI.get(topic,"Kỹ thuật viết")
        kind=collections.Counter(x["kind"] for x in members).most_common(1)[0][0]
        all_atoms=sorted(set().union(*(x["atoms"] for x in members)))
        max_sim=max([edge_sim.get((min(a,b),max(a,b)),0.0) for ai,a in enumerate(mids) for b in mids[ai+1:]] or [1.0])
        rulehash=sha("|".join([topic,direction,norm(text),str(rep["passage_id"]),str(rep["id"])]))
        con.execute("INSERT INTO canonical_rules VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,topic,direction,kind,title,text,
          canonical_confidence(members),len(unique_passages),src["vidian"],src["moxing"],len(src),cross,
          json.dumps(all_atoms,ensure_ascii=False),rep["passage_id"],rulehash,"atomic-semantic-e5-hnsw-v2",round(max_sim,6)))
        con.execute("INSERT INTO canonical_fts(rowid,title,topic,direction,text) VALUES(?,?,?,?,?)",(rid,title,topic,direction,text))
        ranked=[]
        for gi in mids:
            x=atomic[gi]; sim=1.0 if gi==rep_i else edge_sim.get((min(gi,rep_i),max(gi,rep_i)),float(emb[gi]@emb[rep_i]))
            ranked.append((0.58*x["confidence"]+0.27*x["source_quality"]+0.15*sim,sim,x))
        ranked.sort(reverse=True,key=lambda z:z[0]); passage_best={}
        for rank,(_,sim,x) in enumerate(ranked,1):
            con.execute("INSERT INTO canonical_atomic_evidence VALUES(?,?,?,?,?,?)",(rid,x["id"],x["passage_id"],x["source"],round(float(sim),6),rank))
            old=passage_best.get(x["passage_id"])
            if old is None or rank<old[0]: passage_best[x["passage_id"]]=(rank,sim,x)
        ev_rank=0
        for _,(rank,sim,x) in sorted(passage_best.items(),key=lambda kv:kv[1][0]):
            ev_rank+=1
            con.execute("INSERT INTO canonical_evidence VALUES(?,?,?,?,?,?,?,?)",(rid,x["passage_id"],x["source"],x["evidence_id"],x["url"],
              x["confidence"],round(float(sim),6),ev_rank))
        canon_ids.append(rid)
    con.commit()

    canon_ids_arr=np.asarray(canon_ids,dtype="int64")
    rule_rows=[dict(r) for r in con.execute("SELECT id,topic,direction,canonical_text FROM canonical_rules ORDER BY id")]
    canon_emb=encode(model,[r["canonical_text"] for r in rule_rows],batch_size=128)
    np.save(out/"canonical_v2_vectors.npy",canon_emb,allow_pickle=False); np.save(out/"canonical_v2_ids.npy",canon_ids_arr,allow_pickle=False)
    joblib.dump({"model_id":model_id,"prefix_query":"query: ","prefix_passage":"passage: ","dimensions":int(dim)},
      out/"canonical_v2_semantic.joblib",compress=3)

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import Normalizer
    from sklearn.decomposition import TruncatedSVD
    runtime_docs=[" ".join([r["topic"],r["direction"],r["canonical_text"]]) for r in rule_rows]
    runtime_vec=TfidfVectorizer(strip_accents="unicode",ngram_range=(1,2),min_df=2,max_df=.98,max_features=70000,sublinear_tf=True)
    RX=runtime_vec.fit_transform(runtime_docs); runtime_dims=min(128,RX.shape[0]-1,RX.shape[1]-1)
    runtime_svd=TruncatedSVD(runtime_dims,random_state=31,n_iter=7); runtime_norm=Normalizer(copy=False)
    runtime_D=runtime_norm.fit_transform(runtime_svd.fit_transform(RX)).astype("float32")
    np.save(out/"canonical_vectors.npy",runtime_D,allow_pickle=False); np.save(out/"canonical_ids.npy",canon_ids_arr,allow_pickle=False)
    joblib.dump({"vectorizer":runtime_vec,"svd":runtime_svd,"normalizer":runtime_norm},out/"canonical_semantic.joblib",compress=3)

    by_topic=collections.defaultdict(list)
    for pos,r in enumerate(rule_rows): by_topic[r["topic"]].append(pos)
    conflict_id=conflicts=0
    for topic,positions in by_topic.items():
        if len(positions)<2: continue
        local=canon_emb[np.asarray(positions,dtype="int64")]; idx=faiss.IndexHNSWFlat(dim,32,faiss.METRIC_INNER_PRODUCT)
        idx.hnsw.efConstruction=80; idx.hnsw.efSearch=64; idx.add(local); k=min(12,len(positions)); sims,neigh=idx.search(local,k)
        for ap,ga in enumerate(positions):
            ra=rule_rows[ga]
            for n in range(1,k):
                bp=int(neigh[ap,n])
                if bp<0: continue
                gb=positions[bp]
                if gb<=ga: continue
                rb=rule_rows[gb]
                if ra["direction"]==rb["direction"]: continue
                sim=float(sims[ap,n])
                if sim<0.86: continue
                lex=jaccard(token_set(ra["canonical_text"]),token_set(rb["canonical_text"]))
                if lex<0.12 and sim<0.90: continue
                conflict_id+=1; conflicts+=1; a,b=sorted((ra["id"],rb["id"]))
                con.execute("INSERT OR IGNORE INTO canonical_conflicts VALUES(?,?,?,?,?,?,?,?,?)",(conflict_id,a,b,topic,round(sim,6),
                  ra["direction"],rb["direction"],"review","High semantic similarity with different directive directions"))
    con.commit()

    v1con=sqlite3.connect(v1/"writing_brain.sqlite"); v1con.row_factory=sqlite3.Row
    v1_rules=[dict(r) for r in v1con.execute("SELECT id,topic,direction,canonical_text,evidence_count,cross_source FROM canonical_rules ORDER BY id")]
    v1con.close(); v1_emb=encode(model,[r["canonical_text"] for r in v1_rules],batch_size=128)
    v2_rules=[dict(r) for r in con.execute("SELECT id,topic,direction,canonical_text,evidence_count,cross_source FROM canonical_rules ORDER BY id")]
    q_emb=query_encode(model,[q for _,q in BENCH_QUERIES])
    def evaluate(rules,vectors):
        topic_map=collections.defaultdict(list)
        for i,r in enumerate(rules): topic_map[r["topic"]].append(i)
        relevance=[]; redundancy=[]; density=[]; cross_hit=[]; hit_counts=[]
        for qi,(topic,_) in enumerate(BENCH_QUERIES):
            pool=topic_map.get(topic) or list(range(len(rules))); vv=vectors[np.asarray(pool,dtype="int64")]; scores=vv@q_emb[qi]
            order=np.argsort(-scores)[:10]; chosen_pos=[pool[int(x)] for x in order]; chosen=[rules[p] for p in chosen_pos]
            hit_counts.append(len(chosen)); relevance.append(float(np.mean([scores[int(x)] for x in order])) if len(order) else 0.0)
            if len(chosen_pos)>1:
                m=vectors[np.asarray(chosen_pos,dtype="int64")]; simm=m@m.T; tri=simm[np.triu_indices(len(chosen_pos),k=1)]
                redundancy.append(float(np.mean(tri)) if len(tri) else 0.0)
            else: redundancy.append(0.0)
            density.append(float(np.mean([max(1,int(x["evidence_count"] or 1)) for x in chosen])) if chosen else 0.0)
            cross_hit.append(float(any(int(x["cross_source"] or 0) for x in chosen)))
        return {"queries":len(BENCH_QUERIES),"avg_hits":round(float(np.mean(hit_counts)),4),
          "mean_relevance":round(float(np.mean(relevance)),6),"mean_redundancy":round(float(np.mean(redundancy)),6),
          "mean_evidence_density":round(float(np.mean(density)),6),"cross_source_hit_rate":round(float(np.mean(cross_hit)),6)}
    bench_v1=evaluate(v1_rules,v1_emb); bench_v2=evaluate(v2_rules,canon_emb)
    rel_delta=bench_v2["mean_relevance"]-bench_v1["mean_relevance"]
    red_delta=bench_v1["mean_redundancy"]-bench_v2["mean_redundancy"]
    density_gain=bench_v2["mean_evidence_density"]-bench_v1["mean_evidence_density"]
    cross_gain=bench_v2["cross_source_hit_rate"]-bench_v1["cross_source_hit_rate"]
    score=2.2*rel_delta+1.4*red_delta+0.12*density_gain+0.25*cross_gain

    passage_evidence_coverage=con.execute("SELECT count(DISTINCT passage_id) FROM canonical_evidence").fetchone()[0]
    atomic_mapped=con.execute("SELECT count(*) FROM canonical_atomic_evidence").fetchone()[0]
    canonical_cjk=sum(bool(ZH.search(r["canonical_text"] or "")) for r in v2_rules)
    promotion_pass=(passage_evidence_coverage==21210 and atomic_mapped==len(atomic) and canonical_cjk==0 and cross_rules>=10
      and bench_v2["mean_relevance"]>=bench_v1["mean_relevance"]-0.015
      and (bench_v2["mean_redundancy"]<=bench_v1["mean_redundancy"]-0.01 or bench_v2["mean_evidence_density"]>=bench_v1["mean_evidence_density"]+0.05)
      and score>0)
    qa={"schema":"webnovel-writing-brain-semantic-v2-qa","passages_total":21210,"atomic_rules":len(atomic),
      "passage_atomic_coverage":passage_atomic_coverage,"canonical_rules":len(v2_rules),"atomic_collapsed":len(atomic)-len(v2_rules),
      "multi_atomic_rules":multi_rules,"cross_source_rules":cross_rules,"accepted_merge_edges":merge_edges,"accepted_cross_edges":cross_edges,
      "semantic_candidates_checked":candidates,"max_cluster_size":max_cluster,"conflict_candidates":conflicts,"canonical_cjk_rows":canonical_cjk,
      "model_id":model_id,"embedding_dimensions":int(dim),"runtime_semantic_dimensions":int(runtime_dims),
      "benchmark":{"v1":bench_v1,"v2":bench_v2,"relevance_delta":round(rel_delta,6),"redundancy_improvement":round(red_delta,6),
        "evidence_density_gain":round(density_gain,6),"cross_source_hit_rate_gain":round(cross_gain,6),"promotion_score":round(score,6)},
      "promotion_pass":bool(promotion_pass),"contract":"Semantic V2 preserves all source passages, atomizes craft guidance, merges only same-topic/same-direction semantic equivalents, records opposite-direction semantic conflicts, and is promoted only if the shared benchmark beats or safely matches Canonical V1."}
    (out/"semantic_v2_qa.json").write_text(json.dumps(qa,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    mp=out/"manifest.json"; manifest=json.loads(mp.read_text(encoding="utf-8")); manifest.update({"schema":"webnovel-writing-brain-semantic-v2",
      "knowledge_mode":"atomic-semantic-canonical-first","default_retrieval_layer":"canonical_rules","evidence_fallback":"passages",
      "semantic_v2":{"atomic_rules":len(atomic),"canonical_rules":len(v2_rules),"cross_source_rules":cross_rules,"conflict_candidates":conflicts,
        "model_id":model_id,"promotion_pass":bool(promotion_pass),"merge_policy":"Atomic Vietnamese craft statements are embedded with multilingual-e5-small and clustered with HNSW only inside identical topic + directive direction. Same-source and cross-source merges use different conservative thresholds plus lexical/craft-atom agreement. Opposite directions are never merged; high-similarity pairs are recorded as conflicts for review."}})
    mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); con.execute("PRAGMA optimize"); con.close()
    print(json.dumps(qa,ensure_ascii=False,indent=2))


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--base",required=True); ap.add_argument("--v1",required=True); ap.add_argument("--out",required=True)
    ap.add_argument("--model-id",default="intfloat/multilingual-e5-small"); ap.add_argument("--neighbors",type=int,default=24); a=ap.parse_args()
    build(a.base,a.v1,a.out,a.model_id,a.neighbors)


if __name__ == "__main__": main()
