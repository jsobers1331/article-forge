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
from generate_article import persist_checked_article  # noqa: E402
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
            "source": "serp_analysis",
            "difficulty_score": 40,
            "observed_at": today,
            "sample_size": 10,
        },
        "product_fit": {
            "rubric_version": "1.0",
            "score": 90,
            "rationale": "Directly matches verified category facts.",
            "evidence": ["canonical definition"],
        },
        "content_fit": {
            "rubric_version": "1.0",
            "score": 85,
            "rationale": "Can add a useful decision framework.",
            "evidence": ["decision checklist"],
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
