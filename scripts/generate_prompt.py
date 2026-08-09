"""Fill the article prompt template from a site-config.<project>.json + a chosen topic.

Model-agnostic by design: this script only produces a plain-text prompt. You
can paste the output into ANY LLM's chat interface directly — no API
integration required. `generate_article.py` is a convenience layer on top
that also calls a provider automatically.
"""

import argparse
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(REPO_ROOT, "prompts", "article_prompt_template.md")

DEFAULT_BAN_WORDS = [
    "delve", "landscape", "robust", "seamless", "elevate", "game-changer",
    "in today's fast-paced world",
]


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_topic(config, topic_index, title, target_query, article_type):
    backlog = config.get("topic_backlog", [])
    if title or target_query:
        return {
            "title": title or target_query,
            "type": article_type or "standard",
            "target_query": target_query or title,
        }
    if topic_index is not None:
        return backlog[topic_index]
    if backlog:
        return backlog[0]
    raise ValueError("No topic given: pass --topic/--query, --topic-index, or add entries to topic_backlog")


def target_length_for(article_type):
    return {
        "pillar": "up to 2000",
        "standard": "1200-1800",
        "supporting": "800-1200",
    }.get(article_type, "1200-1800")


def format_differentiator(d):
    """A plain string is tier-agnostic (true for every plan). A dict with a
    `tier` key is gated to a specific plan — see RULES.md §2b. Getting this
    distinction wrong is exactly the bug that shipped in article-forge's
    first real deployment (2026-08-09): a feature description without its
    tier led to instructions a free-tier reader couldn't actually follow.
    """
    if isinstance(d, dict):
        tier = d.get("tier", "TIER UNSPECIFIED — verify before publishing")
        return f"  - {d['feature']} [TIER: {tier} — you MUST name this tier if you describe how to use this feature]"
    return f"  - {d}"


def render(config, topic):
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    facts = config.get("verified_facts", {})
    voice = config.get("voice", {})
    ban_words = DEFAULT_BAN_WORDS + voice.get("extra_ban_words", [])

    voice_instructions = (
        "write in first person, include one true specific anecdote"
        if voice.get("first_person") and voice.get("anecdotes_allowed")
        else "write in first person, no anecdotes"
        if voice.get("first_person")
        else "write in the brand's third-person voice, no fabricated founder anecdotes"
    )

    values = {
        "site_name": config.get("site_name", ""),
        "domain": config.get("domain", ""),
        "category_frame": config.get("category_frame", ""),
        "not_positioned_as": config.get("not_positioned_as", ""),
        "icp": config.get("icp", ""),
        "canonical_definition_sentence": config.get("canonical_definition_sentence", ""),
        "real_differentiators": "\n".join(format_differentiator(d) for d in facts.get("real_differentiators", [])) or "  (none listed)",
        "coming_soon_features": "\n".join(f"  - {d}" for d in facts.get("coming_soon_features", [])) or "  (none listed)",
        "pricing_note": facts.get("pricing_and_billing", {}).get("note", "(no pricing/billing facts supplied — omit pricing claims)"),
        "has_real_testimonials": facts.get("has_real_testimonials", False),
        "has_real_press_mentions": facts.get("has_real_press_mentions", False),
        "has_real_usage_stats": facts.get("has_real_usage_stats", False),
        "competitors": ", ".join(f"{c['name']} ({c['url']})" for c in config.get("competitors", [])) or "(none listed)",
        "current_month_year": config.get("current_month_year", "(set current_month_year in your site-config.<project>.json)"),
        "existing_pages": ", ".join(config.get("existing_pages", [])) or "(none listed)",
        "target_query": topic.get("target_query", topic.get("title", "")),
        "article_type": topic.get("type", "standard"),
        "target_length": target_length_for(topic.get("type", "standard")),
        "voice_instructions": voice_instructions,
        "ban_words": ", ".join(ban_words),
    }

    return template.format(**values)


def main():
    parser = argparse.ArgumentParser(description="Render a site-config + topic into a ready-to-send article prompt")
    parser.add_argument("--config", required=True, help="Path to your project's config, e.g. site-config.<project>.json")
    parser.add_argument("--topic-index", type=int, help="Index into the config's topic_backlog")
    parser.add_argument("--title", help="Ad-hoc topic title (skips topic_backlog)")
    parser.add_argument("--query", help="Ad-hoc target query/keyword (skips topic_backlog)")
    parser.add_argument("--type", choices=["pillar", "standard", "supporting"], help="Article type, controls target length")
    parser.add_argument("--out", help="Write the rendered prompt to this file instead of stdout")
    args = parser.parse_args()

    config = load_config(args.config)
    topic = pick_topic(config, args.topic_index, args.title, args.query, args.type)
    prompt = render(config, topic)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"Wrote prompt to {args.out}")
    else:
        print(prompt)


if __name__ == "__main__":
    main()
