# Article Forge report

- Score: **unassessed** (readiness)
- Evidence: **serp_snapshot_missing**
- Score meaning: Pre-SERP editorial readiness based only on deterministic checks and configured evidence; not a ranking or traffic prediction.
- Query: barbados elopement photography cost
- Publication status: **blocked**

## Pillars

- structure_extractability: 100.0/100
- eeat: unassessed
- linking: 100.0/100

## What to fix next

- **P1 — publish_gate:** Dateline freshness is WARN: current_month_year is 'August 2026'; current month is 'October 2026' Fix: Resolve this gate result, then regenerate or rerun check_article.py.
- **P1 — publish_gate:** Evidence-led brief is WARN: missing evidence-led editorial brief and reviewed page decision Fix: Resolve this gate result, then regenerate or rerun check_article.py.
- **P1 — publish_gate:** Final-draft claim coverage is WARN: missing versioned claim-to-sentence manifest; full human semantic review required Fix: Resolve this gate result, then regenerate or rerun check_article.py.
- **P1 — research_evidence:** No organic SERP snapshot was supplied, so intent, topical consensus, and entity coverage were not assessed. Fix: Collect a current serp_snapshot.json with at least five independent organic domains, then rerun the report.

## Gate checks

- **PASS** Config integrity: config has the required product, facts, pages, and tier fields
- **PASS** Facts freshness: verified_facts confirmed 26 day(s) ago
- **PASS** Claim verification ledger: no registry claims selected — final-draft manifest coverage is checked separately
- **PASS** Claim evidence registry: no registry claims used; final-draft coverage is checked separately
- **WARN** Dateline freshness: current_month_year is 'August 2026'; current month is 'October 2026'
- **PASS** Fabrication/placeholder gate: no placeholder/fabrication patterns found
- **PASS** Visible opening-function labels: no visible opening-function labels found
- **PASS** Internal planning artifacts: no internal planning artifacts found
- **PASS** H1 matches target query: H1 matches target query closely (100% word overlap)
- **PASS** Visible dateline: visible 'Last updated' dateline is present after the H1
- **PASS** Bare URLs (not Markdown links): no bare parenthetical URLs found
- **PASS** Coming-soon features: no configured coming-soon features mentioned
- **PASS** Word count: advisory length: 915 words; 700-1400 is a planning range for supporting, not a gate
- **PASS** Banned words: no banned words found
- **PASS** Structured element present: found a structured element (table)
- **PASS** Process structure: ordered steps not required by the reviewed reader task
- **PASS** Tier-gating mentions: tier-gated mentions carry nearby plan evidence
- **PASS** Structural repetition (heuristic): no obvious structural repetition detected (coarse heuristic — still worth a human skim)
- **WARN** Evidence-led brief: missing evidence-led editorial brief and reviewed page decision
- **WARN** Final-draft claim coverage: missing versioned claim-to-sentence manifest; full human semantic review required

## Human review required

- Confirm every claim, date, pricing or tier statement, and CTA against current first-party sources.
- Review originality, usefulness, voice, legal meaning, and any editorial image/alt text before publication.

## Limits

- An automated gate and score do not prove factual accuracy, originality, legal safety, indexing, or ranking.
- A SERP-parity score is evidence-relative to the supplied snapshot and is not a ranking probability.
