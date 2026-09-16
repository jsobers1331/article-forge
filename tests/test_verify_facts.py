import inspect
import json
from datetime import datetime, timedelta, timezone

import pytest

import verify_facts


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    monkeypatch.setattr(verify_facts, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")


def write_config(tmp_path, entries, name="site-config.demo.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"project": "demo", "claim_evidence": entries}), encoding="utf-8")
    return path


def make_entry(claim_id="claim-a", **overrides):
    entry = {
        "claim_id": claim_id,
        "claim": "The demo product costs $10 per month.",
        "source_url": "https://example.com/pricing",
        "verification_scope": "test",
    }
    entry.update(overrides)
    return entry


def read_ledger(tmp_path, name="claim-verification.demo.json"):
    return json.loads((tmp_path / name).read_text(encoding="utf-8"))


def llm_json(status, quotes=None, missing=None):
    return json.dumps({
        "status": status,
        "evidence_quotes": quotes or [],
        "missing_aspects": missing or [],
    })


def test_verified_claim_with_quote_writes_ledger_and_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [make_entry()])
    monkeypatch.setattr(
        verify_facts, "fetch_url",
        lambda url: ("<html><body>Our demo plan costs $10 per month, billed yearly.</body></html>", 200),
    )
    monkeypatch.setattr(
        verify_facts, "call_llm",
        lambda *a, **k: llm_json("verified", quotes=["costs $10 per month"]),
    )

    assert verify_facts.main(["--config", str(config)]) == 0

    ledger = read_ledger(tmp_path)
    assert ledger["project"] == "demo"
    result = ledger["results"][0]
    assert result["status"] == "verified"
    assert result["evidence_quotes"] == ["costs $10 per month"]
    assert result["http_status_or_local"] == 200
    snapshot = tmp_path / result["snapshot_path"]
    assert snapshot.exists()
    assert "costs $10 per month" in snapshot.read_text(encoding="utf-8")


def test_contradicted_claim_is_unsupported_and_still_exits_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [make_entry()])
    monkeypatch.setattr(verify_facts, "fetch_url", lambda url: ("<html>Pricing starts at $25.</html>", 200))
    monkeypatch.setattr(verify_facts, "call_llm", lambda *a, **k: llm_json("unsupported", quotes=["starts at $25"]))

    assert verify_facts.main(["--config", str(config)]) == 0
    assert read_ledger(tmp_path)["results"][0]["status"] == "unsupported"


def test_unparseable_llm_reply_is_inconclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [make_entry()])
    monkeypatch.setattr(verify_facts, "fetch_url", lambda url: ("<html>Some page.</html>", 200))
    monkeypatch.setattr(verify_facts, "call_llm", lambda *a, **k: "I think it's probably fine, honestly.")

    assert verify_facts.main(["--config", str(config)]) == 0
    result = read_ledger(tmp_path)["results"][0]
    assert result["status"] == "inconclusive"
    assert result["missing_aspects"] == ["verifier output was not strict JSON"]


def test_verified_without_matching_quote_is_downgraded(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [make_entry()])
    monkeypatch.setattr(verify_facts, "fetch_url", lambda url: ("<html>Our demo plan costs $10 per month.</html>", 200))
    monkeypatch.setattr(
        verify_facts, "call_llm",
        lambda *a, **k: llm_json("verified", quotes=["absolutely nowhere in the source text"]),
    )

    assert verify_facts.main(["--config", str(config)]) == 0
    result = read_ledger(tmp_path)["results"][0]
    assert result["status"] == "inconclusive"
    assert "verified verdict had no quote matching the source" in result["missing_aspects"]


def test_source_local_wins_over_source_url(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    source = repo / "src" / "page.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("Our demo plan costs $10 per month.", encoding="utf-8")
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(repo))
    config = write_config(
        tmp_path,
        [make_entry(source_local="src/page.tsx", source_url="https://example.com/never-fetched")],
    )

    def fail_fetch(url):
        raise AssertionError(f"fetch_url called for {url} despite source_local")

    monkeypatch.setattr(verify_facts, "fetch_url", fail_fetch)
    monkeypatch.setattr(verify_facts, "call_llm", lambda *a, **k: llm_json("verified", quotes=["costs $10 per month"]))

    assert verify_facts.main(["--config", str(config)]) == 0
    result = read_ledger(tmp_path)["results"][0]
    assert result["http_status_or_local"] == "src/page.tsx"
    assert result["status"] == "verified"


def test_unreadable_source_local_is_inconclusive_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [make_entry(source_local="does/not/exist.tsx")])

    def fail_fetch(url):
        raise AssertionError("fetch_url called for a source_local claim")

    monkeypatch.setattr(verify_facts, "fetch_url", fail_fetch)

    def fail_llm(*a, **k):
        raise AssertionError("LLM called for an unreadable source")

    monkeypatch.setattr(verify_facts, "call_llm", fail_llm)

    assert verify_facts.main(["--config", str(config)]) == 0
    result = read_ledger(tmp_path)["results"][0]
    assert result["status"] == "inconclusive"
    assert "could not read source_local" in result["missing_aspects"][0]
    assert result["snapshot_path"] is None


def test_fresh_entry_is_carried_forward_without_llm_call(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [make_entry()])
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prior = {
        "claim_id": "claim-a",
        "status": "verified",
        "checked_at": checked_at,
        "source": "https://example.com/pricing",
        "http_status_or_local": 200,
        "evidence_quotes": ["costs $10 per month"],
        "missing_aspects": [],
        "snapshot_path": "evidence/demo/claim-a-20260101.txt",
    }
    (tmp_path / "claim-verification.demo.json").write_text(
        json.dumps({"generated_at": checked_at, "project": "demo", "verifier": "prior", "results": [prior]}),
        encoding="utf-8",
    )

    def fail(*a, **k):
        raise AssertionError("a fresh entry must not be re-fetched or re-judged")

    monkeypatch.setattr(verify_facts, "fetch_url", fail)
    monkeypatch.setattr(verify_facts, "call_llm", fail)

    assert verify_facts.main(["--config", str(config)]) == 0
    result = read_ledger(tmp_path)["results"][0]
    assert result["carried_forward"] is True
    assert result["checked_at"] == checked_at
    assert result["snapshot_path"] == "evidence/demo/claim-a-20260101.txt"


def test_stale_entry_is_reverified(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [make_entry()])
    stale_at = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(timespec="seconds")
    prior = {"claim_id": "claim-a", "status": "inconclusive", "checked_at": stale_at, "source": "x"}
    (tmp_path / "claim-verification.demo.json").write_text(
        json.dumps({"generated_at": stale_at, "project": "demo", "verifier": "prior", "results": [prior]}),
        encoding="utf-8",
    )
    calls = []

    def counting_llm(*a, **k):
        calls.append(1)
        return llm_json("verified", quotes=["costs $10 per month"])

    monkeypatch.setattr(verify_facts, "fetch_url", lambda url: ("<html>costs $10 per month</html>", 200))
    monkeypatch.setattr(verify_facts, "call_llm", counting_llm)

    assert verify_facts.main(["--config", str(config)]) == 0
    assert len(calls) == 1
    result = read_ledger(tmp_path)["results"][0]
    assert result["status"] == "verified"
    assert "carried_forward" not in result


def test_claim_id_scope_preserves_others(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [make_entry("claim-a"), make_entry("claim-b")])
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prior = {"claim_id": "claim-a", "status": "verified", "checked_at": checked_at, "source": "x"}
    (tmp_path / "claim-verification.demo.json").write_text(
        json.dumps({"generated_at": checked_at, "project": "demo", "verifier": "prior", "results": [prior]}),
        encoding="utf-8",
    )
    calls = []

    def counting_llm(*a, **k):
        calls.append(1)
        return llm_json("unsupported", quotes=["nope"])

    monkeypatch.setattr(verify_facts, "fetch_url", lambda url: ("<html>Some other content.</html>", 200))
    monkeypatch.setattr(verify_facts, "call_llm", counting_llm)

    assert verify_facts.main(["--config", str(config), "--claim-id", "claim-b"]) == 0
    assert len(calls) == 1
    by_id = {r["claim_id"]: r for r in read_ledger(tmp_path)["results"]}
    assert set(by_id) == {"claim-a", "claim-b"}
    assert by_id["claim-a"]["checked_at"] == checked_at
    assert by_id["claim-b"]["status"] == "unsupported"


def test_entries_for_dropped_claims_are_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [make_entry("claim-a")])
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prior = [
        {"claim_id": "claim-a", "status": "verified", "checked_at": checked_at, "source": "x"},
        {"claim_id": "claim-gone", "status": "verified", "checked_at": checked_at, "source": "x"},
    ]
    (tmp_path / "claim-verification.demo.json").write_text(
        json.dumps({"generated_at": checked_at, "project": "demo", "verifier": "prior", "results": prior}),
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_facts, "fetch_url", lambda url: (_ for _ in ()).throw(AssertionError("fetched")))
    monkeypatch.setattr(verify_facts, "call_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("judged")))

    assert verify_facts.main(["--config", str(config)]) == 0
    ids = [r["claim_id"] for r in read_ledger(tmp_path)["results"]]
    assert ids == ["claim-a"]


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [make_entry()])
    monkeypatch.setattr(verify_facts, "fetch_url", lambda url: (_ for _ in ()).throw(AssertionError("fetched")))
    monkeypatch.setattr(verify_facts, "call_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("judged")))

    assert verify_facts.main(["--config", str(config), "--dry-run"]) == 0
    assert not (tmp_path / "claim-verification.demo.json").exists()
    assert not (tmp_path / "evidence").exists()


def test_missing_config_exits_two(tmp_path):
    assert verify_facts.main(["--config", str(tmp_path / "nope.json")]) == 2


def test_malformed_config_exits_two(tmp_path):
    bad = tmp_path / "site-config.demo.json"
    bad.write_text("{not json", encoding="utf-8")
    assert verify_facts.main(["--config", str(bad)]) == 2


def test_malformed_ledger_exits_two(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [make_entry()])
    (tmp_path / "claim-verification.demo.json").write_text("{broken", encoding="utf-8")
    assert verify_facts.main(["--config", str(config)]) == 2


def test_unknown_claim_id_exits_two(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [make_entry("claim-a")])
    assert verify_facts.main(["--config", str(config), "--claim-id", "nope"]) == 2


def test_missing_api_key_exits_two(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = write_config(tmp_path, [make_entry()])
    assert verify_facts.main(["--config", str(config)]) == 2
    assert verify_facts.main(["--config", str(config), "--dry-run"]) == 0
    # the key that matters is the selected provider's
    monkeypatch.setattr(verify_facts, "fetch_url", lambda url: ("<html>costs $10 per month</html>", 200))
    monkeypatch.setattr(
        verify_facts, "call_llm", lambda *a, **k: llm_json("verified", quotes=["costs $10 per month"])
    )
    assert verify_facts.main(["--config", str(config), "--provider", "deepseek"]) == 0


def test_config_without_claims_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [])
    assert verify_facts.main(["--config", str(config)]) == 0
    assert not (tmp_path / "claim-verification.demo.json").exists()


def test_html_to_text_preserves_non_html_angle_brackets():
    source = (
        'export function pick(items: Item[]) {\n'
        '  if (items.length <= 3 && rank > 0) return items[0];\n'
        '  const label = a < b ? "cheaper" : "pricier";\n'
        '  return items.filter((f) => f.tier <= maxTier);\n'
        '}\n'
        '\n'
        'Debt payoff planner snowball vs. avalanche.\n'
    )

    text = verify_facts.html_to_text(source)

    assert "items.length <= 3 && rank > 0" in text
    assert 'a < b ? "cheaper"' in text
    assert "f.tier <= maxTier" in text
    assert "Debt payoff planner snowball vs. avalanche." in text


def test_html_to_text_strips_real_tags_and_keeps_structured_data():
    raw = (
        '<html><head><script type="application/ld+json">'
        '{"@type": "Product", "offers": {"price": "10"}}'
        "</script></head><body>"
        '<header><nav><a href="/pricing">Pricing</a></nav></header>'
        "<p>Our demo plan costs <strong>$10</strong> per month.</p>"
        '<div itemprop="price" content="$10">ten dollars</div>'
        "</body></html>"
    )

    text = verify_facts.html_to_text(raw)

    assert text.startswith("=== STRUCTURED DATA (JSON-LD / microdata) ===")
    assert '"@type": "Product"' in text
    assert "itemprop" not in text.split("=== PAGE TEXT ===")[1]
    assert "price: $10" in text
    assert "<strong>" not in text
    assert "costs $10 per month" in text
    assert "Pricing" in text


def test_judge_defaults_to_openai_gpt_4o_mini_and_honours_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    config = write_config(tmp_path, [make_entry()])
    monkeypatch.setattr(verify_facts, "fetch_url", lambda url: ("<html>costs $10 per month</html>", 200))
    calls = []

    def capture(prompt, **kwargs):
        calls.append(kwargs)
        return llm_json("verified", quotes=["costs $10 per month"])

    monkeypatch.setattr(verify_facts, "call_llm", capture)
    force = ["--max-age-days", "0"]

    assert verify_facts.main(["--config", str(config), *force]) == 0
    assert calls[-1]["provider"] == "openai"
    assert calls[-1]["model"] == "gpt-4o-mini"
    assert "provider=openai, model=gpt-4o-mini" in read_ledger(tmp_path)["verifier"]

    assert verify_facts.main(
        ["--config", str(config), "--provider", "deepseek", "--model", "deepseek-reasoner", *force]
    ) == 0
    assert calls[-1]["provider"] == "deepseek"
    assert calls[-1]["model"] == "deepseek-reasoner"

    # --provider alone falls back to that provider's default model, not gpt-4o-mini
    assert verify_facts.main(["--config", str(config), "--provider", "deepseek", *force]) == 0
    assert calls[-1]["provider"] == "deepseek"
    from scripts.call_llm import PROVIDERS
    assert calls[-1]["model"] == PROVIDERS["deepseek"]["default_model"]


def test_build_prompt_is_blind_to_verdicts_and_prior_results():
    prompt = verify_facts.build_prompt(
        "The demo product costs $10 per month.",
        "live pricing page",
        "https://example.com/pricing",
        "Our demo plan costs $10 per month.",
    )

    assert "The demo product costs $10 per month." in prompt
    assert "https://example.com/pricing" in prompt
    assert "Our demo plan costs $10 per month." in prompt

    # Verdict words appear only in the fixed answer template; none of the
    # ledger/prior-result fields are handed to the judge.
    blind = verify_facts.build_prompt("", "", "", "")
    for token in ("verified", "unsupported", "inconclusive", "status"):
        assert prompt.count(token) == blind.count(token)
    for field in ("checked_at", "snapshot_path", "carried_forward", "generated_at", "verified_on"):
        assert field not in prompt

    params = set(inspect.signature(verify_facts.build_prompt).parameters)
    assert params == {"claim", "scope", "source_label", "source_text"}


def test_numeric_cross_check_keeps_verified_when_a_claim_price_matches_jsonld(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    entry = make_entry(claim="The demo product costs $10 per month.")
    config = write_config(tmp_path, [entry])
    monkeypatch.setattr(
        verify_facts, "fetch_url",
        lambda url: (
            '<html><head><script type="application/ld+json">'
            '{"@type": "Product", "offers": {"@type": "Offer", "price": "10.00"}}'
            "</script></head><body>Our demo plan costs $10 per month.</body></html>",
            200,
        ),
    )
    monkeypatch.setattr(verify_facts, "call_llm", lambda *a, **k: llm_json("verified", quotes=["costs $10 per month"]))

    assert verify_facts.main(["--config", str(config)]) == 0
    assert read_ledger(tmp_path)["results"][0]["status"] == "verified"


def test_numeric_cross_check_demotes_verified_when_no_claim_price_matches_jsonld(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    entry = make_entry(claim="The demo product costs $1,000 per month.")
    config = write_config(tmp_path, [entry])
    monkeypatch.setattr(
        verify_facts, "fetch_url",
        lambda url: (
            '<html><head><script type="application/ld+json">'
            '{"@type": "Offer", "price": "50"}'
            "</script></head><body>The demo product costs $50 per month.</body></html>",
            200,
        ),
    )
    monkeypatch.setattr(verify_facts, "call_llm", lambda *a, **k: llm_json("verified", quotes=["costs $50 per month"]))

    assert verify_facts.main(["--config", str(config)]) == 0
    result = read_ledger(tmp_path)["results"][0]
    assert result["status"] == "inconclusive"
    assert any("numeric cross-check" in note for note in result["missing_aspects"])


def test_numeric_cross_check_ignores_sources_without_structured_prices(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_facts, "REPO_ROOT", str(tmp_path))
    entry = make_entry(claim="The demo product costs $1,000 per month.")
    config = write_config(tmp_path, [entry])
    monkeypatch.setattr(
        verify_facts, "fetch_url",
        lambda url: ("<html><body>The demo product costs $1,000 per month.</body></html>", 200),
    )
    monkeypatch.setattr(
        verify_facts, "call_llm", lambda *a, **k: llm_json("verified", quotes=["costs $1,000 per month"])
    )

    assert verify_facts.main(["--config", str(config)]) == 0
    assert read_ledger(tmp_path)["results"][0]["status"] == "verified"


def test_jsonld_offer_prices_reads_nested_offers_and_ignores_microdata():
    source = verify_facts.html_to_text(
        '<html><head><script type="application/ld+json">'
        '{"@type": "Product", "offers": {"price": "1,750"}, "priceRange": "$$-$$$"}'
        "</script></head><body>"
        '<div itemprop="price" content="$2,500">two thousand five hundred</div>'
        "</body></html>"
    )

    assert verify_facts.jsonld_offer_prices(source) == {1750.0}
    assert verify_facts.currency_amounts("$1,000 and $1,750.50") == {1000.0, 1750.5}
    assert verify_facts.numeric_mismatch("Costs $2,500.", source) is not None
    assert verify_facts.numeric_mismatch("Costs $1,750.", source) is None
