# Discovery — finding what to write about before you write it

A pre-topic-selection research pass. Run it before `topic_backlog` has
anything in it (first time you point article-forge at a new site), and again
periodically (~90 days, same cadence as RULES.md §10) once the backlog runs
low.

`scripts/collect_serper.py` can now collect current Google SERP observations
through the project's personal Serper credential. The collector is deliberately
limited to evidence capture: an **orchestrating agent** (you, or an LLM with
real search/fetch tools) still decides which queries to research, fetches
competitor pages when needed, extracts their structure, and hands structured
evidence to deterministic scripts. No collector or scorer guesses that a
keyword will rank.

## What this tool tells you — and what it doesn't

This produces **coverage-gap candidates**, not "keywords that will rank
#1." It has no search-volume data, no domain-authority signal, no backlink
data, no click-through data. All it knows is: for the keywords you searched,
here's what today's top-ranking pages cover that your site's page titles and
topic backlog don't currently mention. That's a starting point for judgment,
not a ranked opportunity list — validate against Google Search Console /
Keyword Planner before committing real writing time, same caveat the main
README already states for `topic_backlog` generally.

For live SERP collection:

```bash
python scripts/collect_serper.py --config site-config.<yourproject>.json \
  --query "what is a [category]" --out serp/<yourproject>-discovery.json
```

The command requires `SERPER_API_KEY` in the project environment (or the env
name configured under `research.serper.api_key_env`). It uses a 24-hour disk
cache by default, caps a run at 50 requests, records raw and normalized
responses without request headers, and handles transient failures with bounded
retries. The cache key includes query, country, language, location, and result
count. Use `--refresh` only when a fresh paid request is justified.

The normalized record includes organic titles, links, snippets, positions,
hosts, People Also Ask questions, related searches, visible SERP features, and
raw intent signals. It does not convert `searchInformation.totalResults`, host
counts, or result counts into keyword difficulty.

Every finding below is a candidate for a human to read and decide on, never
an instruction to auto-write anything. Nothing in `discovery_snapshot.json`
or its report is ever wired into `generate_prompt.py`'s template — that
pipeline only ever reads from `verified_facts`.

`import_demand.py` normalizes Keyword Planner exports as market-demand
records and Search Console exports as site-opportunity records. It preserves
the original units and paid-competition fields; normalized scores are only
relative to the imported candidate set. Search Console data cannot be relabeled
as market searches.

## Step 0: identity fields only (no verified_facts required yet)

Discovery needs `site_name`, `domain`, `category_frame`, and `icp` — nothing
else. If you're starting a brand-new `site-config.<project>.json`, fill in
just those four fields first, run discovery, then come back and fill in
`verified_facts`/`topic_backlog` informed by what you found. (Requiring the
full config before discovery would be circular — you'd need to already know
your differentiators to find out what you're missing.)

```bash
python scripts/discover_gaps.py --config site-config.<project>.json --suggest-seeds
```

Prints a starter list of seed queries built from `category_frame`/`icp`
against a small set of query-pattern templates (definitional, cost,
comparison-if-competitors-listed, how-to-choose). Edit/add to this list with
your own judgment — it's a starting point, not exhaustive.

## Step 1: build `discovery_snapshot.json` (orchestrating agent)

For each seed query, group near-duplicate/same-intent queries into one
**cluster** — pooling raw query count across unrelated intents invalidates
the frequency math later (a term common to 5 near-identical "cost" queries
isn't 5 independent signals, it's 1). For each cluster: search it, open the
top-organic-result pages, extract structure. Use at least five independent
organic result domains per cluster. One entry per **distinct domain** per
cluster — the same domain ranking twice in one cluster is one data point, not
two. Do not count syndicated or boilerplate-only copies as independent evidence.

```json
{
  "clusters": [
    {
      "cluster_id": "short-slug-for-this-intent",
      "seed_keywords": ["query 1", "near-duplicate phrasing of query 1"],
      "captured_at": "YYYY-MM-DD",
      "competitors": [
        {
          "url": "https://...",
          "domain": "example.com",
          "position": 1,
          "word_count": 1800,
          "headings": ["...", "..."],
          "subtopics": ["...", "..."],
          "entities": ["...", "..."],
          "brand_terms": ["...", "..."]
        }
      ]
    }
  ]
}
```

`headings`/`subtopics`/`entities` — same meaning as `serp_snapshot.json` in
`score_article.py`'s docstring. `brand_terms`: marketing/positioning phrases
the competitor uses for itself or its category (e.g. "AI-powered," "the
enterprise-grade choice") — captured for the market-language report in Step
2, never for direct reuse (see the quarantine note below).

## Step 2: run the gap report

```bash
python scripts/discover_gaps.py --config site-config.<project>.json \
  --snapshot discovery_snapshot.json [--out discovery-report.json]
```

Three sections, always in this order:

1. **Topical authority gaps** — subtopics/entities that reach consensus
   (at least 60% of at least five distinct domains, same as `score_article.py`) *within* a
   cluster, and recur across **2 or more distinct clusters**. These are the
   closest thing to "own a whole theme" signal this tool can produce. Ranked
   by number of distinct clusters, then by within-cluster consensus count.
2. **Single-cluster gaps** — consensus within one cluster only. Weaker
   signal, still worth a look, ranked lower.
3. **Market language observed (do not auto-adopt)** — every `brand_terms`/
   distinctive `entities` value not found anywhere in your
   `canonical_definition_sentence`/`category_frame`/`real_differentiators`.
   Classified heuristically as `competitor/brand name`, `positioning
   language`, or `generic term` — this classification is a coarse keyword
   heuristic, not a legal or semantic judgment. **Never treat an item here as
   something to write about or claim** until you've separately verified it's
   real, true of your business, safe to reference (not a trademark issue),
   and deliberately not something your `not_positioned_as` field exists to
   avoid. This section is quarantined from the rest of the pipeline on
   purpose: it is observation, not a recommendation.

Every gap candidate in sections 1–2 also carries a feasibility label,
matched heuristically against `verified_facts` (same word-overlap approach
`check_article.py` already uses for tier-gating — a coarse signal, not
proof):

- `possibly supported by verified_facts — verify manually before writing`
- `no matching verified_facts entry — do not write until you've verified this fact is real`

And a coverage label, checked only against your `existing_pages` +
`topic_backlog` **titles/queries** — this script has no access to your
actual page bodies, so a "gap" here can mean "genuinely missing" or just
"covered in the body of a page whose title doesn't mention it." Read the
actual page before trusting the label:

- `no title/query overlap found — unconfirmed gap, read your own pages to confirm`

## Promoting a candidate to `topic_backlog`

Coverage gaps are not keyword opportunities. Before promotion, create an
`article-forge.opportunity.v1` candidate and run
`python scripts/score_opportunities.py --input opportunities.json`. Record
demand separately from organic competition: Search Console impressions/clicks
are site-performance signals, Keyword Planner competition is advertiser
competition, and neither alone proves organic difficulty. The scorer returns
`needs-data` unless measured demand and at least five organic SERP observations
are present; it never manufactures a volume or “low competition” label.

Manual, always. Add it to `site-config.<project>.json` like any other
backlog entry; optionally note where it came from:

```json
{ "title": "...", "type": "standard", "target_query": "...", "priority": 1,
  "source": "discovery-gap 2026-08-09" }
```

## Fact freshness — checked, not just documented

`site-config.<project>.json` has a `facts_last_verified` field
(`YYYY-MM-DD`). `scripts/check_article.py` hard-WARNs if it's more than 30
days old — a forcing function to stop and re-attest, not a silent date
nobody reads. Re-verifying means actually re-reading the target site's own
source of truth (pricing/feature pages, testimonials, whatever encodes the
real facts) — this tool can't do that part for you generically, since it
doesn't know your site's file layout. But it will make you notice when
you've gone a month without doing it.
