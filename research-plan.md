# Article Forge SERP and opportunity research plan

Date: 2026-09-03

## Decision

Add a direct, Serper-specific collector for measured Google SERP observations.
Keep demand, paid advertiser competition, organic SERP observations, intent
evidence, product fit, content fit, freshness, and confidence as separate
evidence fields. The system may recommend a topic, but it must not claim that a
keyword will rank or that a numeric difficulty score is a Google metric.

## Scope and assumptions

- Article Forge remains generalized across products, services, and brands.
- Serper is the user's personal Google SERP provider. Its credential is loaded
  at runtime from the user's personal `/Users/jasonsobers/.claude/secrets.env`
  through the explicit `--env-file` option; no key is logged, printed,
  persisted, or committed.
- The Article Forge repo `.env` does not contain a Serper variable, while the
  separate personal secrets file contains `SERPER_API_KEY`. Five candidate
  queries plus one query using the existing ShootMuse config succeeded through
  the adapter, and a second run returned five cache hits.
- Search Console and Keyword Planner credentials are not currently available
  for direct API calls. Implement import-ready demand records rather than
  inventing OAuth or silently substituting another account.
- Scores are prioritization aids. They are never ranking predictions.

## Evidence-backed recommendations

| Area | Recommended evidence | What Forge may infer | What it must not claim |
|---|---|---|---|
| Demand | Keyword Planner historical metrics for market demand; Search Console clicks/impressions/CTR/position for a site's existing visibility | Relative demand or an optimization opportunity within a declared cohort | Search Console impressions are market search volume; paid competition is organic difficulty |
| SERP competition | Serper organic results, positions, unique hosts, result types, retrieval date, and location/language | Observable SERP composition and competitor coverage; a separately reviewed editorial estimate | A true Google ranking-difficulty or authority score from result count, host count, or `totalResults` alone |
| Intent | Query, title/snippet language, PAA, related searches, answer boxes, shopping/video/news features | A dominant or mixed intent hypothesis with signal-level evidence | That a SERP feature guarantees an intent or ranking outcome |
| Product fit | Current first-party facts, category frame, ICP, and verified claim evidence | A traceable fit score with cited evidence | Fit based only on keyword overlap |
| Content fit, originality, freshness, confidence | First-hand angle, useful unanswered question, dated supporting sources, facts verification date, opportunity age, and explicit limitations | Whether a human-reviewed brief is ready and when to refresh it | Generic AI prose, changed dates without substantive updates, or an 80% confidence ranking guarantee |

## Proposed implementation slices

1. Add `scripts/collect_serper.py` using the direct `https://google.serper.dev/search`
   contract, canonical `SERPER_API_KEY`, optional config-selected env name,
   bounded sequential requests, a versioned raw-plus-normalized disk cache,
   retry-after/backoff handling, a three-failure circuit breaker, and a
   normalized `article-forge.serp.v1` output.
2. Extract only useful evidence: organic result title/link/snippet/position,
   normalized host, PAA questions, related searches, visible SERP feature
   names, and raw intent signals. A hypothesis remains reviewable and cannot be
   promoted above 90 confidence without three signals. Do not turn this into a
   fake authority/difficulty calculator.
3. Extend `article-forge.opportunity.v1` validation so a scored candidate can
   carry Serper evidence, intent evidence, editorial difficulty with explicit
   manual/depth/intent/freshness/first-party evidence, originality/freshness
   evidence, confidence, and clear site-signal versus market-demand semantics.
4. Add a standard-library demand importer for Keyword Planner and Search
   Console exports. It will preserve source units and normalize scores only
   relative to the supplied candidate set.
5. Update the prompt, rules, README, example config, and regression tests so
   the opportunity brief is evidence-first and remains generalized.
6. Run deterministic tests, Ruff, compilation, and a credential-safe smoke
   path. The live personal Serper batch and cache-hit verification both passed;
   continue to treat search volume, organic difficulty, rankings, and traffic
   as separate unverified outcomes.

## DeepSeek convergence

The direct DeepSeek Chat review accepted the plan with changes. It scored the
applied recommendations at or above 80 confidence for the Serper contract,
rate/cost controls, raw-plus-normalized provenance, secret handling, fake
difficulty prevention, demand semantics, product fit, content originality,
and freshness. Those changes are implemented and regression-tested.

DeepSeek rated automated intent classification below the 80 threshold. Forge
therefore records raw signals and an optional reviewable hypothesis, but does
not let a model silently treat intent as fact. Two direct Responses API
attempts intended to obtain independent web-grounded DeepSeek research
completed without visible text; the final Chat review explicitly disclosed
that it was a plan critique, not independent browsing. No unsupported claim of
DeepSeek web validation is made.

## Research sources

- https://serper.dev/
- https://developers.google.com/webmaster-tools/v1/searchanalytics/query
- https://developers.google.com/google-ads/api/docs/keyword-planning/generate-historical-metrics
- https://support.google.com/google-ads/answer/3022575?hl=en
- https://developers.google.com/search/docs/fundamentals/creating-helpful-content
- https://developers.google.com/search/docs/fundamentals/ai-optimization-guide
- https://developers.google.com/search/docs/fundamentals/using-gen-ai-content
- https://developers.google.com/search/docs/appearance/title-link
- https://developers.google.com/search/docs/appearance/snippet
- https://developers.google.com/search/docs/appearance/publication-dates
- https://www.bing.com/webmasters/help/ai-performance-9f8e7d6c
