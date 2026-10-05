# Business Opportunity Research Ledger

Dedicated machine-state layer for cross-source business-opportunity research.

## Authority boundary

- **Projects Map + exact project canonical**: portfolio decision and current NEXT GATE.
- **Business Opportunity D1** (`runner3-business-opportunity`): normalized candidate identity, research-terminal state, evidence pointers/hashes, transition history.
- **Source-local systems**: raw/source evidence and specialist methodology.
- **Finance/Trading Opportunity Radar V2**: separate system; never use its `OPPORTUNITY_DB` here.

## Semantic ingestion rule

Raw scanner output must not write directly to this ledger. A write packet must declare:

```json
{
  "schema_version": 1,
  "semantic_synthesis": true,
  "synthesis_authority": "BUSINESS_OPPORTUNITY_RADAR"
}
```

Allowed synthesis authorities:

- `BUSINESS_OPPORTUNITY_RADAR`
- `PROJECT_AUTHORITY`
- `MARKET_VALIDATION`
- `MANUAL_RECONCILIATION`

Evidence records store only compact pointers/hashes and short notes. Raw text, full HTML, transcripts, and other large evidence payloads are rejected by the client.

## VPS client

Canonical client source:

`scripts/business_opportunity_ledger_client.py`

Live install:

`/usr/local/bin/business-opportunity-ledger`

It reads the existing credential-local `/etc/vps-control/runner3-core.env`; token contents are never printed.

Examples:

```bash
business-opportunity-ledger health

business-opportunity-ledger reconcile \
  --identity-type alias \
  --identity-value "growth ops" \
  --thesis-version growth-ops-v1

business-opportunity-ledger apply /path/to/semantic-packet.json --dry-run
business-opportunity-ledger apply /path/to/semantic-packet.json
```

The expected unchanged-project response is `decision=NO_RECHECK`; an unknown identity returns `NEW_CANDIDATE`.

## Packet skeleton

```json
{
  "schema_version": 1,
  "semantic_synthesis": true,
  "synthesis_authority": "BUSINESS_OPPORTUNITY_RADAR",
  "candidate": {
    "candidate_id": "example-candidate",
    "normalized_problem": "Exact economic/user problem",
    "thesis_version": "example-v1",
    "project_id": null,
    "status": "WATCH",
    "score": 8.1,
    "next_gate": "Specific real-world validation gate",
    "decision_reason": "Why the candidate is in this state",
    "source_lane": "BUSINESS_OPPORTUNITY_RADAR",
    "research_terminal": true,
    "research_terminal_at": "2026-10-05T00:00:00Z",
    "last_material_delta_at": "2026-10-05T00:00:00Z"
  },
  "identities": [
    {
      "identity_type": "alias",
      "identity_value": "example candidate",
      "source_lane": "BUSINESS_OPPORTUNITY_RADAR"
    }
  ],
  "evidence": [
    {
      "source_lane": "REDDIT",
      "source_ref": "reddit://thread-or-durable-ref",
      "evidence_type": "buyer_pain",
      "independence_group": "actor-or-source-group",
      "hard_signal": true,
      "direction": "SUPPORT",
      "observed_at": "2026-10-05T00:00:00Z",
      "evidence_hash": "sha256-or-stable-source-hash",
      "note": "Short decision-useful note only"
    }
  ],
  "reconcile_after": true
}
```
