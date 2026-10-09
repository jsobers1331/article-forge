"""Fixed-query workflow scorecard. Small samples and missing outcomes stay explicit."""

import argparse
import json
import math
from pathlib import Path
from statistics import mean

METRICS = (
    "factual_accuracy",
    "useful_original_contribution",
    "correct_page_choice",
    "evidence_validity",
    "human_review_minutes",
    "cost_usd",
    "elapsed_seconds",
)


def evaluate(document):
    if document.get("schema_version") != "article-forge.workflow-evaluation.v1":
        raise ValueError("versioned evaluation document required")
    queries = document.get("fixed_queries")
    if (
        not isinstance(queries, list)
        or not queries
        or len({q["site"] for q in queries}) < 2
    ):
        raise ValueError(
            "fixed query set must cover at least two configured businesses"
        )
    allowed = {(q["site"], q["query"]) for q in queries}
    runs = document.get("runs", [])
    for run in runs:
        if (run.get("site"), run.get("query")) not in allowed or run.get(
            "workflow"
        ) not in {"current", "evidence_led"}:
            raise ValueError("run outside fixed benchmark contract")
        if not all(
            run.get(k)
            for k in (
                "reviewer",
                "evidence_sha256",
                "forge_commit",
                "provider",
                "model",
            )
        ):
            raise ValueError("run missing evidence/reviewer/provider/commit")
        for metric in METRICS:
            value = run.get(metric)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value < 0
                or (isinstance(value, float) and not math.isfinite(value))
            ):
                raise ValueError("invalid evaluation metric")
            if metric in METRICS[:4] and value is not None and value > 1:
                raise ValueError(
                    "accuracy/contribution/page/evidence metrics must be proportions [0,1]"
                )
    groups = {}
    for workflow in ("current", "evidence_led"):
        sample = [r for r in runs if r["workflow"] == workflow and not r.get("holdout")]
        groups[workflow] = {
            "runs": len(sample),
            "metrics": {
                m: {
                    "mean": mean([r[m] for r in sample if r.get(m) is not None])
                    if any(r.get(m) is not None for r in sample)
                    else None,
                    "sample": sum(r.get(m) is not None for r in sample),
                }
                for m in METRICS
            },
        }
    paired = {
        (r["site"], r["query"])
        for r in runs
        if r["workflow"] == "current" and not r.get("holdout")
    } & {
        (r["site"], r["query"])
        for r in runs
        if r["workflow"] == "evidence_led" and not r.get("holdout")
    }
    minimum = max(5, document.get("minimum_paired_queries", 5))
    cohorts = document.get("published_cohorts", [])
    for cohort in cohorts:
        if cohort.get("review_day") not in {30, 60, 90} or not cohort.get(
            "source_sha256"
        ):
            raise ValueError(
                "cohort needs declared 30/60/90-day review and measured receipt"
            )
    return {
        "schema_version": "article-forge.workflow-scorecard.v1",
        "workflows": groups,
        "paired_queries": len(paired),
        "minimum_paired_queries": minimum,
        "evidence_status": "descriptive_comparison"
        if len(paired) >= minimum
        else "insufficient_sample",
        "holdout_runs": sum(bool(r.get("holdout")) for r in runs),
        "published_cohorts": cohorts,
        "weight_change_authorized": False,
        "limits": "Editorial weights are policy, not ranking predictors. Descriptive human review is not causal evidence. Missing live cohorts stay missing.",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate owner-supplied fixed-query workflow receipts locally"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = evaluate(json.loads(Path(args.input).read_text()))
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
