#!/usr/bin/env python3
"""Resolve Context V2.2 review relations with multilingual NLI.

This layer never reclusters rules or changes retrieval ranking. It only revisits the
V2.2 relations whose status is `review`, stores bidirectional NLI probabilities,
and promotes a pair to true_conflict / conditional / complementary / direction_error
only when confidence gates are satisfied. Ambiguous pairs remain review.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import shutil
import sqlite3
from pathlib import Path

MODEL_ID = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
MODEL_REVISION = "main"
EXPECTED_RULES = 16697
EXPECTED_RELATIONS = 26320
EXPECTED_REVIEW = 2494


def _load_json(s):
    try:
        return json.loads(s or "[]")
    except Exception:
        return []


def _label_map(config):
    out = {}
    for i, label in (config.id2label or {}).items():
        low = str(label).lower()
        if "contrad" in low:
            out["contradiction"] = int(i)
        elif "neutral" in low:
            out["neutral"] = int(i)
        elif "entail" in low:
            out["entailment"] = int(i)
    if len(out) != 3:
        out = {"contradiction": 0, "neutral": 1, "entailment": 2}
    return out


def _infer_batches(model, tokenizer, pairs, batch_size=20, max_length=256):
    import torch

    lm = _label_map(model.config)
    results = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(pairs), batch_size):
            chunk = pairs[start : start + batch_size]
            enc = tokenizer(
                [x[0] for x in chunk],
                [x[1] for x in chunk],
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            logits = model(**enc).logits
            probs = torch.softmax(logits, dim=-1).cpu().tolist()
            for p in probs:
                results.append(
                    {
                        "contradiction": float(p[lm["contradiction"]]),
                        "neutral": float(p[lm["neutral"]]),
                        "entailment": float(p[lm["entailment"]]),
                    }
                )
    return results


def _decision(row, ab, ba):
    c_hi = max(ab["contradiction"], ba["contradiction"])
    c_lo = min(ab["contradiction"], ba["contradiction"])
    e_hi = max(ab["entailment"], ba["entailment"])
    e_lo = min(ab["entailment"], ba["entailment"])
    n_mean = (ab["neutral"] + ba["neutral"]) / 2.0
    c_mean = (ab["contradiction"] + ba["contradiction"]) / 2.0
    e_mean = (ab["entailment"] + ba["entailment"]) / 2.0
    core = float(row["core_jaccard"] or 0.0)
    sim = float(row["similarity"] or 0.0)
    context_a = bool(_load_json(row["context_a"]))
    context_b = bool(_load_json(row["context_b"]))
    contextual = context_a or context_b
    mismatch = bool(row["mismatch_a"] or row["mismatch_b"])

    # Strong symmetric contradiction: same proposition, genuinely opposite claims.
    if c_hi >= 0.82 and c_lo >= 0.50 and (core >= 0.12 or sim >= 0.92):
        if contextual and (context_a != context_b or float(row["context_overlap"] or 0) < 0.50):
            return "conditional", min(0.99, 0.56 + 0.30 * c_mean + 0.10 * sim), "NLI finds contradiction, but application context is asymmetric; preserve as conditional alternatives."
        return "true_conflict", min(0.99, 0.60 + 0.32 * c_mean + 0.06 * sim), "Bidirectional multilingual NLI strongly supports contradiction on the same proposition."

    # Strong paraphrase/entailment: V2.2 review was conservative, not a conflict.
    if e_hi >= 0.90 and c_hi <= 0.18:
        if mismatch and (e_lo >= 0.45 or core >= 0.30):
            return "direction_error", min(0.99, 0.62 + 0.28 * e_hi + 0.06 * sim), "NLI supports semantic alignment while a legacy negative direction label disagrees with Vietnamese text."
        return "complementary", min(0.99, 0.58 + 0.30 * e_hi + 0.05 * sim), "NLI supports entailment/paraphrase rather than contradiction."

    # Strongly neutral in both directions: related but neither entails nor contradicts.
    if n_mean >= 0.80 and c_hi <= 0.20:
        if contextual:
            return "conditional", min(0.96, 0.52 + 0.28 * n_mean + 0.05 * sim), "NLI is neutral and at least one rule is context-scoped; keep as contextual variants."
        return "complementary", min(0.96, 0.54 + 0.28 * n_mean + 0.05 * sim), "NLI is strongly neutral: the rules are adjacent/complementary, not contradictory."

    # Moderate contradiction with explicit context is safer as conditional than conflict.
    if contextual and c_hi >= 0.62 and (core >= 0.10 or sim >= 0.90):
        return "conditional", min(0.94, 0.48 + 0.30 * c_hi + 0.06 * sim), "NLI suggests opposition, but contextual markers make a scoped interpretation safer than a universal conflict."

    # High one-way entailment with low contradiction is enough to clear review conservatively.
    if e_hi >= 0.84 and c_hi <= 0.24 and (e_mean >= 0.52 or core >= 0.18):
        return "complementary", min(0.94, 0.50 + 0.28 * e_hi + 0.05 * sim), "NLI indicates semantic support/overlap without credible contradiction."

    return "review", max(c_hi, e_hi, n_mean), "NLI confidence is insufficient for automatic resolution; retain for human/LLM review."


def _sanity(model, tokenizer):
    pairs = [
        ("Nên thể hiện tính cách nhân vật qua hành động.", "Tính cách nhân vật nên được thể hiện bằng hành động."),
        ("Không nên giải thích dài dòng thế giới ngay chương đầu.", "Nên giải thích thật chi tiết thế giới ngay chương đầu."),
        ("Khi vào cao trào, có thể tăng nhịp kể.", "Ở các đoạn bình thường, nhịp kể có thể chậm hơn."),
    ]
    fwd = _infer_batches(model, tokenizer, pairs, batch_size=3)
    return {
        "paraphrase_entailment": round(fwd[0]["entailment"], 6),
        "explicit_contradiction": round(fwd[1]["contradiction"], 6),
        "context_pair_neutral": round(fwd[2]["neutral"], 6),
    }


def build(source, outdir, model_id=MODEL_ID, batch_size=20):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    src = Path(source)
    out = Path(outdir)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)
    con = sqlite3.connect(out / "writing_brain.sqlite")
    con.row_factory = sqlite3.Row

    assert con.execute("select count(*) from canonical_rules").fetchone()[0] == EXPECTED_RULES
    assert con.execute("select count(*) from canonical_relations").fetchone()[0] == EXPECTED_RELATIONS
    before = con.execute("select count(*) from canonical_relations where relation='review'").fetchone()[0]
    assert before == EXPECTED_REVIEW, before

    model = AutoModelForSequenceClassification.from_pretrained(model_id)
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    sanity = _sanity(model, tokenizer)

    rows = [dict(r) for r in con.execute(
        """
        SELECT cr.relation_id,cr.rule_a,cr.rule_b,cr.topic,cr.similarity,cr.confidence,
               cr.core_jaccard,cr.context_overlap,cr.reason,
               a.canonical_text text_a,b.canonical_text text_b,
               ca.context_markers_json context_a,cb.context_markers_json context_b,
               ca.legacy_direction_mismatch mismatch_a,cb.legacy_direction_mismatch mismatch_b
        FROM canonical_relations cr
        JOIN canonical_rules a ON a.id=cr.rule_a
        JOIN canonical_rules b ON b.id=cr.rule_b
        JOIN canonical_rule_context ca ON ca.rule_id=cr.rule_a
        JOIN canonical_rule_context cb ON cb.rule_id=cr.rule_b
        WHERE cr.relation='review'
        ORDER BY cr.relation_id
        """
    )]
    assert len(rows) == EXPECTED_REVIEW

    forward_pairs = [(r["text_a"], r["text_b"]) for r in rows]
    reverse_pairs = [(r["text_b"], r["text_a"]) for r in rows]
    fwd = _infer_batches(model, tokenizer, forward_pairs, batch_size=batch_size)
    rev = _infer_batches(model, tokenizer, reverse_pairs, batch_size=batch_size)

    con.executescript(
        """
        DROP TABLE IF EXISTS canonical_relation_nli;
        CREATE TABLE canonical_relation_nli(
          relation_id INTEGER PRIMARY KEY,
          pre_nli_relation TEXT NOT NULL,
          final_relation TEXT NOT NULL,
          model_id TEXT NOT NULL,
          contradiction_ab REAL NOT NULL, neutral_ab REAL NOT NULL, entailment_ab REAL NOT NULL,
          contradiction_ba REAL NOT NULL, neutral_ba REAL NOT NULL, entailment_ba REAL NOT NULL,
          decision_confidence REAL NOT NULL,
          decision_reason TEXT NOT NULL
        );
        CREATE INDEX idx_crn_final ON canonical_relation_nli(final_relation,decision_confidence DESC);
        """
    )

    decisions = collections.Counter()
    for row, ab, ba in zip(rows, fwd, rev):
        final, conf, reason = _decision(row, ab, ba)
        decisions[final] += 1
        con.execute(
            "INSERT INTO canonical_relation_nli VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["relation_id"], "review", final, model_id,
                round(ab["contradiction"], 7), round(ab["neutral"], 7), round(ab["entailment"], 7),
                round(ba["contradiction"], 7), round(ba["neutral"], 7), round(ba["entailment"], 7),
                round(float(conf), 7), reason,
            ),
        )
        if final != "review":
            con.execute(
                "UPDATE canonical_relations SET relation=?, confidence=?, reason=? WHERE relation_id=?",
                (final, round(float(conf), 7), "V2.3 NLI: " + reason, row["relation_id"]),
            )
    con.commit()

    after = con.execute("select count(*) from canonical_relations where relation='review'").fetchone()[0]
    final_counts = dict(con.execute("select relation,count(*) from canonical_relations group by relation order by relation").fetchall())
    nli_rows = con.execute("select count(*) from canonical_relation_nli").fetchone()[0]
    changed_nonreview = con.execute(
        """select count(*) from canonical_relation_nli n join canonical_relations r using(relation_id)
           where n.pre_nli_relation!='review'"""
    ).fetchone()[0]
    exact_conflict = con.execute(
        """select count(*) from canonical_relations cr
           join canonical_rules a on a.id=cr.rule_a join canonical_rules b on b.id=cr.rule_b
           where cr.relation='true_conflict' and lower(trim(a.canonical_text))=lower(trim(b.canonical_text))"""
    ).fetchone()[0]

    resolved = before - after
    resolved_rate = resolved / before
    overall_review_rate = after / EXPECTED_RELATIONS
    sanity_pass = (
        sanity["paraphrase_entailment"] >= 0.45
        and sanity["explicit_contradiction"] >= 0.45
    )
    promotion = (
        nli_rows == EXPECTED_REVIEW
        and changed_nonreview == 0
        and exact_conflict == 0
        and resolved_rate >= 0.45
        and overall_review_rate <= 0.055
        and sanity_pass
    )

    qa = {
        "schema": "webnovel-writing-brain-nli-v2.3-qa",
        "model_id": model_id,
        "rules_total": EXPECTED_RULES,
        "relations_total": EXPECTED_RELATIONS,
        "review_before": before,
        "review_after": after,
        "review_resolved": resolved,
        "review_resolved_rate": round(resolved_rate, 6),
        "overall_review_rate": round(overall_review_rate, 6),
        "nli_decisions": dict(decisions),
        "final_relations": final_counts,
        "nli_rows": nli_rows,
        "nonreview_rows_touched": changed_nonreview,
        "exact_true_conflict_sanity_failures": exact_conflict,
        "model_sanity": sanity,
        "promotion_pass": bool(promotion),
        "contract": "V2.3 runs bidirectional multilingual NLI only on the 2,494 unresolved V2.2 review pairs, preserves all rules/evidence/ranking, records every NLI probability, auto-resolves only high-confidence cases, and leaves ambiguous pairs as review.",
    }
    (out / "nli_v2_3_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    mp = out / "manifest.json"
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    manifest["schema"] = "webnovel-writing-brain-nli-v2.3"
    manifest["knowledge_mode"] = "semantic-canonical-context-nli-first"
    manifest["nli_v2_3"] = {
        "model_id": model_id,
        "review_before": before,
        "review_after": after,
        "decisions": dict(decisions),
        "promotion_pass": bool(promotion),
    }
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    con.execute("pragma optimize")
    con.close()
    print(json.dumps(qa, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-id", default=MODEL_ID)
    ap.add_argument("--batch-size", type=int, default=20)
    a = ap.parse_args()
    build(a.source, a.out, a.model_id, a.batch_size)


if __name__ == "__main__":
    main()
