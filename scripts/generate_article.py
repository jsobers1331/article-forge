"""End-to-end: render the prompt, call a chosen LLM provider, save the draft,
and run the pre-publish fabrication/placeholder gate from RULES.md section 11.

This is a convenience wrapper. You do not need this script at all if you'd
rather run generate_prompt.py and paste the result into any LLM by hand.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from call_llm import call_llm, PROVIDERS
from generate_prompt import REPO_ROOT, load_config, pick_topic, render

PLACEHOLDER_PATTERNS = [
    r"example\.com",
    r"lorem ipsum",
    r"\bTBD\b",
    r"\bFIXME\b",
    r"555-\d{4}",
    r"Jane (S\b|Smith)",
    r"John (S\b|Smith)",
    r"Sample (Customer|Client)",
    r"PLACEHOLDER: needs real value",
]


def run_fabrication_gate(text):
    hits = []
    for pattern in PLACEHOLDER_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            line_no = text[: m.start()].count("\n") + 1
            hits.append(f"line {line_no}: matched /{pattern}/ -> {m.group(0)!r}")
    return hits


def main():
    parser = argparse.ArgumentParser(description="Generate one article end-to-end and gate it before publish")
    parser.add_argument("--config", required=True, help="Path to your project's config, e.g. site-config.<project>.json")
    parser.add_argument("--topic-index", type=int)
    parser.add_argument("--title")
    parser.add_argument("--query")
    parser.add_argument("--type", choices=["pillar", "standard", "supporting"])
    parser.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    parser.add_argument("--model")
    parser.add_argument("--out-dir", default=os.path.join(REPO_ROOT, "output"))
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    config = load_config(args.config)
    topic = pick_topic(config, args.topic_index, args.title, args.query, args.type)
    prompt = render(config, topic)

    print(f"Calling {args.provider}...", file=sys.stderr)
    article = call_llm(prompt, provider=args.provider, model=args.model)

    os.makedirs(args.out_dir, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", topic.get("target_query", topic.get("title", "article")).lower()).strip("-")
    out_path = os.path.join(args.out_dir, f"{slug}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(article)
    print(f"Saved draft to {out_path}", file=sys.stderr)

    hits = run_fabrication_gate(article)
    if hits:
        print("\n⚠️  Pre-publish gate found possible placeholders/fabrication tells:", file=sys.stderr)
        for h in hits:
            print(f"  - {h}", file=sys.stderr)
        print("Review and fix before publishing.", file=sys.stderr)
    else:
        print("Pre-publish gate: no placeholder/fabrication patterns found.", file=sys.stderr)


if __name__ == "__main__":
    main()
