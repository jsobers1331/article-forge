# Opportunity pipeline

`scripts/plan_opportunities.py` is Article Forge's automatic bridge from site
context to article candidates. It has two modes:

- Offline: read saved `article-forge.serp.v1` /
  `article-forge.serp-collection.v1` and normalized demand artifacts.
- Live Serper: use the personal `SERPER_API_KEY` at runtime, search configured
  seeds, harvest People Also Ask and related searches, then make a bounded
  follow-up pass over new query candidates.

The live command needs only a site config and the Serper credential:

```bash
python scripts/plan_opportunities.py \
  --config site-config.<yourproject>.json \
  --live-serp \
  --env-file ~/.claude/secrets.env \
  --out opportunity-plan.<yourproject>.json \
  --serp-out opportunity-serp.<yourproject>.json
```

If `--seed` or `--seed-file` is omitted, the planner uses the configured
category frame and competitors to create starter seeds. It uses the Serper
settings in `research.serper`, including the 24-hour cache and request cap.
The `--env-file` option is optional; without it the planner checks the project
`.env`, then the owner's `~/.claude/secrets.env`. Secret values are never
written to output, cache, or logs.

The planner's `discovery_priority.score` is only a deterministic ordering of
observed query signals, coverage gaps, direct SERP evidence, and query shape.
It is not an SEO score, traffic estimate, keyword volume, keyword difficulty,
or ranking probability. Serper does not provide those measurements. A plan
candidate therefore records missing demand, manual editorial-difficulty, and
fit evidence instead of inventing it.

For measured market demand, run the direct Google Ads Keyword Planner adapter
and pass its normalized demand artifact with `--demand`. For site-specific
opportunity, pass the normalized Search Console demand artifact instead. These
signals stay separate: Keyword Planner's paid advertiser competition is never
treated as organic SEO difficulty.

To generate a guarded draft from a selected discovery candidate without
editing `topic_backlog`:

```bash
python scripts/generate_article.py \
  --config site-config.<yourproject>.json \
  --opportunity-plan opportunity-plan.<yourproject>.json \
  --candidate-id <candidate-id> \
  --provider deepseek
```

This is draft generation, not automatic publication. The normal article gate,
image policy, score report, quarantine behavior, human claim/originality/legal
review, and later Search Console measurement still apply. For a final numeric
opportunity score, first enrich a candidate with the required product fit,
content fit, freshness, evidence-confidence, five-domain organic sample, and
manual editorial-difficulty evidence, then run `score_opportunities.py`.
