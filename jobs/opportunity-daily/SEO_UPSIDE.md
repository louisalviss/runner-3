# SEO Upside — Acquisition/Flippa advisory (SHADOW)

Status: integrated into `jobs/opportunity-daily/opportunity_daily.py` after the
existing authenticated Flippa -> verified-domain -> Semrush cross-check lane.
No independent discovery, no provider calls, no buying or promotion.

## Why

Source: Oct 2026 SEO case-study review about improving an established,
already-authoritative commercial website. The optimization recipe
(technical, intent, content, internal links, link building) is not by itself
proof that ranking/headroom translates to upside on another asset.

The module looks for a **BUY-side diligence opportunity** rather than
launching a new SEO Radar scanner or assuming a SeoTrends domain is for sale.

## Input contract

- A Flippa listing identity and an independently verified domain from
  `flippa_semrush_bridge.domain_from_verified_listing`.
- A previously cached domain-matching Semrush JSON under
  `/var/lib/acquisition-radar-scan/flippa-sem-YYYYMMDD/<domain>.json`.
- Optional, separately audited, small local JSON
  `/var/lib/acquisition-radar-scan/seo-upside-evidence/<Flippa-ID>.json`.
  The file is NOT populated automatically. Supplying seller assertions as
  `verified=true` is contrary to this contract and does not constitute DD.

Example independent file:
```json
{
  "backlinks": {
    "verified": true,
    "source": "Ahrefs",
    "checked_at": "2026-10-17",
    "referring_domains": 120
  },
  "issues": [
    {
      "type": "intent_mismatch",
      "url": "https://example.com/tools/example-calculator",
      "verified": true
    }
  ]
}
```

The first screen identifies non-brand commercial page keywords at positions
4–15 with volume >=100, CPC >=0.5 and KD <=50, requiring >=2 distinct
keywords per page. These are heuristics, not a prediction of achievable rank,
CTR, SEO ROI, or cost to fix. Headroom index is NOT money.

Positive authority requires a dated independent backlink audit. Positive
fixable-gap evidence requires a verified page-specific issue.
Observed links may already exist: absence must be measured, not inferred.
A positive advisory still cannot approve BUY.

## Pipeline

`Flippa authenticated + public merge`
-> `verified direct listing + independently identified domain`
-> `existing bounded Semrush cross-check`
-> `seo_upside.attach (read-only)`
-> `qualification.candidates[*].evidence.seo_upside`
-> `qualification / CURRENT synthesis (original BUY/BUILD unchanged)`.

No source scanner change, no Flippa recrawl, no recurring extra Semrush
queries. If Flippa has no verified domains, status
`NO_VERIFIED_LISTING_DOMAIN` is expected, not an operational fault.

## Test protocol

`python3 -m unittest -v test_seo_upside test_build_buy_decision test_opportunity_daily test_daily_pipeline test_flippa_deep_daily test_daily_acceptance`

`python3 opportunity_daily.py --date 2026-10-17 --dry-run`

Fresh historical validation uses existing SeoTrends exports as **algorithm
test fixtures only**. They are never promoted to acquisition inventory.

Promotion beyond SHADOW needs outcome-based A/B evidence and explicit user
authorization. Keep `approved_buy=0`, `approved_build=0`, the buy cap,
and the source-owned scanner boundaries intact.
