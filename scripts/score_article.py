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
from pathlib import Path
from urllib.parse import urlsplit

from check_article import run_checks
from serp_contract import independent_domain, policy_for, validate_snapshot
from evidence_contract import object_hash, text_hash

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
}

REPORT_SCHEMA_VERSION = "article-forge.report.v2"


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
    return independent_domain(
        competitor.get("url") or f"https://{competitor.get('domain', '')}"
    )


def dedupe_competitors(competitors):
    """Keep the strongest result for each independent domain."""
    by_domain = {}
    for competitor in competitors:
        if not isinstance(competitor, dict):
            continue
        domain = _competitor_domain(competitor)
        key = domain or competitor.get("url", "")
        position = competitor.get("position", 999)
        previous = by_domain.get(key, {}).get("position", 999)
        if key not in by_domain or (position if isinstance(position, int) else 999) < (
            previous if isinstance(previous, int) else 999
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
        for n in {_norm(item) for item in c.get(key, [])}:
            counts[n] = counts.get(n, 0) + 1
    threshold = consensus_threshold(len(competitors))
    if threshold is None:
        return set(), counts
    return {item for item, n in counts.items() if n >= threshold}, counts


def score_topical_comprehensiveness(draft_text, competitors):
    if len(dedupe_competitors(competitors)) < CONSENSUS_MIN_PAGES:
        return None, [], []
    consensus, counts = consensus_items(competitors, "subtopics")
    if not consensus:
        return None, [], []
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
        return None, []
    union, counts = consensus_items(competitors, "entities")
    if not union:
        return None, []
    draft_lower = draft_text.lower()
    covered = [e for e in union if _phrase_covered(e, draft_lower)]
    missing = sorted([e for e in union if e not in covered], key=lambda e: -counts[e])
    score = 100.0 * len(covered) / len(union)
    return score, missing


def score_intent_match(draft_type, serp_intent, draft_text=None):
    """Intent needs a content review; article length/type does not prove it."""
    if serp_intent not in {
        "informational",
        "commercial-investigation",
        "transactional",
        "navigational",
        "local",
    }:
        return None
    if not draft_text:
        return None
    # Deterministic cues are observations, not semantic intent approval.
    cues = {
        "informational": r"\b(?:means|defined|how|why|steps)\b",
        "commercial-investigation": r"\b(?:compare|comparison|versus|alternative|trade.?off)\b",
        "transactional": r"\b(?:buy|book|request|sign up|purchase)\b",
        "navigational": r"\b(?:login|contact|support|official)\b",
        "local": r"\b(?:location|address|visit|service area)\b",
    }
    return 60.0 if re.search(cues[serp_intent], draft_text, re.I) else None


def score_structure_extractability(text):
    """Observe readability without prescribing a universal article template."""
    if not text.strip():
        return 0.0
    return (
        100.0
        * sum(
            [
                bool(re.search(r"^#\s+.+", text, re.M)),
                bool(re.search(r"\w", re.sub(r"^#.*$", "", text, flags=re.M))),
                not any(len(p.split()) > 250 for p in text.split("\n\n")),
                not bool(re.search(r"\b(?:TBD|FIXME)\b", text)),
            ]
        )
        / 4
    )


def score_eeat(
    text,
    has_real_stats,
    has_real_testimonials,
    has_real_sources=False,
    has_first_hand_evidence=False,
):
    # Config booleans and phrases are not evidence of expertise/experience.
    # Record the actual manifest/brief review separately; numeric E-E-A-T is
    # unassessed until a defensible rubric and inspected assets are supplied.
    return None


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
    links = re.findall(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", text)
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
    if not links:
        return None, [
            "No links observed; internal-link usefulness/readiness is unassessed."
        ]
    if not internal:
        notes.append("No internal links observed; review the next reader action.")
        penalty += 30
    if unknown:
        penalty += 50
        notes.append(
            f"{len(unknown)} link(s) have unsupported or relative URL forms and need review"
        )
    if word_count > 0 and (len(internal) + len(external)) > 0:
        density = word_count / (len(internal) + len(external))
        if density < 50:
            penalty += 10
            notes.append(f"link density high: one link per ~{density:.0f} words")
    return max(0.0, 100.0 - penalty), notes


def _editorial_total(pillars, weights):
    if any(pillars.get(k) is None for k in weights):
        return None
    return round(
        sum(pillars[k] * w for k, w in weights.items()) / sum(weights.values()), 1
    )


def score_draft(
    draft_text,
    snapshot,
    article_type,
    verified_facts,
    domain=None,
    target_query=None,
    policy=None,
):
    verdict = validate_snapshot(
        snapshot,
        target_query
        or (snapshot.get("keyword") if isinstance(snapshot, dict) else None),
        policy,
    )
    if not verdict["valid"]:
        result = score_readiness(draft_text, article_type, verified_facts, domain)
        result["evidence_status"] = "serp_snapshot_invalid"
        result["evidence_reasons"] = verdict["reasons"]
        return result
    competitors = snapshot.get("competitors", [])
    intent = snapshot.get("serp_intent")

    intent_score = score_intent_match(article_type, intent, draft_text)
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
    total = _editorial_total(pillars, WEIGHTS)

    return {
        "total_score": total,
        "pillars": {
            k: round(v, 1) if v is not None else None for k, v in pillars.items()
        },
        "topical_gaps": topical_gaps,
        "entity_gaps": entity_gaps,
        "linking_notes": linking_notes,
        "consensus_ready": topical_score is not None and entity_score is not None,
        "consensus_min_pages": CONSENSUS_MIN_PAGES,
        "hard_gate_failed": False,
    }


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
    total = _editorial_total(pillars, weights)
    unassessed_pillars = [
        "intent_match",
        "topical_comprehensiveness",
        "entity_coverage",
    ]
    return {
        "total_score": total,
        "pillars": {
            name: round(score, 1) if score is not None else None
            for name, score in pillars.items()
        },
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
        "assessed_pillars": [k for k, v in pillars.items() if v is not None],
        "unassessed_pillars": unassessed_pillars
        + [k for k, v in pillars.items() if v is None],
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
    "structure_extractability": "Make the answer and next reader action clear; use headings, tables or steps when the task benefits.",
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
                "issue": "The supplied SERP snapshot is not valid for this assessment.",
                "fix": f"Collect at least {CONSENSUS_MIN_PAGES} independent organic domains and rerun the report.",
                "evidence": "; ".join(score_result.get("evidence_reasons", []))
                or f"Independent domains supplied: {supplied}; required: {CONSENSUS_MIN_PAGES}.",
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
    target_query=None,
    policy=None,
):
    """Return the right score mode for an always-on article report."""
    snapshot_supplied = snapshot is not None
    verified_facts = verified_facts or {}
    verdict = validate_snapshot(
        snapshot,
        target_query
        or (snapshot.get("keyword") if isinstance(snapshot, dict) else None),
        policy,
    )
    competitors = (
        dedupe_competitors(snapshot["competitors"]) if verdict["valid"] else []
    )
    if snapshot_supplied and verdict["valid"]:
        result = score_draft(
            draft_text,
            snapshot,
            article_type,
            verified_facts,
            domain=domain,
            target_query=target_query,
            policy=policy,
        )
        result.update(
            {
                "score_kind": "serp_parity",
                "evidence_status": "serp_consensus_ready"
                if result["consensus_ready"]
                else "serp_sample_valid_no_consensus",
                "score_semantics": (
                    "Deterministic comparison with the supplied SERP snapshot; "
                    "not a ranking or traffic prediction."
                ),
                "assessed_pillars": [
                    k for k, v in result["pillars"].items() if v is not None
                ],
                "unassessed_pillars": [
                    k for k, v in result["pillars"].items() if v is None
                ],
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
            "serp_snapshot_invalid" if snapshot_supplied else "serp_snapshot_missing"
        )
        if snapshot_supplied:
            result["score_semantics"] = (
                "Editorial observations only; SERP evidence did not pass the shared contract. "
                "Unknown pillars and totals are unassessed, never ranking predictions."
            )
        result["competitor_count"] = verdict["independent_domains"]
    result["evidence_validation"] = verdict
    result["evidence_reasons"] = (
        verdict["reasons"] if snapshot_supplied else ["No SERP snapshot supplied"]
    )
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
        target_query=topic.get("target_query"),
        policy=policy_for(config),
    )
    non_pass = [item for item in _check_payload(checks) if item["status"] != "PASS"]
    if snapshot is not None and not score["evidence_validation"]["valid"]:
        non_pass.append(
            {
                "name": "SERP evidence",
                "status": "WARN",
                "detail": "; ".join(score["evidence_reasons"]),
            }
        )
    for required in (
        "Claim verification ledger",
        "Final-draft claim coverage",
        "Evidence-led brief",
    ):
        if required not in [name for name, _ in checks]:
            non_pass.append(
                {
                    "name": required,
                    "status": "WARN",
                    "detail": "Required verification gate was not supplied",
                }
            )
    if not checks:
        non_pass.append(
            {
                "name": "Verification gates",
                "status": "WARN",
                "detail": "No gate results supplied",
            }
        )
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
            "keyword": snapshot.get("keyword") if isinstance(snapshot, dict) else None,
            "schema_version": snapshot.get("schema_version")
            if isinstance(snapshot, dict)
            else None,
            "competitor_count": score.get("competitor_count", 0),
            "consensus_min_pages": score["consensus_min_pages"],
        },
        "score": score_payload,
        "pillar_limits": {
            "intent_match": "Content cue heuristic only; human intent review required",
            "eeat": "Unassessed: self-declared flags and phrases do not prove experience",
            "linking": "Syntax/safety observations; anchor usefulness requires human review",
            "topical_comprehensiveness": "Lexical consensus coverage, not completeness or truth",
            "entity_coverage": "Lexical coverage, not semantic correctness",
        },
        "gate_checks": _check_payload(checks),
        "gate_assessment": {"all_pass": not non_pass, "non_pass": non_pass},
        "provenance": {
            "draft_sha256": text_hash(draft_text),
            "topic_sha256": object_hash(topic),
            "snapshot_sha256": object_hash(snapshot) if snapshot is not None else None,
        },
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


def _score_label(value):
    return "unassessed" if value is None else f"{value}/100"


def render_report_markdown(report):
    """Render a concise human-readable companion to the JSON report."""
    score = report["score"]
    lines = [
        "# Article Forge report",
        "",
        f"- Score: **{_score_label(score['total_score'])}** ({score['score_kind']})",
        f"- Evidence: **{score['evidence_status']}**",
        f"- Score meaning: {score['score_semantics']}",
        f"- Query: {report.get('target_query') or 'not supplied'}",
        f"- Publication status: **{report['publication_status']}**",
        "",
        "## Pillars",
        "",
    ]
    for pillar, value in score.get("pillars", {}).items():
        lines.append(f"- {pillar}: {_score_label(value)}")
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
    parser.add_argument(
        "--query",
        help="Target query used for the article gate and report; defaults to the snapshot keyword when available.",
    )
    parser.add_argument(
        "--no-ledger",
        action="store_true",
        help="Skip the claim-verification ledger check when generating a report.",
    )
    parser.add_argument(
        "--report-json",
        help="Write the complete Article Forge report as JSON to this path.",
    )
    parser.add_argument(
        "--report-markdown",
        help="Write a human-readable Markdown companion report to this path.",
    )
    parser.add_argument("--brief", help="Evidence-led editorial brief JSON")
    parser.add_argument("--manifest", help="Reviewed exact-draft manifest JSON")
    args = parser.parse_args()

    with open(args.draft, "r", encoding="utf-8") as f:
        draft_text = f.read()
    snapshot = None
    if args.snapshot:
        with open(args.snapshot, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    target_query = args.query or (snapshot or {}).get("keyword")
    if (args.report_json or args.report_markdown) and not target_query:
        parser.error(
            "--query is required for report output when no snapshot keyword is available"
        )

    checks = []
    if target_query:
        checks = run_checks(
            draft_text,
            args.type,
            target_query,
            config,
            config_path=args.config,
            use_ledger=not args.no_ledger,
            manifest=json.loads(Path(args.manifest).read_text())
            if args.manifest
            else None,
            snapshot=snapshot,
            brief=json.loads(Path(args.brief).read_text()) if args.brief else None,
            brief_root=Path(args.brief).parent if args.brief else None,
        )

    result = score_for_report(
        draft_text,
        snapshot,
        args.type,
        config.get("verified_facts", {}),
        domain=config.get("domain"),
        checks=checks,
        target_query=target_query,
        policy=policy_for(config),
    )
    report = build_article_report(
        draft_text,
        config,
        {"target_query": target_query, "type": args.type},
        checks,
        snapshot=snapshot,
        draft_filename=args.draft,
        snapshot_source=args.snapshot,
    )

    if args.report_json:
        Path(args.report_json).write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    if args.report_markdown:
        Path(args.report_markdown).write_text(
            render_report_markdown(report), encoding="utf-8"
        )

    print(
        f"TOTAL SCORE: {_score_label(result['total_score'])} [{result['score_kind']}]"
        + (
            "  [HARD GATE FAILED — wrong format for search intent]"
            if result["hard_gate_failed"]
            else ""
        )
    )
    for pillar, score in result["pillars"].items():
        weight = WEIGHTS.get(pillar, READINESS_WEIGHTS.get(pillar, 0))
        print(f"  {pillar}: {_score_label(score)} (editorial policy weight {weight}%)")
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
    if report["publication_status"] == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
