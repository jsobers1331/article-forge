"""Automated compliance gate for a generated article draft.

This is a CHECK, not a rewrite tool — it verifies a draft against RULES.md
before publishing, the same way generate_article.py's fabrication grep does,
but broader: word count, banned words, structure, and (heuristically)
tier-gated feature mentions. Exit code is non-zero on any HARD failure
(fabrication placeholders). Everything else is a WARNING for human judgment —
this script narrows what a human has to check by hand, it does not replace
the manual QC checklist in RULES.md §11 or IMAGES.md §6. Those require
actually reading the draft against verified_facts; no script does that.
"""

import argparse
import json
import re
import sys

DEFAULT_BAN_WORDS = [
    "delve", "landscape", "robust", "seamless", "elevate", "game-changer",
    "in today's fast-paced world",
]

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

WORD_COUNT_RANGES = {
    "pillar": (1500, 2200),
    "standard": (1000, 2000),
    "supporting": (700, 1400),
}


def word_count(text):
    return len(re.findall(r"\b\w+\b", text))


def check_word_count(text, article_type):
    lo, hi = WORD_COUNT_RANGES.get(article_type, WORD_COUNT_RANGES["standard"])
    n = word_count(text)
    if n < lo:
        return "WARN", f"word count {n} is below the {lo}-{hi} range for '{article_type}' — topic may be too narrow to stand alone"
    if n > hi:
        return "WARN", f"word count {n} is above the {lo}-{hi} range for '{article_type}' — consider splitting into two articles"
    return "PASS", f"word count {n} is within {lo}-{hi} for '{article_type}'"


def check_banned_words(text, extra_ban_words):
    hits = []
    for word in DEFAULT_BAN_WORDS + list(extra_ban_words):
        if re.search(re.escape(word), text, re.IGNORECASE):
            hits.append(word)
    if hits:
        return "WARN", f"banned words present: {', '.join(hits)}"
    return "PASS", "no banned words found"


OPENING_FUNCTION_LABELS = [
    "answer", "assertion", "scenario", "contrast", "continuation", "evidence", "question",
    "common mistakes", "verdict",
]


def check_visible_function_labels(text):
    """Catches a real artifact found 2026-08-09: the model took the prompt
    template's internal "assign each H2 an opening function" planning step
    too literally and printed the function name itself as a visible bolded
    label ("**Answer.**", "**Scenario.**") at the start of sections — just
    as mechanical a repetition as the pattern the rule exists to prevent,
    and NOT caught by check_structural_repetition (each label is a
    different word, so no adjacent-repeat trigger fires). Found by
    generating two fresh test articles and actually reading them, not by
    trusting the other automated checks.
    """
    hits = []
    for label in OPENING_FUNCTION_LABELS:
        for m in re.finditer(rf"^\*\*{re.escape(label)}\.\*\*", text, re.IGNORECASE | re.MULTILINE):
            line_no = text[: m.start()].count("\n") + 1
            hits.append(f"line {line_no}: {m.group(0)!r}")
    if hits:
        return "FAIL", "visible opening-function labels found (should be internal planning only): " + "; ".join(hits)
    return "PASS", "no visible opening-function labels found"


def check_fabrication_placeholders(text):
    hits = []
    for pattern in PLACEHOLDER_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            line_no = text[: m.start()].count("\n") + 1
            hits.append(f"line {line_no}: /{pattern}/ -> {m.group(0)!r}")
    if hits:
        return "FAIL", "placeholder/fabrication patterns found:\n    " + "\n    ".join(hits)
    return "PASS", "no placeholder/fabrication patterns found"


def check_structured_element(text):
    has_table = "|" in text and re.search(r"^\s*\|.*\|.*\|\s*$", text, re.MULTILINE)
    has_numbered_list = re.search(r"^\s*\d+\.\s", text, re.MULTILINE)
    if has_table or has_numbered_list:
        kind = "table" if has_table else "numbered list"
        return "PASS", f"found a structured element ({kind})"
    return "WARN", "no markdown table or numbered list found — RULES.md §2 wants at least one structured element"


def check_bare_urls(text):
    """Catch a real generation bug: the model names a competitor's URL as bare
    parenthetical text — "YNAB (https://ynab.com)" — instead of a Markdown
    link. It reads fine to a human but registers as zero links to the linking
    scorer and to any real crawler looking for an anchor tag. See RULES.md §16/17.
    """
    markdown_link_spans = [m.span() for m in re.finditer(r"\[[^\]]+\]\(https?://[^)]+\)", text)]

    def _inside_markdown_link(pos):
        return any(start <= pos < end for start, end in markdown_link_spans)

    bare = []
    for m in re.finditer(r"\(https?://[^)\s]+\)", text):
        if not _inside_markdown_link(m.start()):
            bare.append(m.group(0))
    if bare:
        return "FAIL", f"{len(bare)} bare URL(s) in parentheses, not Markdown links: {bare[:3]}"
    return "PASS", "no bare parenthetical URLs found"


def check_h1_present(text, target_query):
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if not m:
        return "FAIL", "no H1 (# heading) found"
    h1 = m.group(1).strip().lower()
    query_words = set(re.findall(r"\w+", target_query.lower()))
    h1_words = set(re.findall(r"\w+", h1))
    overlap = len(query_words & h1_words) / max(len(query_words), 1)
    if overlap < 0.5:
        return "WARN", f"H1 ({h1!r}) overlaps only {overlap:.0%} with target query ({target_query!r})"
    return "PASS", f"H1 matches target query closely ({overlap:.0%} word overlap)"


STOPWORDS = {"the", "a", "an", "and", "or", "to", "of", "up", "only", "not", "on", "for", "with"}


def check_structural_repetition(text):
    """WARN-only signal for the flat-register failure mode (RULES.md §7/§12):
    every H2's opening paragraph using the same shape. This is a coarse
    proxy, not comprehension — per cross-model review (DeepSeek + Codex,
    2026-08-09), a simplistic variance/repetition threshold is gameable and
    must not be treated as a hard gate. Use it to flag sections worth a
    human's attention, not to auto-reject a draft.
    """
    sections = re.split(r"^##\s+.+$", text, flags=re.MULTILINE)[1:]
    headings = re.findall(r"^##\s+(.+)$", text, flags=re.MULTILINE)
    if len(sections) < 3:
        return "PASS", "too few H2 sections to assess repetition"

    first_words = []
    sentence_lengths_per_section = []
    for section in sections:
        para = section.strip().split("\n\n")[0].strip()
        words = re.findall(r"[A-Za-z']+", para)
        first_words.append(words[0].lower() if words else "")
        sentences = re.split(r"(?<=[.!?])\s+", para)
        lengths = [len(re.findall(r"\w+", s)) for s in sentences if s.strip()]
        sentence_lengths_per_section.append(lengths)

    repeats = []
    for i in range(1, len(first_words)):
        if first_words[i] and first_words[i] == first_words[i - 1]:
            repeats.append(f"'{headings[i-1]}' and '{headings[i]}' both open with {first_words[i]!r}")

    flat_sections = []
    for h, lengths in zip(headings, sentence_lengths_per_section):
        if len(lengths) >= 2:
            spread = max(lengths) - min(lengths)
            if spread <= 2:
                flat_sections.append(h)

    warnings = []
    if repeats:
        warnings.append("adjacent sections share an opening word: " + "; ".join(repeats))
    if len(flat_sections) >= max(2, len(headings) // 2):
        warnings.append(f"{len(flat_sections)}/{len(headings)} sections have near-uniform sentence length in their opening paragraph")

    if warnings:
        return "WARN", "; ".join(warnings)
    return "PASS", "no obvious structural repetition detected (coarse heuristic — still worth a human skim)"


def _keywords(phrase):
    words = re.findall(r"[a-zA-Z-]+", phrase.lower())
    return {w for w in words if len(w) > 3 and w not in STOPWORDS}


def check_tier_gated_mentions(text, real_differentiators):
    """Heuristic only, word-overlap based (not exact-phrase matching, which
    misses paraphrased mentions almost entirely). If enough of a tier-gated
    feature's keywords show up in the text, treat that feature as
    "discussed" and check whether the tier's own keyword also appears
    anywhere in the text. This catches the exact bug class from 2026-08-09
    (a Family-only feature described without naming the tier) but remains
    NOT a substitute for the manual cross-check in RULES.md §2b — word
    overlap is a coarse signal, not comprehension. It can both miss real
    instances (a feature discussed with zero shared keywords) and flag
    false positives (keywords present for an unrelated reason).
    """
    text_lower = text.lower()
    warnings = []
    for d in real_differentiators:
        if not isinstance(d, dict):
            continue
        feature = d.get("feature", "")
        tier = d.get("tier", "")
        if not feature or not tier:
            continue
        feature_kw = _keywords(feature)
        if not feature_kw:
            continue
        matched = {w for w in feature_kw if w in text_lower}
        if len(matched) >= min(2, len(feature_kw)):
            tier_kw = _keywords(tier)
            if not any(w in text_lower for w in tier_kw):
                warnings.append(
                    f"feature keywords {sorted(matched)} appear (from {feature!r}) but no tier keyword "
                    f"from {tier!r} was found anywhere in the text — verify manually"
                )
    if warnings:
        return "WARN", "; ".join(warnings)
    return "PASS", "no obvious tier-gating gaps found (heuristic only — still do the manual check)"


def run_checks(text, article_type, target_query, config):
    voice = config.get("voice", {})
    real_differentiators = config.get("verified_facts", {}).get("real_differentiators", [])

    checks = [
        ("Fabrication/placeholder gate", check_fabrication_placeholders(text)),
        ("Visible opening-function labels", check_visible_function_labels(text)),
        ("H1 matches target query", check_h1_present(text, target_query)),
        ("Bare URLs (not Markdown links)", check_bare_urls(text)),
        ("Word count", check_word_count(text, article_type)),
        ("Banned words", check_banned_words(text, voice.get("extra_ban_words", []))),
        ("Structured element present", check_structured_element(text)),
        ("Tier-gating mentions (heuristic)", check_tier_gated_mentions(text, real_differentiators)),
        ("Structural repetition (heuristic)", check_structural_repetition(text)),
    ]
    return checks


def main():
    parser = argparse.ArgumentParser(description="Run the automated compliance gate against an article draft")
    parser.add_argument("--draft", required=True, help="Path to the markdown draft")
    parser.add_argument("--config", required=True, help="Path to your project's config, e.g. site-config.<project>.json")
    parser.add_argument("--type", default="standard", choices=["pillar", "standard", "supporting"])
    parser.add_argument("--query", required=True, help="The target query this article is meant to answer")
    args = parser.parse_args()

    with open(args.draft, "r", encoding="utf-8") as f:
        text = f.read()
    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    checks = run_checks(text, args.type, args.query, config)

    hard_fail = False
    for name, (status, detail) in checks:
        marker = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}[status]
        print(f"{marker} [{status}] {name}: {detail}")
        if status == "FAIL":
            hard_fail = True

    print()
    if hard_fail:
        print("HARD FAIL — do not publish until fabrication/placeholder issues are fixed.")
        sys.exit(1)
    print("No hard failures. WARN items still need a human read against RULES.md/IMAGES.md before publishing.")


if __name__ == "__main__":
    main()
