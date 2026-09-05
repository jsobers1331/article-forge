"""Discover and triage article opportunities from the configured site and SERP evidence.

This is the missing orchestration layer between ``discover_gaps.py`` and the
evidence-backed opportunity scorer.  It can run entirely offline from saved
artifacts, or make a bounded, cached Serper pass using the owner's direct API
credential.  The output is deliberately a *plan*, not a ranking prediction:
Serper exposes observed query language and SERP composition, but not market
search volume or organic difficulty.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collect_serper import (  # noqa: E402
    DEFAULT_CACHE_TTL_SECONDS,
    DEFAULT_MAX_REQUESTS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_NUM_RESULTS,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_NUM_RESULTS,
    SerperError,
    collect_queries,
)
from discover_gaps import suggest_seeds  # noqa: E402
from generate_prompt import load_config  # noqa: E402
from score_article import _norm, _phrase_covered  # noqa: E402


SCHEMA_VERSION = "article-forge.opportunity-plan.v1"
SERP_COLLECTION_SCHEMA = "article-forge.serp-collection.v1"
SERP_RECORD_SCHEMA = "article-forge.serp.v1"
DEMAND_SCHEMA = "article-forge.demand.v1"
KEYWORD_PLANNER_SCHEMA = "article-forge.keyword-planner.v1"
GSC_SCHEMA = "article-forge.gsc.v1"
DEFAULT_SEED_LIMIT = 8
DEFAULT_CANDIDATE_LIMIT = 12
GENERIC_TITLE_TERMS = {
    "affordable",
    "barbados",
    "best",
    "candid",
    "ceremony",
    "cost",
    "couples",
    "dinner",
    "destination",
    "elopement",
    "engagement",
    "expect",
    "family",
    "flying",
    "included",
    "maternity",
    "moments",
    "package",
    "packages",
    "photo",
    "photographer",
    "photographers",
    "photography",
    "photos",
    "photoshoot",
    "portrait",
    "portraits",
    "pricing",
    "reception",
    "recommendation",
    "recommendations",
    "shoot",
    "suggestions",
    "tips",
    "visiting",
    "wedding",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _normalized_query(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _query_slug(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    digest = hashlib.sha256(_normalized_query(value).encode("utf-8")).hexdigest()[:8]
    return f"{slug[:48] or 'query'}-{digest}"


def _unique_queries(values):
    seen = set()
    result = []
    for value in values:
        if not isinstance(value, str):
            continue
        query = " ".join(value.split()).strip()
        normalized = _normalized_query(query)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(query)
    return result


def _config_serper(config, name, fallback):
    research = config.get("research", {})
    serper = research.get("serper", {}) if isinstance(research, dict) else {}
    value = serper.get(name, fallback) if isinstance(serper, dict) else fallback
    return value


def _site_corpus(config):
    parts = []
    for topic in config.get("topic_backlog", []):
        if isinstance(topic, dict):
            parts.extend((topic.get("title", ""), topic.get("target_query", "")))
    parts.extend(config.get("existing_pages", []))
    return _norm(" ".join(str(part) for part in parts))


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read JSON artifact {path}: {exc}") from exc


def _load_serp_records(paths):
    records = []
    artifact_sources = []
    for path in paths:
        payload = _read_json(path)
        schema = payload.get("schema_version") if isinstance(payload, dict) else None
        if schema == SERP_COLLECTION_SCHEMA:
            records.extend(
                record
                for record in payload.get("records", [])
                if isinstance(record, dict)
                and record.get("schema_version") == SERP_RECORD_SCHEMA
            )
        elif schema == SERP_RECORD_SCHEMA:
            records.append(payload)
        else:
            raise ValueError(
                f"{path} must be {SERP_COLLECTION_SCHEMA} or {SERP_RECORD_SCHEMA}"
            )
        artifact_sources.append({"path": str(path), "schema_version": schema})
    return records, artifact_sources


def _load_demand_records(paths):
    records = []
    artifact_sources = []
    for path in paths:
        payload = _read_json(path)
        schema = payload.get("schema_version") if isinstance(payload, dict) else None
        if schema == DEMAND_SCHEMA:
            records.extend(
                record
                for record in payload.get("records", [])
                if isinstance(record, dict) and isinstance(record.get("demand"), dict)
            )
        elif schema == KEYWORD_PLANNER_SCHEMA:
            # Raw Keyword Planner output is useful for discovery, but without
            # the normalized demand artifact it cannot meet the scorer's
            # sample-size contract. Keep it visible as raw evidence.
            for row in payload.get("rows", []):
                if isinstance(row, dict) and row.get("keyword"):
                    records.append(
                        {
                            "query": row["keyword"],
                            "raw_market_demand": {
                                "avg_monthly_searches": row.get("avg_monthly_searches"),
                                "paid_competition": row.get("competition"),
                                "paid_competition_index": row.get("competition_index"),
                            },
                        }
                    )
        elif schema == GSC_SCHEMA:
            for row in payload.get("rows", []):
                if not isinstance(row, dict):
                    continue
                keys = row.get("keys") or []
                query = keys[0] if keys else row.get("query")
                if query:
                    records.append({"query": query, "raw_site_opportunity": row})
        else:
            raise ValueError(
                f"{path} must be {DEMAND_SCHEMA}, {KEYWORD_PLANNER_SCHEMA}, or {GSC_SCHEMA}"
            )
        artifact_sources.append({"path": str(path), "schema_version": schema})
    return records, artifact_sources


def _signal_query_items(record):
    signals = []
    for item in record.get("people_also_ask", []):
        if isinstance(item, dict) and item.get("question"):
            signals.append((item["question"], "people_also_ask"))
    for item in record.get("related_searches", []):
        if isinstance(item, dict) and item.get("query"):
            signals.append((item["query"], "related_search"))
    query_tokens = set(_normalized_query(record.get("query", "")).split())
    query_tokens -= {"what", "why", "how", "when", "where", "best", "cost"}
    for item in record.get("organic", []):
        title = item.get("title") if isinstance(item, dict) else None
        if not isinstance(title, str) or "..." in title:
            continue
        lowered_title = title.lower()
        if any(
            marker in lowered_title for marker in ("@", "|", "about -", "showit blog")
        ):
            continue
        title_tokens = _normalized_query(title).split()
        if not 3 <= len(title_tokens) <= 12:
            continue
        if len(query_tokens.intersection(title_tokens)) >= 2:
            generic_terms = set(title_tokens).intersection(GENERIC_TITLE_TERMS)
            if len(generic_terms) < 3:
                continue
            signals.append((title, "serp_title_language"))
    return signals


def _intent_hypothesis(query, records):
    counts = defaultdict(int)
    for record in records:
        for signal in record.get("intent_signals", []):
            if isinstance(signal, dict) and signal.get("intent_hint"):
                counts[signal["intent_hint"]] += 1
    if not counts:
        lowered = query.lower()
        return (
            "informational"
            if re.match(r"^(what|why|how|when|where)", lowered)
            else "mixed"
        )
    return max(sorted(counts), key=lambda item: counts[item])


def _page_type(intent, query, config):
    category = _normalized_query(config.get("category_frame", ""))
    query_words = _normalized_query(query).split()
    if (
        intent == "informational"
        and category
        and any(word in query_words for word in category.split())
    ):
        return "pillar"
    if len(query_words) <= 5:
        return "standard"
    return "supporting"


def _candidate_title(query):
    query = " ".join(query.split()).strip()
    return query[:1].upper() + query[1:] if query else "Untitled article"


def _record_map(records):
    result = defaultdict(list)
    for record in records:
        query = record.get("normalized_query") or record.get("query")
        normalized = _normalized_query(query) if query else ""
        if normalized:
            result[normalized].append(record)
    return result


def _demand_map(records):
    result = defaultdict(list)
    for record in records:
        query = record.get("query")
        normalized = _normalized_query(query) if query else ""
        if normalized:
            result[normalized].append(record)
    return result


def _best_demand(records):
    normalized = [
        record for record in records if isinstance(record.get("demand"), dict)
    ]
    if normalized:
        return max(normalized, key=lambda item: item["demand"].get("score", 0))
    raw = [record for record in records if record.get("raw_market_demand")]
    return max(
        raw,
        key=lambda item: item["raw_market_demand"].get("avg_monthly_searches") or 0,
        default=None,
    )


def _direct_serp_record(records):
    return max(
        (record for record in records if record.get("organic") is not None),
        key=lambda item: len(item.get("organic", [])),
        default=None,
    )


def _serp_summary(record, *, direct):
    if not record:
        return None
    observations = record.get("competition_observations", {})
    return {
        "source": "serper",
        "evidence_scope": "direct_query" if direct else "parent_query_signal",
        "query": record.get("query"),
        "normalized_query": record.get("normalized_query"),
        "observed_at": record.get("retrieved_at"),
        "cache_key": record.get("cache_key"),
        "organic_result_count": observations.get(
            "organic_result_count", len(record.get("organic", []))
        ),
        "unique_hosts": observations.get("unique_hosts", 0),
        "people_also_ask_count": len(record.get("people_also_ask", [])),
        "related_search_count": len(record.get("related_searches", [])),
        "serp_features": record.get("serp_features", []),
        "intent_signals": record.get("intent_signals", []),
        "organic": [
            {
                "position": item.get("position"),
                "title": item.get("title"),
                "host": item.get("host"),
                "link": item.get("link"),
            }
            for item in record.get("organic", [])
            if isinstance(item, dict)
        ],
        "limitation": "Observed SERP composition is not organic keyword difficulty or traffic volume.",
    }


def _preliminary_priority(candidate):
    """Rank discovery evidence only; this is not the opportunity score."""
    serp = candidate.get("serp_evidence") or {}
    reasons = candidate.get("source_reasons", [])
    score = 0.0
    components = {}
    components["query_signals"] = min(40.0, len(reasons) * 10.0)
    score += components["query_signals"]
    components["coverage_gap"] = 30.0 if candidate.get("coverage_gap") else 0.0
    score += components["coverage_gap"]
    components["direct_serp_evidence"] = (
        20.0 if serp.get("evidence_scope") == "direct_query" else 0.0
    )
    score += components["direct_serp_evidence"]
    components["question_shape"] = (
        10.0 if candidate.get("intent_hypothesis") == "informational" else 0.0
    )
    score += components["question_shape"]
    return {
        "score": round(min(100.0, score), 1),
        "semantics": "discovery_triage_only",
        "components": components,
        "note": "Sorts observed SERP/query signals for editorial review; it is not demand, difficulty, traffic, or ranking probability.",
    }


def _candidate_from_query(
    query, reasons, *, serp_records, demand_records, site_corpus, config
):
    direct = _direct_serp_record(serp_records)
    demand = _best_demand(demand_records)
    coverage_gap = not _phrase_covered(query, site_corpus)
    intent = _intent_hypothesis(query, serp_records)
    missing = []
    if not demand or not isinstance(demand.get("demand"), dict):
        missing.append("normalized market-demand or site-opportunity evidence")
    if not direct:
        missing.append("a direct current SERP record for this query")
    elif (
        len(
            {item.get("host") for item in direct.get("organic", []) if item.get("host")}
        )
        < 5
    ):
        missing.append("at least five independent organic domains")
    missing.extend(
        [
            "manual editorial-difficulty/page-depth assessment",
            "verified product-fit and original-content-fit review",
        ]
    )
    topic = {
        "title": _candidate_title(query),
        "type": _page_type(intent, query, config),
        "target_query": query,
        "opportunity": {
            "candidate_id": _query_slug(query),
            "discovery_priority": None,
            "evidence_status": "discovery_only",
            "serp_evidence": None,
            "demand_evidence": demand.get("demand") if demand else None,
        },
    }
    candidate = {
        "candidate_id": _query_slug(query),
        "query": query,
        "suggested_title": _candidate_title(query),
        "page_type": topic["type"],
        "intent_hypothesis": intent,
        "source_reasons": sorted(set(reasons)),
        "coverage_gap": coverage_gap,
        "review_status": "ready_for_editorial_review"
        if coverage_gap
        else "covered_or_needs_review",
        "demand_evidence": demand.get("demand")
        if demand and demand.get("demand")
        else None,
        "raw_demand_evidence": (
            demand.get("raw_market_demand")
            or demand.get("raw_site_opportunity")
            or demand.get("raw")
            if demand
            else None
        ),
        "serp_evidence": _serp_summary(direct, direct=True)
        if direct
        else _serp_summary(serp_records[0], direct=False)
        if serp_records
        else None,
        "missing_evidence": missing,
        "topic": topic,
    }
    candidate["discovery_priority"] = _preliminary_priority(candidate)
    candidate["topic"]["opportunity"]["discovery_priority"] = candidate[
        "discovery_priority"
    ]
    candidate["topic"]["opportunity"]["serp_evidence"] = candidate["serp_evidence"]
    return candidate


def _write_json(path, payload, *, force=False):
    destination = Path(path)
    if destination.exists() and not force:
        raise SystemExit(
            f"refusing to overwrite existing output; pass --force: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_runtime_environment(env_file):
    if env_file:
        load_dotenv(env_file, override=False)
        return
    # Keep project .env support, then fall back to the owner's personal
    # secrets.env without ever printing or copying its values.
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    load_dotenv(Path.home() / ".claude" / "secrets.env", override=False)


def _collect_live(config, seeds, args):
    _load_runtime_environment(args.env_file)
    env_name = args.api_key_env or _config_serper(
        config, "api_key_env", "SERPER_API_KEY"
    )
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", env_name):
        raise ValueError(
            "api-key env name must contain uppercase letters, digits, and underscores"
        )
    api_key = os.environ.get(env_name)
    if not api_key:
        raise RuntimeError(f"{env_name} is missing from the project environment")

    gl = args.gl or _config_serper(config, "gl", "us")
    hl = args.hl or _config_serper(config, "hl", "en")
    location = args.location or _config_serper(config, "location", None)
    num = args.num or _config_serper(config, "num", DEFAULT_NUM_RESULTS)
    max_requests = args.max_requests or _config_serper(
        config, "max_requests_per_run", DEFAULT_MAX_REQUESTS
    )
    if not isinstance(num, int) or not 1 <= num <= MAX_NUM_RESULTS:
        raise ValueError(f"num must be between 1 and {MAX_NUM_RESULTS}")
    if not isinstance(max_requests, int) or max_requests < 1:
        raise ValueError("max-requests must be positive")
    cache_dir = args.cache_dir or _config_serper(
        config,
        "cache_dir",
        str(Path(__file__).resolve().parents[1] / "serp" / ".cache"),
    )
    common = {
        "gl": gl,
        "hl": hl,
        "num": num,
        "location": location,
        "cache_dir": cache_dir,
        "cache_ttl_seconds": args.cache_ttl_seconds
        or _config_serper(config, "cache_ttl_seconds", DEFAULT_CACHE_TTL_SECONDS),
        "refresh": args.refresh,
        "max_retries": args.max_retries
        if args.max_retries is not None
        else _config_serper(config, "max_retries", DEFAULT_MAX_RETRIES),
        "timeout": args.timeout
        or _config_serper(config, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        "delay": args.delay
        if args.delay is not None
        else _config_serper(config, "delay_seconds", 0.0),
    }
    initial = seeds[: min(args.seed_limit, max_requests)]
    initial_collection = collect_queries(
        initial, api_key, max_requests=max_requests, **common
    )
    signal_counts = defaultdict(int)
    signal_reasons = defaultdict(set)
    signal_display = {}
    for record in initial_collection["records"]:
        for query, reason in _signal_query_items(record):
            normalized = _normalized_query(query)
            signal_counts[normalized] += 1
            signal_reasons[normalized].add(reason)
            signal_display.setdefault(normalized, query)
    follow_up = []
    for normalized, _count in sorted(
        signal_counts.items(), key=lambda item: (-item[1], item[0])
    ):
        if normalized not in {_normalized_query(seed) for seed in initial}:
            follow_up.append(signal_display[normalized])
        if len(follow_up) >= args.candidate_limit:
            break
    remaining = max_requests - len(initial)
    follow_up = follow_up[: max(0, remaining)]
    follow_up_collection = (
        collect_queries(
            follow_up, api_key, max_requests=max(1, len(follow_up)), **common
        )
        if follow_up
        else {
            "schema_version": SERP_COLLECTION_SCHEMA,
            "records": [],
            "errors": [],
            "request_budget": {"api_requests": 0, "cache_hits": 0},
        }
    )
    initial_records = [
        {**record, "planner_stage": "initial"}
        for record in initial_collection["records"]
    ]
    follow_up_records = [
        {**record, "planner_stage": "follow_up"}
        for record in follow_up_collection["records"]
    ]
    records = initial_records + follow_up_records
    source_reasons = {
        normalized: sorted(reasons) for normalized, reasons in signal_reasons.items()
    }
    for query in initial:
        source_reasons.setdefault(_normalized_query(query), []).append(
            "configured_seed"
        )
    collection = {
        "schema_version": SERP_COLLECTION_SCHEMA,
        "collected_at": _now(),
        "source": "serper",
        "request_budget": {
            "max_requests_per_run": max_requests,
            "api_requests": initial_collection["request_budget"].get("api_requests", 0)
            + follow_up_collection["request_budget"].get("api_requests", 0),
            "cache_hits": initial_collection["request_budget"].get("cache_hits", 0)
            + follow_up_collection["request_budget"].get("cache_hits", 0),
        },
        "errors": initial_collection.get("errors", [])
        + follow_up_collection.get("errors", []),
        "records": records,
        "planner": {
            "initial_queries": initial,
            "follow_up_queries": follow_up,
            "signal_reasons": source_reasons,
        },
    }
    return collection


def build_plan(
    config,
    *,
    serp_records=None,
    demand_records=None,
    seeds=None,
    max_candidates=25,
    source_artifacts=None,
):
    serp_records = serp_records or []
    demand_records = demand_records or []
    seed_values = _unique_queries(seeds or suggest_seeds(config))
    serp_by_query = _record_map(serp_records)
    demand_by_query = _demand_map(demand_records)
    candidate_reasons = defaultdict(set)
    candidate_display = {}
    for seed in seed_values:
        normalized = _normalized_query(seed)
        candidate_reasons[normalized].add("configured_seed")
        candidate_display.setdefault(normalized, seed)
    for record in serp_records:
        if record.get("planner_stage") == "follow_up":
            # Follow-up results verify selected candidates. Do not recursively
            # mine their titles into a third generation of brand/page names.
            continue
        parent = record.get("normalized_query") or record.get("query")
        for query, reason in _signal_query_items(record):
            normalized = _normalized_query(query)
            candidate_reasons[normalized].add(f"{reason}_from:{parent}")
            candidate_display.setdefault(normalized, query)
    for record in demand_records:
        query = record.get("query")
        if query:
            normalized = _normalized_query(query)
            candidate_reasons[normalized].add("demand_artifact")
            candidate_display.setdefault(normalized, query)

    candidates = []
    skipped = []
    site_corpus = _site_corpus(config)
    for normalized, reasons in candidate_reasons.items():
        query = candidate_display.get(normalized)
        if not query:
            continue
        if not _phrase_covered(query, site_corpus):
            candidates.append(
                _candidate_from_query(
                    query,
                    reasons,
                    serp_records=serp_by_query.get(normalized, []),
                    demand_records=demand_by_query.get(normalized, []),
                    site_corpus=site_corpus,
                    config=config,
                )
            )
        else:
            skipped.append(
                {
                    "query": query,
                    "reason": "existing_pages_or_topic_backlog_overlap",
                }
            )
    candidates.sort(
        key=lambda item: (-item["discovery_priority"]["score"], item["query"].lower())
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "site": {
            "site_name": config.get("site_name", ""),
            "domain": config.get("domain", ""),
            "category_frame": config.get("category_frame", ""),
            "icp": config.get("icp", ""),
        },
        "semantics": {
            "discovery_priority": "triage-only ordering of observed query/SERP signals",
            "serper": "current SERP composition and query language; not traffic volume or organic keyword difficulty",
            "demand": "only normalized Keyword Planner or Search Console artifacts can populate measured demand/site opportunity",
            "promotion": "a candidate still needs editorial difficulty, product fit, content fit, freshness, and confidence evidence before score_opportunities.py can mark it pursue",
        },
        "source_artifacts": source_artifacts or [],
        "candidate_count": min(len(candidates), max_candidates),
        "candidates": candidates[:max_candidates],
        "skipped": skipped,
    }


def print_plan(plan):
    print("QUERY | TRIAGE | STATUS | SERP | DEMAND | MISSING EVIDENCE")
    for candidate in plan["candidates"]:
        serp = candidate.get("serp_evidence") or {}
        demand = "measured" if candidate.get("demand_evidence") else "unmeasured"
        missing = "; ".join(candidate.get("missing_evidence", [])) or "-"
        print(
            f"{candidate['query']} | {candidate['discovery_priority']['score']} | "
            f"{candidate['review_status']} | {serp.get('evidence_scope', 'none')} | {demand} | {missing}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Discover and triage evidence-backed article opportunities"
    )
    parser.add_argument("--config", required=True, help="site-config.<project>.json")
    parser.add_argument("--seed", action="append", help="seed query; repeat as needed")
    parser.add_argument("--seed-file", help="newline-separated seed queries")
    parser.add_argument(
        "--serp",
        action="append",
        help="saved Serper collection or record JSON; repeatable",
    )
    parser.add_argument(
        "--demand",
        action="append",
        help="normalized demand, raw Keyword Planner, or GSC JSON; repeatable",
    )
    parser.add_argument(
        "--live-serp",
        action="store_true",
        help="collect bounded Serper evidence using the runtime API key",
    )
    parser.add_argument(
        "--env-file", help="optional env file; values are never printed"
    )
    parser.add_argument(
        "--api-key-env",
        help="Serper API key variable; defaults to config or SERPER_API_KEY",
    )
    parser.add_argument("--gl", help="Google country code")
    parser.add_argument("--hl", help="Google language code")
    parser.add_argument("--location", help="optional Serper location")
    parser.add_argument("--num", type=int, help="organic results per query")
    parser.add_argument("--cache-dir", help="Serper cache directory")
    parser.add_argument("--cache-ttl-seconds", type=int)
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--max-retries", type=int)
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--delay", type=float)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--seed-limit", type=int, default=DEFAULT_SEED_LIMIT)
    parser.add_argument("--candidate-limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
    parser.add_argument("--max-candidates", type=int, default=25)
    parser.add_argument(
        "--serp-out", help="write the live Serper evidence collection here"
    )
    parser.add_argument("--out", required=True, help="opportunity plan JSON output")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.seed_limit < 1 or args.candidate_limit < 1 or args.max_candidates < 1:
        parser.error("seed-limit, candidate-limit, and max-candidates must be positive")
    config = load_config(args.config)
    file_seeds = []
    if args.seed_file:
        file_seeds = [
            line.strip()
            for line in Path(args.seed_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    seeds = _unique_queries((args.seed or []) + file_seeds) or suggest_seeds(config)
    serp_records = []
    source_artifacts = []
    if args.serp:
        serp_records, sources = _load_serp_records(args.serp)
        source_artifacts.extend(sources)
    if args.live_serp:
        try:
            collection = _collect_live(config, _unique_queries(seeds), args)
        except (RuntimeError, ValueError, SerperError) as exc:
            raise SystemExit(f"live Serper discovery failed: {exc}") from exc
        serp_records.extend(collection["records"])
        if args.serp_out:
            _write_json(args.serp_out, collection, force=args.force)
            source_artifacts.append(
                {"path": str(args.serp_out), "schema_version": SERP_COLLECTION_SCHEMA}
            )
    demand_records = []
    if args.demand:
        demand_records, sources = _load_demand_records(args.demand)
        source_artifacts.extend(sources)
    plan = build_plan(
        config,
        serp_records=serp_records,
        demand_records=demand_records,
        seeds=seeds,
        max_candidates=args.max_candidates,
        source_artifacts=source_artifacts,
    )
    print_plan(plan)
    _write_json(args.out, plan, force=args.force)
    print(f"\nOpportunity plan written to {args.out}")


if __name__ == "__main__":
    main()
