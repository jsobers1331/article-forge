"""Tests for check_article.py's claim-verification ledger gate.

These exercise the ledger logic directly (check_claim_ledger), its place in
run_checks, and the main() hard-fail path. No network, no LLM.
"""

import json
import sys
from datetime import datetime, timedelta, timezone

import check_article

CONFIG_NAME = "site-config.testproject.json"
LEDGER_NAME = "claim-verification.testproject.json"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def days_ago_iso(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def make_config(tmp_path, claim_ids, **extra):
    today = datetime.now(timezone.utc).date().isoformat()
    config = {
        "site_name": "TestProject",
        "domain": "example.com",
        "category_frame": "a test frame",
        "icp": "test readers",
        "canonical_definition_sentence": "TestProject is a test product.",
        "existing_pages": ["/"],
        "current_month_year": "September 2026",
        "verified_facts": {
            "real_differentiators": [],
            "coming_soon_features": [],
            "pricing_and_billing": {},
        },
        "facts_last_verified": today,
        "claim_evidence": [
            {
                "claim_id": cid,
                "claim": f"claim text for {cid}",
                "source_url": f"https://example.com/{cid}",
                "verified_on": today,
                "status": "verified",
                "verification_scope": "fixture",
            }
            for cid in claim_ids
        ],
    }
    config.update(extra)
    path = tmp_path / CONFIG_NAME
    path.write_text(json.dumps(config), encoding="utf-8")
    return config, str(path)


def entry(claim_id, status, checked_at):
    return {"claim_id": claim_id, "status": status, "checked_at": checked_at}


def write_ledger(tmp_path, results):
    path = tmp_path / LEDGER_NAME
    path.write_text(
        json.dumps(
            {
                "generated_at": now_iso(),
                "project": "testproject",
                "verifier": "verify_facts",
                "results": results,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_unsupported_claim_is_hard_fail(tmp_path):
    config, path = make_config(tmp_path, ["claim-a"])
    write_ledger(tmp_path, [entry("claim-a", "unsupported", now_iso())])

    status, detail = check_article.check_claim_ledger(config, path)

    assert status == "FAIL"
    assert "claim-a" in detail
    assert "PLACEHOLDER: claim" in detail


def test_missing_ledger_warns_and_points_at_verifier(tmp_path):
    config, path = make_config(tmp_path, ["claim-a"])

    status, detail = check_article.check_claim_ledger(config, path)

    assert status == "WARN"
    assert "verify_facts" in detail


def test_inconclusive_entry_warns(tmp_path):
    config, path = make_config(tmp_path, ["claim-a", "claim-b"])
    write_ledger(
        tmp_path,
        [entry("claim-a", "verified", now_iso()), entry("claim-b", "inconclusive", now_iso())],
    )

    status, detail = check_article.check_claim_ledger(config, path)

    assert status == "WARN"
    assert "inconclusive" in detail
    assert "claim-b" in detail
    assert "claim-a" not in detail


def test_stale_verified_entry_warns(tmp_path):
    config, path = make_config(tmp_path, ["claim-a"])
    write_ledger(tmp_path, [entry("claim-a", "verified", days_ago_iso(60))])

    status, detail = check_article.check_claim_ledger(config, path)

    assert status == "WARN"
    assert "stale" in detail
    assert "claim-a" in detail


def test_unparseable_checked_at_counts_as_stale(tmp_path):
    config, path = make_config(tmp_path, ["claim-a"])
    write_ledger(tmp_path, [entry("claim-a", "verified", "not-a-date")])

    status, detail = check_article.check_claim_ledger(config, path)

    assert status == "WARN"
    assert "stale" in detail


def test_claim_missing_from_ledger_warns(tmp_path):
    config, path = make_config(tmp_path, ["claim-a"])
    write_ledger(tmp_path, [entry("claim-other", "verified", now_iso())])

    status, detail = check_article.check_claim_ledger(config, path)

    assert status == "WARN"
    assert "never verified" in detail
    assert "claim-a" in detail


def test_malformed_ledger_warns_instead_of_crashing(tmp_path):
    config, path = make_config(tmp_path, ["claim-a"])
    (tmp_path / LEDGER_NAME).write_text("{not valid json", encoding="utf-8")

    status, detail = check_article.check_claim_ledger(config, path)

    assert status == "WARN"
    assert "verify_facts" in detail


def test_wrong_shape_ledger_warns_instead_of_crashing(tmp_path):
    config, path = make_config(tmp_path, ["claim-a"])
    (tmp_path / LEDGER_NAME).write_text(json.dumps({"results": "nope"}), encoding="utf-8")

    status, detail = check_article.check_claim_ledger(config, path)

    assert status == "WARN"
    assert "verify_facts" in detail


def test_fresh_verified_ledger_passes(tmp_path):
    config, path = make_config(tmp_path, ["claim-a", "claim-b"])
    write_ledger(
        tmp_path,
        [entry("claim-a", "verified", now_iso()), entry("claim-b", "verified", days_ago_iso(1))],
    )

    status, detail = check_article.check_claim_ledger(config, path)

    assert status == "PASS"
    assert "2 claim(s)" in detail


def test_no_claim_evidence_passes(tmp_path):
    config, path = make_config(tmp_path, [])

    status, detail = check_article.check_claim_ledger(config, path)

    assert status == "PASS"
    assert "no claim_evidence" in detail


def test_missing_claim_evidence_key_passes(tmp_path):
    config, path = make_config(tmp_path, [], claim_evidence=None)

    status, _ = check_article.check_claim_ledger(config, path)

    assert status == "PASS"


DRAFT_TEXT = (
    "# Autonomous claim verification\n\n"
    "*Last updated: September 2026.*\n\n"
    "A short intro paragraph.\n\n"
    "| column a | column b |\n|---|---|\n| 1 | 2 |\n\n"
) + "filler word " * 700


def test_run_checks_places_ledger_check_after_facts_freshness(tmp_path):
    config, path = make_config(tmp_path, ["claim-a"])
    write_ledger(tmp_path, [entry("claim-a", "verified", now_iso())])

    checks = check_article.run_checks(
        DRAFT_TEXT, "standard", "autonomous claim verification", config, config_path=path
    )
    names = [name for name, _ in checks]

    assert names.index("Claim verification ledger") == names.index("Facts freshness") + 1


def test_run_checks_omits_ledger_check_when_disabled(tmp_path):
    config, path = make_config(tmp_path, ["claim-a"])

    names = [
        name
        for name, _ in check_article.run_checks(
            DRAFT_TEXT, "standard", "autonomous claim verification", config,
            config_path=path, use_ledger=False,
        )
    ]
    assert "Claim verification ledger" not in names

    names_no_path = [
        name
        for name, _ in check_article.run_checks(
            DRAFT_TEXT, "standard", "autonomous claim verification", config
        )
    ]
    assert "Claim verification ledger" not in names_no_path


def _run_main(tmp_path, monkeypatch, extra_args=()):
    config, path = make_config(tmp_path, ["claim-a"])
    write_ledger(tmp_path, [entry("claim-a", "unsupported", now_iso())])
    draft = tmp_path / "draft.md"
    draft.write_text(DRAFT_TEXT, encoding="utf-8")
    argv = [
        "check_article.py",
        "--draft", str(draft),
        "--config", path,
        "--type", "standard",
        "--query", "autonomous claim verification",
        *extra_args,
    ]
    monkeypatch.setattr(sys, "argv", argv)
    return check_article.main


def test_main_exits_1_on_unsupported_claim(tmp_path, monkeypatch, capsys):
    main = _run_main(tmp_path, monkeypatch)

    try:
        main()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit(1) on an unsupported claim")

    out = capsys.readouterr().out
    assert "HARD FAIL" in out
    assert "claim-a" in out


def test_main_no_ledger_flag_bypasses_the_hard_fail(tmp_path, monkeypatch):
    main = _run_main(tmp_path, monkeypatch, extra_args=("--no-ledger",))

    try:
        main()
    except SystemExit as exc:
        raise AssertionError(f"expected no hard fail with --no-ledger, got SystemExit({exc.code})")
