"""Measured feedback from synthetic export receipts; no live writes."""

from datetime import datetime, timedelta, timezone
import json
import subprocess
import sys

import pytest
from publication_registry import (
    empty_registry,
    add_publication,
    add_observation,
    compare_periods,
    review_registry,
    url_key,
    OBSERVATION_SCHEMA,
)
from evaluate_workflows import evaluate


def publication():
    return {
        "candidate_id": "candidate",
        "target_query": "service price",
        "evidence_packet_sha256": "packet-hash",
        "draft_sha256": "draft-hash",
        "reviewer": "Reviewer",
        "provider": "stub",
        "model": "stub-model",
        "canonical_url": "https://test.org/service",
        "published_at": (datetime.now(timezone.utc) - timedelta(days=100)).isoformat(),
        "content_version": "v1",
        "forge_commit": "test-commit",
        "review_windows_days": [30, 60, 90],
        "locale": {"country": "bb", "language": "en"},
        "conversion_definition": "confirmed inquiry",
    }


def measured_fixture():
    registry = empty_registry(
        {"canonical_host": "test.org", "equivalent_hosts": ["www.test.org"]}
    )
    pub = publication()
    pid = add_publication(registry, pub)
    start = datetime.now(timezone.utc).date() - timedelta(days=28)
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    observation = {
        "schema_version": OBSERVATION_SCHEMA,
        "publication_id": pid,
        "url": "https://www.test.org/service",
        "observed_from": start.isoformat(),
        "observed_to": end.isoformat(),
        "source": "synthetic_export",
        "source_sha256": "source-hash",
        "locale": pub["locale"],
        "conversion_definition": pub["conversion_definition"],
        "aggregation": "page",
        "seasonality": "comparable",
        "accessible": True,
        "indexed": True,
        "access_checked_at": datetime.now(timezone.utc).isoformat(),
        "index_checked_at": datetime.now(timezone.utc).isoformat(),
        "impressions": 100,
        "relevant_impressions": 80,
        "query_evidence": ["service price"],
        "clicks": 10,
        "qualified_actions": 2,
        "conversions": None,
    }
    return registry, pub, observation


def test_publication_versions_are_immutable_and_original_urls_are_retained():
    registry, pub, observation = measured_fixture()
    pid = add_publication(registry, pub)
    assert len(registry["publications"]) == 1
    pub["draft_sha256"] = "changed"
    with pytest.raises(ValueError, match="immutable"):
        add_publication(registry, pub)
    pub["content_version"] = "v2"
    assert add_publication(registry, pub) != pid
    add_observation(registry, observation)
    row = registry["observations"][0]
    assert row["url"] == "https://www.test.org/service"
    assert row["url_key"] == "https://test.org/service"


@pytest.mark.parametrize(
    "url",
    [
        "https://test.org.evil.org/service",
        "https://test.org@evil.org/",
        "https://unknown.org/",
        "file:///private/data",
    ],
)
def test_host_normalization_does_not_merge_unapproved_hosts(url):
    with pytest.raises(ValueError):
        url_key(
            url, {"canonical_host": "test.org", "equivalent_hosts": ["www.test.org"]}
        )


def test_query_strings_paths_and_trailing_slashes_are_not_silently_merged():
    identity = {"canonical_host": "test.org"}
    assert url_key("https://test.org/Service?variant=1", identity) != url_key(
        "https://test.org/service/", identity
    )


@pytest.mark.parametrize(
    "field,value,action,stage",
    [
        ("accessible", False, "improve", "accessible"),
        ("indexed", False, "improve", "indexed"),
        ("relevant_impressions", None, "defer", "relevant_impressions"),
        ("relevant_impressions", 0, "defer", "relevant_impressions"),
        ("clicks", 0, "improve", "clicks"),
        ("qualified_actions", None, "defer", "qualified_actions"),
        ("qualified_actions", 0, "improve", "qualified_actions"),
        ("sources_stale", True, "refresh", "evidence"),
    ],
)
def test_diagnosis_is_ordered_and_unknown_stays_unknown(field, value, action, stage):
    registry, _, observation = measured_fixture()
    observation[field] = value
    add_observation(registry, observation)
    review = review_registry(registry)["recommendations"][0]
    assert (review["action"], review["diagnostic_stage"]) == (action, stage)
    assert review["approval_required"]


def test_single_recommendation_per_url_and_minimum_window():
    registry, _, observation = measured_fixture()
    observation["observed_from"] = observation["observed_to"]
    add_observation(registry, observation)
    review = review_registry(registry)["recommendations"]
    assert len(review) == 1 and review[0]["action"] == "defer"
    assert review[0]["due_windows_days"] == [30, 60, 90]


def test_metrics_require_provenance_scope_and_version():
    registry, _, observation = measured_fixture()
    for field, value in [
        ("source_sha256", None),
        ("publication_id", "unknown"),
        ("qualified_actions", -1),
        ("conversion_definition", "other"),
        ("locale", {"country": "us"}),
        ("query_evidence", None),
    ]:
        bad = {**observation, field: value}
        with pytest.raises(ValueError):
            add_observation(registry, bad)


def test_rates_normalize_unequal_windows_and_reject_confounding_periods():
    before = {
        "locale": "bb",
        "source": "gsc",
        "conversion_definition": "inquiry",
        "aggregation": "page",
        "seasonality": "comparable",
        "observed_from": "2026-01-01",
        "observed_to": "2026-01-28",
        "days": 28,
        "clicks": 28,
        "impressions": 280,
    }
    after = {
        **before,
        "observed_from": "2026-02-01",
        "observed_to": "2026-05-01",
        "days": 90,
        "clicks": 90,
        "impressions": 900,
    }
    comparison = compare_periods(before, after)
    assert comparison["comparable"]
    assert comparison["rates"]["clicks"]["change_per_day"] == 0
    assert not compare_periods(before, {**after, "content_edits": ["new article"]})[
        "comparable"
    ]
    assert not compare_periods(before, {**after, "seasonality": None})["comparable"]


def test_ai_visibility_separates_available_citation_referral_and_conversion():
    registry, _, observation = measured_fixture()
    observation["ai_observations"] = [
        {
            "engine": "synthetic engine",
            "query": "service price",
            "locale": "bb-en",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "method": "human observation",
            "available": True,
            "citation_observed": False,
            "referrals": None,
            "conversions": None,
        }
    ]
    add_observation(registry, observation)
    row = registry["observations"][0]["ai_observations"][0]
    assert (
        row["available"] and not row["citation_observed"] and row["referrals"] is None
    )
    observation["ai_observations"][0].pop("method")
    with pytest.raises(ValueError):
        add_observation(registry, observation)


def test_registry_cli_persists_and_reviews_local_fixtures(tmp_path):
    registry, pub, observation = measured_fixture()
    identity = tmp_path / "identity.json"
    receipt = tmp_path / "publication.json"
    obs = tmp_path / "observation.json"
    identity.write_text(json.dumps(registry["site_identity"]))
    receipt.write_text(json.dumps(pub))
    obs.write_text(json.dumps(observation))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/publication_registry.py",
            "--registry",
            str(tmp_path / "registry.json"),
            "--identity",
            str(identity),
            "--publication",
            str(receipt),
            "--observation",
            str(obs),
            "--review-out",
            str(tmp_path / "review.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads((tmp_path / "review.json").read_text())
    assert payload["recommendations"][0]["action"] == "keep"


def test_benchmark_has_fixed_queries_sample_rules_and_missing_live_cohorts():
    document = {
        "schema_version": "article-forge.workflow-evaluation.v1",
        "fixed_queries": [
            {"site": "business-a", "query": "price"},
            {"site": "business-b", "query": "workflow"},
        ],
        "runs": [
            {
                "site": "business-a",
                "query": "price",
                "workflow": workflow,
                "reviewer": "Reviewer",
                "evidence_sha256": "hash",
                "forge_commit": "commit",
                "provider": "stub",
                "model": "stub",
                "factual_accuracy": 1,
                "useful_original_contribution": 0.5,
                "correct_page_choice": 1,
                "evidence_validity": 1,
                "human_review_minutes": 5,
                "cost_usd": 0,
                "elapsed_seconds": 1,
            }
            for workflow in ["current", "evidence_led"]
        ],
    }
    result = evaluate(document)
    assert result["evidence_status"] == "insufficient_sample"
    assert result["published_cohorts"] == [] and not result["weight_change_authorized"]
    document["runs"][0]["query"] = "unplanned query"
    with pytest.raises(ValueError):
        evaluate(document)


def test_existing_export_adapter_preserves_omissions_and_original_urls():
    from publication_registry import observation_from_exports

    registry, _, observation = measured_fixture()
    gsc = {
        "schema_version": "article-forge.gsc.v1",
        "dimensions": ["page"],
        "property": "sc-domain:test.org",
        "date_range": {
            "start": observation["observed_from"],
            "end": observation["observed_to"],
        },
        "rows": [
            {"page": "https://www.test.org/service", "impressions": 100, "clicks": 10}
        ],
    }
    indexing = {
        "schema_version": "article-forge.indexing.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "records": [{"url": "https://test.org/service", "status": "indexed"}],
    }
    row = observation_from_exports(
        registry, observation["publication_id"], gsc, indexing=indexing
    )
    assert row["clicks"] == 10 and row["indexed"] is True
    assert row["accessible"] is None and row["qualified_actions"] is None
    assert row["relevant_impressions"] is None
    assert row["original_urls"] == ["https://www.test.org/service"]
    assert row["source_artifacts"]["indexing"]
    add_observation(registry, row)
    gsc["rows"] = []
    row = observation_from_exports(registry, observation["publication_id"], gsc)
    assert row["impressions"] is None  # No row is not an observed zero.


def test_published_receipt_binds_to_actual_draft_report():
    from publication_registry import publication_from_report

    report = {"publication_status": "blocked"}
    with pytest.raises(ValueError):
        publication_from_report(report, publication())
    report = {
        "publication_status": "ready_for_human_review",
        "gate_assessment": {"all_pass": True},
        "target_query": "service price",
        "provenance": {
            "human_review": {"reviewer": "Actual reviewer"},
            "draft_sha256": "actual-hash",
            "forge_commit": "actual-commit",
            "candidate_id": "actual-candidate",
            "provider": "stub",
            "model": "stub-model",
            "manifest_sha256": "manifest-hash",
        },
    }
    row = publication_from_report(report, publication())
    assert row["draft_sha256"] == "actual-hash" and row["reviewer"] == "Actual reviewer"
    assert (
        row["candidate_id"] == "actual-candidate"
        and row["forge_commit"] == "actual-commit"
    )


def test_stale_observations_cannot_be_treated_as_current_success():
    registry, _, observation = measured_fixture()
    observation["observed_from"] = (
        datetime.now(timezone.utc).date() - timedelta(days=70)
    ).isoformat()
    observation["observed_to"] = (
        datetime.now(timezone.utc).date() - timedelta(days=40)
    ).isoformat()
    add_observation(registry, observation)
    review = review_registry(registry)["recommendations"][0]
    assert review["action"] == "defer" and "stale" in review["reason"]


def test_consolidation_requires_current_human_overlap_evidence():
    registry, _, observation = measured_fixture()
    observation["overlap_review"] = {
        "reviewer": "Reviewer",
        "decision": "consolidate",
        "evidence": "Actual content/intent comparison receipt",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    add_observation(registry, observation)
    assert review_registry(registry)["recommendations"][0]["action"] == "consolidate"
    registry["observations"][0]["overlap_review"]["reviewed_at"] = (
        "2020-01-01T00:00:00+00:00"
    )
    assert review_registry(registry)["recommendations"][0]["action"] == "keep"


@pytest.mark.parametrize("metric", ["relevant_clicks", "qualified_actions"])
@pytest.mark.parametrize("value", [-1, "unknown", True, float("nan"), float("inf")])
def test_diagnostic_metrics_reject_invalid_counts(metric, value):
    registry, _, observation = measured_fixture()
    observation[metric] = value
    with pytest.raises(ValueError, match="invalid metric"):
        add_observation(registry, observation)
    assert registry["observations"] == []


@pytest.mark.parametrize(
    "field,stage",
    [("access_checked_at", "accessible"), ("index_checked_at", "indexed")],
)
@pytest.mark.parametrize(
    "timestamp",
    [
        None,
        "2020-01-01T00:00:00+00:00",
        "2100-01-01T00:00:00+00:00",
        "2026-01-01T00:00:00",
    ],
)
def test_surface_freshness_is_independent_of_fresh_traffic(field, stage, timestamp):
    registry, _, observation = measured_fixture()
    add_observation(registry, observation)
    # Legacy/manually supplied records must also be held at the consuming boundary.
    registry["observations"][0][field] = timestamp
    result = review_registry(registry)["recommendations"][0]
    assert result["action"] == "defer" and result["diagnostic_stage"] == stage


@pytest.mark.parametrize("field", ["access_checked_at", "index_checked_at"])
@pytest.mark.parametrize(
    "timestamp", [None, "2100-01-01T00:00:00+00:00", "2026-01-01T00:00:00"]
)
def test_technical_observations_require_real_dates(field, timestamp):
    registry, _, observation = measured_fixture()
    observation[field] = timestamp
    with pytest.raises(ValueError, match="past observation time"):
        add_observation(registry, observation)


def test_export_adapter_preserves_but_does_not_promote_stale_surface_evidence():
    from publication_registry import observation_from_exports

    registry, _, observation = measured_fixture()
    gsc = {
        "schema_version": "article-forge.gsc.v1",
        "dimensions": ["page", "query"],
        "date_range": {
            "start": observation["observed_from"],
            "end": observation["observed_to"],
        },
        "rows": [
            {
                "page": observation["url"],
                "query": "service price",
                "impressions": 100,
                "clicks": 10,
            }
        ],
    }
    access = {
        "url": observation["url"],
        "observed_at": "2020-01-01T00:00:00+00:00",
        "accessible": True,
        "method": "synthetic probe",
    }
    indexing = {
        "schema_version": "article-forge.indexing.v1",
        "checked_at": access["observed_at"],
        "records": [{"url": observation["url"], "status": "indexed"}],
    }
    actions = {**observation, "qualified_actions": 2}
    row = observation_from_exports(
        registry,
        observation["publication_id"],
        gsc,
        access=access,
        indexing=indexing,
        actions=actions,
    )
    add_observation(registry, row)
    assert review_registry(registry)["recommendations"][0]["action"] == "defer"
    registry["observations"][0]["access_checked_at"] = datetime.now(
        timezone.utc
    ).isoformat()
    result = review_registry(registry)["recommendations"][0]
    assert result["action"] == "defer" and result["diagnostic_stage"] == "indexed"
    registry["observations"][0]["index_checked_at"] = datetime.now(
        timezone.utc
    ).isoformat()
    assert review_registry(registry)["recommendations"][0]["action"] == "keep"
    for field in ("observed_at", "checked_at"):
        bad_access = (
            {**access, "observed_at": None} if field == "observed_at" else access
        )
        bad_index = (
            {**indexing, "checked_at": None} if field == "checked_at" else indexing
        )
        with pytest.raises(ValueError):
            observation_from_exports(
                registry,
                observation["publication_id"],
                gsc,
                access=bad_access,
                indexing=bad_index,
            )


def test_content_versions_are_ordered_by_instant_across_timezones():
    registry, pub, observation = measured_fixture()
    pub["content_version"] = "older-offset-version"
    pub["published_at"] = "2026-07-01T12:00:00+14:00"
    observation["publication_id"] = add_publication(registry, pub)
    add_observation(registry, observation)
    newer = {
        **pub,
        "content_version": "newer-utc-version",
        "published_at": "2026-07-01T10:00:00+00:00",
    }
    new_id = add_publication(registry, newer)
    result = review_registry(registry)["recommendations"][0]
    assert result["publication_id"] == new_id and result["action"] == "defer"
    add_observation(
        registry, {**observation, "publication_id": new_id, "accessible": False}
    )
    assert review_registry(registry)["recommendations"][0]["action"] == "improve"


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_workflow_evaluation_rejects_nonfinite_measurements(value):
    document = {
        "schema_version": "article-forge.workflow-evaluation.v1",
        "fixed_queries": [
            {"site": "a", "query": "price"},
            {"site": "b", "query": "workflow"},
        ],
        "runs": [
            {
                "site": "a",
                "query": "price",
                "workflow": "current",
                "reviewer": "Reviewer",
                "evidence_sha256": "hash",
                "forge_commit": "commit",
                "provider": "stub",
                "model": "stub",
                "factual_accuracy": value,
            }
        ],
    }
    with pytest.raises(ValueError, match="invalid evaluation metric"):
        evaluate(document)
