# AI Answer Substitution — mandatory BUY/BUILD DD gate

This is a **read-only evidence interpretation gate** within the existing
Acquisition / Idea Radar qualification and cumulative Flippa backlog. It is
not a new scanner, model, crawling task, provider API, marketplace writer,
seller contact, bid, or automated purchase/build approval.

## Problem and decision

Informational websites that generate ad revenue from answering standalone
questions can lose clicks when AI assistants or first-party official sites
answer the whole user job without a visit. The risk applies to both (a)
buying historical SEO traffic and (b) building a copycat content site.

A query/theme such as "school calendar" must **never** automatically trigger
a negative decision: some businesses complete real transactions, maintain
opt-in subscriptions, execute repeated critical workflows, control first-party
distribution, or provide proprietary licensed data that an assistant cannot
supply. Risk is determined from **reviewed candidate-specific evidence**,
not title, keyword, ranking, AI hype or unsupported traffic forecasts.

## Source-linked schema

Put a reviewed optional \`ai_substitution_review\` object on the *same* dated
candidate record as its existing site and business evidence, or place an
explicit policy override in \`ai_substitution_reviews.json\` for a human-checked
case. The overrides are version-controlled and effective no earlier than
their \`review_date\`, preserving historical replay.

\`\`\`json
{
  "status": "REVIEWED",
  "identity": "flippa:12345678",
  "review_date": "2026-11-12",
  "customer_job": "Complete a repeated, revenue-generating user workflow",
  "risk": "RESILIENT_WORKFLOW",
  "ai_answer_completes_customer_job": false,
  "revenue_depends_on_answer_pageviews": false,
  "resilience_basis": "TRANSACTION",
  "non_answer_value_source_checked": true,
  "reason": "Source-linked actual transaction and checkout functionality is reviewable.",
  "source_refs": [
    "https://example.com/checkout",
    "https://example.com/docs/payment-history"
  ]
}
\`\`\`

Accepted resilience bases: \`RECURRENT_WORKFLOW\`, \`TRANSACTION\`,
\`DIRECT_DISTRIBUTION\`, and \`PROPRIETARY_DATA\`. A robust review must
link to actual source pages and independently inspect them; setting
\`non_answer_value_source_checked=true\` or pasting fake URLs does not itself
prove that an outcome was executed or that customers paid. The source refs
above are a **shape example, not audited evidence**.

A reviewed answer-only risk uses \`risk: HIGH_ANSWER_SUBSTITUTION\`,
\`ai_answer_completes_customer_job: true\`,
\`revenue_depends_on_answer_pageviews: true\` and
\`resilience_basis: NONE_VERIFIED\` with candidate-specific source refs and
an explicit reason. This is a qualitative business risk assessment, not
a statistical claim that a specific site's revenue will drop by a given rate.

## Gate semantics

- \`HIGH\` reviewed risk: BUY=DROP, BUILD=DROP; carried backlog keeps listing
  as active/historical but marks \`AI_SUBSTITUTION_REJECTED\`. This **never**
  marks a listing SOLD/ENDED and does not erase source cards.
- \`UNREVIEWED\`, malformed, contradictory, or future-dated review:
  candidates cannot advance into actionable BUY/BUILD DD; remain study
  pending or deferred. Missing evidence is **not automatically proof of
  high risk**, and providers remain BLOCKED on actual source outages.
- \`RESILIENT\` reviewed evidence: the existing traffic, source, product,
  keyword, finance, transfer and monetization gates still apply. It may
  enter **manual DD only**, never BUY/BUILD approval.
- A repository-curated exact-identity override, once effective, takes
  precedence over untrusted listing-side assertions. Reversal requires a
  separately reviewed source update and code review.
- In \`qualify(...)\`, \`as_of=day\` makes historical replays deterministic.
  The source-owned Flippa cumulative backlog also applies \`as_of=day\`.
- Source histories and Dropbox daily CURRENT/History are not rewritten.
  No new parallel scheduler, scanner, or mutating business-data pipeline.

## Initial reviewed example

\`flippa:13095813\` SchoolCalendar.net — reviewed on 2026-11-12.
Direct calendar-date queries can be answered inside AI or by official
district websites; the advertised Ezoic pageviews and seller revenue have
not been independently verified as a durable distribution or transaction
moat. The reviewed strategic decision is to **reject both BUY and a copycat
BUILD**. The exact decision is linked to the direct listing, public site and
Dropbox research override in \`ai_substitution_reviews.json\`.

## Validation

\`\`\`bash
cd jobs/opportunity-daily
python3 -m unittest -v test_ai_substitution_gate test_build_buy_decision test_acquisition_backlog
\`\`\`

Review the source references and historical replay before a controlled
production rollout. Daily success only establishes policy *execution*; it
does not establish independent model judgements or a working automated
semantic business-DD producer. A future self-running reviewer/writer needs
its own source provenance and acceptance gate.
