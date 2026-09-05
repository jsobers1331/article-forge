import json
import sys
from datetime import date
from types import SimpleNamespace

sys.path.insert(0, "scripts")

from generate_article import _topic_from_opportunity_plan  # noqa: E402
import plan_opportunities as planner_module  # noqa: E402
from plan_opportunities import build_plan  # noqa: E402


def config():
    return {
        "site_name": "Example Co",
        "domain": "example.com",
        "category_frame": "household bill tracker",
        "icp": "households sharing recurring bills",
        "existing_pages": ["/pricing", "/what-is-a-household-bill-tracker"],
        "topic_backlog": [
            {
                "title": "What is a household bill tracker?",
                "target_query": "what is a household bill tracker",
            }
        ],
    }


def serp_record(query, *, paa=None, related=None, titles=None):
    hosts = [f"site-{index}.example" for index in range(1, 6)]
    return {
        "schema_version": "article-forge.serp.v1",
        "source": "serper",
        "query": query,
        "normalized_query": query.lower(),
        "retrieved_at": f"{date.today().isoformat()}T00:00:00+00:00",
        "cache_key": "a" * 64,
        "organic": [
            {
                "position": index,
                "title": titles[index - 1] if titles else f"Result {index}",
                "host": host,
                "link": f"https://{host}/page",
            }
            for index, host in enumerate(hosts, start=1)
        ],
        "people_also_ask": [{"question": item} for item in paa or []],
        "related_searches": [{"query": item} for item in related or []],
        "serp_features": ["people_also_ask"] if paa else [],
        "intent_signals": [
            {
                "kind": "question_evidence",
                "intent_hint": "informational",
                "observed": True,
            }
        ],
        "competition_observations": {
            "organic_result_count": 5,
            "unique_hosts": 5,
        },
    }


def test_plan_expands_serp_questions_and_marks_unmeasured_evidence():
    records = [
        serp_record(
            "household bill tracker",
            paa=["how do families split recurring bills"],
            related=["household bill tracker for roommates"],
        ),
        serp_record("how do families split recurring bills"),
    ]
    plan = build_plan(
        config(),
        serp_records=records,
        seeds=["household bill tracker"],
    )

    candidate = next(
        item
        for item in plan["candidates"]
        if item["query"] == "how do families split recurring bills"
    )
    assert candidate["serp_evidence"]["evidence_scope"] == "direct_query"
    assert candidate["discovery_priority"]["semantics"] == "discovery_triage_only"
    assert candidate["demand_evidence"] is None
    assert (
        "normalized market-demand or site-opportunity evidence"
        in candidate["missing_evidence"]
    )
    assert "traffic" in plan["semantics"]["serper"]


def test_plan_uses_organic_title_language_when_serp_has_no_paa_or_related():
    plan = build_plan(
        config(),
        serp_records=[
            serp_record(
                "family photographer barbados",
                titles=[
                    "Family photo shoot suggestions in Barbados",
                    "Josee Cole Photographer",
                    "Barbados Family Photographer",
                    "Family portraits for visiting families in Barbados",
                    "Ricky Chase Photography",
                ],
            )
        ],
        seeds=["family photographer barbados"],
    )
    candidate = next(
        item
        for item in plan["candidates"]
        if item["query"] == "Family photo shoot suggestions in Barbados"
    )
    assert any(
        reason.startswith("serp_title_language_from:")
        for reason in candidate["source_reasons"]
    )
    assert all(
        item["query"] != "Josee Cole Photographer" for item in plan["candidates"]
    )
    assert all(
        item["query"] != "Our Wedding | Showit Blog" for item in plan["candidates"]
    )


def test_plan_keeps_measured_demand_separate_from_paid_competition():
    demand = {
        "query": "roommates split recurring expenses",
        "demand": {
            "source": "keyword_planner",
            "role": "market_demand",
            "normalization": "max-value-within-imported-candidate-set",
            "value": 120,
            "unit": "searches",
            "score": 100,
            "observed_at": date.today().isoformat(),
            "sample_size": 12,
        },
        "raw": {
            "avg_monthly_searches": 120,
            "paid_competition": "LOW",
        },
    }
    plan = build_plan(
        config(),
        demand_records=[demand],
        seeds=["roommates split recurring expenses"],
    )
    candidate = plan["candidates"][0]
    assert candidate["query"] == "roommates split recurring expenses"
    assert candidate["demand_evidence"]["role"] == "market_demand"
    assert candidate["demand_evidence"]["unit"] == "searches"
    assert candidate["raw_demand_evidence"]["paid_competition"] == "LOW"
    assert (
        "manual editorial-difficulty/page-depth assessment"
        in candidate["missing_evidence"]
    )


def test_plan_skips_existing_coverage_without_mutating_config():
    plan = build_plan(
        config(),
        seeds=["what is a household bill tracker"],
    )
    assert plan["candidates"] == []
    assert plan["skipped"] == [
        {
            "query": "what is a household bill tracker",
            "reason": "existing_pages_or_topic_backlog_overlap",
        }
    ]


def test_generation_can_consume_plan_candidate_without_backlog_edit(tmp_path):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema_version": "article-forge.opportunity-plan.v1",
                "candidates": [
                    {
                        "candidate_id": "roommates-12345678",
                        "review_status": "ready_for_editorial_review",
                        "missing_evidence": ["market demand"],
                        "topic": {
                            "title": "Household bill tracker for roommates",
                            "type": "standard",
                            "target_query": "household bill tracker for roommates",
                            "opportunity": {"evidence_status": "discovery_only"},
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    topic = _topic_from_opportunity_plan(str(plan_path), "roommates-12345678")
    assert topic["target_query"] == "household bill tracker for roommates"
    assert topic["opportunity"]["plan_path"] == str(plan_path)
    assert topic["opportunity"]["missing_evidence"] == ["market demand"]


def test_live_planner_is_bounded_and_uses_a_second_pass(monkeypatch, tmp_path):
    calls = []

    def fake_collect(queries, api_key, **kwargs):
        del api_key, kwargs
        calls.append(list(queries))
        if len(calls) == 1:
            return {
                "records": [
                    serp_record(
                        "family photographer barbados",
                        titles=[
                            "Family photo shoot suggestions in Barbados",
                            "Result two",
                            "Result three",
                            "Result four",
                            "Result five",
                        ],
                    )
                ],
                "errors": [],
                "request_budget": {"api_requests": 1, "cache_hits": 0},
            }
        return {
            "records": [serp_record(queries[0])],
            "errors": [],
            "request_budget": {"api_requests": 1, "cache_hits": 0},
        }

    monkeypatch.setenv("SERPER_API_KEY", "test-only")
    monkeypatch.setattr(planner_module, "collect_queries", fake_collect)
    args = SimpleNamespace(
        env_file=str(tmp_path / "not-present.env"),
        api_key_env=None,
        gl=None,
        hl=None,
        location=None,
        num=None,
        max_requests=2,
        cache_dir=str(tmp_path / "cache"),
        cache_ttl_seconds=None,
        refresh=False,
        max_retries=None,
        timeout=None,
        delay=None,
        seed_limit=1,
        candidate_limit=1,
    )
    collection = planner_module._collect_live(
        {"research": {"serper": {}}},
        ["family photographer barbados"],
        args,
    )

    assert calls == [
        ["family photographer barbados"],
        ["Family photo shoot suggestions in Barbados"],
    ]
    assert [record["planner_stage"] for record in collection["records"]] == [
        "initial",
        "follow_up",
    ]
    assert collection["request_budget"]["max_requests_per_run"] == 2
