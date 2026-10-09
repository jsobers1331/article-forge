"""Shared identities and provenance. Hashes bind evidence; they do not prove truth."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

CLAIM_SCHEMA = "article-forge.claim-binding.v2"
LEDGER_SCHEMA = "article-forge.claim-ledger.v2"


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def object_hash(value):
    return text_hash(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def claim_fingerprint(claim):
    return object_hash(
        {
            "schema_version": CLAIM_SCHEMA,
            **{
                key: claim.get(key) or ""
                for key in ("claim", "verification_scope", "source_url", "source_local")
            },
        }
    )


def age_days(timestamp, now=None):
    try:
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None:
            return None
        return ((now or datetime.now(timezone.utc)) - parsed).total_seconds() / 86400
    except (TypeError, ValueError):
        return None


def snapshot_text(result, root):
    """Read the declared snapshot from one explicit evidence root."""
    path = result.get("snapshot_path")
    if not isinstance(path, str) or not path:
        return None
    try:
        return (Path(root) / path).read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError):
        return None


def binding_error(claim, result, root):
    if result.get("claim_fingerprint") != claim_fingerprint(claim):
        return "legacy or changed claim binding; re-verify"
    source = snapshot_text(result, root)
    if (
        source is None
        or not result.get("snapshot_sha256")
        or text_hash(source) != result["snapshot_sha256"]
    ):
        return "missing or changed source snapshot; re-verify"
    # Local sources can be checked without a provider/network request.
    if claim.get("source_local"):
        try:
            current = (Path(root) / claim["source_local"]).read_bytes()
        except (OSError, ValueError):
            return "local source unavailable; re-verify"
        if hashlib.sha256(current).hexdigest() != result.get("source_raw_sha256"):
            return "local source changed; re-verify"
    return None
