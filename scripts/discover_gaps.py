"""Pre-topic-selection research pass — see DISCOVERY.md for the full ruleset.

Division of labor (same as score_article.py): this script has no web-search
access. An orchestrating agent builds `discovery_snapshot.json` from real
searches/fetches; this script does the deterministic arithmetic on it.

Produces "coverage-gap candidates," never "ranking opportunities" — there is
no search-volume, domain-authority, or backlink signal here, only lexical
overlap between top-ranking competitor pages and your own page titles/topic
backlog. Every finding is for a human to read and decide on; nothing here is
ever wired into generate_prompt.py.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generate_prompt import load_config  # noqa: E402
from score_article import _norm, _phrase_covered, consensus_items  # noqa: E402

SEED_TEMPLATES = [
    "what is {category_frame}",
    "best {category_frame}",
    "how much does {category_frame} cost",
    "how to choose {category_frame}",
]

MARKETING_BUZZWORDS = {
    "ai-powered", "enterprise-grade", "best-in-class", "industry-leading",
    "cutting-edge", "all-in-one", "game-changing", "revolutionary",
    "next-generation", "world-class", "seamless", "robust", "turnkey",
}


def load_snapshot(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def suggest_seeds(config):
    category_frame = config.get("category_frame", "")
    seeds = [t.format(category_frame=category_frame) for t in SEED_TEMPLATES]
    for c in config.get("competitors", []):
        seeds.append(f"{category_frame} vs {c['name']}")
    seen = set()
    out = []
    for s in seeds:
        n = _norm(s)
        if n not in seen:
            seen.add(n)
            out.append(s)
    return out


def dedupe_by_domain(competitors):
    """One entry per distinct domain — the same domain ranking twice in one
    cluster is one data point, not two (pooling duplicates inflates
    consensus counts without adding real independent signal)."""
    seen = {}
    for c in competitors:
        domain = c.get("domain") or re.sub(r"^https?://(www\.)?", "", c.get("url", "")).split("/")[0]
        if domain not in seen or c.get("position", 999) < seen[domain].get("position", 999):
            seen[domain] = c
    return list(seen.values())


def cluster_consensus(cluster, key):
    competitors = dedupe_by_domain(cluster.get("competitors", []))
    if len(competitors) < 2:
        return set(), {}
    return consensus_items(competitors, key)


def site_corpus_text(config):
    parts = []
    for t in config.get("topic_backlog", []):
        parts.append(t.get("title", ""))
        parts.append(t.get("target_query", ""))
    for path in config.get("existing_pages", []):
        parts.append(re.sub(r"[/\-]+", " ", path))
    return _norm(" ".join(parts))


def feasibility_text(config):
    """Deliberately excludes coming_soon_features — a subtopic that only
    matches a not-yet-real feature must NOT be marked feasible, or this
    would recommend writing about something that doesn't exist yet."""
    facts = config.get("verified_facts", {})
    parts = [config.get("canonical_definition_sentence", ""), config.get("category_frame", "")]
    for d in facts.get("real_differentiators", []):
        parts.append(d["feature"] if isinstance(d, dict) else d)
    parts.append(facts.get("pricing_and_billing", {}).get("note", ""))
    return _norm(" ".join(parts))


def feasibility_label(item, feasibility_corpus):
    if _phrase_covered(item, feasibility_corpus):
        return "possibly supported by verified_facts — verify manually before writing"
    return "no matching verified_facts entry — do not write until you've verified this fact is real"


def classify_market_term(term, known_competitor_names):
    t = term.lower()
    if any(name.lower() == t for name in known_competitor_names):
        return "competitor/brand name"
    if any(buzz in t for buzz in MARKETING_BUZZWORDS):
        return "positioning language"
    if term[:1].isupper() and len(term.split()) <= 3:
        return "competitor/brand name"
    return "generic term"


def build_gap_candidates(config, clusters):
    site_corpus = site_corpus_text(config)
    feas_corpus = feasibility_text(config)

    item_clusters = {}   # normalized item -> {cluster_id: within_cluster_count}
    item_display = {}    # normalized item -> original display string

    for cluster in clusters:
        cid = cluster.get("cluster_id", "unlabeled")
        for key in ("subtopics", "entities"):
            consensus, counts = cluster_consensus(cluster, key)
            for item in consensus:
                if _phrase_covered(item, site_corpus):
                    continue  # our own titles/queries already mention this — not a gap
                item_clusters.setdefault(item, {})[cid] = counts[item]
                item_display.setdefault(item, item)

    cross_cluster, single_cluster = [], []
    for item, per_cluster_counts in item_clusters.items():
        n_clusters = len(per_cluster_counts)
        total_count = sum(per_cluster_counts.values())
        entry = {
            "item": item_display[item],
            "clusters": sorted(per_cluster_counts.keys()),
            "within_cluster_counts": per_cluster_counts,
            "feasibility": feasibility_label(item, feas_corpus),
            "coverage_note": "no title/query overlap found in your existing_pages/topic_backlog — unconfirmed gap, read your own pages to confirm",
        }
        (cross_cluster if n_clusters >= 2 else single_cluster).append((n_clusters, total_count, entry))

    cross_cluster.sort(key=lambda x: (-x[0], -x[1]))
    single_cluster.sort(key=lambda x: -x[1])
    return [e for _, _, e in cross_cluster], [e for _, _, e in single_cluster]


def build_market_language(config, clusters):
    known_names = [c["name"] for c in config.get("competitors", [])]
    own_text = _norm(" ".join([
        config.get("canonical_definition_sentence", ""),
        config.get("category_frame", ""),
        " ".join(
            (d["feature"] if isinstance(d, dict) else d)
            for d in config.get("verified_facts", {}).get("real_differentiators", [])
        ),
    ]))

    seen_terms = {}
    for cluster in clusters:
        for c in dedupe_by_domain(cluster.get("competitors", [])):
            for term in c.get("brand_terms", []) + c.get("entities", []):
                n = _norm(term)
                if n and n not in seen_terms:
                    seen_terms[n] = term

    findings = []
    for norm_term, display_term in seen_terms.items():
        if _phrase_covered(norm_term, own_text):
            continue
        findings.append({
            "term": display_term,
            "classification": classify_market_term(display_term, known_names),
        })
    findings.sort(key=lambda f: f["classification"])
    return findings


def build_report(config, snapshot):
    clusters = snapshot.get("clusters", [])
    cross_cluster, single_cluster = build_gap_candidates(config, clusters)
    market_language = build_market_language(config, clusters)
    return {
        "disclaimer": (
            "These are coverage-gap candidates based on lexical overlap with today's "
            "top-ranking competitor pages for the seed keywords searched. No search-volume, "
            "domain-authority, or backlink signal is included — this cannot tell you a topic "
            "will rank, only that ranking competitors cover it and your site's titles/queries "
            "currently don't. Verify manually (and check real search volume) before committing "
            "writing time."
        ),
        "topical_authority_gaps": cross_cluster,
        "single_cluster_gaps": single_cluster,
        "market_language_observed": market_language,
    }


def print_report(report):
    print(report["disclaimer"])
    print()
    print(f"=== Topical authority gaps (recur across 2+ distinct clusters) — {len(report['topical_authority_gaps'])} found ===")
    for g in report["topical_authority_gaps"]:
        print(f"  - {g['item']!r} — seen in clusters: {', '.join(g['clusters'])}")
        print(f"      {g['feasibility']}")
        print(f"      {g['coverage_note']}")
    print()
    print(f"=== Single-cluster gaps — {len(report['single_cluster_gaps'])} found ===")
    for g in report["single_cluster_gaps"][:15]:
        print(f"  - {g['item']!r} — cluster: {g['clusters'][0]}")
        print(f"      {g['feasibility']}")
    print()
    print(f"=== Market language observed (do not auto-adopt) — {len(report['market_language_observed'])} found ===")
    for f in report["market_language_observed"]:
        print(f"  - {f['term']!r} [{f['classification']}]")


def main():
    parser = argparse.ArgumentParser(description="Pre-topic-selection coverage-gap discovery — see DISCOVERY.md")
    parser.add_argument("--config", required=True, help="Path to your project's config, e.g. site-config.<project>.json")
    parser.add_argument("--suggest-seeds", action="store_true", help="Print a starter seed-keyword list (needs only identity fields, not verified_facts)")
    parser.add_argument("--snapshot", help="Path to discovery_snapshot.json (see DISCOVERY.md for schema)")
    parser.add_argument("--out", help="Also write the full report as JSON to this path")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.suggest_seeds:
        for s in suggest_seeds(config):
            print(s)
        return

    if not args.snapshot:
        parser.error("--snapshot is required unless --suggest-seeds is passed")

    snapshot = load_snapshot(args.snapshot)
    report = build_report(config, snapshot)
    print_report(report)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nFull report written to {args.out}")


if __name__ == "__main__":
    main()
