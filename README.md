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

## What this does NOT do

- It does not check real keyword search volume — validate the topic backlog
  against Google Search Console, Keyword Planner, or similar before
  committing writing time to a topic.
- It does not fact-check the article against the live site — that's on you,
  via `verified_facts` in the config and the pre-publish gate.
- It does not publish anything — output lands in `output/` as markdown for
  you to review and place into your own site/CMS.
