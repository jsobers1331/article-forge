"""Check whether published pages are indexed, via Search Console URL Inspection.

Impressions cannot exist for a page Google has not indexed, so indexation is the
first thing to verify after publishing. This reads each page's index status from
the read-only URL Inspection API (the same ``webmasters.readonly`` login that
``collect_search_console.py`` uses) and flags what needs attention.

It reports observations from Google; it does not request indexing (the API cannot)
and it does not predict ranking. Page URLs come from a sitemap (``<lastmod>`` gives
the page's age) and/or explicit ``--url`` / ``--urls-file`` entries.

``lastmod`` is a modification date, not a publish date, and is only as honest as the
site that emits it. A date shared by many URLs looks like a build timestamp, so it is
ignored (with a warning in the artifact) instead of flagging every static page.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect_search_console import (  # noqa: E402
    _atomic_write_json,
    _property_from_config,
    get_credentials,
)

SCHEMA_VERSION = "article-forge.indexing.v1"
SOURCE = "search_console_url_inspection"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GRACE_DAYS = 14
DEFAULT_STALE_DAYS = 14
DEFAULT_MAX_URLS = 200
# Google's documented URL Inspection limits are per site: 2,000/day and 600/minute.
DAILY_QUOTA_PER_SITE = 2000
MAX_CONSECUTIVE_FAILURES = 3
MAX_CHILD_SITEMAPS = 10
# A lastmod shared by at least this many URLs and this share of the dated URLs is
# treated as a build timestamp, not a modification date (see build_stamped_dates).
MIN_SHARED_LASTMOD = 5
SHARED_LASTMOD_SHARE = 0.25
SITEMAP_TIMEOUT_SECONDS = 30
IMAGE_URL = re.compile(r"\.(?:jpe?g|png|webp|gif|avif|svg)(?:\?|$)", re.IGNORECASE)
# Statuses a reviewer acts on, in the order they are listed in the report.
STATUS_ORDER = ("not_indexed", "error", "pending", "indexed")


class IndexingConfigError(ValueError):
    """A problem with the request itself (exit code 2), not with a page."""


def _fail(message):
    """Exit 2 for a config or credential problem; flagged pages still exit 0."""
    print(message, file=sys.stderr)
    raise SystemExit(2)


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def parse_date(value):
    """``YYYY-MM-DD`` or an ISO-8601 timestamp (with optional ``Z``) -> date."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_sitemap(xml_text, *, fetch=None, _depth=0):
    """Return ``[{"url", "lastmod"}]`` from a urlset, following a sitemap index once."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise IndexingConfigError(f"sitemap is not valid XML: {exc}") from exc
    entries = []
    kind = _tag(root)
    if kind == "urlset":
        for node in root:
            if _tag(node) != "url":
                continue
            fields = {_tag(child): (child.text or "").strip() for child in node}
            loc = fields.get("loc")
            if loc and not IMAGE_URL.search(loc):
                entries.append({"url": loc, "lastmod": fields.get("lastmod") or None})
    elif kind == "sitemapindex":
        if fetch is None or _depth >= 1:
            raise IndexingConfigError("nested sitemap indexes are not supported")
        children = [
            (child.text or "").strip()
            for node in root
            if _tag(node) == "sitemap"
            for child in node
            if _tag(child) == "loc" and (child.text or "").strip()
        ]
        for child_url in children[:MAX_CHILD_SITEMAPS]:
            entries.extend(
                parse_sitemap(fetch(child_url), fetch=fetch, _depth=_depth + 1)
            )
    else:
        raise IndexingConfigError(f"unexpected sitemap root element <{kind}>")
    return entries


def fetch_text(url, *, timeout=SITEMAP_TIMEOUT_SECONDS):
    request = urllib.request.Request(
        url, headers={"User-Agent": "article-forge-indexing-check"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
        raise IndexingConfigError(f"could not fetch {url}: {exc}") from exc


def _normalize_url(value):
    if not isinstance(value, str) or not value:
        return ""
    parts = urlsplit(value.strip())
    path = parts.path.rstrip("/") or "/"
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{path}{query}"


def classify(fields, *, lastmod, today, grace_days, stale_days):
    """Turn one inspection result into ``(status, flags, note)``.

    ``pending`` means not indexed yet but still inside the grace period after
    ``lastmod``; ``not_indexed`` means the grace period has passed. A missing
    ``lastmod`` never hides a problem: the age is unknown, so it is treated as
    outside the grace period.
    """
    flags = []
    age_days = (today - lastmod).days if lastmod else None
    within_grace = age_days is not None and age_days <= grace_days
    indexed = fields["verdict"] == "PASS"

    if indexed:
        status = "indexed"
    else:
        status = "pending" if within_grace else "not_indexed"

    crawl = fields["last_crawl_date"]
    if crawl is None and not indexed and not within_grace:
        flags.append("never_crawled")
    if lastmod and crawl and (lastmod - crawl).days > stale_days:
        flags.append("stale_crawl")
    google_canonical = _normalize_url(fields["google_canonical"])
    user_canonical = _normalize_url(fields["user_canonical"])
    if google_canonical and google_canonical != _normalize_url(fields["url"]):
        flags.append("google_chose_other_canonical")
    if google_canonical and user_canonical and google_canonical != user_canonical:
        flags.append("declared_canonical_disagrees")
    fetch_state = fields["page_fetch_state"]
    # *_UNSPECIFIED means Google has no data (a never-crawled page), not a failure.
    if (
        fetch_state
        and not fetch_state.endswith("UNSPECIFIED")
        and fetch_state != "SUCCESSFUL"
    ):
        flags.append("fetch_problem")
    blocked = str(fields["indexing_state"] or "").startswith("BLOCKED")
    if blocked or fields["robots_txt_state"] == "DISALLOWED":
        flags.append("indexing_blocked")

    note = fields["coverage_state"] or ""
    if status == "pending":
        note = f"{note} (within {grace_days}-day grace period)".strip()
    return status, flags, note


def _fields(url, raw):
    status = (raw.get("inspectionResult") or {}).get("indexStatusResult") or {}
    return {
        "url": url,
        "verdict": status.get("verdict"),
        "coverage_state": status.get("coverageState"),
        "indexing_state": status.get("indexingState"),
        "robots_txt_state": status.get("robotsTxtState"),
        "page_fetch_state": status.get("pageFetchState"),
        "last_crawl_time": status.get("lastCrawlTime"),
        "last_crawl_date": parse_date(status.get("lastCrawlTime")),
        "google_canonical": status.get("googleCanonical"),
        "user_canonical": status.get("userCanonical"),
        "has_result": bool(status),
    }


def _error_text(exc):
    status = getattr(getattr(exc, "resp", None), "status", None)
    try:
        reason = exc._get_reason()
    except Exception:  # noqa: BLE001 - reason text is best effort only
        reason = ""
    return f"HTTP {status}: {str(reason)[:160]}".strip()


def build_stamped_dates(entries):
    """Dates too widely shared to be real modification dates.

    Some sites stamp every static page with the build time, which would make every
    page look modified after Google's last crawl. A date held by many URLs is
    treated as such a stamp: it is ignored for the grace period and ``stale_crawl``
    (the page's age is then unknown, so a problem is never hidden).
    """
    dated = [d for d in (parse_date(e.get("lastmod")) for e in entries) if d]
    counts = Counter(dated)
    return {
        day
        for day, count in counts.items()
        if count >= MIN_SHARED_LASTMOD and count / len(dated) >= SHARED_LASTMOD_SHARE
    }


def inspect_url(service, site_url, url):
    return (
        service.urlInspection()
        .index()
        .inspect(body={"inspectionUrl": url, "siteUrl": site_url})
        .execute()
    )


def check_indexing(
    service,
    site_url,
    entries,
    *,
    today=None,
    grace_days=DEFAULT_GRACE_DAYS,
    stale_days=DEFAULT_STALE_DAYS,
    max_urls=DEFAULT_MAX_URLS,
    delay=0.0,
    sleep=time.sleep,
):
    """Inspect each ``{"url", "lastmod"}`` entry and return the indexing artifact."""
    if not 1 <= max_urls <= DAILY_QUOTA_PER_SITE:
        raise IndexingConfigError(
            f"--max-urls must be between 1 and {DAILY_QUOTA_PER_SITE} "
            "(Google's per-site daily URL Inspection quota)"
        )
    if grace_days < 0 or stale_days < 0:
        raise IndexingConfigError("grace and stale day counts must not be negative")
    seen = set()
    unique = []
    for entry in entries:
        key = _normalize_url(entry["url"])
        if key and key not in seen:
            seen.add(key)
            unique.append(entry)
    if not unique:
        raise IndexingConfigError("no page URLs to inspect")
    if len(unique) > max_urls:
        raise IndexingConfigError(
            f"refusing {len(unique)} URLs; --max-urls is {max_urls}. Narrow the set "
            "with --path-prefix or raise --max-urls (daily quota is "
            f"{DAILY_QUOTA_PER_SITE} per site)"
        )

    today = today or date.today()
    stamped = build_stamped_dates(unique)
    warnings = [
        f"{sum(1 for e in unique if parse_date(e.get('lastmod')) == day)} URLs share "
        f"lastmod {day.isoformat()}; treated as a build timestamp and ignored for the "
        "grace period and stale_crawl"
        for day in sorted(stamped)
    ]
    records = []
    consecutive_failures = 0
    stopped = None
    for index, entry in enumerate(unique):
        url = entry["url"]
        lastmod = parse_date(entry.get("lastmod"))
        reliable = lastmod not in stamped
        base = {
            "url": url,
            "lastmod": lastmod.isoformat() if lastmod else None,
            "lastmod_reliable": reliable,
        }
        if stopped:
            records.append({**base, "status": "error", "flags": [], "note": stopped})
            continue
        try:
            raw = inspect_url(service, site_url, url)
        except HttpError as exc:
            message = _error_text(exc)
            records.append({**base, "status": "error", "flags": [], "note": message})
            consecutive_failures += 1
            if getattr(exc.resp, "status", None) == 429:
                stopped = "not inspected: Search Console quota reached"
            elif consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                stopped = "not inspected: stopped after repeated API failures"
            continue
        consecutive_failures = 0
        fields = _fields(url, raw)
        if not fields["has_result"]:
            records.append(
                {
                    **base,
                    "status": "error",
                    "flags": [],
                    "note": "no index status returned; is the URL inside the property?",
                }
            )
            continue
        status, flags, note = classify(
            fields,
            lastmod=lastmod if reliable else None,
            today=today,
            grace_days=grace_days,
            stale_days=stale_days,
        )
        records.append(
            {
                **base,
                "status": status,
                "flags": flags,
                "note": note,
                "verdict": fields["verdict"],
                "coverage_state": fields["coverage_state"],
                "indexing_state": fields["indexing_state"],
                "robots_txt_state": fields["robots_txt_state"],
                "page_fetch_state": fields["page_fetch_state"],
                "last_crawl_time": fields["last_crawl_time"],
                "google_canonical": fields["google_canonical"],
                "user_canonical": fields["user_canonical"],
            }
        )
        if delay and index < len(unique) - 1:
            sleep(delay)
    return build_artifact(
        site_url,
        records,
        today=today,
        grace_days=grace_days,
        stale_days=stale_days,
        max_urls=max_urls,
        warnings=warnings,
    )


def build_artifact(
    site_url, records, *, today, grace_days, stale_days, max_urls, warnings=()
):
    status_counts = {}
    flag_counts = {}
    for record in records:
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1
        for flag in record["flags"]:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "site_url": site_url,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "as_of": today.isoformat(),
        "grace_days": grace_days,
        "stale_days": stale_days,
        "semantics": (
            "Google's reported index status per URL at check time. It is not a "
            "ranking, traffic, or impressions measurement, and indexed pages can "
            "still receive no impressions."
        ),
        "warnings": list(warnings),
        "request_budget": {
            "max_urls_per_run": max_urls,
            "daily_quota_per_site": DAILY_QUOTA_PER_SITE,
            "inspected": sum(1 for r in records if r["status"] != "error"),
            "errors": status_counts.get("error", 0),
        },
        "summary": {
            "total": len(records),
            "by_status": {
                key: status_counts[key] for key in STATUS_ORDER if key in status_counts
            },
            "by_flag": dict(sorted(flag_counts.items())),
        },
        "records": sorted(
            records, key=lambda r: (STATUS_ORDER.index(r["status"]), r["url"])
        ),
    }


def load_entries(args, config, *, fetch=fetch_text):
    entries = []
    sitemap_url = args.sitemap
    if not sitemap_url and not args.url and not args.urls_file:
        domain = config.get("domain")
        if not domain:
            raise IndexingConfigError(
                "pass --sitemap, --url, or --urls-file (the config has no domain)"
            )
        sitemap_url = f"https://{domain}/sitemap.xml"
    if sitemap_url:
        entries.extend(parse_sitemap(fetch(sitemap_url), fetch=fetch))
    for url in args.url or []:
        entries.append({"url": url.strip(), "lastmod": None})
    if args.urls_file:
        for line in Path(args.urls_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                url, _, lastmod = line.partition(" ")
                entries.append({"url": url, "lastmod": lastmod.strip() or None})
    for entry in entries:
        if not entry["url"].startswith(("http://", "https://")):
            raise IndexingConfigError(f"not an absolute http(s) URL: {entry['url']!r}")
    if args.path_prefix:
        entries = [
            e for e in entries if urlsplit(e["url"]).path.startswith(args.path_prefix)
        ]
    return entries


def print_report(artifact):
    summary = artifact["summary"]
    counts = ", ".join(f"{k}={v}" for k, v in summary["by_status"].items())
    print(f"{artifact['site_url']}: {summary['total']} URL(s) — {counts}")
    for warning in artifact.get("warnings", []):
        print(f"warning: {warning}")
    if summary["by_flag"]:
        print("flags: " + ", ".join(f"{k}={v}" for k, v in summary["by_flag"].items()))
    needs_attention = [
        r for r in artifact["records"] if r["status"] != "indexed" or r["flags"]
    ]
    if needs_attention:
        print("\nSTATUS | LASTMOD | FLAGS | URL | GOOGLE SAYS")
        for record in needs_attention:
            print(
                f"{record['status']} | {record['lastmod'] or '-'} | "
                f"{','.join(record['flags']) or '-'} | {record['url']} | {record['note']}"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Check page indexation with Search Console URL Inspection"
    )
    parser.add_argument("--config", required=True, help="site-config.<project>.json")
    parser.add_argument("--property", help="Search Console property override")
    parser.add_argument(
        "--sitemap", help="sitemap URL; defaults to https://<domain>/sitemap.xml"
    )
    parser.add_argument("--url", action="append", help="extra page URL; repeatable")
    parser.add_argument(
        "--urls-file",
        help="one URL per line, optionally followed by a lastmod date; # comments allowed",
    )
    parser.add_argument(
        "--path-prefix", help="only inspect URL paths starting with this"
    )
    parser.add_argument(
        "--grace-days",
        type=int,
        default=DEFAULT_GRACE_DAYS,
        help="days after lastmod before an unindexed page counts as not_indexed",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=DEFAULT_STALE_DAYS,
        help="flag stale_crawl when the last crawl predates lastmod by more than this",
    )
    parser.add_argument("--max-urls", type=int, default=DEFAULT_MAX_URLS)
    parser.add_argument(
        "--delay", type=float, default=0.0, help="seconds between calls"
    )
    parser.add_argument("--env-file", help="env file loaded before the repo .env")
    parser.add_argument(
        "--out", required=True, help="article-forge.indexing.v1 JSON path"
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        property_url = args.property or _property_from_config(config)
        entries = load_entries(args, config, fetch=fetch_text)
        if args.env_file:
            load_dotenv(args.env_file, override=False)
        if Path(args.out).exists() and not args.force:
            raise IndexingConfigError(
                f"refusing to overwrite existing output; pass --force: {args.out}"
            )
        service = build(
            "searchconsole",
            "v1",
            credentials=get_credentials(),
            cache_discovery=False,
        )
        artifact = check_indexing(
            service,
            property_url,
            entries,
            grace_days=args.grace_days,
            stale_days=args.stale_days,
            max_urls=args.max_urls,
            delay=args.delay,
        )
    except (OSError, KeyError, json.JSONDecodeError, IndexingConfigError) as exc:
        _fail(f"indexing check failed: {exc}")
    except Exception as exc:  # noqa: BLE001 - surface auth failures as a clear config error
        if exc.__class__.__name__ == "RefreshError":
            _fail(
                "indexing check failed: the Search Console login was rejected "
                "(token expired or revoked). Re-run collect_search_console.py --authorize."
            )
        raise
    _atomic_write_json(args.out, artifact, force=args.force)
    print_report(artifact)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
