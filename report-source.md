# Article Forge readiness report source

Updated: 2026-09-03
Repository: Article Forge
Branch: `fix/article-forge-readiness`

## Bottom line

Article Forge is B+ (85/100) for guarded draft generation after the hardening
and evidence-pipeline changes. It is B+ (82/100) for opportunity selection, C
for a fresh ShootMuse production run until product facts and claim evidence are
re-attested, and F for autonomous publishing or ranking guarantees.

The direct Serper adapter is live-verified. The Article Forge repo `.env`
contains `DEEPSEEK_API_KEY` and `OPENAI_API_KEY`, but no `SERPER_API_KEY`; the
separate personal `/Users/jasonsobers/.claude/secrets.env` contains the
`SERPER_API_KEY` variable. Five candidate queries plus one query using the
existing ShootMuse config succeeded with zero errors, and a second run returned
five cache hits with zero new API requests. No credential value is included
here.

## Research matrix

| Area | Evidence to use | Safe conclusion | Boundary |
|---|---|---|---|
| Demand | Keyword Planner historical average monthly searches; Search Console clicks, impressions, CTR, and position | Market demand or site-specific optimization opportunity | Search Console is not market volume; Ads competition is not organic difficulty |
| SERP competition | Serper organic results, positions, hosts, snippets, PAA, related searches, features, locale, timestamp | Current SERP composition and competitor coverage | No Google difficulty, authority, or rank probability from result/host counts |
| Intent | Query modifiers, title/snippet language, PAA, related searches, answer box, shopping/news/video/local features | Raw signals plus a reviewable intent hypothesis | No autonomous intent fact; >90 confidence needs three corroborating signals |
| Product fit | Current first-party facts, verified claims, tiers, source URLs, and verification dates | Traceable editorial fit | Keyword overlap alone cannot establish fit |
| Content fit and freshness | Original angle, unanswered question, dated support, limitations, facts verification, refresh window | Whether a brief is useful and current enough for human review | No date-only freshness, generic AI prose, or confidence-as-ranking guarantee |

## DeepSeek convergence

The direct DeepSeek Chat review accepted the plan with changes and rated the
applied changes at or above 80 confidence for the Serper contract, bounded
retries and request budgets, disk-backed raw-plus-normalized provenance,
secret handling, prevention of fake difficulty, demand semantics, product fit,
content originality, and freshness. Those recommendations are implemented and
covered by tests.

DeepSeek rated automated intent classification below the 80 threshold. The
implementation therefore stores raw intent signals and an optional hypothesis,
but does not silently promote the hypothesis to fact. Two direct Responses API
attempts intended to obtain independent web-grounded research completed without
visible text; they are retained as failed evidence receipts, not described as
independent research. The final DeepSeek response explicitly described itself
as a plan critique from domain knowledge rather than independent browsing.

## Implemented changes

- `scripts/collect_serper.py`: direct `POST https://google.serper.dev/search`,
  runtime-only `SERPER_API_KEY`, locale-aware cache, raw-plus-normalized disk
  cache, 24-hour TTL, 50-request default cap, bounded retries with
  `Retry-After`, exponential jitter, three-failure circuit breaker, normalized
  organic/PAA/related/features/intent evidence, and no fake difficulty score.
- `scripts/import_demand.py`: Keyword Planner and Search Console CSV/JSON
  importer with preserved units, source roles, raw paid-competition fields,
  and candidate-set-relative normalization.
- `scripts/score_opportunities.py`: evidence validation for demand roles,
  Serper provenance, editorial difficulty semantics, raw intent, product fit,
  original angle, unanswered question, dated support, freshness, and an
  evidence-confidence gate that downgrades sub-80 pursue decisions.
- Prompt, rules, README, discovery guidance, example environment/config, and
  regression tests updated to preserve the editorial contract.

## Verification

- `pytest -q`: 21 passed.
- Ruff check and format check: passed on all changed Python files.
- Live Serper CLI batch using the personal secrets file: five candidate queries
  plus one ShootMuse-config query succeeded with zero errors. A second run
  returned five cache hits with zero new API requests. The adapter is verified,
  but search volume, organic difficulty, rankings, and traffic remain
  unverified.
- Main checkout `/Users/jasonsobers/Personal/article-forge` was not modified;
  its existing dirty files remain preserved.

## Sources

- https://serper.dev/
- https://developers.google.com/webmaster-tools/v1/searchanalytics/query
- https://developers.google.com/google-ads/api/docs/keyword-planning/generate-historical-metrics
- https://support.google.com/google-ads/answer/3022575?hl=en
- https://developers.google.com/search/docs/fundamentals/creating-helpful-content
- https://developers.google.com/search/docs/fundamentals/ai-optimization-guide
- https://developers.google.com/search/docs/fundamentals/using-gen-ai-content?hl=en
- https://developers.google.com/search/docs/appearance/title-link
- https://developers.google.com/search/docs/appearance/snippet
- https://developers.google.com/search/docs/appearance/publication-dates?hl=en
- https://www.bing.com/webmasters/help/ai-performance-9f8e7d6c
- https://api-docs.deepseek.com/api/create-chat-completion/
- https://api-docs.deepseek.com/api/create-response/
