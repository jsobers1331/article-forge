# article-forge

A model-agnostic, site-agnostic framework for generating articles that rank
in traditional search **and** get cited by AI answer engines (ChatGPT,
Perplexity, Google AI Overviews, Claude).

It's not a product-specific tool — it's a ruleset (`RULES.md`) plus a small
set of scripts that turn any site's facts (`site-config.json`) and a topic
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

```bash
cp site-config.example.json site-config.json
# edit site-config.json with your site's real facts

pip install -r requirements.txt
cp .env.example .env
# fill in an API key ONLY if you want generate_article.py to call a provider directly

# Option A — fully model-agnostic, zero API integration:
python scripts/generate_prompt.py --topic-index 0
# paste the output into any LLM chat interface yourself

# Option B — let the script call a provider for you:
python scripts/generate_article.py --topic-index 0 --provider deepseek
```

## Files

| Path | Purpose |
|---|---|
| `RULES.md` | The full ruleset — structure, schema/JSON-LD guidance, voice, word counts, cadence, the pre-publish integrity gate. Read this first. |
| `site-config.example.json` | Template for a site's facts: positioning, ICP, verified differentiators, what's NOT real yet, competitors, topic backlog. Copy to `site-config.json` and fill in. |
| `prompts/article_prompt_template.md` | The master prompt template, filled in by `generate_prompt.py`. |
| `scripts/generate_prompt.py` | Renders `site-config.json` + a topic into a ready-to-send prompt. No API calls, no dependencies beyond the standard library. |
| `scripts/call_llm.py` | One function that calls any OpenAI-compatible endpoint (DeepSeek, OpenAI, OpenRouter, Groq, local Ollama) or native Anthropic — swap providers via a flag, not new code. Runnable standalone too. |
| `scripts/generate_article.py` | Ties the above together: render prompt → call provider → save draft → run the pre-publish fabrication/placeholder gate. |
| `IMAGES.md` | Rules for AI-generated supporting imagery (hero/mood images) — model choice, the prompt pattern that avoids garbled text, real cost data, images-per-article guidance, QC checklist. Screenshots are separate and out of scope here. |
| `prompts/image_prompt_template.md` | Fillable image-prompt template implementing the pattern in `IMAGES.md` §3. |
| `scripts/generate_image.py` | Generates one image (OpenAI GPT Image 2 by default) and converts it to WebP. Prints real token-based cost. |
| `scripts/check_article.py` | Automated compliance gate — fabrication grep, word count, banned words, structured-element presence, H1/query match, tier-gating heuristic, and structural-repetition heuristic. Run before publishing every draft. Not a substitute for the manual checklists in `RULES.md`/`IMAGES.md` — it catches shape, not meaning. |
| `scripts/score_article.py` | SERP-parity scorer: weighted 0-100 rubric (intent match, topical/entity coverage vs. real competitor pages, structure, E-E-A-T, linking) against a `serp_snapshot.json` you build from real search results. No live SEO API — an orchestrating agent does the actual keyword research (search, fetch top pages, extract headings/entities) and hands it to this script as structured input. See the module docstring for the snapshot schema. |

## Adding a topic

Either add entries to `topic_backlog` in `site-config.json`, or pass one ad
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

## What this does NOT do

- It does not check real keyword search volume — validate the topic backlog
  against Google Search Console, Keyword Planner, or similar before
  committing writing time to a topic.
- It does not fact-check the article against the live site — that's on you,
  via `verified_facts` in the config and the pre-publish gate.
- It does not publish anything — output lands in `output/` as markdown for
  you to review and place into your own site/CMS.
