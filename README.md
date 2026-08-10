# article-forge

A model-agnostic, site-agnostic framework for generating articles that rank
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
cp site-config.example.json site-config.<yourproject>.json
# edit site-config.<yourproject>.json with your site's real facts — e.g. site-config.homeweal.json

pip install -r requirements.txt
cp .env.example .env
# fill in an API key ONLY if you want generate_article.py to call a provider directly

# --config is required on every script, always — there is no shared default file to fall
# back to. This is deliberate: a silent default is exactly how one project's config got
# clobbered by another's mid-session in practice. See the git history for that incident.

# Option A — fully model-agnostic, zero API integration:
python scripts/generate_prompt.py --config site-config.<yourproject>.json --topic-index 0
# paste the output into any LLM chat interface yourself

# Option B — let the script call a provider for you:
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
| `scripts/generate_article.py` | Ties the above together: render prompt → call provider → save draft → run the pre-publish fabrication/placeholder gate. |
| `IMAGES.md` | Rules for AI-generated supporting imagery (hero/mood images) — model choice, the prompt pattern that avoids garbled text, real cost data, images-per-article guidance, QC checklist. Screenshots are separate and out of scope here. |
| `prompts/image_prompt_template.md` | Fillable image-prompt template implementing the pattern in `IMAGES.md` §3. |
| `scripts/generate_image.py` | Generates one image (OpenAI GPT Image 2 by default) and converts it to WebP. Prints real token-based cost. |
| `scripts/check_article.py` | Automated compliance gate — fabrication grep, word count, banned words, structured-element presence, H1/query match, tier-gating heuristic, and structural-repetition heuristic. Run before publishing every draft. Not a substitute for the manual checklists in `RULES.md`/`IMAGES.md` — it catches shape, not meaning. |
| `scripts/score_article.py` | SERP-parity scorer: weighted 0-100 rubric (intent match, topical/entity coverage vs. real competitor pages, structure, E-E-A-T, linking) against a `serp_snapshot.json` you build from real search results. No live SEO API — an orchestrating agent does the actual keyword research (search, fetch top pages, extract headings/entities) and hands it to this script as structured input. See the module docstring for the snapshot schema. |

## Adding a topic

Either add entries to `topic_backlog` in your `site-config.<project>.json`, or pass one ad
hoc:

```bash
python scripts/generate_prompt.py --title "How to X without Y" --query "how to x without y" --type standard
```

## Targeting an audience or location without creating doorway pages

Article Forge can attach each topic to a verified audience need and location
brief. It targets a life situation, job-to-be-done, or role (for example,
households sharing bills with unequal incomes), not a named person, sensitive
personal data, or protected characteristic. Locations are not a bulk-page
generator: country, regional, and city content requires independent evidence
and unique local value. A city name swapped into the same article is rejected
as a doorway-page risk.

Add `content_targeting`, `audience_segments`, `locations`,
`evidence_sources`, and a topic-level `image_plan` using
`site-config.example.json` as the schema. Then run this hard preflight before
generation:

```bash
python scripts/validate_content_brief.py --config site-config.<yourproject>.json --strict
```

The validator blocks personal-data targeting, protected-class targeting,
programmatic location pages, unknown sources, under-sourced local claims, and
repeated visual fingerprints. It cannot determine whether a source really
supports a claim; the source must still be read and manually checked before
publication.

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

- It does not check real keyword search volume — validate the topic backlog
  against Google Search Console, Keyword Planner, or similar before
  committing writing time to a topic.
- It does not fact-check the article against the live site — that's on you,
  via `verified_facts` in the config and the pre-publish gate.
- It does not publish anything — output lands in `output/` as markdown for
  you to review and place into your own site/CMS.
