import json
import urllib.error
from email.message import Message

import pytest

from collect_authority import (
    BATCH_SIZE,
    DEFAULT_PLATFORM_HOSTS,
    ENDPOINT,
    OpenPageRankError,
    classify_platform,
    clean_host,
    collect_authority,
    domain_stem,
    hosts_from_serp_payload,
    is_platform_hosted,
    load_authority_artifacts,
    platform_hosts_from_config,
    registrable_domain,
    request_open_pagerank,
    summarize_authority,
)

SECRET = "opr_live_test_SECRET_do_not_leak"


def fake_provider(scores, calls, *, omit=(), as_of="2026-09-01"):
    """A request_fn double: scores maps domain -> score; ``omit`` is never returned."""

    def request(domains, api_key, **kwargs):
        calls.append(list(domains))
        results = []
        for domain in domains:
            if domain in omit:
                continue
            if domain in scores:
                results.append(
                    {
                        "domain": domain,
                        "found": True,
                        "open_page_rank": scores[domain],
                        "referring_domains": 7,
                        "rank": 1234,
                    }
                )
            else:
                results.append(
                    {"domain": domain, "found": False, "open_page_rank": None}
                )
        return {"as_of": as_of, "count": len(results), "results": results}

    return request


def run(hosts, scores, tmp_path, calls=None, **kwargs):
    calls = [] if calls is None else calls
    omit = kwargs.pop("omit", ())
    return collect_authority(
        hosts,
        SECRET,
        cache_dir=tmp_path / "cache",
        request_fn=fake_provider(scores, calls, omit=omit),
        sleep=lambda _seconds: None,
        **kwargs,
    )


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def http_error(code):
    return urllib.error.HTTPError(ENDPOINT, code, "err", Message(), None)


def test_host_helpers_handle_www_multi_label_suffixes_and_junk():
    assert clean_host("WWW.Example.COM.") == "example.com"
    assert clean_host("not a host") is None
    assert clean_host("localhost") is None
    assert clean_host(None) is None
    assert registrable_domain("community.weddingwire.ca") == "weddingwire.ca"
    assert registrable_domain("a.b.example.co.uk") == "example.co.uk"
    assert registrable_domain("studio.example.com.bb") == "example.com.bb"
    assert registrable_domain("example.com.bb") == "example.com.bb"
    assert domain_stem("tripadvisor.ie") == "tripadvisor"
    assert is_platform_hosted("buxton.mypixieset.com")
    assert not is_platform_hosted("mypixieset.com")
    assert not is_platform_hosted("notmypixieset.com")


def test_platform_classification_matches_stems_and_honors_config_override():
    assert classify_platform("tripadvisor.ie", DEFAULT_PLATFORM_HOSTS) == "directory"
    assert classify_platform("tripadvisor.ca", DEFAULT_PLATFORM_HOSTS) == "directory"
    assert classify_platform("jsobersphotography.com", DEFAULT_PLATFORM_HOSTS) is None
    assert (
        classify_platform("pubhtml5.com", DEFAULT_PLATFORM_HOSTS) == "document_hosting"
    )
    assert platform_hosts_from_config({}) == DEFAULT_PLATFORM_HOSTS
    override = platform_hosts_from_config(
        {"research": {"authority": {"platform_hosts": ["Brides", " easyweddings "]}}}
    )
    assert override == {"brides": "platform", "easyweddings": "platform"}
    assert classify_platform("brides.com", override) == "platform"
    assert classify_platform("facebook.com", override) is None
    with pytest.raises(ValueError):
        platform_hosts_from_config({"research": {"authority": {"platform_hosts": "x"}}})


def test_scores_are_recorded_with_provider_date_and_no_difficulty_claim(tmp_path):
    result = run(
        ["www.alpha.com", "beta.com"], {"alpha.com": 3.8, "beta.com": 0.09}, tmp_path
    )

    assert result["schema_version"] == "article-forge.authority.v1"
    assert result["provider_as_of"] == "2026-09-01"
    assert result["semantics"] == "link_graph_authority_proxy"
    assert "not Moz DA" in result["limitation"]
    alpha = result["domains"]["alpha.com"]
    assert alpha["status"] == "scored"
    assert alpha["open_page_rank"] == 3.8
    assert alpha["referring_domains"] == 7
    assert result["domains"]["beta.com"]["open_page_rank"] == 0.09
    assert "difficulty" not in json.dumps(result).replace("keyword difficulty", "")


def test_missing_subdomain_falls_back_to_a_labelled_scored_parent(tmp_path):
    calls = []
    result = run(
        ["community.weddingwire.ca"],
        {"weddingwire.ca": 7.1},
        tmp_path,
        calls,
    )

    entry = result["domains"]["community.weddingwire.ca"]
    assert entry["status"] == "scored_via_parent"
    assert entry["resolved_domain"] == "weddingwire.ca"
    assert entry["open_page_rank"] == 7.1
    assert calls == [["community.weddingwire.ca"], ["weddingwire.ca"]]


def test_unfound_and_omitted_domains_are_unscored_never_zero(tmp_path):
    result = run(
        ["gone.example.com", "silent.io"],
        {},
        tmp_path,
        omit={"silent.io"},
    )

    for host in ("gone.example.com", "silent.io"):
        assert result["domains"][host]["status"] == "unscored"
        assert result["domains"][host]["open_page_rank"] is None


def test_platform_hosted_tenants_are_never_sent_or_scored(tmp_path):
    calls = []
    result = run(
        ["buxton.mypixieset.com", "real.com"],
        {"real.com": 1.5, "mypixieset.com": 6.0},
        tmp_path,
        calls,
    )

    tenant = result["domains"]["buxton.mypixieset.com"]
    assert tenant["status"] == "platform_hosted_unscored"
    assert tenant["open_page_rank"] is None
    assert calls == [["real.com"]]


def test_invalid_hosts_are_reported_and_not_sent(tmp_path):
    calls = []
    result = run(["ok.com", "bad host", ""], {"ok.com": 1.0}, tmp_path, calls)

    assert [item["host"] for item in result["errors"]] == ["bad host", ""]
    assert calls == [["ok.com"]]
    with pytest.raises(OpenPageRankError):
        run(["bad host"], {}, tmp_path)


def test_hosts_are_batched_and_capped(tmp_path):
    hosts = [f"site{index}.com" for index in range(BATCH_SIZE + 50)]
    calls = []
    result = run(hosts, {}, tmp_path, calls, max_domains=500)

    assert [len(batch) for batch in calls] == [BATCH_SIZE, 50]
    assert result["request_budget"]["api_requests"] == 2
    with pytest.raises(OpenPageRankError, match="max_domains_per_run"):
        run(hosts, {}, tmp_path / "other", max_domains=10)


def test_cache_serves_repeat_runs_including_misses(tmp_path):
    calls = []
    first = run(["hit.com", "miss.com"], {"hit.com": 2.0}, tmp_path, calls)
    second = run(["hit.com", "miss.com"], {"hit.com": 2.0}, tmp_path, calls)

    assert len(calls) == 1
    assert first["request_budget"]["api_requests"] == 1
    assert second["request_budget"] == {
        **second["request_budget"],
        "api_requests": 0,
        "cache_hits": 2,
    }
    assert second["domains"]["hit.com"]["open_page_rank"] == 2.0
    assert second["domains"]["miss.com"]["status"] == "unscored"

    run(["hit.com"], {"hit.com": 2.5}, tmp_path, calls, refresh=True)
    assert len(calls) == 2


def test_expired_cache_is_refetched(tmp_path):
    calls = []
    run(["hit.com"], {"hit.com": 2.0}, tmp_path, calls)
    run(["hit.com"], {"hit.com": 2.0}, tmp_path, calls, cache_ttl_seconds=-1)

    assert len(calls) == 2


def test_api_key_never_reaches_output_or_cache(tmp_path):
    result = run(["alpha.com"], {"alpha.com": 3.0}, tmp_path)

    assert SECRET not in json.dumps(result)
    for path in (tmp_path / "cache").glob("*.json"):
        assert SECRET not in path.read_text(encoding="utf-8")


def test_request_sends_bearer_header_and_bulk_body():
    seen = {}

    def open_url(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["body"] = json.loads(request.data)
        return FakeResponse({"as_of": "2026-09-01", "results": []})

    request_open_pagerank(["a.com", "b.com"], SECRET, open_url=open_url)

    assert seen["url"] == ENDPOINT
    assert seen["auth"] == f"Bearer {SECRET}"
    assert seen["body"] == {"domains": ["a.com", "b.com"]}


@pytest.mark.parametrize("code", [401, 402, 403, 429])
def test_terminal_http_errors_are_not_retried_and_hide_the_key(code):
    attempts = []

    def open_url(request, timeout):
        attempts.append(code)
        raise http_error(code)

    with pytest.raises(OpenPageRankError) as caught:
        request_open_pagerank(
            ["a.com"], SECRET, open_url=open_url, sleep=lambda _seconds: None
        )

    assert len(attempts) == 1
    assert SECRET not in str(caught.value)
    assert str(code) in str(caught.value)


def test_server_errors_retry_then_succeed():
    outcomes = [http_error(503), http_error(500)]
    sleeps = []

    def open_url(request, timeout):
        if outcomes:
            raise outcomes.pop(0)
        return FakeResponse({"as_of": "2026-09-01", "results": []})

    payload = request_open_pagerank(
        ["a.com"], SECRET, open_url=open_url, sleep=sleeps.append
    )

    assert payload["as_of"] == "2026-09-01"
    assert len(sleeps) == 2


def test_server_errors_stop_after_the_retry_budget():
    attempts = []

    def open_url(request, timeout):
        attempts.append(1)
        raise http_error(502)

    with pytest.raises(OpenPageRankError, match="HTTP 502"):
        request_open_pagerank(
            ["a.com"],
            SECRET,
            open_url=open_url,
            max_retries=2,
            sleep=lambda _seconds: None,
        )
    assert len(attempts) == 3


def test_malformed_provider_payload_is_rejected():
    def open_url(request, timeout):
        return FakeResponse({"results": "nope"})

    with pytest.raises(OpenPageRankError, match="unexpected response"):
        request_open_pagerank(["a.com"], SECRET, open_url=open_url)


def test_serp_hosts_load_from_collections_and_records_only():
    record = {
        "schema_version": "article-forge.serp.v1",
        "organic": [{"host": "a.com"}, {"host": "b.com"}, {"title": "no host"}],
    }
    collection = {
        "schema_version": "article-forge.serp-collection.v1",
        "records": [record, {**record, "organic": [{"host": "c.com"}]}],
    }

    assert hosts_from_serp_payload(record) == ["a.com", "b.com"]
    assert hosts_from_serp_payload(collection) == ["a.com", "b.com", "c.com"]
    with pytest.raises(ValueError, match="unsupported"):
        hosts_from_serp_payload({"schema_version": "other"})


def test_authority_artifacts_round_trip_and_reject_other_schemas(tmp_path):
    artifact = run(["a.com"], {"a.com": 1.0}, tmp_path)
    older = {**artifact, "provider_as_of": "2026-08-01"}
    first = tmp_path / "one.json"
    second = tmp_path / "two.json"
    first.write_text(json.dumps(artifact), encoding="utf-8")
    second.write_text(json.dumps(older), encoding="utf-8")
    loaded = load_authority_artifacts([first, second])

    assert loaded["domains"]["a.com"]["open_page_rank"] == 1.0
    assert loaded["provider_as_of"] == "2026-09-01"
    assert len(loaded["sources"]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": "x"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_authority_artifacts([bad])


def serp_row(position, host):
    return {"position": position, "host": host}


def test_summary_separates_platforms_from_independents_and_finds_own_position(
    tmp_path,
):
    authority = run(
        [
            "facebook.com",
            "tripadvisor.ie",
            "small.com",
            "bigger.com",
            "community.weddingwire.ca",
            "jsobersphotography.com",
            "missing.com",
        ],
        {
            "facebook.com": 9.96,
            "tripadvisor.ie": 7.47,
            "small.com": 0.09,
            "bigger.com": 3.4,
            "weddingwire.ca": 7.1,
            "jsobersphotography.com": 0.09,
        },
        tmp_path,
    )
    organic = [
        serp_row(1, "facebook.com"),
        serp_row(2, "tripadvisor.ie"),
        serp_row(3, "www.jsobersphotography.com"),
        serp_row(4, "small.com"),
        serp_row(5, "bigger.com"),
        serp_row(6, "facebook.com"),
        serp_row(7, "missing.com"),
        serp_row(8, "jsobersphotography.com"),
        serp_row(9, "never-collected.com"),
    ]

    summary = summarize_authority(
        organic, authority, own_domain="jsobersphotography.com"
    )

    assert summary["own_domain"] == {
        "domain": "jsobersphotography.com",
        "best_position": 3,
    }
    assert [item["host"] for item in summary["platforms"]["hosts"]] == [
        "facebook.com",
        "tripadvisor.ie",
    ]
    assert summary["platforms"]["hosts"][1]["platform_type"] == "directory"
    independent = summary["independent"]
    assert [item["host"] for item in independent["hosts"]] == [
        "small.com",
        "bigger.com",
        "missing.com",
        "never-collected.com",
    ]
    assert independent["count"] == 4
    assert independent["scored_count"] == 2
    assert independent["unscored_count"] == 2
    assert independent["median"] == pytest.approx(1.745, abs=0.01)
    assert independent["max"] == 3.4
    assert independent["strongest_host"] == "bigger.com"
    assert independent["hosts"][3]["status"] == "not_collected"
    assert independent["hosts"][2]["open_page_rank"] is None
    assert summary["semantics"] == "link_graph_authority_proxy"
    assert "difficulty" not in {key for key in summary}


def test_summary_marks_parent_resolved_hosts_and_honors_platform_override(tmp_path):
    authority = run(
        ["community.weddingwire.ca", "brides.com"],
        {"weddingwire.ca": 7.1, "brides.com": 7.95},
        tmp_path,
    )
    organic = [serp_row(1, "community.weddingwire.ca"), serp_row(2, "brides.com")]

    summary = summarize_authority(
        organic, authority, platform_hosts={"brides": "publisher"}
    )

    assert summary["platforms"]["hosts"][0]["host"] == "brides.com"
    assert summary["platforms"]["hosts"][0]["platform_type"] == "publisher"
    row = summary["independent"]["hosts"][0]
    assert row["status"] == "scored_via_parent"
    assert row["resolved_domain"] == "weddingwire.ca"


def test_summary_without_scores_reports_none_not_zero():
    summary = summarize_authority(
        [serp_row(1, "a.com")], {"domains": {}, "provider_as_of": None}
    )

    assert summary["independent"]["median"] is None
    assert summary["independent"]["max"] is None
    assert summary["independent"]["strongest_host"] is None
    assert summary["own_domain"]["best_position"] is None
