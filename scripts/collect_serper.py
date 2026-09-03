"""Collect normalized Google SERP observations through the Serper API.

This adapter records observations for later editorial review. It does not
pretend that result counts, host counts, or total-result strings are Google
keyword difficulty or domain authority. The API key is loaded at runtime from
the project's environment and is never written to cache, output, or logs.
"""

import argparse
import hashlib
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://google.serper.dev/search"
SCHEMA_VERSION = "article-forge.serp.v1"
CACHE_SCHEMA_VERSION = "article-forge.serp-cache.v1"
DEFAULT_ENV_VAR = "SERPER_API_KEY"
DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60
DEFAULT_MAX_REQUESTS = 50
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_NUM_RESULTS = 10
MAX_NUM_RESULTS = 100
MAX_CONSECUTIVE_FAILURES = 3
QUERY_MODIFIERS = {
    "informational": {
        "what",
        "why",
        "how",
        "when",
        "where",
        "guide",
        "tutorial",
        "meaning",
        "definition",
    },
    "commercial_investigation": {
        "best",
        "vs",
        "versus",
        "compare",
        "comparison",
        "review",
        "reviews",
        "alternative",
        "alternatives",
    },
    "transactional": {
        "buy",
        "price",
        "pricing",
        "cost",
        "coupon",
        "deal",
        "signup",
        "sign-up",
        "free",
    },
    "navigational": {"login", "log-in", "official", "support", "contact"},
}


class SerperError(RuntimeError):
    """A safe, user-facing Serper collection error."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _normalized_query(query):
    return " ".join(query.split()).strip().lower()


def _cache_key(query, gl, hl, num, location):
    material = json.dumps(
        {
            "query": _normalized_query(query),
            "gl": gl,
            "hl": hl,
            "num": num,
            "location": location or "",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _host(url):
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    return host.removeprefix("www.")


def _short_text(value, limit=700):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _safe_items(value, fields):
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if not isinstance(item, dict):
            continue
        cleaned = {}
        for field in fields:
            if field not in item:
                continue
            current = item[field]
            if isinstance(current, str):
                current = _short_text(current)
            elif not isinstance(current, (int, float, bool)) and current is not None:
                continue
            cleaned[field] = current
        if cleaned:
            items.append(cleaned)
    return items


def _organic_results(payload):
    results = []
    for index, item in enumerate(payload.get("organic", []), start=1):
        link = item.get("link") if isinstance(item, dict) else None
        if not isinstance(link, str) or not link.startswith(("http://", "https://")):
            continue
        results.append(
            {
                "position": item.get("position", index),
                "title": _short_text(item.get("title", ""), 300),
                "link": link,
                "host": _host(link),
                "snippet": _short_text(item.get("snippet", "")),
                **(
                    {"date": _short_text(item["date"], 80)}
                    if item.get("date") is not None
                    else {}
                ),
            }
        )
    return results


def _feature_names(payload):
    key_to_name = {
        "answerBox": "answer_box",
        "knowledgeGraph": "knowledge_graph",
        "peopleAlsoAsk": "people_also_ask",
        "relatedSearches": "related_searches",
        "shopping": "shopping",
        "news": "news",
        "videos": "videos",
        "images": "images",
        "places": "places",
        "topStories": "top_stories",
    }
    return [
        name
        for key, name in key_to_name.items()
        if payload.get(key) not in (None, [], {})
    ]


def _query_modifier_signals(query):
    tokens = set(re.findall(r"[a-z0-9][a-z0-9-]*", _normalized_query(query)))
    signals = []
    for intent, modifiers in QUERY_MODIFIERS.items():
        matched = sorted(tokens.intersection(modifiers))
        if matched:
            signals.append(
                {
                    "kind": "query_modifier",
                    "intent_hint": intent,
                    "values": matched,
                    "observed": True,
                }
            )
    return signals


def _intent_signals(query, payload, features):
    signals = _query_modifier_signals(query)
    feature_hints = {
        "answer_box": "informational",
        "knowledge_graph": "informational",
        "people_also_ask": "informational",
        "shopping": "transactional",
        "places": "local",
        "news": "news",
        "videos": "multimedia",
    }
    for feature in features:
        if feature in feature_hints:
            signals.append(
                {
                    "kind": "serp_feature",
                    "intent_hint": feature_hints[feature],
                    "feature": feature,
                    "observed": True,
                }
            )
    if payload.get("peopleAlsoAsk"):
        signals.append(
            {
                "kind": "question_evidence",
                "intent_hint": "informational",
                "count": len(payload["peopleAlsoAsk"]),
                "observed": True,
            }
        )
    return signals


def normalize_response(query, payload, *, gl, hl, num, location, cache_key):
    """Turn one untrusted provider response into the public evidence schema."""
    organic = _organic_results(payload)
    features = _feature_names(payload)
    hosts = [item["host"] for item in organic if item["host"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "serper",
        "endpoint": ENDPOINT,
        "retrieved_at": _now(),
        "query": query.strip(),
        "normalized_query": _normalized_query(query),
        "gl": gl,
        "hl": hl,
        "location": location or None,
        "num_requested": num,
        "cache_key": cache_key,
        "organic": organic,
        "people_also_ask": _safe_items(
            payload.get("peopleAlsoAsk"), ["question", "snippet", "title", "link"]
        ),
        "related_searches": _safe_items(payload.get("relatedSearches"), ["query"]),
        "serp_features": features,
        "intent_signals": _intent_signals(query, payload, features),
        "competition_observations": {
            "organic_result_count": len(organic),
            "unique_hosts": len(set(hosts)),
            "top_3_unique_hosts": len(set(hosts[:3])),
            "top_10_unique_hosts": len(set(hosts[:10])),
            "note": "Observed SERP composition only; not Google keyword difficulty or domain authority.",
        },
    }


def _retry_after(headers):
    value = headers.get("Retry-After") if headers else None
    try:
        return max(0.0, min(float(value), 60.0))
    except (TypeError, ValueError):
        return None


def _backoff(attempt, headers=None):
    retry_after = _retry_after(headers)
    if retry_after is not None:
        return retry_after
    return min(8.0, 2**attempt) + random.uniform(0.0, 0.25)


def request_serper(
    query,
    api_key,
    *,
    gl,
    hl,
    num,
    location=None,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    max_retries=DEFAULT_MAX_RETRIES,
    sleep=time.sleep,
    open_url=urllib.request.urlopen,
):
    body = {"q": query, "gl": gl, "hl": hl, "num": num, "autocorrect": True}
    if location:
        body["location"] = location
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    for attempt in range(max_retries + 1):
        try:
            with open_url(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise SerperError("Serper returned a non-object JSON response")
                return payload
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            if not retryable or attempt >= max_retries:
                if exc.code in {400, 401, 403}:
                    raise SerperError(
                        f"Serper rejected the request with HTTP {exc.code}; check query/configuration or credential"
                    ) from exc
                raise SerperError(
                    f"Serper request failed with HTTP {exc.code}"
                ) from exc
            sleep(_backoff(attempt, exc.headers))
        except (TimeoutError, urllib.error.URLError) as exc:
            if attempt >= max_retries:
                raise SerperError(
                    "Serper request timed out or failed on the network"
                ) from exc
            sleep(_backoff(attempt))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SerperError("Serper returned invalid JSON") from exc
    raise SerperError("Serper request exhausted its retry budget")


def _read_cache(path, ttl_seconds):
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(cache["cached_at"])
        age = (datetime.now(timezone.utc) - cached_at).total_seconds()
        if (
            cache.get("schema_version") == CACHE_SCHEMA_VERSION
            and age <= ttl_seconds
            and isinstance(cache.get("normalized"), dict)
        ):
            return cache["normalized"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _write_cache(path, cache_key, raw, normalized):
    _atomic_json(
        path,
        {
            "schema_version": CACHE_SCHEMA_VERSION,
            "cache_key": cache_key,
            "cached_at": _now(),
            "raw_response": raw,
            "normalized": normalized,
        },
    )


def collect_queries(
    queries,
    api_key,
    *,
    gl,
    hl,
    num,
    location,
    cache_dir,
    cache_ttl_seconds=DEFAULT_CACHE_TTL_SECONDS,
    refresh=False,
    max_requests=DEFAULT_MAX_REQUESTS,
    max_retries=DEFAULT_MAX_RETRIES,
    timeout=DEFAULT_TIMEOUT_SECONDS,
    delay=0.0,
    sleep=time.sleep,
    request_fn=request_serper,
):
    clean_queries = [query.strip() for query in queries if query.strip()]
    if not clean_queries:
        raise SerperError("at least one non-empty query is required")
    if len(clean_queries) > max_requests:
        raise SerperError(
            f"refusing {len(clean_queries)} queries; max_requests_per_run is {max_requests}"
        )

    cache_dir = Path(cache_dir)
    records = []
    errors = []
    api_requests = 0
    cache_hits = 0
    consecutive_failures = 0
    for index, query in enumerate(clean_queries):
        key = _cache_key(query, gl, hl, num, location)
        cache_path = cache_dir / f"{key}.json"
        cached = None if refresh else _read_cache(cache_path, cache_ttl_seconds)
        if cached is not None:
            cached["cache_hit"] = True
            records.append(cached)
            cache_hits += 1
            continue

        try:
            raw = request_fn(
                query,
                api_key,
                gl=gl,
                hl=hl,
                num=num,
                location=location,
                timeout=timeout,
                max_retries=max_retries,
                sleep=sleep,
            )
            record = normalize_response(
                query,
                raw,
                gl=gl,
                hl=hl,
                num=num,
                location=location,
                cache_key=key,
            )
            record["cache_hit"] = False
            _write_cache(cache_path, key, raw, record)
            records.append(record)
            api_requests += 1
            consecutive_failures = 0
        except SerperError as exc:
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                raise SerperError(
                    "circuit breaker opened after three consecutive Serper failures"
                ) from None
            errors.append({"query": query, "error": str(exc)})
            continue
        if delay and index < len(clean_queries) - 1:
            sleep(delay)
    return {
        "schema_version": "article-forge.serp-collection.v1",
        "collected_at": _now(),
        "source": "serper",
        "request_budget": {
            "max_requests_per_run": max_requests,
            "api_requests": api_requests,
            "cache_hits": cache_hits,
        },
        "errors": errors,
        "records": records,
    }


def _config_value(config, name, fallback):
    research = config.get("research", {})
    serper = research.get("serper", {}) if isinstance(research, dict) else {}
    return serper.get(name, fallback) if isinstance(serper, dict) else fallback


def _load_queries(query_args, queries_file):
    queries = list(query_args or [])
    if queries_file:
        queries.extend(
            line.strip()
            for line in Path(queries_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    return queries


def main():
    parser = argparse.ArgumentParser(
        description="Collect Google SERP evidence via Serper"
    )
    parser.add_argument("--config", required=True, help="site-config.<project>.json")
    parser.add_argument("--query", action="append", help="query; repeat for a batch")
    parser.add_argument("--queries-file", help="newline-separated query file")
    parser.add_argument("--out", required=True, help="normalized collection JSON path")
    parser.add_argument(
        "--force", action="store_true", help="replace an existing output file"
    )
    parser.add_argument("--env-file", help="project env file; values are never printed")
    parser.add_argument(
        "--api-key-env", help="env variable name; defaults to config or SERPER_API_KEY"
    )
    parser.add_argument("--gl", help="Google country code")
    parser.add_argument("--hl", help="Google language code")
    parser.add_argument("--location", help="optional Serper location string")
    parser.add_argument(
        "--num", type=int, help=f"organic results requested, 1-{MAX_NUM_RESULTS}"
    )
    parser.add_argument("--cache-dir", help="disk cache directory")
    parser.add_argument(
        "--cache-ttl-seconds", type=int, help="cache TTL; default 86400"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="ignore valid cache entries"
    )
    parser.add_argument(
        "--max-requests", type=int, help="maximum API requests per run; default 50"
    )
    parser.add_argument(
        "--max-retries", type=int, help="retries for 429/5xx/network errors; default 3"
    )
    parser.add_argument(
        "--timeout", type=int, help="per-request timeout in seconds; default 30"
    )
    parser.add_argument("--delay", type=float, help="delay between uncached requests")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    env_file = args.env_file or str(REPO_ROOT / ".env")
    load_dotenv(dotenv_path=env_file, override=False)
    env_name = args.api_key_env or _config_value(config, "api_key_env", DEFAULT_ENV_VAR)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", env_name):
        parser.error("--api-key-env must be an uppercase environment variable name")
    api_key = os.environ.get(env_name)
    if not api_key:
        raise SystemExit(f"{env_name} is missing from the supplied project environment")

    gl = args.gl or _config_value(config, "gl", "us")
    hl = args.hl or _config_value(config, "hl", "en")
    location = args.location or _config_value(config, "location", None)
    num = args.num or _config_value(config, "num", DEFAULT_NUM_RESULTS)
    if not isinstance(num, int) or not 1 <= num <= MAX_NUM_RESULTS:
        parser.error(f"num must be between 1 and {MAX_NUM_RESULTS}")
    cache_dir = args.cache_dir or _config_value(
        config, "cache_dir", str(REPO_ROOT / "serp" / ".cache")
    )
    out = Path(args.out)
    if out.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite existing output; pass --force: {out}")
    result = collect_queries(
        _load_queries(args.query, args.queries_file),
        api_key,
        gl=gl,
        hl=hl,
        num=num,
        location=location,
        cache_dir=cache_dir,
        cache_ttl_seconds=args.cache_ttl_seconds
        or _config_value(config, "cache_ttl_seconds", DEFAULT_CACHE_TTL_SECONDS),
        refresh=args.refresh,
        max_requests=args.max_requests
        or _config_value(config, "max_requests_per_run", DEFAULT_MAX_REQUESTS),
        max_retries=args.max_retries
        if args.max_retries is not None
        else _config_value(config, "max_retries", DEFAULT_MAX_RETRIES),
        timeout=args.timeout
        or _config_value(config, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        delay=args.delay
        if args.delay is not None
        else _config_value(config, "delay_seconds", 0.0),
    )
    _atomic_json(out, result)
    budget = result["request_budget"]
    print(
        f"Collected {len(result['records'])} SERP record(s); "
        f"API requests={budget['api_requests']}, cache hits={budget['cache_hits']}; wrote {out}"
    )


if __name__ == "__main__":
    main()
