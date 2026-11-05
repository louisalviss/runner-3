# Local Search Intent — additional Deep DD review (not a scanner)

This is a **bounded evidence-only review** attached to the existing BUILD
qualification in `build_buy_decision.py`. The discovery, Semrush, product
keyword, Exact SERP, and Flippa source owners remain unchanged.

## When to use

Only after source-owned Semrush and Exact SERP have completed, and the
candidate has passed the existing `product_intent_checked` gate. A source
outage is `BLOCKED`, never negative demand. Do not run extra queries or
launch a keyword-first scanner to populate this field.

Append an optional `local_search_intent` object to an existing per-domain
record in the date-scoped `*-semantic-business-dd.json` evidence:

```json
{
  "local_search_intent": {
    "markets": [{
      "country": "ID",
      "language": "id",
      "native_keyword": "dari hp ke laptop",
      "literal_translation_keyword": "transfer dari pc",
      "native_volume": 3600,
      "literal_translation_volume": 20,
      "keyword_source_ref": "source-export-identity-and-hash",
      "serp_source_ref": "exact-country-SERP-run-identity-and-hash",
      "serp_checked_at": "2026-10-20",
      "serp_result_urls": ["https://example.org/1", "https://example.org/2", "https://example.org/3", "https://example.org/4", "https://example.org/5"],
      "matches_product_intent": true,
      "unmet_need": "The search results omit a crucial user task and destination."
    }]
  }
}
```

Values above are **illustrative**: they are not live data or a verified
finding. Use source-local identifiers and hashes; keep raw Semrush/SERP
exports in the existing source-owned VPS evidence storage, not Dropbox.

The review screens for a country/language, a native phrase differing from a
literal translation, positive *relative* local volume, product intent,
at least five distinct HTTPS SERP result URLs, a dated query, independent
source references, and a specific unmet-need explanation. Evidence is capped
at eight markets per candidate. It does **not** itself verify that an
operator actually executed either provider query.

## Semantics

- `NOT_REVIEWED`: no usable localized intake.
- `UPSTREAM_INTENT_UNVERIFIED`: product-intent gate is not met.
- `EVIDENCE_INCOMPLETE`: locale, country SERP, provenance or user-gap evidence missing.
- `REVIEW_READY`: a candidate for independent manual review, **not a validated gap**.
- `review_priority=EVIDENCE_REVIEW_ONLY` never promotes `BUILD`,
  changes a terminal `DROP`/`BLOCKED`, or overrides semantic DD.
- `approved_build=0`, `approved_buy=0`, the cap and source-owned
  provider retry controls are unchanged.
- Do not infer actual GSC clicks, conversions, ranking potential, or
  available spend from Semrush modelled volume.

## Validation

```bash
cd jobs/opportunity-daily
python3 -m unittest -v test_build_buy_decision
```

The current live run is independent of this change; historical/daily
snapshots remain immutable. Adoption requires reviewed source evidence
and acceptance of the PR before any deployment.

## Four-part commercial wedge gate (PR #530)

For a candidate originating in the existing SeoTrends/source-owner run, Exact
SERP verification is a **prerequisite**, not a business opportunity. A source
domain's organic traffic is not evidence that a new product can win clicks.

`build_buy_decision.py` now requires all of these before a SeoTrends candidate
can even enter `BUILD_DD` (manual DD shortlist):

1. A matched source domain and a valid date-scoped semantic business-review
   record with `semantic_verdict: QUALIFIED_DD`.
2. A concrete customer `user_job`, `query_cluster`, and `target_market`
   traceable to that same source candidate.
3. Four separately explained, source-referenced findings under
   `candidate_wedge`: `commercial_demand`, `underserved_exact_serp`,
   `bounded_build_scope`, and `credible_monetization`. Each needs
   `verified: true`, `evidence_ref`, and a substantive `finding`.
4. Source provider PASS, source terminal WATCH, `product_intent_checked: true`,
   and `serp_gate` in `SERP_DD_PASS` or `WATCH_COMPETITION`. Source BLOCKED,
   DROP, stale dates and missing input fail closed.

Example **shape only** (do not copy these placeholders into live evidence):

```json
{
  "domain": "candidate.example",
  "terminal_verdict": "WATCH",
  "semantic_verdict": "QUALIFIED_DD",
  "product_intent_checked": true,
  "candidate_wedge": {
    "user_job": "A precise customer task and its expected output",
    "query_cluster": "source-linked exact keyword cluster",
    "target_market": "US/en",
    "commercial_demand": {
      "verified": true,
      "evidence_ref": "source-report-uri-and-identity",
      "finding": "Specific observed demand, not a source-domain traffic total"
    },
    "underserved_exact_serp": {
      "verified": true,
      "evidence_ref": "date-scoped-serp-evidence-identity",
      "finding": "Which output task the competitors fail to satisfy"
    },
    "bounded_build_scope": {
      "verified": true,
      "evidence_ref": "independent-product-feasibility-review",
      "finding": "Small differentiated utility and delivery scope"
    },
    "credible_monetization": {
      "verified": true,
      "evidence_ref": "pricing-or-first-party-wtp-evidence",
      "finding": "Proven monetization route and a bounded conversion model"
    }
  }
}
```

These string fields are **structured claims, not cryptographic proof**.
The reviewing operator must resolve the referenced source content, check dates,
keyword-to-task relevance, country SERP and source/competitor identity, and
reject self-referential, irrelevant, synthetic, or unaudited claims. `verified:
true` is not a substitute for independent evidence inspection.

The canonical `*-semantic-business-dd.json` reader is date-scoped. There is
currently **no verified automatic producer for these four evidence fields** in
the daily SeoTrends/Opportunity scan. This PR does not create a scanner,
provider query, automated semantic reviewer or writer. Absent a reviewed
source-linked record, the result is `DEFER` with
`next_gate: FOUR_PART_CANDIDATE_WEDGE_DD`; old `BUILD_DD` counts may fall to
zero. `DD_PENDING` only permits further manual due diligence, not BUILD/BUY.
A future producer requires its own independent provenance acceptance and
deployment review before use.

Run `python3 -m unittest -v test_build_buy_decision` from
`jobs/opportunity-daily`; offline historical replay must preserve source
counts, BLOCKED semantics, and zero automated approvals.
