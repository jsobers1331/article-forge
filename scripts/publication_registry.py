"""Local publication provenance and reviewable measured outcomes. Never publishes.

Use owner-supplied receipts/exports; missing metrics remain unknown. Every record
retains original URLs and source windows. Registry writes are explicit CLI actions.
"""

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from evidence_contract import age_days, object_hash

SCHEMA = "article-forge.publication-registry.v1"
OBSERVATION_SCHEMA = "article-forge.outcome-observation.v1"
ACTIONS = {"keep", "improve", "consolidate", "refresh", "defer"}


def url_key(url, identity):
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("absolute public URL required")
    host = parsed.hostname.lower().rstrip(".")
    canonical = identity["canonical_host"].lower()
    equivalents = {h.lower() for h in identity.get("equivalent_hosts", [])}
    if host == canonical or host in equivalents:
        host = canonical
    else:
        raise ValueError("URL outside the explicitly configured site identity")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("nonstandard URL port requires explicit review")
    # Keep case, trailing slashes and query strings; equivalence is not assumed.
    return urlunsplit(("https", host, parsed.path or "/", parsed.query, ""))


def empty_registry(identity):
    return {
        "schema_version": SCHEMA,
        "site_identity": identity,
        "publications": [],
        "observations": [],
    }


def add_publication(registry, publication):
    if registry.get("schema_version") != SCHEMA:
        raise ValueError("unsupported registry schema")
    required = (
        "candidate_id",
        "target_query",
        "evidence_packet_sha256",
        "draft_sha256",
        "reviewer",
        "provider",
        "model",
        "canonical_url",
        "published_at",
        "content_version",
        "forge_commit",
        "review_windows_days",
        "locale",
        "conversion_definition",
    )
    missing = [k for k in required if publication.get(k) in (None, "", [])]
    if missing:
        raise ValueError("publication missing provenance: " + ", ".join(missing))
    if publication["review_windows_days"] != [30, 60, 90]:
        raise ValueError("declare 30/60/90-day cohort review windows")
    age = age_days(publication["published_at"])
    if age is None or age < 0:
        raise ValueError(
            "publication time must be a real timezone-aware past observation"
        )
    key = url_key(publication["canonical_url"], registry["site_identity"])
    identifier = object_hash(
        {"url": key, "content_version": publication["content_version"]}
    )[:24]
    row = {**publication, "publication_id": identifier, "url_key": key}
    existing = [
        p for p in registry["publications"] if p["publication_id"] == identifier
    ]
    if existing:
        if existing[0] != row:
            raise ValueError(
                "immutable content-version provenance changed; record a new version"
            )
        return identifier
    registry["publications"].append(row)
    return identifier


def add_observation(registry, observation):
    if observation.get("schema_version") != OBSERVATION_SCHEMA:
        raise ValueError("outcome observation schema required")
    pub = next(
        (
            p
            for p in registry["publications"]
            if p["publication_id"] == observation.get("publication_id")
        ),
        None,
    )
    if pub is None:
        raise ValueError("unknown publication/content version")
    if url_key(observation["url"], registry["site_identity"]) != pub["url_key"]:
        raise ValueError("observation URL differs from publication")
    start = date.fromisoformat(observation["observed_from"])
    end = date.fromisoformat(observation["observed_to"])
    if (
        end < start
        or end > date.today()
        or start < datetime.fromisoformat(pub["published_at"]).date()
    ):
        raise ValueError("invalid/pre-publication/future observation window")
    if observation.get("locale") != pub["locale"]:
        raise ValueError("observation locale differs from publication cohort")
    if observation.get("conversion_definition") != pub["conversion_definition"]:
        raise ValueError("conversion/attribution definition differs")
    if not observation.get("source") or not observation.get("source_sha256"):
        raise ValueError("observation needs source identity and artifact hash")
    for key in (
        "impressions",
        "relevant_impressions",
        "clicks",
        "qualified_actions",
        "conversions",
    ):
        value = observation.get(key)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
        ):
            raise ValueError(f"invalid metric {key}; use null for unknown")
    for key in ("accessible", "indexed"):
        if observation.get(key) is not None and not isinstance(observation[key], bool):
            raise ValueError(f"{key} must be bool or null")
    if observation.get("relevant_impressions") is not None and not observation.get(
        "query_evidence"
    ):
        raise ValueError(
            "relevant impressions require query evidence; anonymous query omissions stay unknown"
        )
    for citation in observation.get("ai_observations", []):
        if not all(
            citation.get(k) is not None
            for k in (
                "engine",
                "query",
                "locale",
                "observed_at",
                "method",
                "available",
                "citation_observed",
            )
        ):
            raise ValueError(
                "AI observation needs engine/query/locale/time/method and separate availability/citation"
            )
        if citation.get("citation_observed") and not citation.get("cited_url"):
            raise ValueError("observed AI citation needs cited URL")
        if age_days(citation["observed_at"]) is None:
            raise ValueError("AI observation time requires timezone")
    row = {
        **observation,
        "url_key": pub["url_key"],
        "days": (end - start).days + 1,
        "observation_id": object_hash(observation),
    }
    if not any(
        o["observation_id"] == row["observation_id"] for o in registry["observations"]
    ):
        registry["observations"].append(row)


def observation_from_exports(
    registry, publication_id, gsc, *, indexing=None, access=None, actions=None
):
    """Join existing read-only collectors. Export omissions remain unknown.

    Query rows undercount anonymized queries. Page totals are not market demand.
    Locale is the publication cohort; export_scope explicitly records whether
    the collector exported global or country/device-specific observations.
    """
    pub = next(
        p for p in registry["publications"] if p["publication_id"] == publication_id
    )
    if gsc.get("schema_version") != "article-forge.gsc.v1" or "page" not in gsc.get(
        "dimensions", []
    ):
        raise ValueError("versioned GSC export with page dimension required")

    def matching(url):
        try:
            return url_key(url, registry["site_identity"]) == pub["url_key"]
        except (ValueError, TypeError):
            return False

    rows = [r for r in gsc.get("rows", []) if matching(r.get("page"))]
    relevant = [
        r for r in rows if r.get("query", "").lower() == pub["target_query"].lower()
    ]
    index_rows = []
    if indexing is not None:
        if indexing.get("schema_version") != "article-forge.indexing.v1":
            raise ValueError("versioned indexation export required")
        index_rows = [r for r in indexing.get("records", []) if matching(r.get("url"))]
    index_status = index_rows[0].get("status") if len(index_rows) == 1 else None
    indexed = (
        True
        if index_status == "indexed"
        else False
        if index_status == "not_indexed"
        else None
    )
    if access is not None and (
        not matching(access.get("url")) or age_days(access.get("observed_at")) is None
    ):
        raise ValueError(
            "access observation must name the URL and dated observation method"
        )
    if actions is not None and (
        not matching(actions.get("url"))
        or actions.get("conversion_definition") != pub["conversion_definition"]
        or actions.get("observed_from") != gsc["date_range"]["start"]
        or actions.get("observed_to") != gsc["date_range"]["end"]
        or not actions.get("source")
        or not actions.get("source_sha256")
    ):
        raise ValueError(
            "action export must match the URL, attribution definition and exact period"
        )
    return {
        "schema_version": OBSERVATION_SCHEMA,
        "publication_id": publication_id,
        "url": pub["canonical_url"],
        "observed_from": gsc["date_range"]["start"],
        "observed_to": gsc["date_range"]["end"],
        "locale": pub["locale"],
        "export_scope": {
            "dimensions": gsc["dimensions"],
            "property": gsc.get("property"),
            "locale_filter": "unavailable in collector export; do not infer cohort-specific demand",
        },
        "conversion_definition": pub["conversion_definition"],
        "aggregation": gsc["dimensions"],
        "source": "google_search_console",
        "source_sha256": object_hash(gsc),
        "source_artifacts": {
            "gsc": object_hash(gsc),
            "indexing": object_hash(indexing) if indexing else None,
            "access": object_hash(access) if access else None,
            "actions": object_hash(actions) if actions else None,
        },
        "original_urls": sorted({r["page"] for r in rows}),
        "accessible": access.get("accessible") if access else None,
        "access_checked_at": access.get("observed_at") if access else None,
        "indexed": indexed,
        "index_checked_at": (indexing or {}).get("checked_at"),
        "impressions": sum(r["impressions"] for r in rows) if rows else None,
        "clicks": sum(r["clicks"] for r in rows) if rows else None,
        "relevant_clicks": sum(r["clicks"] for r in relevant) if relevant else None,
        "relevant_impressions": sum(r["impressions"] for r in relevant)
        if relevant
        else None,
        "query_evidence": [r["query"] for r in relevant] or None,
        "qualified_actions": (actions or {}).get("qualified_actions"),
        "conversions": (actions or {}).get("conversions"),
        "query_omissions": "Anonymous and truncated query omissions are not zero. Query totals may undercount.",
        "seasonality": None,
        "limits": "Collector page rows describe observed site performance, not market demand or causation.",
    }


def publication_from_report(report, owner_receipt):
    """Join a passing draft's actual hashes/provider/reviewer to a confirmed URL."""
    if report.get("publication_status") != "ready_for_human_review" or not report.get(
        "gate_assessment", {}
    ).get("all_pass"):
        raise ValueError("blocked draft cannot be registered as a reviewed publication")
    provenance = report.get("provenance") or {}
    review = provenance.get("human_review") or {}
    packet_keys = (
        "manifest_sha256",
        "brief_sha256",
        "ledger_sha256",
        "snapshot_sha256",
        "config_sha256",
    )
    return {
        **owner_receipt,
        "candidate_id": provenance.get("candidate_id")
        or provenance.get("topic_sha256"),
        "target_query": report["target_query"],
        "evidence_packet_sha256": object_hash(
            {k: provenance.get(k) for k in packet_keys}
        ),
        "draft_sha256": provenance.get("draft_sha256"),
        "reviewer": review.get("reviewer"),
        "provider": provenance.get("provider") or "owner_supplied",
        "model": provenance.get("model") or "not_recorded",
        "forge_commit": provenance.get("forge_commit"),
        "generation_provenance": provenance,
    }


def compare_periods(before, after):
    """Compare rates only for genuinely comparable attribution/aggregation."""
    keys = ("locale", "source", "conversion_definition", "aggregation", "export_scope")
    reasons = [f"{k} differs" for k in keys if before.get(k) != after.get(k)]
    if before.get("content_edits") or after.get("content_edits"):
        reasons.append("content edits confound comparison")
    if (
        before.get("seasonality") != after.get("seasonality")
        or before.get("seasonality") is None
    ):
        reasons.append("seasonality not confirmed comparable")
    if before["observed_to"] >= after["observed_from"]:
        reasons.append("periods overlap or are not chronological")
    deltas = {}
    if not reasons:
        for metric in ("impressions", "clicks", "qualified_actions", "conversions"):
            a, b = before.get(metric), after.get(metric)
            if a is not None and b is not None:
                deltas[metric] = {
                    "before_per_day": a / before["days"],
                    "after_per_day": b / after["days"],
                    "change_per_day": b / after["days"] - a / before["days"],
                }
    return {
        "comparable": not reasons,
        "reasons": reasons,
        "rates": deltas,
        "limits": "Rates normalize window duration. This observational comparison does not establish causation.",
    }


def review_registry(registry, as_of=None, min_days=7):
    as_of = as_of or datetime.now(timezone.utc)
    rows = []
    latest_versions = {}
    for pub in registry["publications"]:
        old = latest_versions.get(pub["url_key"])
        if old is None or pub["published_at"] > old["published_at"]:
            latest_versions[pub["url_key"]] = pub
    for pub in latest_versions.values():
        age = age_days(pub["published_at"], as_of)
        due = [w for w in pub["review_windows_days"] if age >= w]
        obs = sorted(
            [
                o
                for o in registry["observations"]
                if o["publication_id"] == pub["publication_id"]
            ],
            key=lambda o: o["observed_to"],
        )
        current = obs[-1] if obs else None
        clicks = (
            (
                current.get("relevant_clicks")
                if "relevant_clicks" in current
                else current.get("clicks")
            )
            if current
            else None
        )
        action, stage, reason = (
            "defer",
            "evidence",
            "No valid measured observation for this version",
        )
        if not due:
            reason = "Declared cohort review window is not due yet"
        elif current is not None:
            if (as_of.date() - date.fromisoformat(current["observed_to"])).days > 30:
                reason = "Observation is stale for the current review; collect a comparable recent period"
            elif current.get("accessible") is not True:
                action, stage, reason = (
                    "improve" if current.get("accessible") is False else "defer",
                    "accessible",
                    "Resolve accessibility or collect dated access evidence",
                )
            elif current.get("indexed") is not True:
                action, stage, reason = (
                    "improve" if current.get("indexed") is False else "defer",
                    "indexed",
                    "Resolve indexation or collect index evidence",
                )
            elif current.get("sources_stale"):
                action, stage, reason = (
                    "refresh",
                    "evidence",
                    "Bound claims/source snapshots need re-verification",
                )
            elif current["days"] < min_days:
                reason = f"Insufficient observation window (<{min_days} days)"
            elif current.get("relevant_impressions") is None:
                stage, reason = (
                    "relevant_impressions",
                    "Relevant-query evidence missing; anonymous omissions prevent inference",
                )
            elif current["relevant_impressions"] == 0:
                stage, reason = (
                    "relevant_impressions",
                    "No relevant impressions observed in this window; review demand/page choice",
                )
            elif clicks is None:
                stage, reason = (
                    "clicks",
                    "Relevant impressions observed; scoped click measurement missing",
                )
            elif clicks == 0:
                action, stage, reason = (
                    "improve",
                    "clicks",
                    "Relevant impressions present; review answer, title and click intent",
                )
            elif current.get("qualified_actions") is None:
                stage, reason = (
                    "qualified_actions",
                    "Clicks observed; downstream action measurement missing",
                )
            elif current["qualified_actions"] == 0:
                action, stage, reason = (
                    "improve",
                    "qualified_actions",
                    "Review the next action and conversion fit",
                )
            else:
                action, stage, reason = (
                    "keep",
                    "qualified_actions",
                    "Qualified actions observed; retain and monitor at the next window",
                )
            overlap = current.get("overlap_review") or {}
            if (
                stage in {"clicks", "qualified_actions"}
                and overlap.get("reviewer")
                and overlap.get("evidence")
                and age_days(overlap.get("reviewed_at"), as_of) is not None
                and 0 <= age_days(overlap.get("reviewed_at"), as_of) <= 30
                and overlap.get("decision") == "consolidate"
            ):
                action, reason = (
                    "consolidate",
                    "Human-reviewed content/intent overlap supports a consolidation proposal",
                )
        comparison = compare_periods(obs[-2], obs[-1]) if len(obs) > 1 else None
        rows.append(
            {
                "publication_id": pub["publication_id"],
                "canonical_url": pub["canonical_url"],
                "content_version": pub["content_version"],
                "due_windows_days": due,
                "action": action,
                "diagnostic_stage": stage,
                "reason": reason,
                "evidence": current,
                "comparison": comparison,
                "approval_required": True,
            }
        )
    return {
        "schema_version": "article-forge.outcome-review.v1",
        "as_of": as_of.isoformat(),
        "recommendations": rows,
        "limits": "One recommendation per URL; proposals only. Availability, indexing, citations, traffic and conversions are distinct.",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Record local publication provenance or review supplied outcomes; never publishes"
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument(
        "--identity", help="JSON site identity when initializing a registry"
    )
    parser.add_argument(
        "--publication", help="Owner-confirmed publication receipt JSON"
    )
    parser.add_argument("--observation", help="Versioned measured observation JSON")
    parser.add_argument("--review-out", help="Write reviewable recommendations JSON")
    parser.add_argument(
        "--report", help="Passing generation report to bind publication receipt"
    )
    parser.add_argument("--gsc")
    parser.add_argument("--publication-id")
    parser.add_argument("--indexing")
    parser.add_argument("--access")
    parser.add_argument("--actions")
    args = parser.parse_args()
    path = Path(args.registry)
    path.parent.mkdir(parents=True, exist_ok=True)
    import fcntl

    with path.with_suffix(path.suffix + ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        registry = (
            json.loads(path.read_text())
            if path.exists()
            else empty_registry(json.loads(Path(args.identity).read_text()))
        )
        if registry.get("schema_version") != SCHEMA:
            raise SystemExit("Unsupported registry schema")
        if args.publication:
            receipt = json.loads(Path(args.publication).read_text())
            if args.report:
                receipt = publication_from_report(
                    json.loads(Path(args.report).read_text()), receipt
                )
            add_publication(registry, receipt)
        if args.observation:
            add_observation(registry, json.loads(Path(args.observation).read_text()))
        if args.gsc:
            if not args.publication_id:
                parser.error("--publication-id required with --gsc")
            exports = {
                key: json.loads(Path(getattr(args, key)).read_text())
                if getattr(args, key)
                else None
                for key in ("indexing", "access", "actions")
            }
            add_observation(
                registry,
                observation_from_exports(
                    registry,
                    args.publication_id,
                    json.loads(Path(args.gsc).read_text()),
                    **exports,
                ),
            )
        if args.publication or args.observation or args.gsc or not path.exists():
            from generate_article import _atomic_write

            _atomic_write(path, json.dumps(registry, indent=2) + "\n")
        if args.review_out:
            from generate_article import _atomic_write

            _atomic_write(
                Path(args.review_out),
                json.dumps(review_registry(registry), indent=2) + "\n",
            )
    print(
        f"Local registry: {len(registry['publications'])} content versions; {len(registry['observations'])} observations"
    )


if __name__ == "__main__":
    main()
