"""Synthetic evidence contracts; no external data or providers."""

from datetime import datetime, timezone
from evidence_contract import claim_fingerprint, object_hash, text_hash
from serp_contract import SCHEMA


def current_time():
    return datetime.now(timezone.utc).isoformat()


def bind_result(root, claim, result, text=None):
    text = text or claim["claim"]
    path = root / ("snapshot-" + claim["claim_id"] + ".txt")
    path.write_text(text)
    return {
        **result,
        "claim_fingerprint": claim_fingerprint(claim),
        "snapshot_path": str(path),
        "snapshot_sha256": text_hash(text),
    }


def valid_snapshot(query="how to choose a photography CRM", pages=None):
    pages = (
        pages
        if pages is not None
        else [
            {
                "url": f"https://sample{i}.org/page",
                "position": i + 1,
                "headings": ["Workflow"],
                "subtopics": ["client portal"],
                "entities": ["CRM"],
            }
            for i in range(5)
        ]
    )
    for page in pages:
        page.setdefault("headings", ["Workflow"])
        page["source_snapshot"] = {
            "text": "A synthetic source describes "
            + " ".join(page["subtopics"] + page["entities"]),
            "source_url": page["url"],
            "captured_at": current_time(),
        }
        page["source_snapshot"]["sha256"] = text_hash(page["source_snapshot"]["text"])
        page["extraction"] = {
            "status": "complete",
            "complete": True,
            "sha256": object_hash(
                {k: page[k] for k in ("subtopics", "entities", "headings")}
            ),
        }
    return {
        "schema_version": SCHEMA,
        "keyword": query,
        "captured_at": current_time(),
        "locale": {"country": "us", "language": "en"},
        "provenance": {"method": "fixture", "source": "synthetic"},
        "serp_intent": "informational",
        "competitors": pages,
    }
