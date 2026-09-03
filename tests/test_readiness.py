import json
import sys
from datetime import date, timedelta

sys.path.insert(0, "scripts")

from check_article import (  # noqa: E402
    check_claim_evidence,
    check_coming_soon_mentions,
    check_config_integrity,
    check_tier_gated_mentions,
)
from call_llm import PROVIDERS  # noqa: E402
from collect_serper import (  # noqa: E402
    SerperError,
    collect_queries,
    normalize_response,
)
from generate_article import persist_checked_article  # noqa: E402
from import_demand import build_demand_document  # noqa: E402
from score_article import (  # noqa: E402
    CONSENSUS_MIN_PAGES,
    _phrase_covered,
    consensus_items,
    score_eeat,
    score_linking,
)
from score_opportunities import score_candidate  # noqa: E402


def valid_config():
    return {
        "site_name": "Example Co",
        "domain": "example.com",
        "category_frame": "household bill tracker",
        "icp": "households sharing recurring bills",
        "canonical_definition_sentence": "Example Co is a household bill tracker.",
        "verified_facts": {
            "real_differentiators": [
                {
                    "feature": "AI rebook predictions and revenue forecasting",
                    "tier": "Studio",
                },
            ],
            "coming_soon_features": ["multi-brand support"],
            "pricing_and_billing": {"note": "Monthly billing."},
        },
        "existing_pages": ["/pricing"],
        "claim_evidence": [
            {
                "claim_id": "crm",
                "claim": "The CRM exists.",
                "source_url": "https://example.com/features",
                "verified_on": date.today().isoformat(),
                "status": "verified",
            }
        ],
    }


def competitor(domain, subtopics=None, entities=None, position=1):
    return {
        "domain": domain,
        "url": f"https://{domain}/page",
        "position": position,
        "subtopics": subtopics or ["client portal"],
        "entities": entities or ["CRM"],
    }


def complete_candidate(**overrides):
    today = date.today().isoformat()
    candidate = {
        "candidate_id": "crm-definition",
        "query": "what is a photography CRM",
        "intent": "informational",
        "page_type": "pillar",
        "demand": {
            "source": "keyword_planner",
            "role": "market_demand",
            "normalization": "relative-to-candidate-set",
            "value": 1000,
            "unit": "searches",
            "score": 70,
            "observed_at": today,
            "sample_size": 12,
        },
        "paid_competition": {
            "source": "keyword_planner",
            "value": "low",
            "observed_at": today,
        },
        "organic_competition": {
            "source": "serper",
            "observed_at": today,
            "sample_size": 10,
            "serp_cache_key": "a" * 64,
            "serp_retrieved_at": today,
            "observations": {"organic_result_count": 10, "unique_hosts": 9},
            "editorial_difficulty": {
                "semantics": "editorial_estimate",
                "score": 40,
                "rationale": "A manual review found a useful, defeatable gap.",
                "evidence_types": ["manual_page_review", "content_depth_assessment"],
                "evidence": ["serp-record", "manual-page-review"],
            },
        },
        "intent_evidence": {
            "source": "serper",
            "signals": ["people_also_ask", "query modifier: what"],
            "observed_at": today,
        },
        "product_fit": {
            "rubric_version": "1.0",
            "score_semantics": "editorial",
            "score": 90,
            "rationale": "Directly matches verified category facts.",
            "evidence_types": ["first_party_fact", "verified_claim"],
            "evidence": ["canonical definition"],
        },
        "content_fit": {
            "rubric_version": "1.0",
            "score_semantics": "editorial",
            "score": 85,
            "rationale": "Can add a useful decision framework.",
            "original_angle": "A decision framework based on the reader's workflow.",
            "limitation": "No ranking guarantee can be made from a SERP snapshot.",
            "unanswered_question": "Which workflow criteria matter before choosing a CRM?",
            "source_dates": [today],
            "evidence_types": ["original_angle", "limitation", "unanswered_question"],
            "evidence": ["decision checklist"],
        },
        "freshness": {
            "source": "research-review",
            "status": "current",
            "observed_at": today,
            "refresh_after_days": 90,
            "evidence": ["current-source-review"],
        },
        "evidence_confidence": {
            "score": 85,
            "rationale": "Current demand and SERP evidence are traceable.",
            "evidence": ["demand-record", "serp-record", "fit-review"],
        },
    }
    candidate.update(overrides)
    return candidate


def test_consensus_requires_independent_sample_and_sixty_percent():
    item, counts = consensus_items(
        [competitor("a.example.com"), competitor("b.example.com")], "subtopics"
    )
    assert item == set()
    assert counts["client portal"] == 2

    competitors = [competitor(f"{letter}.example.com") for letter in "abcde"]
    competitors[-1]["subtopics"] = ["different topic"]
    item, _ = consensus_items(competitors, "subtopics")
    assert CONSENSUS_MIN_PAGES == 5
    assert "client portal" in item
    assert "different topic" not in item


def test_consensus_dedupes_same_domain():
    competitors = [
        competitor("same.example.com", position=1),
        competitor("same.example.com", position=2),
    ]
    competitors.extend(competitor(f"{letter}.example.com") for letter in "abcd")
    item, counts = consensus_items(competitors, "subtopics")
    assert "client portal" in item
    assert counts["client portal"] == 5


def test_phrase_matching_does_not_match_substrings():
    assert not _phrase_covered("CRM", "crms are useful")
    assert _phrase_covered("CRM", "a CRM helps")


def test_tier_gate_rejects_universal_scope_and_missing_nearby_tier():
    facts = valid_config()["verified_facts"]["real_differentiators"]
    status, _ = check_tier_gated_mentions(
        "We provide AI rebook predictions and revenue forecasting on every plan.", facts
    )
    assert status == "FAIL"
    status, _ = check_tier_gated_mentions(
        "AI rebook predictions and revenue forecasting are available.", facts
    )
    assert status == "FAIL"
    status, _ = check_tier_gated_mentions(
        "Studio includes AI rebook predictions and revenue forecasting.", facts
    )
    assert status == "PASS"


def test_coming_soon_feature_is_blocked():
    status, detail = check_coming_soon_mentions(
        "Multi-brand support lets agencies switch brands.", ["multi-brand support"]
    )
    assert status == "FAIL"
    assert "multi-brand" in detail


def test_config_requires_evidence_registry_for_generation():
    config = valid_config()
    assert check_config_integrity(config)[0] == "PASS"
    assert check_claim_evidence({**config, "claim_evidence": None})[0] == "WARN"
    assert check_claim_evidence({**config, "claim_evidence": []})[0] == "WARN"
    assert check_claim_evidence(config)[0] == "PASS"
    external = {
        **config,
        "claim_evidence": [
            {
                **config["claim_evidence"][0],
                "source_url": "https://other.example/source",
            }
        ],
    }
    assert check_claim_evidence(external)[0] == "FAIL"


def test_eeat_does_not_award_generic_brand_language():
    assert score_eeat("Updated. This is our overview.", False, False) < 100
    assert (
        score_eeat(
            "Updated. We tested this on 2026-09-03.",
            False,
            False,
            has_first_hand_evidence=True,
        )
        > 20
    )


def test_linking_does_not_require_fixed_counts_or_accept_spoofed_host():
    score, notes = score_linking("A short draft with no links.", "shootmuse.com")
    assert score == 100
    assert notes == []
    score, _ = score_linking(
        "[spoof](https://shootmuse.com.evil.example/claim)", "shootmuse.com"
    )
    assert score < 100


def test_quarantine_receipt_blocks_non_pass_draft(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(valid_config()), encoding="utf-8")
    passed, path, payload = persist_checked_article(
        "# Draft",
        tmp_path / "out",
        "draft",
        [("Rule", ("WARN", "needs review"))],
        "prompt",
        config_path,
    )
    assert not passed
    assert path.parent.name == ".quarantine"
    assert path.exists()
    assert not (tmp_path / "out" / "draft.md").exists()
    receipt = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert receipt["normal_output_blocked"] is True
    assert receipt["quarantined_at"]
    assert payload[0]["status"] == "WARN"


def test_all_pass_article_is_saved_and_existing_draft_is_protected(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(valid_config()), encoding="utf-8")
    checks = [("Rule", ("PASS", "ok"))]
    passed, path, _ = persist_checked_article(
        "# Draft", tmp_path / "out", "draft", checks, "prompt", config_path
    )
    assert passed
    assert path.read_text(encoding="utf-8") == "# Draft"
    try:
        persist_checked_article(
            "# Changed", tmp_path / "out", "draft", checks, "prompt", config_path
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing draft should require --force")


def test_opportunity_score_requires_measured_data_and_separates_paid_competition():
    result = score_candidate(complete_candidate())
    assert result["status"] == "scored"
    assert result["opportunity_score"] == 75.5
    assert result["competition_opportunity_score"] == 60.0

    missing = complete_candidate()
    del missing["demand"]["score"]
    result = score_candidate(missing)
    assert result["status"] == "needs-data"
    assert result["opportunity_score"] is None

    search_console = complete_candidate()
    search_console["demand"].update({"source": "search_console", "unit": "searches"})
    result = score_candidate(search_console)
    assert result["status"] == "needs-data"
    assert any("site signals" in item for item in result["missing_evidence"])


def test_opportunity_score_expires_stale_evidence():
    old = (date.today() - timedelta(days=91)).isoformat()
    candidate = complete_candidate()
    candidate["demand"]["observed_at"] = old
    result = score_candidate(candidate)
    assert result["status"] == "stale"
    assert result["decision"] == "refresh-data"


def test_deepseek_provider_uses_current_model_default():
    assert PROVIDERS["deepseek"]["default_model"] == "deepseek-v4-pro"


def test_serper_normalization_preserves_observations_without_fake_difficulty():
    payload = {
        "organic": [
            {
                "position": 1,
                "title": "What is a CRM?",
                "link": "https://one.example/guide",
                "snippet": "A direct definition.",
            },
            {
                "position": 2,
                "title": "CRM comparison",
                "link": "https://www.two.example/compare",
                "snippet": "Compare options.",
            },
            {
                "position": 3,
                "title": "CRM pricing",
                "link": "https://three.example/pricing",
                "snippet": "Pricing details.",
            },
            {"position": 4, "link": "https://four.example/page"},
            {"position": 5, "link": "https://five.example/page"},
        ],
        "peopleAlsoAsk": [{"question": "How does a CRM work?"}],
        "relatedSearches": [{"query": "best CRM"}],
        "answerBox": {"answer": "A definition."},
        "shopping": [{"title": "CRM"}],
        "searchInformation": {"totalResults": "About 1,000 results"},
    }
    record = normalize_response(
        "what is a CRM",
        payload,
        gl="us",
        hl="en",
        num=10,
        location=None,
        cache_key="key",
    )
    assert record["competition_observations"]["unique_hosts"] == 5
    assert "people_also_ask" in record["serp_features"]
    assert "shopping" in record["serp_features"]
    assert record["related_searches"] == [{"query": "best CRM"}]
    assert not any("difficulty" in key for key in record)
    assert any(
        signal["kind"] == "question_evidence" for signal in record["intent_signals"]
    )


def test_serper_cache_prevents_repeat_request_and_keeps_raw_response(tmp_path):
    calls = []

    def fake_request(query, api_key, **kwargs):
        calls.append((query, api_key, kwargs["gl"], kwargs["hl"]))
        return {
            "organic": [
                {"position": index, "link": f"https://{index}.example/page"}
                for index in range(1, 6)
            ]
        }

    first = collect_queries(
        ["  What is CRM  "],
        "secret-value",
        gl="us",
        hl="en",
        num=10,
        location=None,
        cache_dir=tmp_path / "cache",
        request_fn=fake_request,
    )
    second = collect_queries(
        ["what is crm"],
        "secret-value",
        gl="us",
        hl="en",
        num=10,
        location=None,
        cache_dir=tmp_path / "cache",
        request_fn=fake_request,
    )
    assert len(calls) == 1
    assert first["request_budget"]["api_requests"] == 1
    assert second["request_budget"]["cache_hits"] == 1
    cache_text = next((tmp_path / "cache").glob("*.json")).read_text()
    assert "secret-value" not in cache_text


def test_serper_circuit_breaker_stops_three_consecutive_failures(tmp_path):
    def fail_request(*args, **kwargs):
        raise SerperError("temporary failure")

    try:
        collect_queries(
            ["one", "two", "three", "four"],
            "secret-value",
            gl="us",
            hl="en",
            num=10,
            location=None,
            cache_dir=tmp_path / "cache",
            request_fn=fail_request,
        )
    except SerperError as exc:
        assert "circuit breaker" in str(exc)
    else:
        raise AssertionError("three consecutive failures must open the circuit")


def test_demand_import_preserves_market_and_site_semantics():
    planner = build_demand_document(
        [
            {"keyword": "crm", "avg_monthly_searches": "1,000", "competition": "LOW"},
            {
                "keyword": "crm for photographers",
                "avg_monthly_searches": "500",
                "competition": "MEDIUM",
            },
        ],
        source="keyword_planner",
        observed_at=date.today().isoformat(),
        sample_size=12,
        metric="impressions",
    )
    assert planner["records"][0]["demand"]["role"] == "market_demand"
    assert planner["records"][0]["demand"]["unit"] == "searches"
    assert planner["records"][0]["raw"]["paid_competition"] == "LOW"

    console = build_demand_document(
        [{"query": "crm", "clicks": "12", "impressions": "100"}],
        source="search_console",
        observed_at=date.today().isoformat(),
        sample_size=28,
        metric="impressions",
    )
    assert console["records"][0]["demand"]["role"] == "site_opportunity"
    assert console["records"][0]["demand"]["unit"] == "impressions"


def test_opportunity_score_requires_evidence_and_downgrades_low_confidence():
    candidate = complete_candidate()
    candidate["evidence_confidence"]["score"] = 79
    result = score_candidate(candidate)
    assert result["status"] == "scored"
    assert result["decision"] == "investigate"
    assert result["evidence_confidence"]["gate"] == "below-80"

    missing_intent = complete_candidate()
    del missing_intent["intent_evidence"]
    result = score_candidate(missing_intent)
    assert result["status"] == "needs-data"
    assert any("intent_evidence" in item for item in result["missing_evidence"])


def test_intent_confidence_over_90_requires_multiple_signals():
    candidate = complete_candidate()
    candidate["intent_evidence"].update(
        {
            "intent_hypothesis": "informational",
            "intent_confidence": 95,
            "intent_rationale": "One signal only.",
            "signals": ["PAA"],
        }
    )
    result = score_candidate(candidate)
    assert result["status"] == "needs-data"
    assert any("three corroborating" in item for item in result["missing_evidence"])


def test_serper_difficulty_is_optional_raw_evidence_but_not_scoreable_without_editorial_review():
    candidate = complete_candidate()
    del candidate["organic_competition"]["editorial_difficulty"]
    result = score_candidate(candidate)
    assert result["status"] == "needs-data"
    assert result["opportunity_score"] is None


def test_serper_counts_alone_cannot_be_editorial_difficulty():
    candidate = complete_candidate()
    candidate["organic_competition"]["editorial_difficulty"].update(
        {
            "evidence_types": [],
            "evidence": ["Serper", "result count", "unique hosts"],
        }
    )
    result = score_candidate(candidate)
    assert result["status"] == "needs-data"
    assert any("sole basis" in item for item in result["missing_evidence"])
