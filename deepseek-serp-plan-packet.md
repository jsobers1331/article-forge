# DeepSeek independent research and plan review packet

You are the independent reviewer for Article Forge, a generalized framework
that produces human-reviewed article drafts for many brands and products.

## Part A — independent research task

Research these questions from current authoritative sources, preferably first
party documentation:

1. What can a Serper Google SERP response reliably establish about organic
   competition, result composition, related searches, and People Also Ask?
2. What do Google Search Console Search Analytics and Google Ads Keyword
   Planner historical metrics actually measure, and what semantic mistakes
   must an opportunity scorer prevent?
3. Which intent signals can be extracted from observed SERPs without treating
   a heuristic classifier as ground truth?
4. How should product fit and content fit be scored for a generalized brand
   content system without rewarding keyword overlap alone?
5. What does current Google guidance say about originality, first-hand
   experience, freshness, AI-assisted content, and ranking guarantees? What
   can Bing AI Performance actually measure for LLM visibility?

For every recommendation, state confidence from 0–100, supporting sources,
limitations, and any disagreement with common SEO assumptions. Do not promise
rankings, traffic, or citations.

## Part B — review this proposed plan

The implementation plan is:

- Add a direct `scripts/collect_serper.py` adapter for
  `https://google.serper.dev/search`.
- Load only a canonical project env variable, `SERPER_API_KEY`, at runtime;
  allow a config-selected env name but never print, persist, or commit the
  key. Use bounded sequential requests, a TTL cache, timeout/retry handling,
  and compact normalized output.
- Emit `article-forge.serp.v1` records containing query, locale/language,
  retrieval time, organic title/link/snippet/position/host, PAA questions,
  related searches, visible SERP features, explicit intent signals, and
  observable competition counts.
- Do not calculate fake domain-authority or Google keyword-difficulty values
  from result count. Preserve raw observations and require a separately
  justified organic difficulty score for opportunity prioritization.
- Add `scripts/import_demand.py` for Keyword Planner and Search Console CSV or
  JSON exports. Preserve units and source semantics; normalize only relative
  to the supplied candidate set.
- Extend the opportunity schema and validation with intent evidence,
  freshness/originality evidence, confidence, and a clear distinction between
  market demand and a site's existing Search Console opportunity.
- Keep product fit and content fit as evidence-backed editorial rubrics, not
  keyword-overlap scores. Require an explicit original angle and limitations.
- Keep deterministic checks as final authority. Use models only for research,
  classification, and critique; all generated drafts remain quarantined until
  the existing full gate and human review pass.

## Part C — requested output

1. Independent research findings with source URLs and confidence.
2. Critical review of the plan: PASS, CHANGE, or BLOCK for each slice.
3. The smallest high-confidence corrections needed before implementation.
4. A final convergence statement. A recommendation may be applied only when
   it is supported by authoritative evidence and no unresolved credible
   safety or semantic objection remains.

## Source starting points

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
