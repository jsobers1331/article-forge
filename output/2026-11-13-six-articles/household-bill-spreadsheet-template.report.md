# Article Forge report

- Score: **unassessed** (readiness)
- Evidence: **serp_snapshot_missing**
- Score meaning: Pre-SERP editorial readiness based only on deterministic checks and configured evidence; not a ranking or traffic prediction.
- Query: household bill spreadsheet template
- Publication status: **ready_for_human_review**

## Pillars

- structure_extractability: 100.0/100
- eeat: unassessed
- linking: 100.0/100

## What to fix next

- **P1 — research_evidence:** No organic SERP snapshot was supplied, so intent, topical consensus, and entity coverage were not assessed. Fix: Collect a current serp_snapshot.json with at least five independent organic domains, then rerun the report.

## Gate checks

- **PASS** Config integrity: config has the required product, facts, pages, and tier fields
- **PASS** Facts freshness: verified_facts confirmed 0 day(s) ago
- **PASS** Claim verification ledger: all 5 claim(s) verified by the ledger
- **PASS** Claim evidence registry: 5 claim-evidence record(s) have source and verification metadata
- **PASS** Dateline freshness: current_month_year is current (November 2026)
- **PASS** Fabrication/placeholder gate: no placeholder/fabrication patterns found
- **PASS** Visible opening-function labels: no visible opening-function labels found
- **PASS** Internal planning artifacts: no internal planning artifacts found
- **PASS** H1 matches target query: H1 matches target query closely (100% word overlap)
- **PASS** Visible dateline: visible 'Last updated' dateline is present after the H1
- **PASS** Bare URLs (not Markdown links): no bare parenthetical URLs found
- **PASS** Coming-soon features: no configured coming-soon features mentioned
- **PASS** Word count: advisory length: 1395 words; 1000-2000 is a planning range for standard, not a gate
- **PASS** Banned words: no banned words found
- **PASS** Structured element present: found a structured element (table)
- **PASS** Process structure: target query does not signal a process article
- **PASS** Tier-gating mentions: tier-gated mentions carry nearby plan evidence
- **PASS** Structural repetition (heuristic): no obvious structural repetition detected (coarse heuristic — still worth a human skim)
- **PASS** Evidence-led brief: reader problem, action, original contribution, assets, limitation and page decision reviewed
- **PASS** Final-draft claim coverage: exact-draft manifest and deterministic provenance checks passed; human semantic review recorded, factual truth is not proven

## Human review required

- Confirm every claim, date, pricing or tier statement, and CTA against current first-party sources.
- Review originality, usefulness, voice, legal meaning, and any editorial image/alt text before publication.

## Limits

- An automated gate and score do not prove factual accuracy, originality, legal safety, indexing, or ranking.
- A SERP-parity score is evidence-relative to the supplied snapshot and is not a ranking probability.
