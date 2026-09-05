import json
import sys
from datetime import date, timedelta

from PIL import Image

sys.path.insert(0, "scripts")

from check_article import (  # noqa: E402
    check_claim_evidence,
    check_coming_soon_mentions,
    check_config_integrity,
    check_internal_planning_artifacts,
    check_process_structure,
    check_tier_gated_mentions,
    check_visible_dateline,
)
from check_image import check_image_asset  # noqa: E402
import call_llm as call_llm_module  # noqa: E402
from call_llm import PROVIDERS  # noqa: E402
import collect_keyword_planner as keyword_planner_module  # noqa: E402
from collect_serper import (  # noqa: E402
    SerperError,
    collect_queries,
    normalize_response,
)
from collect_search_console import (  # noqa: E402
    _atomic_write_json,
    _check_output_paths,
    _query_demand_rows,
    normalize_rows as normalize_gsc_rows,
    parse_dimensions,
    query_search_analytics,
    validate_window,
)
from collect_keyword_planner import build_request, normalize_results  # noqa: E402
from generate_article import persist_checked_article  # noqa: E402
import generate_article as generate_article_module  # noqa: E402
from generate_prompt import render as render_article_prompt  # noqa: E402
from import_demand import build_demand_document  # noqa: E402
from score_article import (  # noqa: E402
    CONSENSUS_MIN_PAGES,
    _phrase_covered,
    build_article_report,
    consensus_items,
    score_eeat,
    score_linking,
    score_for_report,
    score_structure_extractability,
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


def test_internal_opening_plan_is_blocked_from_visible_draft():
    text = """**Per-H2 opening-function plan:**

- **H2: What is a CRM?** — *Answer.* Direct definition.

# What is a CRM?
"""
    status, detail = check_internal_planning_artifacts(text)
    assert status == "FAIL"
    assert "planning artifact" in detail


def test_process_intent_requires_numbered_steps():
    assert (
        check_process_structure(
            "# How to book a photographer\n\nA table.", "how to book a photographer"
        )[0]
        == "FAIL"
    )
    assert (
        check_process_structure(
            "# How to book a photographer\n\n1. Check availability.",
            "how to book a photographer",
        )[0]
        == "PASS"
    )
    assert (
        check_process_structure("# Pricing guide\n\nA table.", "photographer pricing")[
            0
        ]
        == "PASS"
    )


def test_visible_dateline_is_required_after_h1():
    assert (
        check_visible_dateline("# A guide\n\n*Last updated: September 2026.*\n")[0]
        == "PASS"
    )
    assert check_visible_dateline("# A guide\n\nIntroductory paragraph.\n")[0] == "FAIL"


def test_image_gate_checks_dimensions_format_alt_and_duplicate_reuse(tmp_path):
    image_path = tmp_path / "barbados-wedding-hero.webp"
    Image.new("RGB", (1536, 1024), (180, 140, 95)).save(image_path, "WEBP", quality=85)

    status, detail, receipt = check_image_asset(
        image_path,
        "Warm editorial still life with camera lenses and a blank wedding album",
    )
    assert status == "PASS"
    assert receipt["format"] == "WEBP"
    assert receipt["width"] == 1536
    assert "passed image" in detail

    duplicate_path = tmp_path / "previous-article.webp"
    duplicate_path.write_bytes(image_path.read_bytes())
    status, detail, receipt = check_image_asset(
        image_path,
        "Warm editorial still life with camera lenses and a blank wedding album",
        [duplicate_path],
    )
    assert status == "FAIL"
    assert "duplicate" in detail
    assert receipt["duplicate"]["path"] == str(duplicate_path)


def test_rendered_prompt_carries_the_ai_image_contract():
    config = valid_config()
    config["current_month_year"] = "September 2026"
    prompt = render_article_prompt(
        config,
        {
            "title": "How to choose a photographer",
            "target_query": "how to choose a photographer",
        },
    )
    assert '"mode": "ai_generated_for_editorial_context"' in prompt
    assert '"avoid_duplicate_assets": true' in prompt
    assert "scripts/check_image.py" in prompt


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


def test_report_always_scores_without_mislabeling_missing_serp_evidence():
    article = """# How to choose a photography CRM

*Last updated: September 4, 2026.*

Choosing a photography CRM means comparing the workflow, evidence, and support a studio actually needs. Start with the client record, then check whether inquiries, sessions, invoices, and follow-up live in one reliable place. A useful decision should fit the studio's current process rather than promising a generic solution.

## Which workflow should the CRM support?

The best choice follows the work from first inquiry to delivery. Review the handoffs before choosing a tool.

1. List the client details you must keep current.
2. Map the inquiry, booking, and follow-up steps.
3. Test the workflow with a real example.

## What should you compare before choosing?

Compare the features that change daily work, not a long checklist of vague benefits.

| Area | Question |
| --- | --- |
| Workflow | Does it fit the studio's process? |
| Evidence | Can you verify the claim? |

We tested this workflow on 2026-09-03. Read the [pricing page](https://example.com/pricing) before deciding.
"""
    result = score_for_report(
        article,
        None,
        "pillar",
        valid_config()["verified_facts"],
        domain="example.com",
        checks=[("gate", ("PASS", "ok"))],
    )
    assert result["score_kind"] == "readiness"
    assert result["evidence_status"] == "serp_snapshot_missing"
    assert 0 <= result["total_score"] <= 100
    assert result["unassessed_pillars"] == [
        "intent_match",
        "topical_comprehensiveness",
        "entity_coverage",
    ]
    assert any(
        item["category"] == "research_evidence" for item in result["improvements"]
    )


def test_structure_score_ignores_required_title_and_dateline_wrapper():
    article = """# A useful article title

*Last updated: September 4, 2026.*

This is the direct answer capsule with enough words to be extractable by a reader or a search system before the article explains the decision in detail and gives the reader a practical basis for choosing between a paper system, spreadsheet, and app.

## What should the reader compare?

Use the table and the numbered process below.

## Which option fits?

Choose the smallest useful workflow.

## When should you review it?

Review it when the household changes.

## What should you avoid?

Avoid features that add maintenance without helping the workflow.

1. Compare the current options.
2. Choose the smallest useful workflow.

| Option | Fit |
| --- | --- |
| A | Good |
"""
    assert score_structure_extractability(article) == 100.0


def test_insufficient_serp_report_uses_actual_domain_count():
    snapshot = {
        "competitors": [competitor(f"{letter}.example.org") for letter in "abcd"]
    }
    result = score_for_report(
        "# Draft\n\n*Last updated: September 2026.*",
        snapshot,
        "standard",
        None,
    )
    evidence = next(
        item["evidence"]
        for item in result["improvements"]
        if item["category"] == "research_evidence"
    )
    assert "supplied: 4" in evidence
    assert result["evidence_status"] == "serp_snapshot_insufficient"


def test_serp_report_turns_consensus_gaps_into_fix_actions():
    snapshot = {
        "serp_intent": "informational",
        "competitors": [
            competitor(
                f"{letter}.example.org",
                subtopics=["budget planning", "privacy settings"],
                entities=["YNAB", "Monarch"],
            )
            for letter in "abcde"
        ],
    }
    article = """# How to choose a photography CRM

*Last updated: September 4, 2026.*

This guide covers budget planning for choosing a photography CRM and explains the workflow a studio should review before committing.

## What should you compare?

Start with budget planning and test the workflow against a real example.
"""
    result = score_for_report(
        article,
        snapshot,
        "pillar",
        valid_config()["verified_facts"],
        domain="example.com",
    )
    assert result["score_kind"] == "serp_parity"
    assert result["evidence_status"] == "serp_consensus_ready"
    assert result["competitor_count"] == 5
    assert "privacy settings" in result["topical_gaps"]
    assert "monarch" in result["entity_gaps"]
    assert any(item["category"] == "topical_gap" for item in result["improvements"])
    assert any(item["category"] == "entity_gap" for item in result["improvements"])


def test_generated_article_report_is_persisted_for_pass_and_quarantine(tmp_path):
    config_path = tmp_path / "config.json"
    config = valid_config()
    config_path.write_text(json.dumps(config), encoding="utf-8")
    topic = {"target_query": "how to choose a photography CRM", "type": "pillar"}
    report = build_article_report(
        "# How to choose a photography CRM\n\n*Last updated: September 2026.*\n",
        config,
        topic,
        [("Rule", ("PASS", "ok"))],
    )

    passed, passing_path, _ = persist_checked_article(
        "# Draft",
        tmp_path / "passing",
        "draft",
        [("Rule", ("PASS", "ok"))],
        "prompt",
        config_path,
        report=report,
    )
    assert passed
    passing_report = json.loads(
        passing_path.with_suffix(".report.json").read_text(encoding="utf-8")
    )
    assert passing_report["score"]["total_score"] >= 0
    assert "improvements" not in passing_report["score"]
    assert "Score meaning:" in passing_path.with_suffix(".report.md").read_text(
        encoding="utf-8"
    )
    assert passing_path.with_suffix(".report.md").exists()

    blocked_report = build_article_report(
        "# Draft", config, topic, [("Rule", ("FAIL", "placeholder found"))]
    )
    passed, blocked_path, _ = persist_checked_article(
        "# Draft",
        tmp_path / "blocked",
        "draft",
        [("Rule", ("FAIL", "placeholder found"))],
        "prompt",
        config_path,
        report=blocked_report,
    )
    assert not passed
    blocked_payload = json.loads(
        blocked_path.with_suffix(".report.json").read_text(encoding="utf-8")
    )
    assert blocked_payload["publication_status"] == "blocked"
    assert blocked_payload["what_to_fix_next"][0]["priority"] == "P0"
    assert not any(
        item["category"] == "research_evidence"
        for item in blocked_payload["what_to_fix_next"]
    )
    assert blocked_path.with_suffix(".report.md").exists()


def test_generate_article_cli_emits_report_on_quarantine_path(
    tmp_path, monkeypatch, capsys
):
    config = valid_config()
    config["current_month_year"] = date.today().strftime("%B %Y")
    config["topic_backlog"] = [
        {
            "title": "How to choose a photography CRM",
            "target_query": "how to choose a photography CRM",
            "type": "pillar",
        }
    ]
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    out_dir = tmp_path / "generated"
    monkeypatch.setattr(
        generate_article_module, "call_llm", lambda *args, **kwargs: "# Draft"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_article.py",
            "--config",
            str(config_path),
            "--topic-index",
            "0",
            "--provider",
            "deepseek",
            "--out-dir",
            str(out_dir),
        ],
    )

    try:
        generate_article_module.main()
    except SystemExit as error:
        assert error.code == 1
    captured = capsys.readouterr()
    assert "Article score:" in captured.err
    reports = list((out_dir / ".quarantine").glob("*.report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["publication_status"] == "blocked"
    assert report["score"]["score_kind"] == "readiness"


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


def test_deepseek_generation_disables_thinking_for_visible_content(monkeypatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": "# Draft"}}]}
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        requests.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(call_llm_module.urllib.request, "urlopen", fake_urlopen)

    content = call_llm_module.call_llm(
        "Write a draft.", provider="deepseek", max_tokens=20, timeout=1
    )

    assert content == "# Draft"
    assert requests[0]["thinking"] == {"type": "disabled"}


def test_openai_compatible_empty_content_is_rejected(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": ""}}]}).encode(
                "utf-8"
            )

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(
        call_llm_module.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(),
    )

    try:
        call_llm_module.call_llm("Write a draft.", provider="deepseek")
    except RuntimeError as exc:
        assert str(exc) == "LLM returned no visible content"
    else:
        raise AssertionError("empty provider content should be rejected")


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


def test_search_console_request_is_final_web_data():
    requests = []

    class Query:
        def execute(self):
            return {"rows": []}

    class Analytics:
        def query(self, **kwargs):
            requests.append(kwargs)
            return Query()

    class Service:
        def searchanalytics(self):
            return Analytics()

    assert (
        query_search_analytics(
            Service(),
            "sc-domain:example.com",
            "2026-01-01",
            "2026-01-30",
            ["query"],
            100,
        )
        == []
    )
    body = requests[0]["body"]
    assert body["type"] == "web"
    assert body["dataState"] == "final"
    assert body["dimensions"] == ["query"]


def test_search_console_validation_and_query_aggregation():
    assert parse_dimensions("query,page") == ["query", "page"]
    validate_window(1, 25_000)
    try:
        parse_dimensions("query,unknown")
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("unknown Search Console dimensions must be rejected")

    rows = normalize_gsc_rows(
        [
            {"keys": ["crm", "/one"], "clicks": 2, "impressions": 10, "position": 4},
            {"keys": ["crm", "/two"], "clicks": 1, "impressions": 5, "position": 8},
        ],
        ["query", "page"],
    )
    aggregated = _query_demand_rows(rows, ["query", "page"])
    assert aggregated == [
        {
            "query": "crm",
            "clicks": 3.0,
            "impressions": 15.0,
            "ctr": 0.2,
            "position": 5.333333333333333,
        }
    ]


def test_keyword_planner_normalization_preserves_paid_semantics():
    class EnumValue:
        name = "LOW"

    class Metrics:
        avg_monthly_searches = 1234
        competition = EnumValue()
        competition_index = 17
        low_top_of_page_bid_micros = 100000

    class Idea:
        text = "crm for photographers"
        keyword_idea_metrics = Metrics()

    rows = normalize_results([Idea()])
    assert rows == [
        {
            "keyword": "crm for photographers",
            "avg_monthly_searches": 1234,
            "competition": "LOW",
            "competition_index": 17,
            "low_top_of_page_bid_micros": 100000,
        }
    ]


def test_keyword_planner_request_uses_explicit_seed_and_geo():
    from types import SimpleNamespace

    class FakeClient:
        enums = SimpleNamespace(
            KeywordPlanNetworkEnum=SimpleNamespace(GOOGLE_SEARCH="search")
        )

        def get_type(self, name):
            assert name == "GenerateKeywordIdeasRequest"
            return SimpleNamespace(
                keyword_seed=SimpleNamespace(keywords=[]),
                keyword_and_url_seed=SimpleNamespace(keywords=[], url=""),
                url_seed=SimpleNamespace(url=""),
                geo_target_constants=[],
            )

    request = build_request(
        FakeClient(),
        "123-456-7890",
        "2840",
        "1000",
        "GOOGLE_SEARCH",
        ["household bill tracker"],
        None,
    )
    assert request.customer_id == "1234567890"
    assert request.language == "languageConstants/1000"
    assert request.geo_target_constants == ["geoTargetConstants/2840"]
    assert request.keyword_seed.keywords == ["household bill tracker"]
    assert request.keyword_plan_network == "search"


def test_evidence_writes_are_atomic_and_do_not_overwrite_by_default(tmp_path):
    output = tmp_path / "evidence.json"
    _atomic_write_json(output, {"schema_version": "test.v1"})
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == "test.v1"
    try:
        _check_output_paths([output])
    except SystemExit as exc:
        assert "--force" in str(exc)
    else:
        raise AssertionError("existing evidence must require explicit overwrite")
    _atomic_write_json(output, {"schema_version": "test.v2"}, force=True)
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == "test.v2"
    assert not list(tmp_path.glob("*.tmp"))


def test_keyword_planner_missing_credentials_fails_before_artifact_creation(
    monkeypatch,
):
    for name in keyword_planner_module.REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    try:
        keyword_planner_module._required_environment()
    except RuntimeError as exc:
        assert "GOOGLE_ADS_DEVELOPER_TOKEN" in str(exc)
    else:
        raise AssertionError("Keyword Planner must fail closed without credentials")


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
