"""Collect link-graph authority proxies for SERP hosts through Open PageRank.

Open PageRank scores hosts 0-10 from the Common Crawl web graph. It is a
link-graph popularity proxy: it is not Moz Domain Authority, Ahrefs Domain
Rating, Google PageRank, keyword difficulty, or a ranking prediction. This
adapter records observations for later editorial review and never turns them
into an editorial-difficulty score. The API key is loaded at runtime from the
environment and is never written to cache, output, or logs.
"""

import argparse
import hashlib
import json
import os
import re
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from collect_serper import _atomic_json, _backoff, _now

REPO_ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://openpagerank.keywordseverywhere.com/v1/domains/bulk"
SCHEMA_VERSION = "article-forge.authority.v1"
CACHE_SCHEMA_VERSION = "article-forge.authority-cache.v1"
SERP_COLLECTION_SCHEMA = "article-forge.serp-collection.v1"
SERP_RECORD_SCHEMA = "article-forge.serp.v1"
SOURCE = "open_page_rank"
SEMANTICS = "link_graph_authority_proxy"
DEFAULT_ENV_VAR = "OPENPAGERANK_API_KEY"
# Provider data is refreshed monthly, so a month-old answer is still current.
DEFAULT_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
DEFAULT_MAX_DOMAINS = 500
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 30
BATCH_SIZE = 100
SCORED_STATUSES = {"scored", "scored_via_parent"}
LIMITATION = (
    "Open PageRank is a Common Crawl link-graph popularity proxy (0-10). It is "
    "not Moz DA, Ahrefs DR, Google PageRank, keyword difficulty, or a ranking "
    "prediction, and it is domain-level, not page-level."
)
# Terminal provider answers: retrying cannot help and may burn quota.
NON_RETRYABLE_CODES = {401, 402, 403, 429}

# Registrable domains under these suffixes keep three labels (example.co.uk).
MULTI_LABEL_SUFFIXES = {
    "co.uk",
    "org.uk",
    "ac.uk",
    "com.au",
    "net.au",
    "co.nz",
    "co.za",
    "com.br",
    "co.in",
    "co.jp",
    "com.mx",
    "com.bb",
    "org.bb",
    "co.bb",
}
# Hosts on these builders belong to whoever rents the subdomain. The parent's
# score describes the platform, not the tenant, so tenants stay unscored.
PLATFORM_HOSTED_SUFFIXES = (
    "mypixieset.com",
    "pixieset.com",
    "eweddingcalendar.com",
    "wixsite.com",
    "squarespace.com",
    "wordpress.com",
    "blogspot.com",
    "weebly.com",
    "godaddysites.com",
    "github.io",
    "netlify.app",
    "vercel.app",
    "myshopify.com",
    "substack.com",
    "medium.com",
)
# Large aggregators and social/UGC hosts. Their authority says little about
# whether an independent site can win a query, so the planner reports them
# apart from independents. Override with research.authority.platform_hosts.
DEFAULT_PLATFORM_HOSTS = {
    "facebook": "social",
    "instagram": "social",
    "pinterest": "social",
    "tiktok": "social",
    "linkedin": "social",
    "twitter": "social",
    "youtube": "video",
    "reddit": "forum",
    "quora": "forum",
    "weddingwire": "directory",
    "theknot": "directory",
    "zola": "directory",
    "yelp": "directory",
    "tripadvisor": "directory",
    "thumbtack": "directory",
    "wikipedia": "reference",
    "amazon": "marketplace",
    "etsy": "marketplace",
    "pubhtml5": "document_hosting",
    "issuu": "document_hosting",
    "scribd": "document_hosting",
}
_HOST_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)


class OpenPageRankError(RuntimeError):
    """A safe, user-facing Open PageRank collection error."""


def clean_host(value):
    """Lowercase a host and drop ``www.``; return ``None`` when it is not a host."""
    if not isinstance(value, str):
        return None
    host = value.strip().lower().rstrip(".")
    host = host.removeprefix("www.")
    if len(host) > 253 or not _HOST_RE.match(host):
        return None
    return host


def registrable_domain(host):
    """Best-effort registrable domain without a public-suffix dependency."""
    labels = host.lower().rstrip(".").split(".")
    if len(labels) < 2:
        return host
    if ".".join(labels[-2:]) in MULTI_LABEL_SUFFIXES:
        return ".".join(labels[-3:]) if len(labels) >= 3 else host
    return ".".join(labels[-2:])


def domain_stem(host):
    """The name label of a host: tripadvisor.ie -> tripadvisor."""
    return registrable_domain(host).split(".")[0]


def is_platform_hosted(host):
    return any(host.endswith(f".{suffix}") for suffix in PLATFORM_HOSTED_SUFFIXES)


def platform_hosts_from_config(config):
    """Platform stems from ``research.authority.platform_hosts`` or the defaults."""
    research = config.get("research", {}) if isinstance(config, dict) else {}
    authority = research.get("authority", {}) if isinstance(research, dict) else {}
    configured = (
        authority.get("platform_hosts") if isinstance(authority, dict) else None
    )
    if configured is None:
        return dict(DEFAULT_PLATFORM_HOSTS)
    if not isinstance(configured, list) or not all(
        isinstance(item, str) and item.strip() for item in configured
    ):
        raise ValueError("research.authority.platform_hosts must be a list of names")
    return {item.strip().lower(): "platform" for item in configured}


def classify_platform(host, platform_hosts):
    """Return the platform type for ``host`` or ``None`` for an independent site."""
    return platform_hosts.get(domain_stem(host))


def request_open_pagerank(
    domains,
    api_key,
    *,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    max_retries=DEFAULT_MAX_RETRIES,
    sleep=time.sleep,
    open_url=urllib.request.urlopen,
):
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({"domains": list(domains)}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    for attempt in range(max_retries + 1):
        try:
            with open_url(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise OpenPageRankError(
                    "Open PageRank rejected the credential (HTTP 401); check the API key"
                ) from exc
            if exc.code in NON_RETRYABLE_CODES:
                raise OpenPageRankError(
                    f"Open PageRank refused the request with HTTP {exc.code}; "
                    "a plan, billing, or rate limit may be reached. Not retrying"
                ) from exc
            if exc.code >= 500 and attempt < max_retries:
                sleep(_backoff(attempt, exc.headers))
                continue
            raise OpenPageRankError(
                f"Open PageRank request failed with HTTP {exc.code}"
            ) from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            if attempt >= max_retries:
                raise OpenPageRankError(
                    "Open PageRank request timed out or failed on the network"
                ) from exc
            sleep(_backoff(attempt))
            continue
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenPageRankError("Open PageRank returned invalid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(
            payload.get("results"), list
        ):
            raise OpenPageRankError("Open PageRank returned an unexpected response")
        return payload
    raise OpenPageRankError("Open PageRank request exhausted its retry budget")


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_entry(result, as_of):
    """One provider result -> stored fields, or ``None`` when it has no score."""
    if not isinstance(result, dict) or result.get("found") is not True:
        return None
    score = result.get("open_page_rank")
    if not _number(score) or not 0 <= score <= 10:
        return None
    referring = result.get("referring_domains")
    rank = result.get("rank")
    return {
        "open_page_rank": float(score),
        "referring_domains": int(referring) if _number(referring) else None,
        "rank": int(rank) if _number(rank) else None,
        "provider_as_of": as_of if isinstance(as_of, str) else None,
    }


def _cache_path(cache_dir, domain):
    return (
        Path(cache_dir) / f"{hashlib.sha256(domain.encode('utf-8')).hexdigest()}.json"
    )


def _read_cache(path, ttl_seconds):
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(cache["cached_at"])
        age = (datetime.now(timezone.utc) - cached_at).total_seconds()
        if (
            cache.get("schema_version") == CACHE_SCHEMA_VERSION
            and age <= ttl_seconds
            and isinstance(cache.get("found"), bool)
        ):
            return cache
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def _write_cache(path, domain, entry):
    _atomic_json(
        path,
        {
            "schema_version": CACHE_SCHEMA_VERSION,
            "domain": domain,
            "cached_at": _now(),
            "found": entry is not None,
            "entry": entry,
        },
    )


def _lookup(
    domains,
    api_key,
    *,
    cache_dir,
    ttl_seconds,
    refresh,
    max_retries,
    timeout,
    sleep,
    request_fn,
    stats,
):
    """Resolve domains to entries (or ``None``); cache hits and misses alike."""
    resolved = {}
    pending = []
    for domain in domains:
        cached = (
            None
            if refresh
            else _read_cache(_cache_path(cache_dir, domain), ttl_seconds)
        )
        if cached is not None:
            resolved[domain] = cached.get("entry") if cached["found"] else None
            stats["cache_hits"] += 1
        else:
            pending.append(domain)
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        payload = request_fn(
            batch, api_key, timeout=timeout, max_retries=max_retries, sleep=sleep
        )
        stats["api_requests"] += 1
        as_of = payload.get("as_of")
        by_domain = {
            result["domain"].lower(): result
            for result in payload["results"]
            if isinstance(result, dict) and isinstance(result.get("domain"), str)
        }
        for domain in batch:
            entry = _normalize_entry(by_domain.get(domain), as_of)
            _write_cache(_cache_path(cache_dir, domain), domain, entry)
            resolved[domain] = entry
    return resolved


def collect_authority(
    hosts,
    api_key,
    *,
    cache_dir,
    cache_ttl_seconds=DEFAULT_CACHE_TTL_SECONDS,
    refresh=False,
    max_domains=DEFAULT_MAX_DOMAINS,
    max_retries=DEFAULT_MAX_RETRIES,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    sleep=time.sleep,
    request_fn=request_open_pagerank,
):
    errors = []
    cleaned = []
    for value in hosts:
        host = clean_host(value)
        if host is None:
            errors.append({"host": str(value)[:120], "error": "not a valid hostname"})
        elif host not in cleaned:
            cleaned.append(host)
    hosted = [host for host in cleaned if is_platform_hosted(host)]
    queryable = [host for host in cleaned if host not in hosted]
    if not queryable and not hosted:
        raise OpenPageRankError("at least one valid host is required")
    if len(queryable) > max_domains:
        raise OpenPageRankError(
            f"refusing {len(queryable)} domains; max_domains_per_run is {max_domains}"
        )

    stats = {"api_requests": 0, "cache_hits": 0}
    options = {
        "cache_dir": cache_dir,
        "ttl_seconds": cache_ttl_seconds,
        "refresh": refresh,
        "max_retries": max_retries,
        "timeout": timeout,
        "sleep": sleep,
        "request_fn": request_fn,
        "stats": stats,
    }
    resolved = _lookup(queryable, api_key, **options)
    # A missing subdomain often has a scored parent (community.example.com).
    parents = {
        host: registrable_domain(host)
        for host in queryable
        if resolved[host] is None and registrable_domain(host) != host
    }
    wanted = sorted({parent for parent in parents.values() if parent not in resolved})
    if wanted:
        resolved.update(_lookup(wanted, api_key, **options))

    domains = {}
    for host in hosted:
        domains[host] = {
            "status": "platform_hosted_unscored",
            "open_page_rank": None,
            "reason": "tenant of a site builder; the parent's score describes the platform",
        }
    for host in queryable:
        entry = resolved[host]
        if entry is not None:
            domains[host] = {"status": "scored", "resolved_domain": host, **entry}
            continue
        parent_entry = resolved.get(parents.get(host))
        if parent_entry is not None:
            domains[host] = {
                "status": "scored_via_parent",
                "resolved_domain": parents[host],
                **parent_entry,
            }
        else:
            domains[host] = {
                "status": "unscored",
                "open_page_rank": None,
                "reason": "not found by provider",
            }
    as_of_values = sorted(
        {
            item["provider_as_of"]
            for item in domains.values()
            if item.get("provider_as_of")
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "endpoint": ENDPOINT,
        "collected_at": _now(),
        "provider_as_of": as_of_values[-1] if as_of_values else None,
        "semantics": SEMANTICS,
        "limitation": LIMITATION,
        "request_budget": {
            "max_domains_per_run": max_domains,
            "domains_requested": len(queryable) + len(wanted),
            "api_requests": stats["api_requests"],
            "cache_hits": stats["cache_hits"],
        },
        "errors": errors,
        "domains": domains,
    }


def hosts_from_serp_payload(payload):
    """Organic hosts from a saved Serper collection or single SERP record."""
    if not isinstance(payload, dict):
        raise ValueError("SERP artifact must be a JSON object")
    schema = payload.get("schema_version")
    if schema == SERP_COLLECTION_SCHEMA:
        records = [
            item for item in payload.get("records", []) if isinstance(item, dict)
        ]
    elif schema == SERP_RECORD_SCHEMA:
        records = [payload]
    else:
        raise ValueError(
            f"unsupported SERP artifact schema_version: {schema!r}; "
            f"expected {SERP_COLLECTION_SCHEMA} or {SERP_RECORD_SCHEMA}"
        )
    hosts = []
    for record in records:
        for item in record.get("organic", []):
            if isinstance(item, dict) and item.get("host"):
                hosts.append(item["host"])
    return hosts


def load_authority_artifacts(paths):
    """Merge saved authority artifacts; later files win for the same host."""
    domains = {}
    provider_as_of = None
    sources = []
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != SCHEMA_VERSION
        ):
            raise ValueError(f"{path} is not an {SCHEMA_VERSION} artifact")
        if not isinstance(payload.get("domains"), dict):
            raise ValueError(f"{path} has no domains map")
        domains.update(payload["domains"])
        stamp = payload.get("provider_as_of")
        if isinstance(stamp, str) and (
            provider_as_of is None or stamp > provider_as_of
        ):
            provider_as_of = stamp
        sources.append({"path": str(path), "schema_version": SCHEMA_VERSION})
    return {"domains": domains, "provider_as_of": provider_as_of, "sources": sources}


def _score_of(entry):
    if isinstance(entry, dict) and entry.get("status") in SCORED_STATUSES:
        return entry.get("open_page_rank")
    return None


def summarize_authority(organic, authority, *, own_domain=None, platform_hosts=None):
    """Summarize one SERP's host authority without producing a difficulty score.

    Platforms and independent sites are reported separately because a
    platform ranking says little about whether an independent site can win.
    """
    platform_hosts = (
        DEFAULT_PLATFORM_HOSTS if platform_hosts is None else platform_hosts
    )
    domains = authority.get("domains", {})
    own = clean_host(own_domain) if own_domain else None
    own_registrable = registrable_domain(own) if own else None
    seen = set()
    independents = []
    platforms = []
    own_positions = []
    for item in organic:
        host = clean_host(item.get("host")) if isinstance(item, dict) else None
        if host is None:
            continue
        position = item.get("position")
        if own_registrable and registrable_domain(host) == own_registrable:
            if isinstance(position, int):
                own_positions.append(position)
            continue
        if host in seen:
            continue
        seen.add(host)
        entry = domains.get(host)
        row = {
            "host": host,
            "position": position,
            "status": entry.get("status")
            if isinstance(entry, dict)
            else "not_collected",
            "open_page_rank": _score_of(entry),
        }
        if isinstance(entry, dict) and entry.get("status") == "scored_via_parent":
            row["resolved_domain"] = entry.get("resolved_domain")
        platform_type = classify_platform(host, platform_hosts)
        if platform_type:
            platforms.append({**row, "platform_type": platform_type})
        else:
            independents.append(row)

    scored = [
        row["open_page_rank"]
        for row in independents
        if row["open_page_rank"] is not None
    ]
    strongest = max(
        (row for row in independents if row["open_page_rank"] is not None),
        key=lambda row: row["open_page_rank"],
        default=None,
    )
    return {
        "source": SOURCE,
        "semantics": SEMANTICS,
        "provider_as_of": authority.get("provider_as_of"),
        "own_domain": {
            "domain": own,
            "best_position": min(own_positions) if own_positions else None,
        },
        "independent": {
            "count": len(independents),
            "scored_count": len(scored),
            "unscored_count": len(independents) - len(scored),
            "median": round(statistics.median(scored), 2) if scored else None,
            "max": max(scored) if scored else None,
            "strongest_host": strongest["host"] if strongest else None,
            "hosts": independents,
        },
        "platforms": {
            "count": len(platforms),
            "hosts": platforms,
        },
        "limitation": LIMITATION,
    }


def _load_runtime_environment(env_file):
    if env_file:
        load_dotenv(env_file, override=False)
        return
    # Keep project .env support, then fall back to the owner's personal
    # secrets.env without ever printing or copying its values.
    load_dotenv(REPO_ROOT / ".env", override=False)
    load_dotenv(Path.home() / ".claude" / "secrets.env", override=False)


def _authority_config(config, name, fallback):
    research = config.get("research", {})
    authority = research.get("authority", {}) if isinstance(research, dict) else {}
    return authority.get(name, fallback) if isinstance(authority, dict) else fallback


def main():
    parser = argparse.ArgumentParser(
        description="Collect Open PageRank authority proxies for SERP hosts"
    )
    parser.add_argument("--config", required=True, help="site-config.<project>.json")
    parser.add_argument(
        "--serp",
        action="append",
        help="saved Serper collection or record JSON; repeatable",
    )
    parser.add_argument("--host", action="append", help="extra host; repeatable")
    parser.add_argument("--out", required=True, help="authority artifact JSON path")
    parser.add_argument(
        "--force", action="store_true", help="replace an existing output file"
    )
    parser.add_argument("--env-file", help="env file; values are never printed")
    parser.add_argument(
        "--api-key-env",
        help="env variable name; defaults to config or OPENPAGERANK_API_KEY",
    )
    parser.add_argument("--cache-dir", help="disk cache directory")
    parser.add_argument(
        "--cache-ttl-seconds", type=int, help="cache TTL; default 30 days"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="ignore valid cache entries"
    )
    parser.add_argument(
        "--max-domains", type=int, help="maximum domains per run; default 500"
    )
    parser.add_argument(
        "--max-retries", type=int, help="retries for 5xx/network errors; default 3"
    )
    parser.add_argument(
        "--timeout", type=int, help="per-request timeout in seconds; default 30"
    )
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    _load_runtime_environment(args.env_file)
    env_name = args.api_key_env or _authority_config(
        config, "api_key_env", DEFAULT_ENV_VAR
    )
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", env_name):
        parser.error("--api-key-env must be an uppercase environment variable name")
    api_key = os.environ.get(env_name)
    if not api_key:
        raise SystemExit(f"{env_name} is missing from the supplied environment")

    hosts = list(args.host or [])
    try:
        for path in args.serp or []:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            hosts.extend(hosts_from_serp_payload(payload))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"could not read SERP evidence: {exc}") from exc
    out = Path(args.out)
    if out.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite existing output; pass --force: {out}")
    try:
        result = collect_authority(
            hosts,
            api_key,
            cache_dir=args.cache_dir
            or _authority_config(
                config, "cache_dir", str(REPO_ROOT / "serp" / ".cache" / "authority")
            ),
            cache_ttl_seconds=args.cache_ttl_seconds
            or _authority_config(
                config, "cache_ttl_seconds", DEFAULT_CACHE_TTL_SECONDS
            ),
            refresh=args.refresh,
            max_domains=args.max_domains
            or _authority_config(config, "max_domains_per_run", DEFAULT_MAX_DOMAINS),
            max_retries=args.max_retries
            if args.max_retries is not None
            else _authority_config(config, "max_retries", DEFAULT_MAX_RETRIES),
            timeout=args.timeout
            or _authority_config(config, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        )
    except OpenPageRankError as exc:
        raise SystemExit(f"authority collection failed: {exc}") from exc
    _atomic_json(out, result)
    counts = {}
    for item in result["domains"].values():
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    budget = result["request_budget"]
    print(
        f"Collected authority for {len(result['domains'])} host(s) "
        f"{dict(sorted(counts.items()))}; API requests={budget['api_requests']}, "
        f"cache hits={budget['cache_hits']}; wrote {out}"
    )


if __name__ == "__main__":
    main()
