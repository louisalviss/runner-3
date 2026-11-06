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


## Website/Product DD — source-first review before BUILD_DD

The existing SeoTrends product-intent and Exact SERP scanner remains the source
owner. After its candidate passes the source gate, the reviewer must **open the
actual public site**, not merely copy Semrush keywords or use the site's title.
Review only a few promising products; do not run a new broad website crawler,
schedule, paid agent, or keyword discovery loop.

Inspect the live canonical homepage, a page demonstrating features/real workflow,
and a pricing/commercial or demo page. Include each HTTPS URL, a short concrete
finding, and an evidence reference that an independent reviewer can retrieve.
When login/demo prevents product use, distinguish marketing claims from
observed functionality and leave the unobserved step unverified. An access
challenge is BLOCKED/needs source-owned browser recovery, not proof of no market.

Store the bounded assessment as optional `site_product_review` on the **same
candidate** in the date-scoped `*-semantic-business-dd.json` record. Reuse
the current semantic record and review workflow, not a second scanner/writer.
The record includes:

- `status: REVIEWED`, `domain`, `user_job`, and `pages` (3–6 same-domain
  HTTPS URL records typed `home`, `product`, `pricing` or `demo`,
  with concrete `finding` and retrievable `source_ref`);
- `buyer`, `product_type`, `actual_workflow`, `actual_output`,
  `monetization`, `replication_risk`;
- `proposed_small_utility` and `small_utility_feasibility: SUPPORTED`
  only if a bounded product/output can reasonably be delivered; otherwise
  leave it `NOT_SUPPORTED` or `UNKNOWN`.

The source domain and user job must match the candidate and its existing
`candidate_wedge`. Before a candidate may enter manual `BUILD_DD`, the
existing four sourced business checks *and* the website/product review must
pass. Failure to collect enough site pages → `DEFER` with exact missing
evidence; a complex enterprise product is not declared buildable because
its source domain has traffic. This remains review eligibility, not BUILD
approval or evidence that an asserted `verified: true` is true.

The source-owned scanner's `product_intent_checked` flag, terminal verdict,
and same-day Semrush/SERP evidence take precedence over reviewer claims.
A review is not an automatic producer of verified business evidence: the
reviewer must inspect real page content, verify references, buyer, workflow,
pricing, differentiator, and executable scope before marking `REVIEWED`.

Example reviewed sites from 2026-11-06 (public marketing evidence only):
- Planera: `https://www.planera.io/`, `/features`, `/pricing` — CPM,
  construction scheduling, risk simulation, custom sales pricing;
  full-product clone is not a bounded utility.
- UrbiStat: `https://www.urbistat.com/ugeo-software-geomarketing/` —
  geography/data-intensive business; bespoke subscriptions and demo.
  An independently funded narrow product gap is not established.
- PDF24: `https://tools.pdf24.org/en/faq`, `/create-pdf` —
  unrestricted free PDF toolkit financed by ads; high traffic alone
  provides no replicable new-product advantage.

No real source-backed `QUALIFIED_DD` producer has been accepted. Until it
exists and is independently reviewed, the live result stays `DEFER`.
No automatic site fetching, Semrush query, data overwrite, BUILD/BUY, or
production promotion is added by this PR.

Run `python3 -m unittest -v test_build_buy_decision` from
`jobs/opportunity-daily`; offline historical replay must preserve source
counts, BLOCKED semantics, and zero automated approvals.

## Flippa asset-site DD (unified Acquisition Idea Radar)

The Flippa lane and SeoTrends lane share one daily **BUILD-versus-BUY**
qualification report, but their website evidence gates differ.

For Flippa, discovery and listing-detail price/profit/traffic claims are only
cheap DD prefilters. An eligible listing remains `SITE_DD_PENDING` (shown in
`study_queue`, never silently dropped) until the operator has confirmed the
**exact listing ID → actual asset domain** in authenticated or current direct
listing evidence and inspected the real website. A guessed domain based on
title/brand similarity is not evidence.

Use the *existing* authenticated Flippa listing detail source and the existing
`flippa-deep-YYYYMMDD.json` record for listing-bound enrichment. Fields on
that same detail record, only after source verification:

- `verified_asset_domain`, `asset_domain_verified: true`,
  `asset_domain_source_kind: AUTHENTICATED_LIVE | DIRECT_LISTING_CURRENT`,
  `asset_domain_source_ref` (retrievable exact-listing evidence).
- `site_product_review` with `status: REVIEWED`, matching `listing_id`
  and `asset_domain`, `asset_type`, `buyer`, `asset_offer`,
  `actual_workflow`, `observed_conversion_path`,
  `monetization_mechanism`, `operator_dependencies`, `transfer_risks`,
  and 2–6 same-asset HTTPS `pages`. Include the homepage and at least
  one product/content/offer/monetization/pricing/demo page. Every page
  needs `url`, `kind`, a source-faithful `finding` and an independently
  checkable `source_ref`.
- Optional `independent_build_gap`: matching `user_job` plus four
  separate reviewable claims `matched_keyword`, `exact_serp_gap`,
  `small_utility_scope`, `revenue_path`; each needs `verified: true`,
  `source_ref`, and concrete `finding`.

The daily merger copies **only the above allowlisted fields from a verified
direct-detail row** into the Flippa candidate. No new scanner, token, browser,
timer, service or publisher is installed. Unknown/hidden buyer-domain mapping,
blocked product pages, inaccessible platform demos, or conflicting seller
claims remain `SITE_DD_PENDING`, with exact missing evidence. This is a
source-evidence contract, **not** a claim that automated website inspection
is already running.

Flippa BUY DD may begin *only after* the verified website review, and still
needs independent seller processor accounting, GA/GSC, ownership rights,
traffic mix, asset/domain transfer, recurring costs, current listing status,
and total transaction price. Flippa BUILD DD also requires independent
keyword-to-underserved-task/feasibility/pricing evidence; copying the asset
or believing seller traffic is insufficient. `DUAL_DD` requires both gates.
Neither DD category grants permission to bid, contact sellers, sign an NDA,
purchase, launch a product or promote to production.

Example **not verified asset identity**: Flippa listing ID `13524796`
is titled "Salon Home"; a matching-name public site
`https://salon-home.com/` offers home/habitat editorial and paid
visibility placements, but similarity is not identity proof. Its public
site describes more than 40,000 monthly readers and lists packages from
€99/€149, while the historical Flippa detail snapshot lists 439 monthly
pageviews and the card reports $253 monthly profit. These are different
surfaces/metric definitions, **not independently reconciled**. Do not mark
this listing as `BUY_DD` until the exact asset, traffic period/definition,
seller processor data and sale terms have been verified.

Offline replay of the cached 2026-11-05 input changes its prior one
Flippa `DUAL_DD` into `SITE_DD_PENDING`; the seven SeoTrends
candidates stay `DEFER`. All raw source records remain unchanged;
`approved_buy=0`, `approved_build=0`. The new flag carries evidence
for manual review; it cannot manufacture provenance or verify payment data.


## Flippa public website capture — source-backed browser stage (PR #530)

The existing Flippa authenticated detail owner `flippa_deep_daily.py` now performs
a **bounded post-detail capture** when the exact current Flippa listing contains
one unambiguous, explicitly labeled external "Visit Website" / "Website" link.
It records the URL, source-linked domain and anchor fingerprint in the SAME
`flippa-deep-YYYYMMDD.json` record. No title guessing and no confidential/NDA
domain recovery. Multiple distinct candidate domains or no labeled website
link produce **no verified asset identity**.

After the authenticated Flippa browser context is closed, a single
Guardian-owned *public* CDP worker (`/usr/local/bin/vps-cdp-job`) may inspect
**one verified asset per daily run**, up to two same-domain HTTPS public pages
(home and best matching product, pricing, services or advertising page).
The worker has separate transient proxy-backed identity and browser slot,
no sharing of Flippa cookies, a bounded timeout, public DNS/IP checks, and
cleanup of its own temporary job/result workspaces. Failed/blocked pages do
not rewrite the original listing evidence. The linked domain must match the
final retrieved public-page domain; redirects elsewhere fail closed.

Captured public evidence is `site_product_review.status:
CAPTURED_PUBLIC_PENDING_REVIEW` (or `PARTIAL_PUBLIC_CAPTURE` /
`PUBLIC_CAPTURE_BLOCKED`). It includes exact URLs, observed title and
bounded page-text excerpt, content SHA256, listing ID and local source
pointers; `semantic_review_required: true` and
`financials_independently_verified: false`. **Do not** change this
automatically to `REVIEWED`. The existing strict BUY/BUILD gates
intentionally need independent semantic inspection, source/provenance
and financial verification. The daily report exposes verified domain,
page count and capture status while keeping such listings in
`SITE_DD_PENDING`.

Also, `flippa_semrush_bridge.py` no longer infers a domain for provider
queries from a listing title. Semrush cross-check only uses source-proven
asset identity in the direct verified listing. Cached legacy cross-check
records do not establish ownership.

Offline controls: exact listing ID, labeled anchor, disallowed ambiguous
external links and unsafe URL, 2-page bounds, off-domain redirect, incomplete
capture, no automatic BUY upgrade, and existing backup/source cases.
GitHub Actions `Opportunity Daily Qualification` checks qualification,
daily synthesis, Flippa detail and Semrush bridge tests together.

Implementation lives in Draft PR #530; no production promotion,
automatic bid, buyer account mutation, extra scanner/timer or separately
owned writer was introduced. After CI, acceptance still requires an observed
live listing-to-website identity and public material capture, independent
review, authorized merge/deploy and fresh report readback.


### 2026-11-06 live acceptance note — public listing is not authenticated

Read-only live smoke against exact Flippa listing IDs 13524796 (Salon Home) and
14720037 (StarsVeins) on the existing persistent profile returned HTTP 200,
challenge NONE and correct listing URL, but the visible page header had
`Log In` / `Sign Up` and no expected buyer-account marker. Listing content
was readable, yet the profile's authenticated state was **not** verified.
Neither listing exposed a unique, explicit external asset Website/Visit
Website anchor in the inspected DOM. Therefore neither may be credited with
an authenticated site identity nor promoted beyond `SITE_DD_PENDING`.

The source reader now records `session_auth_state` and sets
`asset_domain_source_kind` to `AUTHENTICATED_LIVE` **only** when the
expected authenticated account marker is visible; otherwise any exact
public listing-link evidence would be `DIRECT_LISTING_CURRENT`. HTTP 200,
a title matching the listing, and challenge NONE alone are not login proof.

An isolated live public CDP smoke of the independent, matching-name site
timed out at the existing Resource Guardian-owned wrapper's 60-second
caller limit; no public material was accepted from that run. Temporary
job/results were cleaned up and a subsequent read-only lock check found
no lingering smoke-job process or lock. The precise timeout cause is not
confirmed. Do not substitute this failed smoke for a successful 2-page
capture, alter Guardian or credentials, or change the production browser
policy to force acceptance. The next live acceptance requires restored
authorized Flippa authentication (or a clearly evidenced public direct
asset link), a successful Guardian-admitted public read, source SHA
verification, and a human product/monetization review.
