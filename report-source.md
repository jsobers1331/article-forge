# Article Forge readiness report source

Updated: 2026-09-04
Repository: Article Forge
Branch: `main`
Commit: `62fde41` (PR #6)

## Bottom line

Article Forge is B+ (85/100) for guarded draft generation after the hardening
and evidence-pipeline changes. It is B+ (82/100) for opportunity selection, B
for a guarded ShootMuse pilot run, and F for autonomous publishing or ranking
guarantees.

The direct Serper adapter is live-verified. The Article Forge repo `.env`
contains `DEEPSEEK_API_KEY` and `OPENAI_API_KEY`, but no `SERPER_API_KEY`; the
separate personal `/Users/jasonsobers/.claude/secrets.env` contains the
`SERPER_API_KEY` variable. Five candidate queries plus one query using the
existing ShootMuse config succeeded with zero errors, and a second run returned
five cache hits with zero new API requests. The local ShootMuse config was
re-attested against the current site source. Search Console OAuth refresh,
property listing, final Search Analytics, and URL Inspection are now live
verified through the personal authorized environment. ShootMuse is indexed but
returned zero query rows for the tested 365-day period; a control property
returned 129 rows. No credential value is included here.

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
- `scripts/collect_search_console.py`: direct read-only Search Console OAuth
  collector with final web-data requests, versioned provenance, atomic output,
  overwrite protection, query aggregation, and optional normalized demand
  output.
- `scripts/collect_keyword_planner.py`: direct Google Ads Keyword Planner
  collector with explicit seed/geography inputs, versioned market-demand
  output, optional normalized demand output, and fail-closed credential checks.
- `scripts/score_opportunities.py`: evidence validation for demand roles,
  Serper provenance, editorial difficulty semantics, raw intent, product fit,
  original angle, unanswered question, dated support, freshness, and an
  evidence-confidence gate that downgrades sub-80 pursue decisions.
- `scripts/call_llm.py` and `prompts/article_prompt_template.md`: DeepSeek
  visible-content handling and explicit suppression of internal planning notes
  and roadmap-feature mentions.
- `scripts/check_article.py`: fail-closed detection for leaked per-H2 planning
  artifacts.
- Prompt, rules, README, discovery guidance, example environment/config, and
  regression tests updated to preserve the editorial contract.
- `FEEDBACK_LOOP.md`: reusable post-publication measurement contract, owner
  boundaries, cadence, and decision labels for Search Console and observed LLM
  citations.

## Verification

- `pytest -q`: 30 passed.
- Ruff check and format check: passed on all changed Python files.
- Live Serper CLI batch using the personal secrets file: five candidate queries
  plus one ShootMuse-config query succeeded with zero errors. A second run
  returned five cache hits with zero new API requests. The adapter is verified,
  but search volume, organic difficulty, rankings, and traffic remain
  unverified.
- ShootMuse config attestation: 9 claim-evidence records, current dates, and
  Serper research settings were added locally against the current
  `focal-studio-website` source review. A live DeepSeek pilot generated a
  10,627-byte “What Is a Photography CRM?” draft. The gate quarantined it for
  one structural warning; after one human editorial sentence correction, the
  standalone strict checker returned all PASS. The reviewed draft remains
  outside the repository at
  `/tmp/article-forge-shootmuse-pilot-final3/.quarantine/what-is-a-photography-crm.md`.
- Feedback loop: `FEEDBACK_LOOP.md` records the reusable measurement and
  refresh workflow. Search Console live access is verified, but ShootMuse has
  no query rows in the tested period, so no market-demand score was invented.
  Keyword Planner code is present and locally tested, but its live path remains
  unverified until Google Ads developer-token/OAuth/customer credentials are
  supplied.
- Tracked files in the main checkout `/Users/jasonsobers/Personal/article-forge`
  were not modified; its existing dirty files remain preserved. The ignored
  `site-config.shootmuse.json` there was intentionally updated with the local
  claim attestation and Serper settings described above.

## Sources

- https://serper.dev/
- https://developers.google.com/webmaster-tools/v1/how-tos/authorizing
- https://developers.google.com/webmaster-tools/v1/searchanalytics/query
- https://developers.google.com/google-ads/api/docs/rest/auth
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
