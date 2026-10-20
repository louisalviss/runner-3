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
