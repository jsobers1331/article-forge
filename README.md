# article-forge

A model-agnostic, site-agnostic framework for generating guarded article drafts that can rank
in traditional search **and** get cited by AI answer engines (ChatGPT,
Perplexity, Google AI Overviews, Claude).

It's not a product-specific tool — it's a ruleset (`RULES.md`) plus a small
set of scripts that turn any site's facts (`site-config.<project>.json`) and a topic
into a fully-specified article prompt. That prompt works with literally any
LLM: paste it into a chat window, or point the included scripts at whichever
provider you have an API key for.

## Why this exists

Distilled from independent research across two different models (Claude and
DeepSeek were each asked the same questions about SEO semantics and article
strategy, cross-checked against live web research) plus hard lessons from a
real site that shipped inaccurate content (stale pricing claims, a promotion
that should've been retired). The core discipline — **never state anything
the site owner hasn't verified as true** — is baked into the framework, not
left as an afterthought.

The framework earned its first real bug report from its own first live
deployment: a generated how-to article correctly avoided fabricating
anything, but still implied a paid-tier-only feature was available more
broadly than it was — because the config schema had no way to say "this is
real, but only on plan X." See `RULES.md` §2b and `site-config.example.json`
for the fix (tier-tagged differentiators). Left in as evidence the
integrity rules are tested against reality, not just written down.

Also covers supporting imagery: `IMAGES.md` documents a real generate-and-inspect test
cycle against OpenAI's GPT Image 2, including a failed first attempt (garbled
pseudo-text on documents despite an explicit "no text" instruction) and the fix
(describe surfaces as blank/closed/face-down, not just "no text"). Real measured cost:
$0.006–$0.02/image, not the $0.10+ estimates the initial cross-model consultation gave —
verify cost/model claims against a real test call the same way this framework verifies
content claims against `verified_facts`.

## Quick start

This repo is shared across every product you use it for — name your config per project so
switching projects never means overwriting another one's facts:

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in an API key ONLY if you want generate_article.py to call a provider directly

cp site-config.example.json site-config.<yourproject>.json
# fill in ONLY the identity fields for now: site_name, domain, category_frame, icp.
# verified_facts, claim_evidence, and topic_backlog come later, informed by Step 0 below.
```

**Step 0 — Discovery (new project, or topic_backlog running low):** find out
what's actually worth writing about before guessing. Needs only the identity
fields above, not the full config — see `DISCOVERY.md` for the full
walkthrough (seed-keyword suggestion → orchestrating-agent research →
coverage-gap report). Skippable if you already know your topics; recommended
otherwise.

```bash
python scripts/discover_gaps.py --config site-config.<yourproject>.json --suggest-seeds
# ... orchestrating agent researches those seeds, builds discovery_snapshot.json ...
python scripts/discover_gaps.py --config site-config.<yourproject>.json --snapshot discovery_snapshot.json
```

Now finish filling in `site-config.<yourproject>.json` — `verified_facts` from
the real site, `topic_backlog` from Step 0's report (manually reviewed, never
auto-applied) plus your own judgment — and generate:

```bash
# --config is required on every script, always — there is no shared default file to fall
# back to. This is deliberate: a silent default is exactly how one project's config got
# clobbered by another's mid-session in practice. See the git history for that incident.

# Option A — fully model-agnostic, zero API integration:
python scripts/generate_prompt.py --config site-config.<yourproject>.json --topic-index 0
# paste the output into any LLM chat interface yourself

# Option B — let the script call a provider for you. DeepSeek defaults to
# `deepseek-v4-pro`. Only an all-PASS draft is
# written to normal output; blocked drafts go to output/.quarantine/:
python scripts/generate_article.py --config site-config.<yourproject>.json --topic-index 0 --provider deepseek
```

## Files

| Path | Purpose |
|---|---|
| `RULES.md` | The full ruleset — structure, schema/JSON-LD guidance, voice, word counts, cadence, the pre-publish integrity gate. Read this first. |
| `site-config.example.json` | Template for a site's facts: positioning, ICP, verified differentiators, what's NOT real yet, competitors, topic backlog. Copy to `site-config.<project>.json` and fill in. |
| `prompts/article_prompt_template.md` | The master prompt template, filled in by `generate_prompt.py`. |
| `scripts/generate_prompt.py` | Renders `site-config.<project>.json` + a topic into a ready-to-send prompt. No API calls, no dependencies beyond the standard library. |
| `scripts/call_llm.py` | One function that calls any OpenAI-compatible endpoint (DeepSeek, OpenAI, OpenRouter, Groq, local Ollama) or native Anthropic — swap providers via a flag, not new code. Runnable standalone too. |
| `scripts/generate_article.py` | Render prompt → call provider → run the full gate → atomically save only an all-PASS draft, or quarantine it with a receipt. |
| `IMAGES.md` | Rules for AI-generated supporting imagery (hero/mood images) — model choice, the prompt pattern that avoids garbled text, real cost data, images-per-article guidance, QC checklist. Screenshots are separate and out of scope here. |
| `prompts/image_prompt_template.md` | Fillable image-prompt template implementing the pattern in `IMAGES.md` §3. |
| `scripts/generate_image.py` | Generates one image (OpenAI GPT Image 2 by default) and converts it to WebP. Prints real token-based cost. |
| `scripts/check_article.py` | Automated compliance gate — config/evidence integrity, freshness, placeholders, H1/query match, coming-soon and tier scope, links, structure, and style signals. Run before publishing every draft; human meaning review remains required. |
| `scripts/score_article.py` | SERP-parity scorer: weighted 0-100 rubric (intent match, topical/entity coverage vs. real competitor pages, structure, E-E-A-T, linking) against a `serp_snapshot.json` you build from real search results. No live SEO API — an orchestrating agent does the actual keyword research (search, fetch top pages, extract headings/entities) and hands it to this script as structured input. See the module docstring for the snapshot schema. |
| `scripts/collect_serper.py` | Direct personal Serper adapter: collects timestamped Google organic results, hosts, snippets, People Also Ask, related searches, visible SERP features, and raw intent signals into a disk-backed `article-forge.serp.v1` evidence record. It never calculates Google keyword difficulty. |
| `scripts/import_demand.py` | Normalizes Keyword Planner or Search Console CSV/JSON exports while preserving market-demand versus site-opportunity semantics and source units. |
| `DISCOVERY.md` | Pre-topic-selection ruleset — find coverage-gap candidates vs. real competitor pages before guessing at `topic_backlog`. Read this before starting a brand-new site config. |
| `scripts/discover_gaps.py` | Deterministic half of Discovery: `--suggest-seeds` prints starter queries from identity fields alone; `--snapshot discovery_snapshot.json` produces a ranked coverage-gap report. No search-volume/authority signal — see DISCOVERY.md for exactly what this can and can't tell you. |
| `scripts/score_opportunities.py` | Score a versioned, provider-neutral opportunity dataset. Missing/stale demand or organic-competition evidence becomes `needs-data`; paid advertiser competition is never substituted for organic difficulty. Editorial difficulty, intent, fit, freshness, and evidence confidence remain explicit. |
| `FEEDBACK_LOOP.md` | Measurement contract and review cadence for Search Console, qualified actions, conversions, indexation, and observed LLM citations after publication. |

## Adding a topic

Before adding a topic because it appears in a competitor gap report, populate a
candidate in the `article-forge.opportunity.v1` schema and run
`scripts/score_opportunities.py`. The score is a prioritization aid only:
Search Console is a site signal, Keyword Planner competition is an advertising
signal, and neither is organic ranking difficulty. A candidate without measured
demand and a five-result organic SERP sample cannot be scored.

For a live SERP evidence pass:

```bash
python scripts/collect_serper.py --config site-config.<yourproject>.json \
  --query "what is a [category]" --out serp/<yourproject>-serper.json
```

The collector reads `SERPER_API_KEY` from the project environment (or the
configured env name), uses a versioned 24-hour disk cache, caps each run at 50
requests, and handles transient failures with bounded retry/backoff and a
three-failure circuit breaker. Cache files contain the provider response and
normalized observation but never request headers. Query, country, language,
location, and result count are part of the cache key. Use `--refresh` only for a
deliberately fresh paid request.

Serper observations include organic titles, links, snippets, positions, hosts,
People Also Ask, related searches, SERP features, and raw intent signals. They
do not become Google keyword difficulty, domain authority, or ranking
probability. Add any editorial difficulty estimate separately with a rationale
and evidence beyond result counts.

To import demand evidence from exports:

```bash
python scripts/import_demand.py --input keyword-planner.csv \
  --source keyword_planner --observed-at YYYY-MM-DD --sample-size 12 \
  --out demand.json
python scripts/import_demand.py --input search-console.csv \
  --source search_console --metric impressions --observed-at YYYY-MM-DD \
  --sample-size 28 --out demand.json
```

Keyword Planner records are market-demand observations. Search Console records
are site-opportunity observations for the selected property and period. The
importer preserves raw units and paid-competition fields; normalized scores are
relative to the supplied candidate set.

After publication, use [`FEEDBACK_LOOP.md`](FEEDBACK_LOOP.md) to collect
outcomes and recalibrate the opportunity weights. The feedback loop is
measurement-only: it does not publish pages or turn a rank/citation observation
into a guarantee.

## Readiness boundary

Forge is suitable for guarded draft generation once the site config has current
facts plus a verified `claim_evidence` registry. It is not an autonomous
publisher. Every article still needs human claim, comparison, originality,
brand-voice, and legal/compliance review; published results must be measured in
Search Console and refreshed when facts or search evidence age.

### Opportunity record shape

Each candidate needs `candidate_id`, `query`, `intent`, `page_type`, and these
separate evidence records:

```json
{
  "demand": {"source": "keyword_planner", "role": "market_demand", "normalization": "max-value-within-imported-candidate-set", "value": 1000, "unit": "searches", "score": 70, "observed_at": "YYYY-MM-DD", "sample_size": 12},
  "paid_competition": {"source": "keyword_planner", "value": "low", "observed_at": "YYYY-MM-DD"},
  "organic_competition": {"source": "serper", "observed_at": "YYYY-MM-DD", "sample_size": 10, "serp_cache_key": "sha256", "serp_retrieved_at": "YYYY-MM-DD", "observations": {"organic_result_count": 10, "unique_hosts": 9}, "editorial_difficulty": {"semantics": "editorial_estimate", "score": 40, "rationale": "Manual comparison of the observed pages found a narrow but defeatable gap.", "evidence_types": ["manual_page_review", "content_depth_assessment"], "evidence": ["serp-record", "manual-page-review"]}},
  "intent_evidence": {"source": "serper", "signals": ["people_also_ask", "query modifier: what"], "observed_at": "YYYY-MM-DD"},
  "product_fit": {"rubric_version": "1.0", "score_semantics": "editorial", "score": 90, "rationale": "Verified product fit.", "evidence_types": ["first_party_fact", "verified_claim"], "evidence": ["fact-id", "claim-id"]},
  "content_fit": {"rubric_version": "1.0", "score_semantics": "editorial", "score": 85, "rationale": "A distinct useful angle exists.", "original_angle": "A decision framework based on the reader's workflow.", "limitation": "The article cannot claim measured ranking difficulty without an external source.", "unanswered_question": "Which workflow criteria matter before choosing a CRM?", "source_dates": ["YYYY-MM-DD"], "evidence_types": ["original_angle", "limitation", "unanswered_question"], "evidence": ["original-framework"]},
  "freshness": {"source": "research-review", "status": "current", "observed_at": "YYYY-MM-DD", "refresh_after_days": 90, "evidence": ["current-source-review"]},
  "evidence_confidence": {"score": 85, "rationale": "Demand and SERP evidence are current and the editorial judgments are traceable.", "evidence": ["demand-record", "serp-record", "fit-review"]}
}
```

The initial formula is `0.30D + 0.25(100-editorial difficulty) + 0.25F +
0.20CF`. Keep component scores, sources, dates, sample sizes, and rationales
visible so the model cannot turn a guess into a fact. Editorial difficulty must
also name a manual/page-depth/intent/freshness/first-party assessment; raw SERP
counts alone are rejected. If editorial difficulty is omitted, raw SERP
evidence remains useful but the numeric opportunity score is `needs-data`. A
score below 80 evidence confidence cannot be promoted to `pursue`.

Either add entries to `topic_backlog` in your `site-config.<project>.json`, or pass one ad
hoc:

```bash
python scripts/generate_prompt.py --title "How to X without Y" --query "how to x without y" --type standard
```

## Adding a new LLM provider

`call_llm.py`'s `PROVIDERS` dict covers the common OpenAI-compatible APIs and
Anthropic. Anything else that speaks either of those two request shapes
works without touching the code:

```bash
python scripts/call_llm.py --prompt-file output/some-prompt.md \
  --base-url https://your-provider/v1/chat/completions \
  --api-key-env YOUR_PROVIDER_API_KEY \
  --kind openai_compatible \
  --model your-model-name
```

## Verified on fresh topics, not just the topics that shaped the rules

After building the fixes above from the HomeWeal test run, two NEW topics
(a definitional pillar and a comparison listicle, neither used to derive
any of the rules) were generated and run through `check_article.py` to
confirm the fixes actually generalize. First pass found two real, new
bugs — the model printed its internal opening-function plan as a visible
label ("**Answer.**", "**Scenario.**") on one draft, and both drafts used
`##` instead of `#` for the H1 — neither caught by intuition, both caught
by the gate. Fixed in the template (rules 2 and 4), regenerated, both
passed clean. See `RULES.md` §12 and `IMAGES.md` for the same discipline
applied to voice and images respectively: state what you found, fix the
template rather than the one draft, and verify the fix on new material
before trusting it.

## Running the full backlog through score_article.py surfaced two more bugs

Scoring all 6 backlog articles for one site in one pass (instead of one-off spot
checks) surfaced two failure modes that smaller tests hadn't hit:

1. **The linking rule was satisfied by intent, not by syntax.** DeepSeek would
   sometimes write "YNAB (https://ynab.com)" — a competitor named next to its
   real URL — and consider that "linked." A human reads that as a link; the
   scorer (correctly) doesn't, because it isn't one, and neither does a crawler
   looking for an anchor. Fixed by making rules 16/17 spell out the exact
   `[anchor text](url)` syntax requirement, and added `check_bare_urls()` to
   `check_article.py` as a hard-fail gate so this can't slip through silently
   again. Confirmed the failure was real (not a scorer bug) by checking the
   raw draft text before fixing.
2. **Scoring an already-shipped page requires care in how you get its text
   back out.** Two already-published articles were scored by converting their
   TSX back to plain text for `score_article.py`. The first extraction pass
   silently dropped an entire comparison table (data passed as a component
   prop, not inline JSX text) and flattened `<ol>` into unordered bullets,
   which cost real structure points that the live page actually has. It also
   briefly zeroed out the E-E-A-T "updated" signal by deleting the dateline
   line instead of relocating it. None of these were content problems — they
   were artifacts of the conversion step — but an unverified artifact produces
   a wrong score you'd act on as if it were real. Lesson: when scoring a
   shipped page rather than a fresh draft, sanity-check the extracted text
   against the source before trusting the number, the same way you'd sanity-check
   any other measurement before using it to make a decision.

Net effect on the 4 backlog articles scored/fixed in this pass: 81.0→93.2,
83.6→92.0, and two new articles shipped at 89.6 and 90.2 — all from real,
verifiable additions (naming a competitor already being discussed, linking a
URL that was already named, adding one already-true "our take" phrase). No
score was raised by adding anything unverifiable.

## What this does NOT do

- It does not check real keyword search volume without an imported demand
  record — validate the topic backlog against Google Search Console, Keyword
  Planner, or similar before committing writing time to a topic.
- It does not fact-check the article against the live site — that's on you,
  via `verified_facts`, `claim_evidence`, and the pre-publish gate.
- It does not connect directly to Search Console or Keyword Planner APIs, or a
  CMS. The demand importer accepts exports; direct API integrations remain
  provider-specific and human-owned. Serper collection is available through
  the direct personal adapter described above.
- It does not publish anything — all-PASS output lands in `output/` as markdown
  for you to review and place into your own site/CMS.
