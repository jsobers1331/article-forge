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

Consensus subtopic/entity = appears in at least 60% of at least five distinct
competitor domains. Smaller samples are insufficient and produce no consensus
signal.
"""

import argparse
import json
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

# Consensus is deliberately conservative. A small SERP sample is not enough to
# distinguish a real category expectation from one page's editorial choice.
CONSENSUS_MIN_FRACTION = 0.6
CONSENSUS_MIN_PAGES = 5

WEIGHTS = {
    "intent_match": 20,
    "topical_comprehensiveness": 25,
    "entity_coverage": 15,
    "structure_extractability": 15,
    "eeat": 15,
    "linking": 10,
}

# These weights deliberately exclude SERP-only pillars. A report without a
# current organic snapshot must still be useful, but it must not pretend that
# editorial checks are a ranking prediction.
READINESS_WEIGHTS = {
    "structure_extractability": 30,
    "eeat": 30,
    "linking": 20,
    "gate_compliance": 20,
}

REPORT_SCHEMA_VERSION = "article-forge.report.v1"


def _norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "up",
    "in",
    "on",
    "for",
    "with",
    "your",
    "you",
}


def _phrase_covered(phrase, text_lower, overlap_threshold=0.6):
    """Word-overlap match, not exact substring. Exact-substring matching
    penalizes honest paraphrasing — "settle-up tracker" doesn't register as
    covering competitor subtopic "settlement calculation" even though it's
    the same real feature described differently. For single/two-word brand
    or product names, require exact substring instead (paraphrase-matching
    "revolut" against unrelated text would produce nonsense matches).
    """
    text_lower = text_lower.lower()
    words = [
        w
        for w in re.findall(r"[a-z0-9'-]+", phrase.lower())
        if w not in _STOPWORDS and len(w) > 2
    ]

    def contains_token(token):
        return (
            re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text_lower)
            is not None
        )

    if len(words) <= 1:
        return bool(words) and contains_token(words[0])
    matched = sum(1 for w in words if contains_token(w))
    return (matched / len(words)) >= overlap_threshold


def _competitor_domain(competitor):
    domain = competitor.get("domain", "")
    if not domain:
        domain = urlsplit(competitor.get("url", "")).hostname or ""
    return domain.lower().removeprefix("www.").split(":", 1)[0]


def dedupe_competitors(competitors):
    """Keep the strongest result for each independent domain."""
    by_domain = {}
    for competitor in competitors:
        domain = _competitor_domain(competitor)
        key = domain or competitor.get("url", "")
        if key not in by_domain or competitor.get("position", 999) < by_domain[key].get(
            "position", 999
        ):
            by_domain[key] = competitor
    return list(by_domain.values())


def consensus_threshold(competitor_count):
    if competitor_count < CONSENSUS_MIN_PAGES:
        return None
    return max(2, math.ceil(competitor_count * CONSENSUS_MIN_FRACTION))


def consensus_items(competitors, key):
    competitors = dedupe_competitors(competitors)
    counts = {}
    for c in competitors:
        for item in c.get(key, []):
            n = _norm(item)
            counts[n] = counts.get(n, 0) + 1
    threshold = consensus_threshold(len(competitors))
    if threshold is None:
        return set(), counts
    return {item for item, n in counts.items() if n >= threshold}, counts


def score_topical_comprehensiveness(draft_text, competitors):
    if len(dedupe_competitors(competitors)) < CONSENSUS_MIN_PAGES:
        return 0.0, [], []
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
    if len(dedupe_competitors(competitors)) < CONSENSUS_MIN_PAGES:
        return 0.0, []
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
    # The generated format requires an H1 and a visible dateline before the
    # answer capsule. Skip those metadata blocks so the first-paragraph signal
    # measures the actual answer, not the document wrapper.
    first_para = ""
    for block in text.strip().split("\n\n") if text.strip() else []:
        candidate = block.strip()
        candidate = re.sub(
            r"^\s*#{1,6}\s+[^\n]+\s*$", "", candidate, flags=re.MULTILINE
        )
        candidate = re.sub(
            r"^\s*[*_]?Last updated:\s*[^\n]+[*_]?\s*$",
            "",
            candidate,
            flags=re.IGNORECASE | re.MULTILINE,
        ).strip()
        if re.search(r"\w", candidate):
            first_para = candidate
            break
    if (
        30
        <= len(re.findall(r"\w+", re.sub(r"^#.*$", "", first_para, flags=re.MULTILINE)))
        <= 120
    ):
        points += 1
    if re.search(r"^\s*\|.*\|.*\|\s*$", text, re.MULTILINE) or re.search(
        r"^\s*\d+\.\s", text, re.MULTILINE
    ):
        points += 1
    question_h2s = len(re.findall(r"^##\s+.+\?\s*$", text, re.MULTILINE))
    total_h2s = max(1, len(re.findall(r"^##\s+.+$", text, re.MULTILINE)))
    if question_h2s / total_h2s >= 0.3:
        points += 1
    if len(re.findall(r"^##\s+.+$", text, re.MULTILINE)) >= 4:
        points += 1
    return 100.0 * points / total


def score_eeat(
    text,
    has_real_stats,
    has_real_testimonials,
    has_real_sources=False,
    has_first_hand_evidence=False,
):
    points = 0
    total = 5
    if re.search(r"\bupdated\b|\bpublished\b", text, re.IGNORECASE):
        points += 1
    if has_real_stats and re.search(r"\d+%|\$\d", text) and has_real_sources:
        points += 1
    if has_first_hand_evidence and re.search(
        r"\bwe (tested|found|built|use)\b", text, re.IGNORECASE
    ):
        points += 1
    if has_real_sources and re.search(r"\[[^\]]+\]\(https?://[^)]+\)", text):
        points += 1
    if has_real_testimonials and re.search(
        r"testimonial|customer said|\"[^\"]+\"", text, re.IGNORECASE
    ):
        points += 1
    return 100.0 * points / total


def _is_own_host(href, domain):
    host = (urlsplit(href).hostname or "").lower().removeprefix("www.")
    expected = (domain or "").lower().removeprefix("www.").split(":", 1)[0]
    return bool(
        host and expected and (host == expected or host.endswith(f".{expected}"))
    )


def score_linking(
    text,
    domain,
    min_internal=None,
    max_internal=None,
    min_external=None,
    max_external=None,
):
    """Score link safety and usefulness without arbitrary link-count quotas."""
    links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)
    internal = []
    external = []
    unknown = []
    for link in links:
        href = link[1].strip()
        if href.startswith("/") and not href.startswith("//"):
            internal.append(link)
        elif urlsplit(href).scheme in {"http", "https"}:
            (internal if _is_own_host(href, domain) else external).append(link)
        else:
            unknown.append(href)
    word_count = len(re.findall(r"\w+", text))

    penalty = 0
    notes = []
    if unknown:
        notes.append(
            f"{len(unknown)} link(s) have unsupported or relative URL forms and need review"
        )
    if word_count > 0 and (len(internal) + len(external)) > 0:
        density = word_count / (len(internal) + len(external))
        if density < 50:
            penalty += 10
            notes.append(f"link density high: one link per ~{density:.0f} words")
    return max(0.0, 100.0 - penalty), notes


def score_draft(draft_text, snapshot, article_type, verified_facts, domain=None):
    competitors = snapshot.get("competitors", [])
    intent = snapshot.get("serp_intent", "informational")

    intent_score = score_intent_match(article_type, intent)
    topical_score, topical_gaps, _ = score_topical_comprehensiveness(
        draft_text, competitors
    )
    entity_score, entity_gaps = score_entity_coverage(draft_text, competitors)
    structure_score = score_structure_extractability(draft_text)
    eeat_score = score_eeat(
        draft_text,
        verified_facts.get("has_real_usage_stats", False),
        verified_facts.get("has_real_testimonials", False),
        verified_facts.get("has_real_sources", False),
        verified_facts.get("has_real_first_hand_evidence", False),
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
        "consensus_ready": len(dedupe_competitors(competitors)) >= CONSENSUS_MIN_PAGES,
        "consensus_min_pages": CONSENSUS_MIN_PAGES,
        "hard_gate_failed": intent_score < 50,
    }


def _gate_compliance_score(checks):
    """Turn the deterministic gate result into a report-only signal.

    WARN is intentionally partial credit rather than a pass. This score is
    not used to decide whether a draft may be published; ``check_article``
    remains the authority for that decision.
    """
    if not checks:
        return None
    points = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}
    return (
        100.0 * sum(points.get(status, 0.0) for _, (status, _) in checks) / len(checks)
    )


def score_readiness(draft_text, article_type, verified_facts, domain=None, checks=None):
    """Score the evidence available before a SERP consensus snapshot exists.

    This is intentionally a separate score from :func:`score_draft`. It gives
    generation runs a useful deterministic result while making the unavailable
    intent, topical, and entity evidence explicit instead of treating missing
    research as a zero-quality article.
    """
    del article_type  # The pre-SERP score cannot prove query intent alignment.
    verified_facts = verified_facts or {}
    eeat_score = score_eeat(
        draft_text,
        verified_facts.get("has_real_usage_stats", False),
        verified_facts.get("has_real_testimonials", False),
        verified_facts.get("has_real_sources", False),
        verified_facts.get("has_real_first_hand_evidence", False),
    )
    linking_score, linking_notes = score_linking(draft_text, domain)
    pillars = {
        "structure_extractability": score_structure_extractability(draft_text),
        "eeat": eeat_score,
        "linking": linking_score,
    }
    weights = dict(READINESS_WEIGHTS)
    gate_score = _gate_compliance_score(checks)
    if gate_score is not None:
        pillars["gate_compliance"] = gate_score
    else:
        weights.pop("gate_compliance")

    weight_total = sum(weights.values())
    total = sum(pillars[name] * weight / 100 for name, weight in weights.items())
    unassessed_pillars = [
        "intent_match",
        "topical_comprehensiveness",
        "entity_coverage",
    ]
    if gate_score is None:
        unassessed_pillars.append("gate_compliance")
    return {
        "total_score": round(total * 100 / weight_total, 1),
        "pillars": {name: round(score, 1) for name, score in pillars.items()},
        "topical_gaps": [],
        "entity_gaps": [],
        "linking_notes": linking_notes,
        "consensus_ready": False,
        "consensus_min_pages": CONSENSUS_MIN_PAGES,
        "hard_gate_failed": bool(
            checks and any(status == "FAIL" for status, _ in checks)
        ),
        "score_kind": "readiness",
        "evidence_status": "serp_snapshot_missing",
        "score_semantics": (
            "Pre-SERP editorial readiness based only on deterministic checks and "
            "configured evidence; not a ranking or traffic prediction."
        ),
        "assessed_pillars": list(pillars),
        "unassessed_pillars": unassessed_pillars,
    }


def _check_payload(checks):
    return [
        {"name": name, "status": status, "detail": detail}
        for name, (status, detail) in (checks or [])
    ]


_PILLAR_FIXES = {
    "intent_match": "Align the article format and answer depth with the observed query intent.",
    "topical_comprehensiveness": "Address the highest-frequency consensus subtopics that are relevant and supported by verified facts.",
    "entity_coverage": "Define the relevant entities readers need to understand, without adding unsupported claims.",
    "structure_extractability": "Strengthen the answer capsule, question-led headings, and a real table or numbered process so key answers are easy to extract.",
    "eeat": "Add only verifiable dates, first-party evidence, source links, or real usage evidence; never fill gaps with invented proof.",
    "linking": "Review link destinations and anchor relevance; keep links useful, safe, and connected to the article's next reader action.",
    "gate_compliance": "Resolve every warning or failure and rerun the full article gate before publication.",
}


def build_improvements(score_result, checks=None, snapshot_supplied=False):
    """Build prioritized, evidence-linked actions for a generated article."""
    improvements = []
    payload = _check_payload(checks)
    for check in payload:
        if check["status"] == "PASS":
            continue
        priority = "P0" if check["status"] == "FAIL" else "P1"
        improvements.append(
            {
                "priority": priority,
                "category": "publish_gate",
                "issue": f"{check['name']} is {check['status']}: {check['detail']}",
                "fix": "Resolve this gate result, then regenerate or rerun check_article.py.",
                "evidence": check["detail"],
            }
        )

    has_gate_failure = any(check["status"] == "FAIL" for check in payload)
    if not snapshot_supplied and not has_gate_failure:
        improvements.append(
            {
                "priority": "P1",
                "category": "research_evidence",
                "issue": "No organic SERP snapshot was supplied, so intent, topical consensus, and entity coverage were not assessed.",
                "fix": "Collect a current serp_snapshot.json with at least five independent organic domains, then rerun the report.",
                "evidence": f"Required independent-domain sample: {CONSENSUS_MIN_PAGES}; supplied: 0.",
            }
        )
    elif (
        snapshot_supplied
        and not score_result.get("consensus_ready")
        and not has_gate_failure
    ):
        supplied = score_result.get("competitor_count", 0)
        improvements.append(
            {
                "priority": "P1",
                "category": "research_evidence",
                "issue": "The supplied SERP snapshot is below the independent-domain consensus threshold.",
                "fix": f"Collect at least {CONSENSUS_MIN_PAGES} independent organic domains and rerun the report.",
                "evidence": f"Independent domains supplied: {supplied}; required: {CONSENSUS_MIN_PAGES}.",
            }
        )

    for gap in score_result.get("topical_gaps", [])[:10]:
        improvements.append(
            {
                "priority": "P1",
                "category": "topical_gap",
                "issue": f"Consensus subtopic is missing: {gap}",
                "fix": "Add a genuinely useful answer only if it fits the query and is supported by verified facts.",
                "evidence": "Observed in the supplied independent-domain SERP consensus.",
            }
        )
    for gap in score_result.get("entity_gaps", [])[:10]:
        improvements.append(
            {
                "priority": "P1",
                "category": "entity_gap",
                "issue": f"Consensus entity is missing: {gap}",
                "fix": "Explain the entity's relevance in plain language without inventing a relationship or claim.",
                "evidence": "Observed in the supplied independent-domain SERP consensus.",
            }
        )
    for note in score_result.get("linking_notes", []):
        improvements.append(
            {
                "priority": "P2",
                "category": "linking",
                "issue": note,
                "fix": _PILLAR_FIXES["linking"],
                "evidence": note,
            }
        )

    for pillar, score in score_result.get("pillars", {}).items():
        if score is None or score >= 95:
            continue
        priority = "P0" if score < 80 else "P2"
        improvements.append(
            {
                "priority": priority,
                "category": "score_pillar",
                "issue": f"{pillar} scored {score}/100.",
                "fix": _PILLAR_FIXES.get(
                    pillar, "Review this pillar against the current evidence."
                ),
                "evidence": f"Deterministic {score_result.get('score_kind', 'article')} scorer.",
            }
        )

    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return sorted(improvements, key=lambda item: priority_order[item["priority"]])


def score_for_report(
    draft_text,
    snapshot,
    article_type,
    verified_facts,
    domain=None,
    checks=None,
):
    """Return the right score mode for an always-on article report."""
    snapshot_supplied = snapshot is not None
    if snapshot_supplied and not isinstance(snapshot, dict):
        raise ValueError("SERP snapshot must be a JSON object")
    verified_facts = verified_facts or {}
    competitors = dedupe_competitors((snapshot or {}).get("competitors", []))
    if snapshot_supplied and len(competitors) >= CONSENSUS_MIN_PAGES:
        result = score_draft(
            draft_text,
            snapshot,
            article_type,
            verified_facts,
            domain=domain,
        )
        result.update(
            {
                "score_kind": "serp_parity",
                "evidence_status": "serp_consensus_ready",
                "score_semantics": (
                    "Deterministic comparison with the supplied SERP snapshot; "
                    "not a ranking or traffic prediction."
                ),
                "assessed_pillars": list(result["pillars"]),
                "unassessed_pillars": [],
                "competitor_count": len(competitors),
            }
        )
    else:
        result = score_readiness(
            draft_text,
            article_type,
            verified_facts,
            domain=domain,
            checks=checks,
        )
        result["evidence_status"] = (
            "serp_snapshot_insufficient"
            if snapshot_supplied
            else "serp_snapshot_missing"
        )
        if snapshot_supplied:
            result["score_semantics"] = (
                "Pre-consensus editorial readiness; the supplied SERP snapshot "
                "does not contain enough independent domains for topical/entity "
                "consensus, so this is not a ranking or traffic prediction."
            )
        result["competitor_count"] = len(competitors)
    result["improvements"] = build_improvements(
        result, checks=checks, snapshot_supplied=snapshot_supplied
    )
    if checks:
        result["hard_gate_failed"] = result["hard_gate_failed"] or any(
            status == "FAIL" for status, _ in checks
        )
    return result


def build_article_report(
    draft_text,
    config,
    topic,
    checks,
    snapshot=None,
    draft_filename=None,
    snapshot_source=None,
):
    """Create a durable, safe-to-share report for every generated draft."""
    score = score_for_report(
        draft_text,
        snapshot,
        topic.get("type", "standard"),
        config.get("verified_facts", {}),
        domain=config.get("domain"),
        checks=checks,
    )
    non_pass = [item for item in _check_payload(checks) if item["status"] != "PASS"]
    improvements = score["improvements"]
    score_payload = {
        key: value for key, value in score.items() if key != "improvements"
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "draft_filename": draft_filename,
        "target_query": topic.get("target_query"),
        "article_type": topic.get("type", "standard"),
        "serp_evidence": {
            "supplied": snapshot is not None,
            "source": snapshot_source,
            "keyword": (snapshot or {}).get("keyword") if snapshot else None,
            "schema_version": (snapshot or {}).get("schema_version")
            if snapshot
            else None,
            "competitor_count": score.get("competitor_count", 0),
            "consensus_min_pages": score["consensus_min_pages"],
        },
        "score": score_payload,
        "gate_checks": _check_payload(checks),
        "what_to_fix_next": improvements,
        "score_status": "improvements_available"
        if improvements
        else "no_automated_gaps_found",
        "human_review_required": [
            "Confirm every claim, date, pricing or tier statement, and CTA against current first-party sources.",
            "Review originality, usefulness, voice, legal meaning, and any editorial image/alt text before publication.",
        ],
        "publication_status": "blocked" if non_pass else "ready_for_human_review",
        "limits": [
            "An automated gate and score do not prove factual accuracy, originality, legal safety, indexing, or ranking.",
            "A SERP-parity score is evidence-relative to the supplied snapshot and is not a ranking probability.",
        ],
    }


def render_report_markdown(report):
    """Render a concise human-readable companion to the JSON report."""
    score = report["score"]
    lines = [
        "# Article Forge report",
        "",
        f"- Score: **{score['total_score']}/100** ({score['score_kind']})",
        f"- Evidence: **{score['evidence_status']}**",
        f"- Score meaning: {score['score_semantics']}",
        f"- Query: {report.get('target_query') or 'not supplied'}",
        f"- Publication status: **{report['publication_status']}**",
        "",
        "## Pillars",
        "",
    ]
    for pillar, value in score.get("pillars", {}).items():
        lines.append(f"- {pillar}: {value}/100")
    lines.extend(["", "## What to fix next", ""])
    improvements = report.get("what_to_fix_next", [])
    if improvements:
        for item in improvements:
            lines.append(
                f"- **{item['priority']} — {item['category']}:** {item['issue']} "
                f"Fix: {item['fix']}"
            )
    else:
        lines.append(
            "- No automated improvement was identified in the measured evidence."
        )
    lines.extend(["", "## Gate checks", ""])
    for check in report.get("gate_checks", []):
        lines.append(f"- **{check['status']}** {check['name']}: {check['detail']}")
    lines.extend(["", "## Human review required", ""])
    lines.extend(f"- {item}" for item in report.get("human_review_required", []))
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {item}" for item in report.get("limits", []))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Score a draft against a SERP snapshot"
    )
    parser.add_argument("--draft", required=True)
    parser.add_argument(
        "--snapshot", help="Optional path to serp_snapshot.json for SERP-parity scoring"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to your project's config, e.g. site-config.<project>.json",
    )
    parser.add_argument(
        "--type", default="standard", choices=["pillar", "standard", "supporting"]
    )
    args = parser.parse_args()

    with open(args.draft, "r", encoding="utf-8") as f:
        draft_text = f.read()
    snapshot = None
    if args.snapshot:
        with open(args.snapshot, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    result = score_for_report(
        draft_text,
        snapshot,
        args.type,
        config.get("verified_facts", {}),
        domain=config.get("domain"),
    )

    print(
        f"TOTAL SCORE: {result['total_score']}/100 [{result['score_kind']}]"
        + (
            "  [HARD GATE FAILED — wrong format for search intent]"
            if result["hard_gate_failed"]
            else ""
        )
    )
    for pillar, score in result["pillars"].items():
        weight = WEIGHTS.get(pillar, READINESS_WEIGHTS.get(pillar, 0))
        print(f"  {pillar}: {score}/100 (weight {weight}%)")
    if result["topical_gaps"]:
        print(
            "\nTopical gaps (consensus subtopics we don't cover, highest-frequency first):"
        )
        for g in result["topical_gaps"][:10]:
            print(f"  - {g}")
    if result["entity_gaps"]:
        print("\nEntity gaps:")
        for g in result["entity_gaps"][:10]:
            print(f"  - {g}")
    if result["linking_notes"]:
        print("\nLinking:")
        for n in result["linking_notes"]:
            print(f"  - {n}")

    if result["improvements"]:
        print("\nWhat to fix next:")
        for item in result["improvements"][:10]:
            print(f"  - [{item['priority']}] {item['fix']}")

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
