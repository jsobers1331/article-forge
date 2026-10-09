"""Evidence-led reader briefs and reviewed page decisions, independent of a site."""

from pathlib import Path

from evidence_contract import age_days

SCHEMA = "article-forge.editorial-brief.v1"
PAGE_TYPES = {
    "article",
    "service",
    "feature",
    "comparison",
    "documentation",
    "interactive_example",
}
DECISIONS = {"create", "improve", "consolidate", "defer"}


def check_brief(brief, query, root):
    if not isinstance(brief, dict) or brief.get("schema_version") != SCHEMA:
        return "WARN", "missing evidence-led editorial brief and reviewed page decision"
    errors = []
    for key in (
        "reader_problem",
        "intended_action",
        "original_contribution",
        "limitation",
    ):
        if not isinstance(brief.get(key), str) or not brief[key].strip():
            errors.append(f"missing {key}")
    if " ".join(brief.get("target_query", "").lower().split()) != " ".join(
        query.lower().split()
    ):
        errors.append("brief query differs from target")
    decision = brief.get("page_decision") or {}
    if not isinstance(decision, dict):
        decision = {}
    if (
        decision.get("action") not in DECISIONS
        or decision.get("page_type") not in PAGE_TYPES
    ):
        errors.append("invalid page action/type")
    if not decision.get("reason") or not decision.get("reviewer"):
        errors.append("page decision requires a reviewer and evidence-led reason")
    age = age_days(decision.get("reviewed_at"))
    if age is None or not 0 <= age <= 30:
        errors.append("page decision review missing/stale")
    if decision.get("action") in {"improve", "consolidate"} and not decision.get(
        "existing_urls"
    ):
        errors.append("improve/consolidate requires existing URLs")
    # URLs/titles alone cannot establish overlap or harmful cannibalization.
    corpus = brief.get("existing_page_evidence")
    if not isinstance(corpus, list):
        errors.append(
            "existing-page content evidence must be an explicit list (empty allowed for a new site)"
        )
    else:
        for page in corpus:
            if (
                not isinstance(page, dict)
                or not page.get("url")
                or not _asset_ok(page, root)
            ):
                errors.append("existing page content snapshot missing/changed")
    if decision.get("action") in {"improve", "consolidate"} and isinstance(
        corpus, list
    ):
        urls = {page.get("url") for page in corpus if isinstance(page, dict)}
        if any(url not in urls for url in decision.get("existing_urls", [])):
            errors.append("selected existing URLs require actual content snapshots")
    if brief.get("query_page_observations") is None:
        errors.append(
            "record query-to-page observations or an explicit unavailable reason"
        )
    assets = brief.get("supporting_assets")
    if not isinstance(assets, list) or not assets:
        errors.append("original contribution requires inspectable supporting assets")
    else:
        for asset in assets:
            if (
                not isinstance(asset, dict)
                or not _asset_ok(asset, root)
                or not asset.get("source")
                or not asset.get("rights")
            ):
                errors.append(
                    "supporting asset missing/changed or lacks provenance/rights"
                )
                continue
            if (
                asset.get("role") == "evidence"
                and asset.get("kind") == "generated_image"
            ):
                errors.append(
                    "generated illustration cannot establish experience or product behavior"
                )
            if asset.get("kind") in {"screenshot", "photograph", "generated_image"}:
                if not all(
                    asset.get(k)
                    for k in ("caption", "alt_text", "visible_content_reviewed_by")
                ):
                    errors.append(
                        "media requires accurate caption, descriptive alt text and visible-content review"
                    )
            if asset.get("kind") == "interview" and not asset.get("permission_record"):
                errors.append("interview requires a permission record")
        if not any(
            isinstance(a, dict)
            and a.get("role") == "evidence"
            and a.get("kind") != "generated_image"
            for a in assets
        ):
            errors.append("no original evidentiary asset supplied")
    if errors:
        return "FAIL", "; ".join(errors)
    if decision["action"] == "defer":
        return "WARN", "reviewed decision is defer; do not generate or publish"
    return (
        "PASS",
        "reader problem, action, original contribution, assets, limitation and page decision reviewed",
    )


def _asset_ok(asset, root):
    try:
        path = Path(root) / asset["path"]
        content = path.read_bytes()
        if asset.get("kind") in {"screenshot", "photograph", "generated_image"}:
            from PIL import Image

            with Image.open(path) as visual:
                visual.verify()
        import hashlib

        return hashlib.sha256(content).hexdigest() == asset.get("sha256")
    except (OSError, KeyError, TypeError, ValueError):
        return False


def suggest_page_decision(query, page_evidence, query_pages):
    """Review signal from actual content, never an automatic consolidation order."""
    tokens = set(query.lower().split())
    overlaps = []
    for page in page_evidence:
        content = page.get("content", "")
        if tokens and len(tokens & set(content.lower().split())) / len(tokens) >= 0.6:
            overlaps.append(page["url"])
    observed_urls = sorted(
        {
            r["page"]
            for r in query_pages
            if r.get("query", "").lower() == query.lower() and r.get("page")
        }
    )
    return {
        "suggested_action": "improve" if overlaps else "create",
        "existing_urls": overlaps,
        "query_page_urls": observed_urls,
        "review_required": True,
        "limits": "Content overlap and multiple URLs are review signals; neither proves harmful cannibalization.",
    }


def attach_brief(topic, brief):
    topic = dict(topic)
    topic["editorial_brief"] = brief
    return topic
