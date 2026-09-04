# Measurement and feedback loop

Article Forge can prepare and gate a draft, but only published outcomes can
calibrate opportunity scoring. This workflow is provider-neutral: it accepts
exports and observations without treating any one metric as a ranking or
LLM-citation guarantee.

## Before publishing

Retain the opportunity record and final editorial receipt together. The receipt
should identify the exact query, page type, locale, canonical URL, demand
source and period, Serper cache key and retrieval timestamp, product facts and
claim-evidence records, original angle, unanswered question, limitations,
human reviewer, draft hash, and Article Forge commit.

Do not publish a candidate missing demand evidence, a five-domain SERP sample,
or the human claim/originality review. An all-PASS draft is a safe handoff,
not approval to publish.

## After publishing

Record one row per URL and observation period. Keep the source and period
attached to every metric:

| Field | Meaning |
|---|---|
| `url` | Canonical published URL |
| `query_or_cluster` | Target query or named query cluster |
| `observed_from`, `observed_to` | Measurement window |
| `impressions` | Search Console impressions, when available |
| `clicks` | Search Console clicks, when available |
| `ctr` | Search Console CTR, when available |
| `position` | Search Console average position, when available |
| `qualified_actions` | Defined downstream actions such as signup or inquiry |
| `conversions` | Business conversion count and attribution definition |
| `indexed` | Indexation result and check date |
| `llm_surface`, `citation_observed` | Engine/surface and observed citation status |
| `notes` | Edits, seasonality, product changes, or anomalies |

Search Console values describe the selected site's observed performance; they
are not market search volume. LLM citation observations are directional and
must name the engine, query, date, and surface. A missing citation is not proof
that an article is invisible.

## Review cadence and actions

- **Weekly for the first four weeks:** check indexation, technical errors,
  impressions, clicks, CTR, and qualified actions for new pages.
- **Monthly:** compare performance with the query cluster and record meaningful
  changes, not just rank snapshots.
- **Every 90 days or after a material product/search change:** re-run the SERP
  observation, re-attest product facts, and refresh the article if its sources,
  pricing, screenshots, or workflow claims changed.
- **After enough comparable observations:** recalibrate opportunity weights
  against qualified visits and conversions. Keep both the original and
  recalibrated score so the change is auditable.

Use these decision labels: `keep` for healthy or improving outcomes,
`improve` for indexed pages receiving impressions but needing a clearer answer
or stronger evidence, `consolidate` for overlapping intent, `refresh` for
aged facts/sources/SERP expectations, and `defer` when no meaningful
opportunity evidence appears after the declared window.

## Data owners and boundaries

The site owner supplies Search Console/analytics exports and approves the
conversion definition. The editor owns claim truth, originality, and the
decision label. Forge owns normalization, provenance, freshness warnings, and
fail-closed draft gating. It does not log into owner dashboards, publish to a
CMS, or claim that a score predicts Google rankings or LLM recommendations.
