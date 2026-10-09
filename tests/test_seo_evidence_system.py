"""October 8 bypass regressions, all fixtures isolated and providers stubbed."""

import json
from datetime import datetime, timezone

import pytest
import check_article
import generate_article
import score_article
from test_check_article_ledger import make_config, entry, write_ledger, now_iso


from datetime import timedelta
from pathlib import Path

from evidence_contract import claim_fingerprint, object_hash, text_hash
from evidence_fixtures import bind_result, valid_snapshot, current_time
from claim_manifest import check_manifest, propose_manifest
from editorial_brief import check_brief, suggest_page_decision
from serp_contract import validate_snapshot
import verify_facts


def test_claim_id_does_not_bind_changed_price(tmp_path):
    config, path = make_config(tmp_path, ["price"])
    write_ledger(tmp_path, [entry("price", "verified", now_iso())])
    config["claim_evidence"][0]["claim"] = "The service costs $999999."
    assert check_article.check_claim_ledger(config, path)[0] != "PASS"


def test_unknown_intent_and_empty_evidence_are_unassessed():
    assert score_article.score_intent_match("standard", "unknown") is None
    assert score_article.score_linking("No links.", "test.org")[0] is None
    pages = [
        {"url": f"https://domain{i}.org/", "subtopics": [], "entities": []}
        for i in range(5)
    ]
    assert score_article.score_topical_comprehensiveness("Text", pages)[0] is None
    assert score_article.score_entity_coverage("Text", pages)[0] is None


def test_old_wrong_query_serp_is_rejected():
    snapshot = {
        "keyword": "wrong query",
        "captured_at": "2020-01-01",
        "competitors": [
            {"url": f"https://domain{i}.org/", "subtopics": [], "entities": []}
            for i in range(5)
        ],
    }
    report = score_article.build_article_report(
        "Text", {}, {"target_query": "right query"}, [], snapshot=snapshot
    )
    assert report["score"]["evidence_status"] != "serp_consensus_ready"
    assert report["publication_status"] == "blocked"


@pytest.mark.parametrize("opportunity", [False, True])
@pytest.mark.parametrize("status", ["unsupported", "inconclusive", "missing", "stale"])
def test_generation_ledger_quarantine(tmp_path, monkeypatch, opportunity, status):
    config, config_path = make_config(tmp_path, ["price"])
    config["current_month_year"] = datetime.now(timezone.utc).strftime("%B %Y")
    config["topic_backlog"] = [
        {"title": "Price", "target_query": "price", "type": "standard"}
    ]
    claim = config["claim_evidence"][0]
    draft = (
        "# Price\n\n*Last updated: "
        + config["current_month_year"]
        + ".*\n\n"
        + claim["claim"]
    )
    # Keep the integration focused on forwarding config_path; other gates are tested separately.
    real_check = check_article.check_claim_ledger

    def focused_checks(text, article_type, query, cfg, config_path=None, **kwargs):
        return (
            [("Claim verification ledger", real_check(cfg, config_path))]
            if config_path
            else []
        )

    monkeypatch.setattr(generate_article, "run_checks", focused_checks)
    monkeypatch.setattr(generate_article, "call_llm", lambda *a, **k: draft)
    if status != "missing":
        write_ledger(
            tmp_path,
            [
                entry(
                    "price",
                    "verified" if status == "stale" else status,
                    "2020-01-01T00:00:00+00:00" if status == "stale" else now_iso(),
                )
            ],
        )
    from pathlib import Path

    Path(config_path).write_text(json.dumps(config))
    out = tmp_path / "output"
    argv = [
        "generate_article.py",
        "--config",
        config_path,
        "--provider",
        "deepseek",
        "--out-dir",
        str(out),
    ]
    if opportunity:
        plan = tmp_path / "plan.json"
        plan.write_text(
            json.dumps(
                {
                    "schema_version": "article-forge.opportunity-plan.v1",
                    "candidates": [
                        {"candidate_id": "price", "topic": config["topic_backlog"][0]}
                    ],
                }
            )
        )
        argv += ["--opportunity-plan", str(plan), "--candidate-id", "price"]
    else:
        argv += ["--topic-index", "0"]
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as exc:
        generate_article.main()
    assert exc.value.code == 1
    assert not list(out.glob("*.md"))
    reports = list((out / ".quarantine").glob("*.report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text())
    assert report["publication_status"] == "blocked"
    assert report["gate_checks"][0]["status"] != "PASS"


def covered_fixture(tmp_path, claim_text="The service costs $10 per month."):
    config, path = make_config(tmp_path, ["price", "unused"])
    from datetime import date

    config["facts_last_verified"] = date.today().isoformat()
    config["domain"] = "test.org"
    config["current_month_year"] = datetime.now(timezone.utc).strftime("%B %Y")
    for claim in config["claim_evidence"]:
        claim["source_url"] = "https://test.org/source"
        claim["verified_on"] = date.today().isoformat()
    config["claim_evidence"][0]["claim"] = claim_text
    config["claim_evidence"][1]["claim"] = "An unrelated offer costs $999."
    claim = config["claim_evidence"][0]
    result = bind_result(
        tmp_path, claim, entry("price", "verified", now_iso()), claim_text
    )
    ledger = {
        "evidence_root": str(tmp_path),
        "results": [result, entry("unused", "unsupported", now_iso())],
    }
    (tmp_path / "claim-verification.testproject.json").write_text(json.dumps(ledger))
    text = (
        "# Price\n\n*Last updated: "
        + config["current_month_year"]
        + ".*\n\n"
        + claim_text
    )
    manifest = propose_manifest(text, config, ledger)
    manifest["human_review"] = {
        "reviewer": "Synthetic reviewer",
        "reviewed_at": now_iso(),
        "draft_sha256": text_hash(text),
        "coverage": "all_material_assertions",
        "limitations": "Synthetic fixture only; semantic heuristics are incomplete.",
    }
    return config, path, text, manifest, ledger


def test_unused_unsupported_entry_does_not_block_real_checks(tmp_path):
    config, path, text, manifest, _ = covered_fixture(tmp_path)
    checks = check_article.run_checks(
        text,
        "standard",
        "price",
        config,
        config_path=path,
        manifest=manifest,
        brief=real_brief(tmp_path),
    )
    assert all(status == "PASS" for _, (status, _) in checks), checks


@pytest.mark.parametrize(
    "assertion",
    [
        "It costs $999 per month.",
        "The product supports facial recognition.",
        "The Basic tier includes every feature.",
        "Conversion increased 50%.",
        "Setup takes 7 minutes.",
        "Refunds are guaranteed.",
        "We tested the workflow.",
        '"A fabricated quote."',
        "Feature ID SKU-123 is available.",
    ],
)
def test_new_material_assertion_blocks_coverage(tmp_path, assertion):
    config, _, text, manifest, ledger = covered_fixture(tmp_path)
    text += "\n\n" + assertion
    # Even a fresh whole-draft signature cannot excuse an unmapped assertion.
    manifest["draft_sha256"] = text_hash(text)
    manifest["human_review"]["draft_sha256"] = text_hash(text)
    status, detail = check_manifest(text, manifest, config, ledger, tmp_path)
    assert status == "FAIL"
    assert "unmapped material" in detail


@pytest.mark.parametrize(
    "field,value",
    [
        ("claim", "The service costs $99."),
        ("claim", "The service guarantees success."),
        ("verification_scope", "enterprise only"),
        ("source_url", "https://test.org/new"),
        ("source_local", "new-source.md"),
    ],
)
def test_bound_field_changes_invalidate_verdict(tmp_path, field, value):
    config, path, _, _, _ = covered_fixture(tmp_path)
    config["claim_evidence"][0][field] = value
    assert (
        check_article.check_claim_ledger(config, path, used_claim_ids={"price"})[0]
        != "PASS"
    )


def test_snapshot_tampering_invalidates_verdict(tmp_path):
    config, path, _, _, ledger = covered_fixture(tmp_path)
    Path(ledger["results"][0]["snapshot_path"]).write_text("Changed source")
    assert (
        check_article.check_claim_ledger(config, path, used_claim_ids={"price"})[0]
        != "PASS"
    )


def test_legacy_verified_ledger_not_grandfathered(tmp_path):
    config, path, _, _, ledger = covered_fixture(tmp_path)
    original_date = ledger["results"][0]["checked_at"]
    ledger["results"][0].pop("claim_fingerprint")
    Path(check_article.ledger_path_for_config(path)).write_text(json.dumps(ledger))
    assert (
        check_article.check_claim_ledger(config, path, used_claim_ids={"price"})[0]
        == "WARN"
    )
    assert (
        json.loads(Path(check_article.ledger_path_for_config(path)).read_text())[
            "results"
        ][0]["checked_at"]
        == original_date
    )


@pytest.mark.parametrize(
    "change", ["draft", "mapping", "claim_id", "source_hash", "reviewer", "duplicate"]
)
def test_manifest_consistency(tmp_path, change):
    config, _, text, manifest, ledger = covered_fixture(tmp_path)
    if change == "draft":
        text += "\nAn edit"
    elif change == "mapping":
        manifest["assertions"][0]["sentence"] += " changed"
    elif change == "claim_id":
        manifest["assertions"][0]["claim_ids"] = ["missing"]
    elif change == "source_hash":
        manifest["assertions"][0]["evidence_binding"] = "incorrect"
    elif change == "reviewer":
        manifest["human_review"] = None
    else:
        manifest["assertions"].append(manifest["assertions"][0])
    assert check_manifest(text, manifest, config, ledger, tmp_path)[0] == "FAIL"


def test_supported_claim_cannot_be_strengthened_using_same_id(tmp_path):
    config, _, text, _, ledger = covered_fixture(tmp_path)
    text = text.replace(
        "The service costs $10 per month.", "The service always costs $10 per month."
    )
    manifest = propose_manifest(text, config, ledger)
    manifest["assertions"][0]["claim_ids"] = ["price"]
    result = ledger["results"][0]
    binding = object_hash(
        [
            {
                "claim_id": "price",
                "claim_fingerprint": claim_fingerprint(config["claim_evidence"][0]),
                "snapshot_sha256": result["snapshot_sha256"],
            }
        ]
    )
    manifest["assertions"][0]["evidence_binding"] = binding
    manifest["human_review"] = {
        "reviewer": "Reviewer",
        "reviewed_at": now_iso(),
        "draft_sha256": text_hash(text),
        "coverage": "all_material_assertions",
        "limitations": "Human review is incomplete.",
    }
    manifest["assertions"][0]["semantic_review"] = {
        "reviewer": "Reviewer",
        "assertion_sha256": text_hash(manifest["assertions"][0]["sentence"]),
        "evidence_binding": binding,
        "verdict": "supported_without_strengthening",
    }
    status, detail = check_manifest(text, manifest, config, ledger, tmp_path)
    assert status == "FAIL" and "strengthening" in detail


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_date",
        "old_date",
        "future_date",
        "query",
        "country",
        "language",
        "location",
        "extraction",
        "missing_fields",
        "snapshot_hash",
        "provenance",
        "subdomains",
        "extraction_hash",
    ],
)
def test_snapshot_contract_rejects_invalid_evidence(mutation):
    snapshot = valid_snapshot("price")
    policy = {"country": "us", "language": "en", "location": "Bridgetown"}
    snapshot["locale"]["location"] = "Bridgetown"
    if mutation == "missing_date":
        snapshot.pop("captured_at")
    if mutation == "old_date":
        snapshot["captured_at"] = "2020-01-01T00:00:00+00:00"
    if mutation == "future_date":
        snapshot["captured_at"] = (
            datetime.now(timezone.utc) + timedelta(days=1)
        ).isoformat()
    if mutation == "query":
        snapshot["keyword"] = "unrelated"
    if mutation in {"country", "language", "location"}:
        snapshot["locale"][mutation] = "wrong"
    if mutation == "extraction":
        snapshot["competitors"][0]["extraction"]["status"] = "failed"
    if mutation == "missing_fields":
        snapshot["competitors"][0].pop("entities")
    if mutation == "snapshot_hash":
        snapshot["competitors"][0]["source_snapshot"]["text"] += "tamper"
    if mutation == "provenance":
        snapshot.pop("provenance")
    if mutation == "subdomains":
        for i, page in enumerate(snapshot["competitors"]):
            page["url"] = f"https://sub{i}.same.org/"
    if mutation == "extraction_hash":
        snapshot["competitors"][0]["entities"].append("Invented")
    verdict = validate_snapshot(snapshot, "price", policy)
    assert not verdict["valid"] and verdict["reasons"]
    result = score_article.score_for_report(
        "Draft", snapshot, "standard", {}, target_query="price", policy=policy
    )
    assert result["score_kind"] == "readiness"
    assert "topical_comprehensiveness" in result["unassessed_pillars"]


def test_reviewed_query_cluster_and_configurable_freshness():
    snapshot = valid_snapshot("price")
    snapshot["reviewed_query_cluster"] = {
        "queries": ["cost"],
        "reviewer": "Reviewer",
        "reason": "Same documented intent",
        "reviewed_at": current_time(),
    }
    assert validate_snapshot(snapshot, "cost")["valid"]
    snapshot["captured_at"] = (
        datetime.now(timezone.utc) - timedelta(days=10)
    ).isoformat()
    assert not validate_snapshot(snapshot, "cost", {"max_age_days": 7})["valid"]
    assert validate_snapshot(snapshot, "cost", {"max_age_days": 14})["valid"]


def test_complete_empty_extraction_is_distinct_from_extraction_failure():
    snapshot = valid_snapshot(
        "price",
        [
            {
                "url": f"https://sample{i}.org/",
                "subtopics": [],
                "entities": [],
                "headings": [],
            }
            for i in range(5)
        ],
    )
    assert validate_snapshot(snapshot, "price")["valid"]
    score = score_article.score_for_report(
        "Draft", snapshot, "standard", {}, target_query="price"
    )
    assert score["pillars"]["topical_comprehensiveness"] is None
    assert score["pillars"]["entity_coverage"] is None


def real_brief(root, query="price", action="create"):
    asset = root / "experiment.md"
    asset.write_text("Synthetic worked example, with explicit limitations.")
    return {
        "schema_version": "article-forge.editorial-brief.v1",
        "target_query": query,
        "reader_problem": "Choose a suitable service",
        "intended_action": "Review suitability",
        "original_contribution": "A documented worked example",
        "limitation": "Synthetic test only",
        "supporting_assets": [
            {
                "path": str(asset),
                "sha256": text_hash(asset.read_text()),
                "source": "local experiment",
                "rights": "owned",
                "role": "evidence",
                "kind": "worked_calculation",
            }
        ],
        "existing_page_evidence": [
            {
                "url": "https://test.org/service",
                "path": str(asset),
                "sha256": text_hash(asset.read_text()),
            }
        ]
        if action in {"improve", "consolidate"}
        else [],
        "query_page_observations": {"unavailable_reason": "New synthetic site"},
        "page_decision": {
            "action": action,
            "page_type": "service",
            "reviewer": "Reviewer",
            "reviewed_at": now_iso(),
            "reason": "Reader needs a service page",
            "existing_urls": ["https://test.org/service"]
            if action in {"improve", "consolidate"}
            else [],
        },
    }


@pytest.mark.parametrize("action", ["create", "improve", "consolidate", "defer"])
def test_page_decisions_and_briefs_are_reviewed(tmp_path, action):
    brief = real_brief(tmp_path, action=action)
    assert check_brief(brief, "price", tmp_path)[0] == (
        "WARN" if action == "defer" else "PASS"
    )
    brief["supporting_assets"][0]["sha256"] = "wrong"
    assert check_brief(brief, "price", tmp_path)[0] == "FAIL"


def test_generated_image_cannot_prove_experience(tmp_path):
    brief = real_brief(tmp_path)
    brief["supporting_assets"][0]["kind"] = "generated_image"
    assert check_brief(brief, "price", tmp_path)[0] == "FAIL"


def test_page_overlap_uses_content_and_is_not_cannibalization_proof():
    signal = suggest_page_decision(
        "shared bills",
        [{"url": "/guide", "content": "A guide to shared bills"}],
        [
            {"query": "shared bills", "page": "/guide"},
            {"query": "shared bills", "page": "/service"},
        ],
    )
    assert signal["suggested_action"] == "improve" and signal["existing_urls"] == [
        "/guide"
    ]
    assert len(signal["query_page_urls"]) == 2 and signal["review_required"]


@pytest.mark.parametrize(
    "status", ["verified", "unsupported", "inconclusive", "missing", "stale"]
)
@pytest.mark.parametrize("opportunity", [False, True])
@pytest.mark.parametrize("review_mode", [False, True])
def test_full_generation_cli_and_review_path(
    tmp_path, monkeypatch, status, opportunity, review_mode
):
    config, path, text, manifest, ledger = covered_fixture(tmp_path)
    brief = real_brief(tmp_path)
    topic = {
        "target_query": "price",
        "title": "Price",
        "type": "standard",
        "editorial_brief": brief,
    }
    config["topic_backlog"] = [topic]
    if status == "missing":
        ledger["results"] = []
    elif status == "stale":
        ledger["results"][0]["checked_at"] = "2020-01-01T00:00:00+00:00"
    else:
        ledger["results"][0]["status"] = status
    Path(check_article.ledger_path_for_config(path)).write_text(json.dumps(ledger))
    Path(path).write_text(json.dumps(config))
    mp = tmp_path / "manifest.json"
    mp.write_text(json.dumps(manifest))
    # Genuine run_checks, no focused gate stub. Review mode must make no provider call.
    draft = tmp_path / "review.md"
    draft.write_text(text)

    def writer(*args, **kwargs):
        if review_mode:
            raise AssertionError("provider called in local review mode")
        return text

    monkeypatch.setattr(generate_article, "call_llm", writer)
    out = tmp_path / "generated"
    argv = [
        "generate_article.py",
        "--config",
        path,
        "--provider",
        "deepseek",
        "--manifest",
        str(mp),
        "--out-dir",
        str(out),
    ]
    if review_mode:
        argv += ["--review-draft", str(draft)]
    if opportunity:
        plan = tmp_path / "plan.json"
        plan.write_text(
            json.dumps(
                {
                    "schema_version": "article-forge.opportunity-plan.v1",
                    "candidates": [{"candidate_id": "price", "topic": topic}],
                }
            )
        )
        argv += ["--opportunity-plan", str(plan), "--candidate-id", "price"]
    else:
        argv += ["--topic-index", "0"]
    monkeypatch.setattr("sys.argv", argv)
    if status == "verified":
        generate_article.main()
        result = json.loads((out / "price.report.json").read_text())
        assert result["publication_status"] == "ready_for_human_review"
        assert result["provenance"]["provider"] == (
            None if review_mode else "deepseek"
        )  # Supplied draft, no false writer attribution.
        assert (out / "price.provenance.json").exists()
    else:
        with pytest.raises(SystemExit) as exc:
            generate_article.main()
        assert exc.value.code == 1
        assert not list(out.glob("*.md"))
        result = json.loads((out / ".quarantine/price.report.json").read_text())
        assert result["publication_status"] == "blocked"
        assert any(
            c["name"] == "Claim verification ledger" and c["status"] != "PASS"
            for c in result["gate_checks"]
        )


def test_invalid_serp_blocks_before_writer_call(tmp_path, monkeypatch):
    config, path, _, _, _ = covered_fixture(tmp_path)
    config["topic_backlog"] = [{"target_query": "price", "title": "Price"}]
    Path(path).write_text(json.dumps(config))
    sp = tmp_path / "snapshot.json"
    sp.write_text(json.dumps(valid_snapshot("wrong query")))
    monkeypatch.setattr(
        generate_article,
        "call_llm",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("writer called")),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_article.py",
            "--config",
            path,
            "--topic-index",
            "0",
            "--provider",
            "deepseek",
            "--snapshot",
            str(sp),
            "--out-dir",
            str(tmp_path / "out"),
        ],
    )
    with pytest.raises(SystemExit, match="SERP snapshot rejected"):
        generate_article.main()


@pytest.mark.parametrize(
    "field,value",
    [
        ("claim", "Costs $99."),
        ("verification_scope", "changed scope"),
        ("source_url", "https://test.org/new"),
    ],
)
def test_verifier_rechecks_changed_binding_and_legacy(
    tmp_path, monkeypatch, field, value
):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(verify_facts, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    config, path, _, _, ledger = covered_fixture(tmp_path)
    config["claim_evidence"] = config["claim_evidence"][:1]
    config["claim_evidence"][0][field] = value
    Path(path).write_text(json.dumps(config))
    calls = []
    monkeypatch.setattr(
        verify_facts, "fetch_url", lambda url: ("<p>The service costs $99.</p>", 200)
    )
    monkeypatch.setattr(
        verify_facts,
        "call_llm",
        lambda *a, **k: (
            calls.append(1),
            json.dumps(
                {
                    "status": "verified",
                    "evidence_quotes": ["The service costs $99."],
                    "missing_aspects": [],
                }
            ),
        )[1],
    )
    assert verify_facts.main(["--config", path]) == 0
    assert len(calls) == 1
    result = json.loads(Path(check_article.ledger_path_for_config(path)).read_text())[
        "results"
    ][0]
    assert result["claim_fingerprint"] == claim_fingerprint(config["claim_evidence"][0])
    assert result["snapshot_sha256"] == text_hash(
        (tmp_path / result["snapshot_path"]).read_text()
    )


def test_all_judge_quotes_must_match_and_all_prices_must_match():
    assert not verify_facts.quotes_in_source(
        ["A real quote", "An invented quote"], "A real quote"
    )
    source = verify_facts.html_to_text(
        '<script type="application/ld+json">{"@type":"Offer","price":"10"}</script>'
    )
    assert verify_facts.numeric_mismatch("Costs $10 or $999.", source)


def test_substantive_text_cannot_hide_on_dateline(tmp_path):
    config, _, text, manifest, ledger = covered_fixture(tmp_path)
    text = text.replace(".*\n\n", ".* Our service costs $999.\n\n")
    manifest["draft_sha256"] = text_hash(text)
    manifest["human_review"]["draft_sha256"] = text_hash(text)
    assert check_manifest(text, manifest, config, ledger, tmp_path)[0] == "FAIL"


def test_empty_consensus_has_explicit_evidence_status():
    snapshot = valid_snapshot(
        "price",
        [
            {
                "url": f"https://sample{i}.org/",
                "subtopics": [],
                "entities": [],
                "headings": [],
            }
            for i in range(5)
        ],
    )
    result = score_article.score_for_report(
        "Text", snapshot, "standard", {}, target_query="price"
    )
    assert result["evidence_status"] == "serp_sample_valid_no_consensus"
    assert result["consensus_ready"] is False


@pytest.mark.parametrize(
    "bad", [None, [], {"competitors": [None, 1, {"url": 42}]}, {"competitors": "bad"}]
)
def test_malformed_serp_does_not_promote_readiness(bad):
    verdict = validate_snapshot(bad, "price")
    assert not verdict["valid"] and verdict["reasons"]


@pytest.mark.parametrize("snapshot", [[], [1], {"competitors": [None, {"url": 42}]}])
def test_malformed_snapshot_reports_explicit_unassessed_reasons(snapshot):
    report = score_article.build_article_report(
        "Draft", {}, {"target_query": "price"}, [], snapshot=snapshot
    )
    assert report["publication_status"] == "blocked"
    assert report["score"]["evidence_status"] == "serp_snapshot_invalid"
    assert report["score"]["evidence_reasons"]
    assert "topical_comprehensiveness" in report["score"]["unassessed_pillars"]


def test_duplicate_ledger_cannot_hide_an_unsupported_used_claim(tmp_path):
    config, path, _, _, ledger = covered_fixture(tmp_path)
    ledger["results"].insert(0, entry("price", "unsupported", now_iso()))
    Path(check_article.ledger_path_for_config(path)).write_text(json.dumps(ledger))
    assert (
        check_article.check_claim_ledger(config, path, used_claim_ids={"price"})[0]
        == "FAIL"
    )


def test_local_source_changes_require_fresh_verification(tmp_path):
    from evidence_contract import binding_error

    config, _, _, _, ledger = covered_fixture(tmp_path)
    claim = config["claim_evidence"][0]
    source = tmp_path / "local-source.md"
    source.write_text(claim["claim"])
    claim["source_local"] = str(source)
    result = ledger["results"][0]
    result["claim_fingerprint"] = claim_fingerprint(claim)
    result["source_raw_sha256"] = text_hash(source.read_text())
    assert binding_error(claim, result, tmp_path) is None
    source.write_text("A different price and scope")
    assert "local source changed" in binding_error(claim, result, tmp_path)


@pytest.mark.parametrize("kind", ["screenshot", "photograph"])
def test_real_media_requires_inspectable_image_and_caption_review(tmp_path, kind):
    from PIL import Image

    brief = real_brief(tmp_path)
    image = tmp_path / "actual.png"
    Image.new("RGB", (64, 64), color="green").save(image)
    import hashlib

    asset = {
        "path": str(image),
        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "kind": kind,
        "role": "evidence",
        "source": "Synthetic test image",
        "rights": "Synthetic owner",
        "caption": "A solid green synthetic test image.",
        "alt_text": "Green rectangle",
        "visible_content_reviewed_by": "Synthetic reviewer",
    }
    brief["supporting_assets"] = [asset]
    assert check_brief(brief, "price", tmp_path)[0] == "PASS"
    asset.pop("caption")
    assert check_brief(brief, "price", tmp_path)[0] == "FAIL"


def test_update_decision_cannot_rely_on_url_alone(tmp_path):
    brief = real_brief(tmp_path, action="improve")
    brief["existing_page_evidence"] = []
    assert check_brief(brief, "price", tmp_path)[0] == "FAIL"
