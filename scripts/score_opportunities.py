"""Score evidence-backed article opportunities without inventing demand.

The input is intentionally provider-neutral. Keyword Planner, Search Console,
Serper, a manual SERP study, or a future adapter can populate the evidence
records, but missing or stale evidence remains ``needs-data``. Editorial
difficulty and intent are hypotheses with provenance, not Google ranking facts.
"""

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "article-forge.opportunity.v1"
MIN_SERP_SAMPLE = 5
STALE_AFTER_DAYS = 90
MIN_EVIDENCE_CONFIDENCE = 80
WEIGHTS = {
    "demand": 0.30,
    "competition_opportunity": 0.25,
    "product_fit": 0.25,
    "content_fit": 0.20,
}
DECISIONS = ((70, "pursue"), (50, "investigate"), (0, "defer"))
INTENT_HYPOTHESES = {
    "informational",
    "commercial_investigation",
    "transactional",
    "navigational",
    "local",
    "news",
    "multimedia",
    "mixed",
}
FRESHNESS_STATUSES = {"current", "evergreen", "time_sensitive", "needs_review"}
EDITORIAL_DIFFICULTY_EVIDENCE_TYPES = {
    "content_depth_assessment",
    "first_party_comparison",
    "freshness_assessment",
    "intent_match_assessment",
    "manual_page_review",
}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _score_field(record):
    value = record.get("score")
    if not _number(value) or not 0 <= value <= 100:
        return None
    return float(value)


def _nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def _nonempty_list(value):
    return (
        isinstance(value, list)
        and bool(value)
        and all(_nonempty_string(item) for item in value)
    )


def _validate_demand(demand):
    errors = []
    if not isinstance(demand, dict):
        return ["demand must be an object"]
    source = demand.get("source")
    if not _nonempty_string(source):
        errors.append("demand.source is required")
    role = demand.get("role")
    if role not in {"market_demand", "site_opportunity"}:
        errors.append("demand.role must be market_demand or site_opportunity")
    if not _nonempty_string(demand.get("normalization")):
        errors.append("demand.normalization is required to explain the 0-100 score")
    if demand.get("unit") not in {"searches", "impressions", "clicks"}:
        errors.append("demand.unit must be searches, impressions, or clicks")
    if not _number(demand.get("value")) or demand["value"] < 0:
        errors.append("demand.value must be a non-negative number")
    if _score_field(demand) is None:
        errors.append("demand.score must be a normalized 0-100 score")
    if not _number(demand.get("sample_size")) or demand["sample_size"] < 5:
        errors.append("demand.sample_size must be at least 5 observations/months")
    if not _parse_date(demand.get("observed_at")):
        errors.append("demand.observed_at must be YYYY-MM-DD or ISO-8601")
    if source == "search_console":
        if role != "site_opportunity":
            errors.append("Search Console demand must use role site_opportunity")
        if demand.get("unit") == "searches":
            errors.append(
                "Search Console impressions/clicks are site signals, not market search volume"
            )
    if source == "keyword_planner":
        if role != "market_demand" or demand.get("unit") != "searches":
            errors.append("Keyword Planner market demand must use unit searches")
    return errors


def _validate_intent(candidate):
    record = candidate.get("intent_evidence")
    if not isinstance(record, dict):
        return ["intent_evidence must be an object with raw observed signals"]
    errors = []
    if not _nonempty_string(record.get("source")):
        errors.append("intent_evidence.source is required")
    if not _nonempty_list(record.get("signals")):
        errors.append("intent_evidence.signals must contain observed signals")
    if not _parse_date(record.get("observed_at")):
        errors.append("intent_evidence.observed_at must be YYYY-MM-DD or ISO-8601")
    hypothesis = record.get("intent_hypothesis")
    if hypothesis is not None:
        if hypothesis not in INTENT_HYPOTHESES:
            errors.append("intent_evidence.intent_hypothesis is not a supported label")
        if (
            not _number(record.get("intent_confidence"))
            or not 0 <= record["intent_confidence"] <= 100
        ):
            errors.append("intent_evidence.intent_confidence must be normalized 0-100")
        if not _nonempty_string(record.get("intent_rationale")):
            errors.append(
                "intent_evidence.intent_rationale is required for a hypothesis"
            )
        if (
            record.get("intent_confidence", 0) > 90
            and len(record.get("signals", [])) < 3
        ):
            errors.append(
                "intent confidence over 90 requires at least three corroborating signals"
            )
    return errors


def _validate_fit(record, field):
    errors = []
    if not isinstance(record, dict):
        return [f"{field} must be an object"]
    if record.get("rubric_version") != "1.0":
        errors.append(f"{field}.rubric_version must be 1.0")
    if record.get("score_semantics") != "editorial":
        errors.append(f"{field}.score_semantics must be editorial")
    if _score_field(record) is None:
        errors.append(f"{field}.score must be normalized 0-100")
    if not _nonempty_string(record.get("rationale")):
        errors.append(f"{field}.rationale is required")
    if not _nonempty_list(record.get("evidence")):
        errors.append(f"{field}.evidence must contain non-empty evidence items")
    return errors


def _validate_product_fit(record):
    errors = _validate_fit(record, "product_fit")
    if isinstance(record, dict):
        evidence_types = set(record.get("evidence_types") or [])
        for required in ("first_party_fact", "verified_claim"):
            if required not in evidence_types:
                errors.append(f"product_fit.evidence_types must include {required}")
    return errors


def _validate_content_fit(record):
    errors = _validate_fit(record, "content_fit")
    if isinstance(record, dict):
        for field in ("original_angle", "limitation", "unanswered_question"):
            if not _nonempty_string(record.get(field)):
                errors.append(f"content_fit.{field} is required")
        source_dates = record.get("source_dates")
        if (
            not isinstance(source_dates, list)
            or not source_dates
            or any(not _parse_date(value) for value in source_dates)
        ):
            errors.append("content_fit.source_dates must contain at least one ISO date")
        evidence_types = set(record.get("evidence_types") or [])
        for required in ("original_angle", "limitation", "unanswered_question"):
            if required not in evidence_types:
                errors.append(f"content_fit.evidence_types must include {required}")
    return errors


def _validate_organic_competition(record):
    if not isinstance(record, dict):
        return ["organic_competition must be an object"]
    errors = []
    if not _nonempty_string(record.get("source")):
        errors.append("organic_competition.source is required")
    if (
        not _number(record.get("sample_size"))
        or record["sample_size"] < MIN_SERP_SAMPLE
    ):
        errors.append(
            f"organic_competition.sample_size must be at least {MIN_SERP_SAMPLE} SERP results"
        )
    if not _parse_date(record.get("observed_at")):
        errors.append("organic_competition.observed_at must be YYYY-MM-DD or ISO-8601")

    editorial = record.get("editorial_difficulty")
    if editorial is not None:
        if not isinstance(editorial, dict):
            errors.append("organic_competition.editorial_difficulty must be an object")
        else:
            if _score_field(editorial) is None:
                errors.append("editorial_difficulty.score must be normalized 0-100")
            if not _nonempty_string(editorial.get("rationale")):
                errors.append("editorial_difficulty.rationale is required")
            if not _nonempty_list(editorial.get("evidence")):
                errors.append(
                    "editorial_difficulty.evidence must contain non-empty items"
                )
            evidence_types = set(editorial.get("evidence_types") or [])
            if not evidence_types.intersection(EDITORIAL_DIFFICULTY_EVIDENCE_TYPES):
                errors.append(
                    "editorial_difficulty.evidence_types must identify a manual, depth, intent, freshness, or first-party assessment"
                )
            if editorial.get("semantics") != "editorial_estimate":
                errors.append(
                    "editorial_difficulty.semantics must be editorial_estimate"
                )
            if record.get("source") == "serper":
                count_only = {
                    "serper",
                    "serper api",
                    "serp record",
                    "result count",
                    "organic result count",
                    "host count",
                    "unique hosts",
                    "total results",
                }
                evidence = {
                    " ".join(str(item).lower().split())
                    for item in editorial.get("evidence", [])
                }
                if evidence and evidence.issubset(count_only):
                    errors.append(
                        "Serper observations cannot be the sole basis for editorial difficulty"
                    )
    if record.get("source") == "serper":
        if not _nonempty_string(record.get("serp_cache_key")):
            errors.append("Serper organic evidence requires serp_cache_key provenance")
        if not _parse_date(record.get("serp_retrieved_at")):
            errors.append("Serper organic evidence requires serp_retrieved_at")
        observations = record.get("observations")
        if not isinstance(observations, dict):
            errors.append("Serper organic evidence requires observations")
        else:
            if (
                not _number(observations.get("organic_result_count"))
                or observations["organic_result_count"] < MIN_SERP_SAMPLE
            ):
                errors.append(
                    f"Serper observations need at least {MIN_SERP_SAMPLE} organic results"
                )
            if (
                not _number(observations.get("unique_hosts"))
                or observations["unique_hosts"] < MIN_SERP_SAMPLE
            ):
                errors.append(
                    f"Serper observations need at least {MIN_SERP_SAMPLE} unique hosts"
                )
    if "difficulty_score" in record:
        errors.append(
            "use organic_competition.editorial_difficulty; legacy difficulty_score is ambiguous"
        )
    return errors


def _validate_freshness(record):
    if not isinstance(record, dict):
        return ["freshness must be an object"]
    errors = []
    if record.get("status") not in FRESHNESS_STATUSES:
        errors.append(f"freshness.status must be one of {sorted(FRESHNESS_STATUSES)}")
    if not _parse_date(record.get("observed_at")):
        errors.append("freshness.observed_at must be YYYY-MM-DD or ISO-8601")
    if (
        not _number(record.get("refresh_after_days"))
        or record["refresh_after_days"] < 1
    ):
        errors.append("freshness.refresh_after_days must be positive")
    if not _nonempty_string(record.get("source")):
        errors.append("freshness.source is required")
    if not _nonempty_list(record.get("evidence")):
        errors.append("freshness.evidence must contain non-empty items")
    return errors


def _validate_confidence(record):
    if not isinstance(record, dict):
        return ["evidence_confidence must be an object"]
    errors = []
    if _score_field(record) is None:
        errors.append("evidence_confidence.score must be normalized 0-100")
    if not _nonempty_string(record.get("rationale")):
        errors.append("evidence_confidence.rationale is required")
    if not _nonempty_list(record.get("evidence")):
        errors.append("evidence_confidence.evidence must contain non-empty items")
    return errors


def validate_candidate(candidate):
    errors = []
    for field in ("candidate_id", "query", "intent", "page_type"):
        if not _nonempty_string(candidate.get(field)):
            errors.append(f"missing {field}")
    errors.extend(_validate_demand(candidate.get("demand")))
    errors.extend(_validate_organic_competition(candidate.get("organic_competition")))
    errors.extend(_validate_intent(candidate))
    errors.extend(_validate_product_fit(candidate.get("product_fit")))
    errors.extend(_validate_content_fit(candidate.get("content_fit")))
    errors.extend(_validate_freshness(candidate.get("freshness")))
    errors.extend(_validate_confidence(candidate.get("evidence_confidence")))
    return errors


def _is_stale(candidate, today=None):
    today = today or date.today()
    dates = [
        _parse_date(candidate.get("demand", {}).get("observed_at")),
        _parse_date(candidate.get("organic_competition", {}).get("observed_at")),
    ]
    freshness = candidate.get("freshness", {})
    freshness_date = _parse_date(freshness.get("observed_at"))
    refresh_after = freshness.get("refresh_after_days", STALE_AFTER_DAYS)
    if freshness_date is not None and _number(refresh_after):
        if (today - freshness_date).days > refresh_after:
            return True
    return any(
        value is None or (today - value).days > STALE_AFTER_DAYS for value in dates
    )


def score_candidate(candidate, today=None):
    errors = validate_candidate(candidate)
    if errors:
        return {
            **candidate,
            "status": "needs-data",
            "decision": "needs-data",
            "opportunity_score": None,
            "missing_evidence": errors,
        }
    if _is_stale(candidate, today=today):
        return {
            **candidate,
            "status": "stale",
            "decision": "refresh-data",
            "opportunity_score": None,
            "missing_evidence": [
                "demand, organic competition, or freshness evidence is older than its allowed window"
            ],
        }
    if candidate["freshness"]["status"] == "needs_review":
        return {
            **candidate,
            "status": "needs-data",
            "decision": "needs-data",
            "opportunity_score": None,
            "missing_evidence": [
                "freshness.status is needs_review; refresh or explicitly re-attest the content evidence"
            ],
        }

    editorial = candidate["organic_competition"].get("editorial_difficulty")
    if not isinstance(editorial, dict):
        return {
            **candidate,
            "status": "needs-data",
            "decision": "needs-data",
            "opportunity_score": None,
            "missing_evidence": [
                "organic_competition.editorial_difficulty is optional for raw SERP evidence but required to calculate a prioritization score"
            ],
        }
    demand_score = float(candidate["demand"]["score"])
    competition_opportunity = 100.0 - float(editorial["score"])
    product_fit = float(candidate["product_fit"]["score"])
    content_fit = float(candidate["content_fit"]["score"])
    score = (
        demand_score * WEIGHTS["demand"]
        + competition_opportunity * WEIGHTS["competition_opportunity"]
        + product_fit * WEIGHTS["product_fit"]
        + content_fit * WEIGHTS["content_fit"]
    )
    decision = next(label for threshold, label in DECISIONS if score >= threshold)
    evidence_confidence = float(candidate["evidence_confidence"]["score"])
    confidence_gate = (
        "pass" if evidence_confidence >= MIN_EVIDENCE_CONFIDENCE else "below-80"
    )
    if decision == "pursue" and confidence_gate != "pass":
        decision = "investigate"
    return {
        **candidate,
        "status": "scored",
        "decision": decision,
        "opportunity_score": round(score, 1),
        "competition_opportunity_score": round(competition_opportunity, 1),
        "evidence_confidence": {
            **candidate["evidence_confidence"],
            "gate": confidence_gate,
        },
        "missing_evidence": [],
    }


def score_document(document):
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    candidates = document.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")
    return {
        **document,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "candidates": sorted(
            (score_candidate(candidate) for candidate in candidates),
            key=lambda item: (
                item["opportunity_score"] is None,
                -(item["opportunity_score"] or 0),
                item.get("query", ""),
            ),
        ),
    }


def print_report(document):
    print("QUERY | STATUS | DECISION | SCORE | CONFIDENCE | MISSING EVIDENCE")
    for candidate in document["candidates"]:
        missing = "; ".join(candidate.get("missing_evidence", [])) or "-"
        score = candidate.get("opportunity_score")
        confidence = candidate.get("evidence_confidence", {}).get("score", "-")
        print(
            f"{candidate.get('query', '')} | {candidate.get('status')} | "
            f"{candidate.get('decision')} | {score if score is not None else '-'} | "
            f"{confidence} | {missing}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Score evidence-backed content opportunities"
    )
    parser.add_argument("--input", required=True, help="Versioned opportunity JSON")
    parser.add_argument("--out", help="Write scored JSON to this path")
    args = parser.parse_args()

    document = json.loads(Path(args.input).read_text(encoding="utf-8"))
    scored = score_document(document)
    print_report(scored)
    if args.out:
        Path(args.out).write_text(json.dumps(scored, indent=2) + "\n", encoding="utf-8")
        print(f"Scored report written to {args.out}")


if __name__ == "__main__":
    main()
