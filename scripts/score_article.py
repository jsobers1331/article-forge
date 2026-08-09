"""SERP-parity scorer + gap-fill refine loop.

Division of labor (article-forge scripts have no web-search/SEO-API access):
an orchestrating agent does the real research — search the keyword, fetch
the top-10 organic results, extract their headings/entities/subtopics — and
writes that into a serp_snapshot.json (schema below). This script is the
deterministic half: same snapshot + draft in, same score out, so a refine
loop actually converges instead of chasing noise.

serp_snapshot.json shape:
{
  "keyword": "...", "serp_intent": "commercial-investigation|informational|...",
  "competitors": [
    {"url": "...", "position": 1, "word_count": 2100,
     "headings": ["...", "..."], "subtopics": ["...", "..."], "entities": ["...", "..."]}
  ]
}

Consensus subtopic/entity = appears in >= CONSENSUS_MIN competitors (default 3,
or half the competitor count if fewer than 6 are supplied).
"""

import argparse
import json
import re

CONSENSUS_MIN_FRACTION = 0.4  # a subtopic/entity counts as "consensus" if this fraction of competitors cover it

WEIGHTS = {
    "intent_match": 20,
    "topical_comprehensiveness": 25,
    "entity_coverage": 15,
    "structure_extractability": 15,
    "eeat": 15,
    "linking": 10,
}


def _norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


_STOPWORDS = {"the", "a", "an", "and", "or", "to", "of", "up", "in", "on", "for", "with", "your", "you"}


def _phrase_covered(phrase, text_lower, overlap_threshold=0.6):
    """Word-overlap match, not exact substring. Exact-substring matching
    penalizes honest paraphrasing — "settle-up tracker" doesn't register as
    covering competitor subtopic "settlement calculation" even though it's
    the same real feature described differently. For single/two-word brand
    or product names, require exact substring instead (paraphrase-matching
    "revolut" against unrelated text would produce nonsense matches).
    """
    words = [w for w in re.findall(r"[a-z0-9'-]+", phrase.lower()) if w not in _STOPWORDS and len(w) > 2]
    if len(words) <= 1:
        return _norm(phrase) in text_lower
    matched = sum(1 for w in words if w in text_lower)
    return (matched / len(words)) >= overlap_threshold


def consensus_items(competitors, key):
    counts = {}
    for c in competitors:
        for item in c.get(key, []):
            n = _norm(item)
            counts[n] = counts.get(n, 0) + 1
    threshold = max(1, round(len(competitors) * CONSENSUS_MIN_FRACTION))
    return {item for item, n in counts.items() if n >= threshold}, counts


def score_topical_comprehensiveness(draft_text, competitors):
    consensus, counts = consensus_items(competitors, "subtopics")
    if not consensus:
        return 100.0, [], []
    draft_lower = draft_text.lower()
    covered = [s for s in consensus if _phrase_covered(s, draft_lower)]
    gaps = sorted(
        [s for s in consensus if s not in covered],
        key=lambda s: -counts[s],
    )
    score = 100.0 * len(covered) / len(consensus)
    return score, gaps, covered


def score_entity_coverage(draft_text, competitors):
    union, counts = consensus_items(competitors, "entities")
    if not union:
        return 100.0, []
    draft_lower = draft_text.lower()
    covered = [e for e in union if _phrase_covered(e, draft_lower)]
    missing = sorted([e for e in union if e not in covered], key=lambda e: -counts[e])
    score = 100.0 * len(covered) / len(union)
    return score, missing


def score_intent_match(draft_type, serp_intent):
    mapping = {
        "commercial-investigation": {"standard", "pillar"},
        "informational": {"pillar", "standard", "supporting"},
        "transactional": {"standard"},
    }
    ok_types = mapping.get(serp_intent, {"standard", "pillar", "supporting"})
    return 100.0 if draft_type in ok_types else 40.0


def score_structure_extractability(text):
    points = 0
    total = 4
    first_para = text.strip().split("\n\n")[0] if text.strip() else ""
    if 30 <= len(re.findall(r"\w+", re.sub(r"^#.*$", "", first_para, flags=re.MULTILINE))) <= 120:
        points += 1
    if re.search(r"^\s*\|.*\|.*\|\s*$", text, re.MULTILINE) or re.search(r"^\s*\d+\.\s", text, re.MULTILINE):
        points += 1
    question_h2s = len(re.findall(r"^##\s+.+\?\s*$", text, re.MULTILINE))
    total_h2s = max(1, len(re.findall(r"^##\s+.+$", text, re.MULTILINE)))
    if question_h2s / total_h2s >= 0.3:
        points += 1
    if len(re.findall(r"^##\s+.+$", text, re.MULTILINE)) >= 4:
        points += 1
    return 100.0 * points / total


def score_eeat(text, has_real_stats, has_real_testimonials):
    points = 0
    total = 4
    if re.search(r"\bupdated\b|\bpublished\b", text, re.IGNORECASE):
        points += 1
    if has_real_stats and re.search(r"\d+%|\$\d", text):
        points += 1
    elif not has_real_stats:
        points += 1  # not penalized for correctly omitting stats it doesn't have
    if re.search(r"\bwe (tested|found|built|use)\b|\bour\b", text, re.IGNORECASE):
        points += 1
    if has_real_testimonials or "testimonial" not in text.lower():
        points += 1  # correctly not faking testimonials counts as a pass, not a penalty
    return 100.0 * points / total


def score_linking(text, domain, min_internal=3, max_internal=5, min_external=2, max_external=4):
    links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)
    internal = [l for l in links if l[1].startswith("/") or (domain and domain in l[1])]
    external = [l for l in links if l[1].startswith("http") and not (domain and domain in l[1])]
    word_count = len(re.findall(r"\w+", text))

    penalty = 0
    notes = []
    if len(internal) < min_internal:
        penalty += 25
        notes.append(f"only {len(internal)} internal links (want {min_internal}-{max_internal})")
    if len(internal) > max_internal:
        penalty += 10
        notes.append(f"{len(internal)} internal links may be excessive (want {min_internal}-{max_internal})")
    if len(external) < min_external:
        penalty += 25
        notes.append(f"only {len(external)} external links (want {min_external}-{max_external})")
    if len(external) > max_external:
        penalty += 15
        notes.append(f"{len(external)} external links risks looking spammy (want {min_external}-{max_external})")
    if word_count > 0 and (len(internal) + len(external)) > 0:
        density = word_count / (len(internal) + len(external))
        if density < 100:
            penalty += 15
            notes.append(f"link density high: one link per ~{density:.0f} words (keep above ~150)")
    return max(0.0, 100.0 - penalty), notes


def score_draft(draft_text, snapshot, article_type, verified_facts, domain=None):
    competitors = snapshot.get("competitors", [])
    intent = snapshot.get("serp_intent", "informational")

    intent_score = score_intent_match(article_type, intent)
    topical_score, topical_gaps, _ = score_topical_comprehensiveness(draft_text, competitors)
    entity_score, entity_gaps = score_entity_coverage(draft_text, competitors)
    structure_score = score_structure_extractability(draft_text)
    eeat_score = score_eeat(
        draft_text,
        verified_facts.get("has_real_usage_stats", False),
        verified_facts.get("has_real_testimonials", False),
    )
    linking_score, linking_notes = score_linking(draft_text, domain)

    pillars = {
        "intent_match": intent_score,
        "topical_comprehensiveness": topical_score,
        "entity_coverage": entity_score,
        "structure_extractability": structure_score,
        "eeat": eeat_score,
        "linking": linking_score,
    }
    total = sum(pillars[k] * WEIGHTS[k] / 100 for k in WEIGHTS)

    return {
        "total_score": round(total, 1),
        "pillars": {k: round(v, 1) for k, v in pillars.items()},
        "topical_gaps": topical_gaps,
        "entity_gaps": entity_gaps,
        "linking_notes": linking_notes,
        "hard_gate_failed": intent_score < 50,
    }


def main():
    parser = argparse.ArgumentParser(description="Score a draft against a SERP snapshot")
    parser.add_argument("--draft", required=True)
    parser.add_argument("--snapshot", required=True, help="Path to serp_snapshot.json")
    parser.add_argument("--config", required=True, help="Path to your project's config, e.g. site-config.<project>.json")
    parser.add_argument("--type", default="standard", choices=["pillar", "standard", "supporting"])
    args = parser.parse_args()

    with open(args.draft, "r", encoding="utf-8") as f:
        draft_text = f.read()
    with open(args.snapshot, "r", encoding="utf-8") as f:
        snapshot = json.load(f)
    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    result = score_draft(draft_text, snapshot, args.type, config.get("verified_facts", {}), domain=config.get("domain"))

    print(f"TOTAL SCORE: {result['total_score']}/100" + ("  [HARD GATE FAILED — wrong format for search intent]" if result["hard_gate_failed"] else ""))
    for pillar, score in result["pillars"].items():
        print(f"  {pillar}: {score}/100 (weight {WEIGHTS[pillar]}%)")
    if result["topical_gaps"]:
        print(f"\nTopical gaps (consensus subtopics we don't cover, highest-frequency first):")
        for g in result["topical_gaps"][:10]:
            print(f"  - {g}")
    if result["entity_gaps"]:
        print(f"\nEntity gaps:")
        for g in result["entity_gaps"][:10]:
            print(f"  - {g}")
    if result["linking_notes"]:
        print(f"\nLinking:")
        for n in result["linking_notes"]:
            print(f"  - {n}")

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
