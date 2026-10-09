"""Versioned final-draft coverage, deterministic checks plus explicit human review.

The detector is conservative and incomplete. A reviewer must check ALL sentences,
including assertions it misses. A signed manifest alone does not establish truth.
No provider is called by this module.
"""

import re

from evidence_contract import (
    age_days,
    claim_fingerprint,
    object_hash,
    snapshot_text,
    text_hash,
)

SCHEMA = "article-forge.claim-manifest.v1"
NUMBER = re.compile(r"(?<!\w)\d[\d,]*(?:\.\d+)?(?:%|\b)")
MATERIAL = re.compile(
    r"\b(?:we|I|our team)\s+(?:tested|found|used|measured|visited|photographed|interviewed)\b|"
    r"\b(?:costs?|pricing|prices?|offers?|supports?|includes?|provides?|allows?|can|cannot|only|unlimited|"
    r"guarantees?|refunds?|polic(?:y|ies)|requires?|expires?|launched|released|available|tier|plan|"
    r"percent|statistics?|customers?|users?|exports?|automates?|integrates?|encrypts?|stores?|tracks?|syncs?|generates?|sends?|billed|charged|trial|subscription|retention|free)\b",
    re.I,
)


def sentences(text):
    """Stable IDs bind every occurrence, including lists and table cells."""
    result = []
    # Comments must not be used to smuggle claimed coverage into visible prose.
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for line in text.splitlines():
        line = line.strip()
        if (
            not line
            or re.fullmatch(r"[|:\-\s]+", line)
            or re.fullmatch(
                r"[*_]?Last updated:\s*(?:[A-Za-z]+ \d{4}|[A-Za-z]+ \d{1,2}, \d{4}|\d{4}-\d{2}-\d{2})\.?[*_]?",
                line,
                re.I,
            )
        ):
            continue
        line = re.sub(r"^#{1,6}\s+|^[-*]\s+|^\d+\.\s+", "", line)
        line = re.sub(r"!?\[([^\]]+)\]\([^)]+\)", r"\1", line)
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            if sentence.strip():
                result.append(
                    {"sentence_id": len(result) + 1, "text": sentence.strip()}
                )
    return result


def is_material(sentence):
    return bool(
        NUMBER.search(sentence)
        or "“" in sentence
        or '"' in sentence
        or re.search(r"\b(?:free|unlimited|guaranteed|refunds?)\b", sentence, re.I)
        or (
            not sentence.endswith("?")
            and len(sentence.split()) >= 3
            and MATERIAL.search(sentence)
        )
    )


def used_ids(text, manifest, config):
    ids = set()
    if isinstance(manifest, dict) and isinstance(manifest.get("assertions"), list):
        for item in manifest["assertions"]:
            if isinstance(item, dict) and isinstance(item.get("claim_ids"), list):
                ids.update(cid for cid in item["claim_ids"] if isinstance(cid, str))
    visible = "\n".join(s["text"] for s in sentences(text))
    for claim in config.get("claim_evidence") or []:
        if isinstance(claim, dict) and claim.get("claim") and claim["claim"] in visible:
            ids.add(claim.get("claim_id"))
    return ids


def check_manifest(text, manifest, config, ledger, root):
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA:
        return (
            "WARN",
            "missing versioned claim-to-sentence manifest; full human semantic review required",
        )
    errors = []
    draft_hash = text_hash(text)
    if manifest.get("draft_sha256") != draft_hash:
        errors.append("manifest does not bind the exact final draft")
    review = manifest.get("human_review")
    if not isinstance(review, dict):
        review = {}
    age = age_days(review.get("reviewed_at"))
    if (
        not review.get("reviewer")
        or review.get("draft_sha256") != draft_hash
        or review.get("coverage") != "all_material_assertions"
        or age is None
        or not 0 <= age <= 30
        or not review.get("limitations")
    ):
        errors.append(
            "current human semantic/coverage review of the exact draft is required"
        )
    assertions = manifest.get("assertions")
    if not isinstance(assertions, list):
        return "FAIL", "manifest assertions must be a list"
    registry = {
        c["claim_id"]: c
        for c in config.get("claim_evidence") or []
        if isinstance(c, dict) and c.get("claim_id")
    }
    results = {
        r["claim_id"]: r
        for r in (ledger or {}).get("results", [])
        if isinstance(r, dict) and r.get("claim_id")
    }
    rows = {s["sentence_id"]: s["text"] for s in sentences(text)}
    covered = set()
    for item in assertions:
        if not isinstance(item, dict):
            errors.append("assertion must be an object")
            continue
        sid = item.get("sentence_id")
        if (
            not isinstance(sid, int)
            or sid in covered
            or rows.get(sid) != item.get("sentence")
        ):
            errors.append("missing, duplicate or changed sentence mapping")
            continue
        covered.add(sid)
        ids = item.get("claim_ids")
        if (
            not isinstance(ids, list)
            or not ids
            or any(not isinstance(cid, str) or cid not in registry for cid in ids)
        ):
            errors.append(f"sentence {sid}: unknown evidence record")
            continue
        sources = []
        bound = []
        for cid in ids:
            claim, result = registry[cid], results.get(cid, {})
            bound.append(
                {
                    "claim_id": cid,
                    "claim_fingerprint": claim_fingerprint(claim),
                    "snapshot_sha256": result.get("snapshot_sha256"),
                }
            )
            source = snapshot_text(result, root)
            if (
                source is None
                or not result.get("snapshot_sha256")
                or text_hash(source) != result["snapshot_sha256"]
            ):
                errors.append(
                    f"sentence {sid}: missing or changed source snapshot for {cid}"
                )
            else:
                sources.append(source)
        if item.get("evidence_binding") != object_hash(bound):
            errors.append(f"sentence {sid}: changed evidence binding")
        sentence = item["sentence"]
        source_text = "\n".join(sources)
        claim_text = " ".join(registry[cid]["claim"] for cid in ids)
        if not set(NUMBER.findall(sentence)) <= set(NUMBER.findall(claim_text)):
            errors.append(
                f"sentence {sid}: numbers strengthen/change the verified claim"
            )
        first_hand = r"\b(?:we|I|our team)\s+(?:tested|found|used|measured|visited|photographed|interviewed)\b"
        if re.search(first_hand, sentence, re.I) and not re.search(
            first_hand, claim_text, re.I
        ):
            errors.append(f"sentence {sid}: unverified first-hand strengthening")
        for number in NUMBER.findall(sentence):
            if number not in NUMBER.findall(source_text):
                errors.append(f"sentence {sid}: number {number} absent from snapshots")
        for quote in re.findall(r'[“"]([^”"]+)[”"]', sentence):
            if quote not in source_text:
                errors.append(f"sentence {sid}: quotation absent from snapshots")
        for identifier in re.findall(r"\b[A-Z]{2,}[-_]\w+\b|https?://\S+", sentence):
            if identifier not in source_text:
                errors.append(f"sentence {sid}: identifier absent from snapshots")
        # Exact claim text is the deterministic safe default. Paraphrases require
        # an explicit, evidence-bound entailment attestation by the human reviewer.
        if sentence not in [registry[cid]["claim"] for cid in ids]:
            attestation = item.get("semantic_review", {})
            if (
                not isinstance(attestation, dict)
                or attestation.get("reviewer") != review.get("reviewer")
                or attestation.get("assertion_sha256") != text_hash(sentence)
                or attestation.get("evidence_binding") != item.get("evidence_binding")
                or attestation.get("verdict") != "supported_without_strengthening"
            ):
                errors.append(
                    f"sentence {sid}: paraphrase/strengthening needs explicit human entailment review"
                )
            # Obvious universal strengthening cannot be excused by a checkbox.
            qualifiers = r"\b(?:all|every|always|guaranteed|unlimited|never)\b"
            extra = set(re.findall(qualifiers, sentence.lower())) - set(
                re.findall(
                    qualifiers, " ".join(registry[c]["claim"].lower() for c in ids)
                )
            )
            if extra:
                errors.append(f"sentence {sid}: unsupported universal strengthening")
    for sid, sentence in rows.items():
        if is_material(sentence) and sid not in covered:
            errors.append(
                f"sentence {sid}: unmapped material assertion: {sentence[:100]}"
            )
    if errors:
        return "FAIL", "; ".join(errors)
    return (
        "PASS",
        "exact-draft manifest and deterministic provenance checks passed; human semantic review recorded, factual truth is not proven",
    )


def propose_manifest(text, config, ledger):
    """An unsigned worklist, deliberately not a passing attestation."""
    assertions = []
    registry = {
        c["claim_id"]: c
        for c in config.get("claim_evidence") or []
        if isinstance(c, dict) and c.get("claim_id")
    }
    results = {
        r["claim_id"]: r
        for r in (ledger or {}).get("results", [])
        if isinstance(r, dict) and r.get("claim_id")
    }
    for row in sentences(text):
        ids = [cid for cid, c in registry.items() if c["claim"] == row["text"]]
        if ids or is_material(row["text"]):
            assertions.append(
                {
                    "sentence_id": row["sentence_id"],
                    "sentence": row["text"],
                    "claim_ids": ids,
                    "evidence_binding": object_hash(
                        [
                            {
                                "claim_id": cid,
                                "claim_fingerprint": claim_fingerprint(registry[cid]),
                                "snapshot_sha256": results.get(cid, {}).get(
                                    "snapshot_sha256"
                                ),
                            }
                            for cid in ids
                        ]
                    ),
                }
            )
    return {
        "schema_version": SCHEMA,
        "draft_sha256": text_hash(text),
        "assertions": assertions,
        "human_review": None,
        "limitations": "Unsigned heuristic worklist; may miss assertions. Review the whole draft.",
    }


def main():
    import argparse
    import json
    from pathlib import Path
    from check_article import load_claim_ledger

    parser = argparse.ArgumentParser(
        description="Prepare an unsigned final-draft assertion worklist; no semantic approval"
    )
    parser.add_argument("--draft", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    target = Path(args.out)
    if target.exists():
        raise SystemExit("Refusing to overwrite a manifest; choose a new output path")
    proposal = propose_manifest(
        Path(args.draft).read_text(),
        json.loads(Path(args.config).read_text()),
        load_claim_ledger(args.config),
    )
    target.write_text(json.dumps(proposal, indent=2) + "\n")
    print(
        "Unsigned manifest proposal written; whole-draft human semantic review is required"
    )


if __name__ == "__main__":
    main()
