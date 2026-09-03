"""Score evidence-backed article opportunities without inventing demand.

The input is intentionally provider-neutral. Search Console, Keyword Planner,
Bing, a manual SERP study, or a future adapter can all populate the same
versioned record, but missing or stale evidence remains ``needs-data``.
"""

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "article-forge.opportunity.v1"
MIN_SERP_SAMPLE = 5
STALE_AFTER_DAYS = 90
WEIGHTS = {
    "demand": 0.30,
    "competition_opportunity": 0.25,
    "product_fit": 0.25,
    "content_fit": 0.20,
}
DECISIONS = ((70, "pursue"), (50, "investigate"), (0, "defer"))


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _score_field(record, field):
    value = record.get("score")
    if not _number(value) or not 0 <= value <= 100:
        return None
    return float(value)


def validate_candidate(candidate):
    errors = []
    for field in ("candidate_id", "query", "intent", "page_type"):
        if not isinstance(candidate.get(field), str) or not candidate[field].strip():
            errors.append(f"missing {field}")

    demand = candidate.get("demand")
    if not isinstance(demand, dict):
        errors.append("demand must be an object")
    else:
        if not demand.get("source"):
            errors.append("demand.source is required")
        if (
            not isinstance(demand.get("normalization"), str)
            or not demand["normalization"].strip()
        ):
            errors.append("demand.normalization is required to explain the 0-100 score")
        if demand.get("unit") not in {"searches", "impressions", "clicks"}:
            errors.append("demand.unit must be searches, impressions, or clicks")
        if not _number(demand.get("value")) or demand["value"] < 0:
            errors.append("demand.value must be a non-negative number")
        if not _number(demand.get("score")) or not 0 <= demand["score"] <= 100:
            errors.append("demand.score must be a normalized 0-100 score")
        if not _number(demand.get("sample_size")) or demand["sample_size"] < 5:
            errors.append("demand.sample_size must be at least 5 observations/months")
        if not _parse_date(demand.get("observed_at")):
            errors.append("demand.observed_at must be YYYY-MM-DD or ISO-8601")
        if (
            demand.get("source") == "search_console"
            and demand.get("unit") == "searches"
        ):
            errors.append(
                "Search Console impressions/clicks are site signals, not market search volume"
            )

    competition = candidate.get("organic_competition")
    if not isinstance(competition, dict):
        errors.append("organic_competition must be an object")
    else:
        if not competition.get("source"):
            errors.append("organic_competition.source is required")
        if (
            not _number(competition.get("difficulty_score"))
            or not 0 <= competition["difficulty_score"] <= 100
        ):
            errors.append(
                "organic_competition.difficulty_score must be normalized 0-100"
            )
        if (
            not _number(competition.get("sample_size"))
            or competition["sample_size"] < MIN_SERP_SAMPLE
        ):
            errors.append(
                f"organic_competition.sample_size must be at least {MIN_SERP_SAMPLE} SERP results"
            )
        if not _parse_date(competition.get("observed_at")):
            errors.append(
                "organic_competition.observed_at must be YYYY-MM-DD or ISO-8601"
            )

    for field in ("product_fit", "content_fit"):
        record = candidate.get(field)
        if not isinstance(record, dict):
            errors.append(f"{field} must be an object")
            continue
        if record.get("rubric_version") != "1.0":
            errors.append(f"{field}.rubric_version must be 1.0")
        if _score_field(record, field) is None:
            errors.append(f"{field}.score must be normalized 0-100")
        if (
            not isinstance(record.get("rationale"), str)
            or not record["rationale"].strip()
        ):
            errors.append(f"{field}.rationale is required")
        if not isinstance(record.get("evidence"), list) or not record["evidence"]:
            errors.append(f"{field}.evidence must contain at least one evidence item")
    return errors


def _is_stale(candidate, today=None):
    today = today or date.today()
    dates = [
        _parse_date(candidate.get("demand", {}).get("observed_at")),
        _parse_date(candidate.get("organic_competition", {}).get("observed_at")),
    ]
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
                f"demand or organic competition data is older than {STALE_AFTER_DAYS} days"
            ],
        }

    demand_score = float(candidate["demand"]["score"])
    competition_opportunity = 100.0 - float(
        candidate["organic_competition"]["difficulty_score"]
    )
    product_fit = float(candidate["product_fit"]["score"])
    content_fit = float(candidate["content_fit"]["score"])
    score = (
        demand_score * WEIGHTS["demand"]
        + competition_opportunity * WEIGHTS["competition_opportunity"]
        + product_fit * WEIGHTS["product_fit"]
        + content_fit * WEIGHTS["content_fit"]
    )
    decision = next(label for threshold, label in DECISIONS if score >= threshold)
    return {
        **candidate,
        "status": "scored",
        "decision": decision,
        "opportunity_score": round(score, 1),
        "competition_opportunity_score": round(competition_opportunity, 1),
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
    print("QUERY | STATUS | DECISION | SCORE | MISSING EVIDENCE")
    for candidate in document["candidates"]:
        missing = "; ".join(candidate.get("missing_evidence", [])) or "-"
        score = candidate.get("opportunity_score")
        print(
            f"{candidate.get('query', '')} | {candidate.get('status')} | "
            f"{candidate.get('decision')} | {score if score is not None else '-'} | {missing}"
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
