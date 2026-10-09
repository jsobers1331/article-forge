"""Shared SERP snapshot contract. Legacy snapshots are research leads only."""

from urllib.parse import urlsplit

from publicsuffix2 import get_sld
from evidence_contract import age_days, object_hash, text_hash

SCHEMA = "article-forge.serp-snapshot.v2"


def independent_domain(url):
    if not isinstance(url, str):
        return ""
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    return get_sld(host, strict=True) or ""


def normalize_query(query):
    return " ".join(str(query or "").lower().split())


def validate_snapshot(snapshot, target_query, policy=None, now=None):
    policy = policy or {}
    reasons = []
    if not isinstance(snapshot, dict):
        return {
            "valid": False,
            "reasons": ["snapshot is missing or not an object"],
            "independent_domains": 0,
        }
    if snapshot.get("schema_version") != SCHEMA:
        reasons.append(
            "legacy/missing snapshot contract; recollect or explicitly migrate provenance"
        )
    query = normalize_query(target_query)
    if not query:
        reasons.append("target query is required")
    if query != normalize_query(snapshot.get("keyword")):
        cluster = snapshot.get("reviewed_query_cluster") or {}
        age = (
            age_days(cluster.get("reviewed_at"), now)
            if isinstance(cluster, dict)
            else None
        )
        if (
            not isinstance(cluster, dict)
            or not cluster.get("reviewer")
            or not cluster.get("reason")
            or age is None
            or not 0 <= age <= policy.get("max_age_days", 30)
            or not isinstance(cluster.get("queries"), list)
            or query not in [normalize_query(q) for q in cluster.get("queries", [])]
        ):
            reasons.append(
                "snapshot query differs from target; explicit reviewed query cluster required"
            )
    age = age_days(snapshot.get("captured_at"), now)
    if age is None or not 0 <= age <= policy.get("max_age_days", 30):
        reasons.append("missing, future, timezone-less or expired capture time")
    locale = snapshot.get("locale") or {}
    if not isinstance(locale, dict):
        locale = {}
    for key in ("country", "language"):
        if not isinstance(locale.get(key), str) or not locale[key].strip():
            reasons.append(f"missing locale {key}")
        elif policy.get(key) and locale[key].lower() != policy[key].lower():
            reasons.append(f"locale {key} mismatch")
    if policy.get("location") and normalize_query(
        locale.get("location")
    ) != normalize_query(policy["location"]):
        reasons.append("relevant location mismatch")
    provenance = snapshot.get("provenance") or {}
    if (
        not isinstance(provenance, dict)
        or not provenance.get("method")
        or not provenance.get("source")
    ):
        reasons.append("missing source provenance")
    competitors = snapshot.get("competitors")
    if not isinstance(competitors, list):
        competitors = []
        reasons.append("competitors must be a list")
    domains = set()
    for index, page in enumerate(competitors):
        if not isinstance(page, dict):
            reasons.append(f"competitor {index}: malformed")
            continue
        domain = independent_domain(page.get("url", ""))
        if not domain or urlsplit(page.get("url", "")).scheme not in {"http", "https"}:
            reasons.append(f"competitor {index}: invalid independent domain")
        else:
            domains.add(domain)
        extraction = page.get("extraction") or {}
        if (
            not isinstance(extraction, dict)
            or extraction.get("status") != "complete"
            or extraction.get("complete") is not True
        ):
            reasons.append(f"competitor {index}: extraction incomplete/failed")
        for key in ("subtopics", "entities", "headings"):
            if not isinstance(page.get(key), list) or any(
                not isinstance(s, str) or not s.strip() for s in page[key]
            ):
                reasons.append(
                    f"competitor {index}: missing/malformed {key} extraction"
                )
        source = page.get("source_snapshot") or {}
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("text"), str)
            or not source.get("text", "").strip()
            or source.get("sha256") != text_hash(source["text"])
            or source.get("source_url") != page.get("url")
        ):
            reasons.append(
                f"competitor {index}: missing/changed source snapshot provenance"
            )
        source_age = (
            age_days(source.get("captured_at"), now)
            if isinstance(source, dict)
            else None
        )
        if source_age is None or not 0 <= source_age <= policy.get("max_age_days", 30):
            reasons.append(f"competitor {index}: source snapshot expired/undated")
        if isinstance(extraction, dict) and extraction.get("sha256") != object_hash(
            {k: page.get(k) for k in ("subtopics", "entities", "headings")}
        ):
            reasons.append(f"competitor {index}: extraction binding changed")
    if len(domains) < policy.get("min_domains", 5):
        reasons.append("insufficient independent-domain sample")
    return {
        "valid": not reasons,
        "reasons": reasons,
        "independent_domains": len(domains),
        "snapshot_sha256": object_hash(snapshot),
    }


def policy_for(config):
    research = config.get("research") or {}
    serper = research.get("serper") or {}
    return {
        "country": serper.get("gl", "us"),
        "language": serper.get("hl", "en"),
        "location": serper.get("location"),
        **(config.get("serp_policy") or {}),
    }


def snapshot_gate(snapshot, query, config):
    verdict = validate_snapshot(snapshot, query, policy_for(config))
    return (
        ("PASS", "current query/locale/provenance/extraction contract passed")
        if verdict["valid"]
        else ("WARN", "; ".join(verdict["reasons"]))
    )
