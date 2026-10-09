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

## Checking indexation

A page Google has not indexed cannot earn impressions, so check indexation
before reading any ranking signal. `scripts/check_indexing.py` reads each page's
index status from the read-only Search Console URL Inspection API (the login
`collect_search_console.py --authorize` sets up) and writes an
`article-forge.indexing.v1` artifact:

```bash
python scripts/check_indexing.py --config site-config.<yourproject>.json \
  --out indexing.<yourproject>.json [--path-prefix /blog/]
```

It takes URLs from the site's sitemap (`https://<domain>/sitemap.xml` unless
`--sitemap` is given) plus any `--url` / `--urls-file` entries. Each record gets
one status and zero or more flags:

| Status | Meaning |
|---|---|
| `indexed` | Google reports the page as indexed |
| `pending` | Not indexed yet, but still inside `--grace-days` (default 14) of its `lastmod` |
| `not_indexed` | Not indexed and past the grace period, or its age is unknown |
| `error` | Google returned no status for the URL (quota, API error, URL outside the property) |

| Flag | Meaning |
|---|---|
| `never_crawled` | Not indexed, past the grace period, and Google has no crawl on record |
| `stale_crawl` | Google last crawled the page more than `--stale-days` (default 14) before its `lastmod` |
| `google_chose_other_canonical` | Google treats a different URL as this page's canonical (often a host or trailing-slash split) |
| `declared_canonical_disagrees` | The page's own canonical tag differs from the one Google chose |
| `fetch_problem` | Google's last fetch of the page did not succeed |
| `indexing_blocked` | robots.txt, a meta tag, or an HTTP header blocks indexing |

How to read it:

- **It reports Google's view at check time.** It is not a ranking, traffic, or
  impressions measurement, and an indexed page can still receive no impressions.
- **`lastmod` is a modification date, not a publish date.** It is only as honest
  as the site that emits it. A date shared by many URLs looks like a build
  timestamp, so it is ignored for the grace period and `stale_crawl`, with a
  warning in the artifact, instead of flagging every static page.
- **It cannot request indexing.** The API is read-only. For flagged pages, use
  **Request indexing** in Search Console and record the date in the `indexed` field
  above.
- **Limits.** Google allows 2,000 inspections per site per day and 600 per minute;
  `--max-urls` (default 200) bounds a run and a quota error stops it.
- **Exit codes.** Flagged pages still exit 0. Exit 2 means the request itself is
  wrong (bad config, no URLs, a rejected login, refusing to overwrite the output).

## Review cadence and actions

- **Weekly for the first four weeks:** run the indexation check, then review
  technical errors, impressions, clicks, CTR, and qualified actions for new pages.
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

## Implemented local registry and evaluation

`scripts/publication_registry.py` stores immutable content versions joined to
a passing draft report and owner-confirmed publication receipt. Its export
adapter joins the existing GSC and indexation collector artifacts; access and
qualified-action evidence are supplied separately. No provider login, article
publication or scheduling is performed. Original URLs, exact periods and source
hashes remain in the observations. Explicit equivalent hosts can be joined;
path case, trailing slashes and query parameters are preserved.

`review_registry` emits one approval-held keep/improve/consolidate/refresh/defer
recommendation per URL at declared review windows. Anonymous GSC query omissions
remain unknown; rates normalize unequal durations only when scopes, attribution,
seasonality and edits permit comparison.

`scripts/evaluate_workflows.py` evaluates a fixed set of queries across businesses
using factual accuracy, original contribution, page choice, evidence validity,
human review time, cost and elapsed time. Minimum paired samples and holdouts
are recorded separately from 30/60/90-day published cohorts. Synthetic regression
fixtures verify the implementation, not search effectiveness. No weights are
automatically changed. See [EVIDENCE_SYSTEM.md](EVIDENCE_SYSTEM.md) for commands.
