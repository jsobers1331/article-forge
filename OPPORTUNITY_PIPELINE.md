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

## Authority evidence (Open PageRank)

Coverage gaps say what competitors write about; they do not say who the
competitors are. `scripts/collect_authority.py` rates the hosts already in your
saved SERP evidence so a reviewer can see whether a query is held by national
platforms or by small independent sites before anyone writes.

```bash
python scripts/collect_authority.py \
  --config site-config.<yourproject>.json \
  --serp opportunity-serp.<yourproject>.json \
  --out authority.<yourproject>.json

python scripts/plan_opportunities.py \
  --config site-config.<yourproject>.json \
  --serp opportunity-serp.<yourproject>.json \
  --authority authority.<yourproject>.json \
  --out opportunity-plan.<yourproject>.json
```

The key is `OPENPAGERANK_API_KEY`, read from the environment, the project
`.env`, then `~/.claude/secrets.env`; it is never written to output, cache, or
logs. Results are cached per domain for 30 days (the provider refreshes
monthly) under `serp/.cache/authority/`, including "not found" answers, so a
re-run spends no quota. `--max-domains` (default 500) caps a run.

What the number is — and is not:

- It is a 0–10 link-graph popularity score built from the Common Crawl web
  graph, per host. It is **not** Moz Domain Authority, Ahrefs Domain Rating,
  Google PageRank, keyword difficulty, or a ranking prediction.
- It never changes `discovery_priority` or the opportunity score. Each
  candidate gains `authority_evidence` as reviewer context only.
- Small local sites cluster near 0, so it cannot rank them against each other.
  It is informative when national platforms or publishers appear in the SERP.

How hosts are treated:

- **Independent vs platform.** Social, forum, directory, and marketplace hosts
  (facebook, instagram, reddit, tripadvisor, weddingwire, and so on) are
  reported apart from independent sites, because a platform ranking says little
  about whether an independent site can win. Matching is on the name stem, so
  `tripadvisor.ie` and `tripadvisor.ca` both count. Replace the default list
  with `research.authority.platform_hosts` in the site config.
- **Platform-hosted tenants** (`*.mypixieset.com`, `*.wixsite.com`, and similar)
  are never sent to the provider and stay `platform_hosted_unscored`: the
  parent's score describes the platform, not the photographer.
- **Missing subdomains** fall back to the registrable parent
  (`community.weddingwire.ca` → `weddingwire.ca`) and are labelled
  `scored_via_parent`.
- **Unknown stays unknown.** A host the provider does not return is
  `unscored` with a `null` score, never 0, and is excluded from the median.
- Each candidate also records the site's own best position in the observed SERP.

To use it in a scored dataset, copy the independent summary into the
candidate's `organic_competition.authority_sample`:

```json
"authority_sample": {
  "source": "open_page_rank",
  "semantics": "link_graph_authority_proxy",
  "provider_as_of": "2026-09-01",
  "scored_count": 6,
  "median": 1.2,
  "max": 3.4
}
```

`score_opportunities.py` validates the sample and carries it through, but
authority is not an `editorial_difficulty` evidence type. An estimate whose
evidence is only authority is rejected, exactly like a Serper-count-only one,
and a sample may not carry a difficulty score. Write `editorial_difficulty`
yourself from a manual page review, then cite authority beside it.
