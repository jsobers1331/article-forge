import json
import sys
from argparse import Namespace
from datetime import date

import httplib2
import pytest
from googleapiclient.errors import HttpError

import check_indexing as module
from check_indexing import (
    IndexingConfigError,
    build_stamped_dates,
    check_indexing,
    classify,
    load_entries,
    parse_date,
    parse_sitemap,
)

SITE = "sc-domain:example.com"
TODAY = date(2026, 10, 8)


class FakeRequest:
    def __init__(self, outcome):
        self.outcome = outcome

    def execute(self):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FakeService:
    """Mimics service.urlInspection().index().inspect(body=...).execute()."""

    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.bodies = []

    def urlInspection(self):  # noqa: N802 - mirrors the Google client API
        return self

    def index(self):
        return self

    def inspect(self, body):
        self.bodies.append(body)
        return FakeRequest(self.outcomes[body["inspectionUrl"]])


def inspection(url, *, verdict="PASS", coverage="Submitted and indexed", **overrides):
    status = {
        "verdict": verdict,
        "coverageState": coverage,
        "indexingState": "INDEXING_ALLOWED",
        "robotsTxtState": "ALLOWED",
        "pageFetchState": "SUCCESSFUL",
        "lastCrawlTime": "2026-10-01T00:00:00Z",
        "googleCanonical": url,
        "userCanonical": url,
    }
    status.update(overrides)
    return {"inspectionResult": {"indexStatusResult": status}}


def api_error(code):
    response = httplib2.Response({"status": str(code), "reason": "test"})
    return HttpError(response, json.dumps({"error": {"message": "boom"}}).encode())


def run(entries, outcomes, **kwargs):
    service = FakeService(outcomes)
    kwargs.setdefault("today", TODAY)
    return check_indexing(service, SITE, entries, **kwargs), service


def entry(url, lastmod="2026-09-01"):
    return {"url": url, "lastmod": lastmod}


def fields(**overrides):
    base = {
        "url": "https://example.com/a",
        "verdict": "PASS",
        "coverage_state": "Submitted and indexed",
        "indexing_state": "INDEXING_ALLOWED",
        "robots_txt_state": "ALLOWED",
        "page_fetch_state": "SUCCESSFUL",
        "last_crawl_date": date(2026, 10, 1),
        "google_canonical": "https://example.com/a",
        "user_canonical": "https://example.com/a",
    }
    base.update(overrides)
    return base


def classify_with(lastmod=date(2026, 9, 1), **overrides):
    return classify(
        fields(**overrides),
        lastmod=lastmod,
        today=TODAY,
        grace_days=14,
        stale_days=14,
    )


def test_parse_date_accepts_dates_and_iso_timestamps_only():
    assert parse_date("2026-09-04") == date(2026, 9, 4)
    assert parse_date("2026-10-08T04:39:55.027Z") == date(2026, 10, 8)
    assert parse_date("2026-08-11T15:47:05+00:00") == date(2026, 8, 11)
    assert parse_date("last month") is None
    assert parse_date("") is None
    assert parse_date(None) is None


def test_sitemap_urlset_drops_image_urls_and_keeps_lastmod():
    xml = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/</loc><lastmod>2026-10-08T00:00:00.000Z</lastmod></url>
      <url><loc>https://example.com/blog/a</loc></url>
      <url><loc>https://res.example.com/hero.JPG?v=1</loc></url>
    </urlset>"""

    assert parse_sitemap(xml) == [
        {"url": "https://example.com/", "lastmod": "2026-10-08T00:00:00.000Z"},
        {"url": "https://example.com/blog/a", "lastmod": None},
    ]


def test_sitemap_index_follows_children_once():
    index = """<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://example.com/one.xml</loc></sitemap>
      <sitemap><loc>https://example.com/two.xml</loc></sitemap>
    </sitemapindex>"""
    child = (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://example.com/{}</loc></url></urlset>"
    )
    pages = {
        "https://example.com/one.xml": child.format("a"),
        "https://example.com/two.xml": child.format("b"),
    }

    entries = parse_sitemap(index, fetch=pages.__getitem__)

    assert [item["url"] for item in entries] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    nested = '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://example.com/one.xml</loc></sitemap></sitemapindex>'
    with pytest.raises(IndexingConfigError, match="nested"):
        parse_sitemap(index, fetch=lambda url: nested)


def test_sitemap_rejects_bad_xml_and_unknown_roots():
    with pytest.raises(IndexingConfigError, match="not valid XML"):
        parse_sitemap("<urlset>")
    with pytest.raises(IndexingConfigError, match="unexpected sitemap root"):
        parse_sitemap("<html/>")


def test_indexed_page_has_no_flags():
    status, flags, note = classify_with()

    assert (status, flags) == ("indexed", [])
    assert note == "Submitted and indexed"


def test_unindexed_page_is_pending_inside_grace_and_not_indexed_after():
    pending = classify_with(
        lastmod=date(2026, 10, 1),
        verdict="NEUTRAL",
        coverage_state="Discovered - currently not indexed",
        last_crawl_date=None,
    )
    overdue = classify_with(
        lastmod=date(2026, 9, 1),
        verdict="NEUTRAL",
        coverage_state="Discovered - currently not indexed",
        last_crawl_date=None,
    )

    assert pending[0] == "pending"
    assert "never_crawled" not in pending[1]
    assert "grace period" in pending[2]
    assert overdue[0] == "not_indexed"
    assert "never_crawled" in overdue[1]


def test_missing_lastmod_never_hides_an_unindexed_page():
    status, flags, _ = classify_with(
        lastmod=None, verdict="NEUTRAL", last_crawl_date=None
    )

    assert status == "not_indexed"
    assert "never_crawled" in flags


def test_stale_crawl_needs_a_real_gap_between_crawl_and_lastmod():
    just_inside = classify_with(
        lastmod=date(2026, 8, 12), last_crawl_date=date(2026, 7, 29)
    )
    outside = classify_with(
        lastmod=date(2026, 8, 12), last_crawl_date=date(2026, 7, 28)
    )

    assert "stale_crawl" not in just_inside[1]
    assert "stale_crawl" in outside[1]
    assert "stale_crawl" not in classify_with(lastmod=None)[1]


def test_canonical_flags_ignore_trailing_slash_but_catch_host_changes():
    slash = classify_with(
        url="https://example.com/a",
        google_canonical="https://example.com/a/",
        user_canonical="https://example.com/a/",
    )
    other_host = classify_with(
        verdict="NEUTRAL",
        coverage_state="Alternate page with proper canonical tag",
        url="https://www.example.com/a",
        google_canonical="https://example.com/a",
        user_canonical="https://example.com/a",
    )
    disagrees = classify_with(
        google_canonical="https://www.example.com/a",
        user_canonical="https://example.com/a",
    )

    assert slash[1] == []
    assert other_host[1] == ["google_chose_other_canonical"]
    assert "declared_canonical_disagrees" in disagrees[1]


def test_fetch_and_blocking_problems_are_flagged():
    fetch = classify_with(page_fetch_state="SOFT_404")
    meta = classify_with(indexing_state="BLOCKED_BY_META_TAG")
    robots = classify_with(robots_txt_state="DISALLOWED")

    assert "fetch_problem" in fetch[1]
    assert "indexing_blocked" in meta[1]
    assert "indexing_blocked" in robots[1]


def test_check_indexing_summarizes_orders_and_dedupes():
    entries = [
        entry("https://example.com/ok"),
        entry("https://example.com/missing"),
        entry("https://example.com/ok/"),
        entry("https://example.com/new", lastmod="2026-10-06"),
    ]
    outcomes = {
        "https://example.com/ok": inspection("https://example.com/ok"),
        "https://example.com/missing": inspection(
            "https://example.com/missing",
            verdict="NEUTRAL",
            coverage="Discovered - currently not indexed",
            lastCrawlTime=None,
        ),
        "https://example.com/new": inspection(
            "https://example.com/new",
            verdict="NEUTRAL",
            coverage="URL is unknown to Google",
            lastCrawlTime=None,
        ),
    }

    artifact, service = run(entries, outcomes)

    assert artifact["schema_version"] == "article-forge.indexing.v1"
    assert artifact["summary"]["total"] == 3
    assert artifact["summary"]["by_status"] == {
        "not_indexed": 1,
        "pending": 1,
        "indexed": 1,
    }
    assert [r["status"] for r in artifact["records"]] == [
        "not_indexed",
        "pending",
        "indexed",
    ]
    assert artifact["summary"]["by_flag"] == {"never_crawled": 1}
    assert artifact["request_budget"]["inspected"] == 3
    assert len(service.bodies) == 3
    assert service.bodies[0] == {
        "inspectionUrl": "https://example.com/ok",
        "siteUrl": SITE,
    }
    assert "not a ranking" in artifact["semantics"]


def test_a_failing_url_is_recorded_and_the_run_continues():
    outcomes = {
        "https://example.com/a": api_error(500),
        "https://example.com/b": inspection("https://example.com/b"),
    }

    artifact, _ = run(
        [entry("https://example.com/a"), entry("https://example.com/b")], outcomes
    )

    by_url = {r["url"]: r for r in artifact["records"]}
    assert by_url["https://example.com/a"]["status"] == "error"
    assert "HTTP 500" in by_url["https://example.com/a"]["note"]
    assert by_url["https://example.com/b"]["status"] == "indexed"
    assert artifact["request_budget"] == {
        **artifact["request_budget"],
        "inspected": 1,
        "errors": 1,
    }


def test_quota_error_stops_further_calls():
    urls = [f"https://example.com/{n}" for n in range(4)]
    outcomes = {urls[0]: api_error(429)}
    outcomes.update({url: inspection(url) for url in urls[1:]})

    artifact, service = run([entry(url) for url in urls], outcomes)

    assert len(service.bodies) == 1
    assert [r["status"] for r in artifact["records"]] == ["error"] * 4
    assert any("quota" in r["note"] for r in artifact["records"])


def test_repeated_failures_open_the_circuit_breaker():
    urls = [f"https://example.com/{n}" for n in range(5)]
    outcomes = {url: api_error(500) for url in urls}

    artifact, service = run([entry(url) for url in urls], outcomes)

    assert len(service.bodies) == 3
    assert sum("repeated API failures" in r["note"] for r in artifact["records"]) == 2


def test_result_without_index_status_is_an_error_not_a_pass():
    artifact, _ = run([entry("https://example.com/a")], {"https://example.com/a": {}})

    record = artifact["records"][0]
    assert record["status"] == "error"
    assert "inside the property" in record["note"]


def test_run_size_is_bounded_by_config_and_google_quota():
    urls = [entry(f"https://example.com/{n}") for n in range(3)]

    with pytest.raises(IndexingConfigError, match="refusing 3 URLs"):
        run(urls, {}, max_urls=2)
    with pytest.raises(IndexingConfigError, match="between 1 and 2000"):
        run(urls, {}, max_urls=2001)
    with pytest.raises(IndexingConfigError, match="no page URLs"):
        run([], {})
    with pytest.raises(IndexingConfigError, match="negative"):
        run(urls, {}, grace_days=-1)


def test_delay_is_applied_between_calls_only():
    urls = [f"https://example.com/{n}" for n in range(3)]
    outcomes = {url: inspection(url) for url in urls}
    sleeps = []

    run([entry(url) for url in urls], outcomes, delay=0.5, sleep=sleeps.append)

    assert sleeps == [0.5, 0.5]


def args(**overrides):
    base = {
        "sitemap": None,
        "url": None,
        "urls_file": None,
        "path_prefix": None,
    }
    base.update(overrides)
    return Namespace(**base)


SITEMAP = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/</loc></url>
  <url><loc>https://example.com/blog/a</loc><lastmod>2026-09-04</lastmod></url>
</urlset>"""


def test_load_entries_defaults_to_the_domain_sitemap():
    seen = []

    def fetch(url):
        seen.append(url)
        return SITEMAP

    entries = load_entries(args(), {"domain": "example.com"}, fetch=fetch)

    assert seen == ["https://example.com/sitemap.xml"]
    assert len(entries) == 2
    with pytest.raises(IndexingConfigError, match="no domain"):
        load_entries(args(), {}, fetch=fetch)


def test_load_entries_merges_sources_and_filters_by_prefix(tmp_path):
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text(
        "# comment\nhttps://example.com/blog/b 2026-10-01\n\nhttps://example.com/about\n",
        encoding="utf-8",
    )

    entries = load_entries(
        args(
            sitemap="https://example.com/sitemap.xml",
            url=["https://example.com/blog/c"],
            urls_file=str(urls_file),
            path_prefix="/blog/",
        ),
        {},
        fetch=lambda url: SITEMAP,
    )

    assert {e["url"]: e["lastmod"] for e in entries} == {
        "https://example.com/blog/a": "2026-09-04",
        "https://example.com/blog/c": None,
        "https://example.com/blog/b": "2026-10-01",
    }
    with pytest.raises(IndexingConfigError, match="absolute"):
        load_entries(args(url=["/relative"]), {}, fetch=lambda url: SITEMAP)


def test_print_report_lists_only_pages_that_need_attention(capsys):
    outcomes = {
        "https://example.com/ok": inspection("https://example.com/ok"),
        "https://example.com/bad": inspection(
            "https://example.com/bad",
            verdict="NEUTRAL",
            coverage="Discovered - currently not indexed",
            lastCrawlTime=None,
        ),
    }
    artifact, _ = run(
        [entry("https://example.com/ok"), entry("https://example.com/bad")], outcomes
    )

    module.print_report(artifact)

    output = capsys.readouterr().out
    assert "not_indexed=1" in output
    assert "https://example.com/bad" in output
    assert "https://example.com/ok" not in output


def test_cli_exits_2_for_a_config_problem_before_touching_credentials(
    tmp_path, monkeypatch
):
    config = tmp_path / "site-config.example.json"
    config.write_text(json.dumps({"domain": "example.com"}), encoding="utf-8")
    existing = tmp_path / "indexing.json"
    existing.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(module, "fetch_text", lambda url, **kw: SITEMAP)
    monkeypatch.setattr(
        module, "get_credentials", lambda: pytest.fail("credentials must not load")
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["check_indexing.py", "--config", str(config), "--out", str(existing)],
    )

    with pytest.raises(SystemExit) as caught:
        module.main()

    assert caught.value.code == 2


def test_unspecified_google_states_mean_no_data_not_a_problem():
    status, flags, _ = classify_with(
        verdict="NEUTRAL",
        coverage_state="Discovered - currently not indexed",
        last_crawl_date=None,
        page_fetch_state="PAGE_FETCH_STATE_UNSPECIFIED",
        indexing_state="INDEXING_STATE_UNSPECIFIED",
        robots_txt_state="ROBOTS_TXT_STATE_UNSPECIFIED",
    )

    assert status == "not_indexed"
    assert flags == ["never_crawled"]


def test_build_stamped_dates_need_both_a_count_and_a_share():
    stamped = [entry(f"https://example.com/p{n}", "2026-09-27") for n in range(6)]
    honest = [entry(f"https://example.com/b{n}", f"2026-08-0{n + 1}") for n in range(4)]

    assert build_stamped_dates(stamped + honest) == {date(2026, 9, 27)}
    # Below the minimum count of 5.
    assert build_stamped_dates(stamped[:4] + honest) == set()
    # Five URLs, but only 20% of 25 dated URLs.
    spread = [
        entry(f"https://example.com/x{n}", f"2026-07-{n + 1:02d}") for n in range(20)
    ]
    assert build_stamped_dates(spread + stamped[:5]) == set()
    # Undated entries do not count toward the share.
    assert build_stamped_dates([entry("https://example.com/n", None)]) == set()


def test_a_build_stamp_is_ignored_while_honest_dates_still_count():
    stamped = [entry(f"https://example.com/p{n}", "2026-10-07") for n in range(5)]
    honest = entry("https://example.com/blog/a", "2026-09-01")
    entries = stamped + [honest]
    outcomes = {
        e["url"]: inspection(e["url"], lastCrawlTime="2026-08-01T00:00:00Z")
        for e in entries
    }
    # Trusting the stamp, this page would be "pending" (modified yesterday).
    outcomes[stamped[0]["url"]] = inspection(
        stamped[0]["url"],
        verdict="NEUTRAL",
        coverage="Discovered - currently not indexed",
        lastCrawlTime=None,
    )

    artifact, _ = run(entries, outcomes)

    by_url = {r["url"]: r for r in artifact["records"]}
    assert len(artifact["warnings"]) == 1
    assert "5 URLs share lastmod 2026-10-07" in artifact["warnings"][0]
    assert by_url[stamped[0]["url"]]["status"] == "not_indexed"
    assert by_url[stamped[0]["url"]]["lastmod_reliable"] is False
    assert "stale_crawl" not in by_url[stamped[1]["url"]]["flags"]
    assert "stale_crawl" in by_url["https://example.com/blog/a"]["flags"]
    assert by_url["https://example.com/blog/a"]["lastmod_reliable"] is True


def test_runs_without_a_build_stamp_carry_no_warnings():
    artifact, _ = run(
        [entry("https://example.com/a")],
        {"https://example.com/a": inspection("https://example.com/a")},
    )

    assert artifact["warnings"] == []
