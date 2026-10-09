"""Automated compliance gate for a generated article draft.

This is a CHECK, not a rewrite tool. It validates config/evidence shape,
freshness, placeholders, scope, links, structure, and style before a draft can
leave generation quarantine. It also enforces the autonomous claim-verification
ledger: a claim the ledger marks unsupported is a HARD FAIL (replace it with
`<!-- PLACEHOLDER: claim <id> not verifiable -->` or drop it). A passing result
is necessary but not sufficient: the QC checklist still requires reading the
draft against verified_facts and the current source of truth (AUTONOMY.md).
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from urllib.parse import urlsplit
from pathlib import Path
from evidence_contract import age_days, binding_error
from claim_manifest import check_manifest, used_ids
from serp_contract import snapshot_gate
from editorial_brief import check_brief

DEFAULT_BAN_WORDS = [
    "delve",
    "landscape",
    "robust",
    "seamless",
    "elevate",
    "game-changer",
    "in today's fast-paced world",
]

PLACEHOLDER_PATTERNS = [
    r"example\.com",
    r"lorem ipsum",
    r"\bTBD\b",
    r"\bFIXME\b",
    r"555-\d{4}",
    r"Jane (S\b|Smith)",
    r"John (S\b|Smith)",
    r"Sample (Customer|Client)",
    r"PLACEHOLDER: needs real value",
]

WORD_COUNT_RANGES = {
    "pillar": (1500, 2200),
    "standard": (1000, 2000),
    "supporting": (700, 1400),
}


def check_config_integrity(config):
    """Validate the minimum shape needed to safely render product claims."""
    required = [
        "site_name",
        "domain",
        "category_frame",
        "icp",
        "canonical_definition_sentence",
    ]
    missing = [
        key
        for key in required
        if not isinstance(config.get(key), str) or not config[key].strip()
    ]
    facts = config.get("verified_facts")
    errors = [f"missing required config field: {key}" for key in missing]
    if not isinstance(facts, dict):
        errors.append("verified_facts must be an object")
        facts = {}
    differentiators = facts.get("real_differentiators", [])
    if not isinstance(differentiators, list):
        errors.append("verified_facts.real_differentiators must be a list")
    else:
        for index, item in enumerate(differentiators):
            if isinstance(item, dict) and (
                not item.get("feature") or not item.get("tier")
            ):
                errors.append(
                    f"real_differentiators[{index}] needs both feature and tier"
                )
            elif not isinstance(item, (str, dict)):
                errors.append(
                    f"real_differentiators[{index}] must be a string or object"
                )
    if not isinstance(facts.get("coming_soon_features", []), list):
        errors.append("verified_facts.coming_soon_features must be a list")
    if not isinstance(facts.get("pricing_and_billing", {}), dict):
        errors.append("verified_facts.pricing_and_billing must be an object")
    if not isinstance(config.get("existing_pages", []), list) or not all(
        isinstance(page, str) and page.startswith("/")
        for page in config.get("existing_pages", [])
    ):
        errors.append("existing_pages must be a list of relative paths")
    if errors:
        return "FAIL", "; ".join(errors)
    return "PASS", "config has the required product, facts, pages, and tier fields"


def check_claim_evidence(config, used_claim_ids=None):
    """Require a provenance registry before a draft can leave quarantine."""
    evidence = config.get("claim_evidence")
    if evidence is None:
        return (
            "WARN",
            "no claim_evidence registry supplied — every product claim still needs a human source attestation",
        )
    if not isinstance(evidence, list):
        return "FAIL", "claim_evidence must be a list"
    if used_claim_ids is not None:
        evidence = [
            e
            for e in evidence
            if isinstance(e, dict) and e.get("claim_id") in used_claim_ids
        ]
        if not evidence and not used_claim_ids:
            return (
                "PASS",
                "no registry claims used; final-draft coverage is checked separately",
            )
    if not evidence:
        return (
            "WARN",
            "claim_evidence is empty — attest the product claims before generation",
        )
    errors = []
    stale = []
    seen_ids = set()
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            errors.append(f"claim_evidence[{index}] must be an object")
            continue
        if not item.get("claim_id") or not item.get("claim"):
            errors.append(f"claim_evidence[{index}] needs claim_id and claim")
        if item.get("claim_id") in seen_ids:
            errors.append(f"duplicate claim_id: {item.get('claim_id')}")
        seen_ids.add(item.get("claim_id"))
        source_url = item.get("source_url", "")
        parsed = urlsplit(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            errors.append(
                f"claim_evidence[{index}] needs an absolute http(s) source_url"
            )
        try:
            verified_on = date.fromisoformat(item.get("verified_on", ""))
        except (TypeError, ValueError):
            errors.append(
                f"claim_evidence[{index}] needs verified_on in YYYY-MM-DD form"
            )
        else:
            if not 0 <= (date.today() - verified_on).days <= 30:
                stale.append(item.get("claim_id", str(index)))
        if item.get("status") != "verified":
            errors.append(
                f"claim_evidence[{index}] must have status=verified before generation"
            )
    if errors:
        return "FAIL", "; ".join(errors)
    if stale:
        return (
            "WARN",
            "stale claim-evidence record(s) need re-attestation: " + ", ".join(stale),
        )
    return (
        "PASS",
        f"{len(evidence)} claim-evidence record(s) have source and verification metadata",
    )


def check_current_month_year(config):
    value = config.get("current_month_year")
    expected = date.today().strftime("%B %Y")
    if not isinstance(value, str) or not value.strip():
        return (
            "WARN",
            f"current_month_year is missing — set it to {expected} before generation",
        )
    if value.strip() != expected:
        return "WARN", f"current_month_year is {value!r}; current month is {expected!r}"
    return "PASS", f"current_month_year is current ({expected})"


def word_count(text):
    return len(re.findall(r"\b\w+\b", text))


def check_word_count(text, article_type):
    lo, hi = WORD_COUNT_RANGES.get(article_type, WORD_COUNT_RANGES["standard"])
    n = word_count(text)
    return (
        "PASS",
        f"advisory length: {n} words; {lo}-{hi} is a planning range for {article_type}, not a gate",
    )


def check_banned_words(text, extra_ban_words):
    hits = []
    for word in DEFAULT_BAN_WORDS + list(extra_ban_words):
        if re.search(re.escape(word), text, re.IGNORECASE):
            hits.append(word)
    if hits:
        return "WARN", f"banned words present: {', '.join(hits)}"
    return "PASS", "no banned words found"


OPENING_FUNCTION_LABELS = [
    "answer",
    "assertion",
    "scenario",
    "contrast",
    "continuation",
    "evidence",
    "question",
    "common mistakes",
    "verdict",
]


def check_visible_function_labels(text):
    """Catches a real artifact found 2026-08-09: the model took the prompt
    template's internal "assign each H2 an opening function" planning step
    too literally and printed the function name itself as a visible bolded
    label ("**Answer.**", "**Scenario.**") at the start of sections — just
    as mechanical a repetition as the pattern the rule exists to prevent,
    and NOT caught by check_structural_repetition (each label is a
    different word, so no adjacent-repeat trigger fires). Found by
    generating two fresh test articles and actually reading them, not by
    trusting the other automated checks.
    """
    hits = []
    for label in OPENING_FUNCTION_LABELS:
        for m in re.finditer(
            rf"^\*\*{re.escape(label)}\.\*\*", text, re.IGNORECASE | re.MULTILINE
        ):
            line_no = text[: m.start()].count("\n") + 1
            hits.append(f"line {line_no}: {m.group(0)!r}")
    if hits:
        return (
            "FAIL",
            "visible opening-function labels found (should be internal planning only): "
            + "; ".join(hits),
        )
    return "PASS", "no visible opening-function labels found"


def check_internal_planning_artifacts(text):
    """Reject prompt-planning notes that a model accidentally prints.

    A prior pilot included a useful article preceded by a visible per-H2
    opening-function plan. It was not caught by the label check because the
    function names appeared in a planning bullet rather than as section labels.
    Planning metadata is not reader-facing content and must not reach output.
    """
    patterns = [
        r"^\s*\*\*Per-H2 opening-function plan\b",
        r"^\s*-\s*\*\*H2:\s+.+?\*\*\s+[—-]\s+\*(?:answer|assertion|scenario|contrast|continuation|evidence|question|common mistakes|verdict)\.?\*",
    ]
    hits = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
            line_no = text[: match.start()].count("\n") + 1
            hits.append(f"line {line_no}: {match.group(0).strip()!r}")
    if hits:
        return (
            "FAIL",
            "internal planning artifact found in visible draft: " + "; ".join(hits),
        )
    return "PASS", "no internal planning artifacts found"


def check_facts_freshness(config, max_age_days=30):
    """Enforced, not just documented — DISCOVERY.md's whole premise is that
    verified_facts can drift (a price change, a paused promo) between runs.
    A facts_last_verified field nobody checks is just a date; this makes
    staleness visible every single run instead of trusting it gets read.
    """
    verified = config.get("facts_last_verified")
    if not verified:
        return (
            "WARN",
            "no facts_last_verified set on this config — add one (YYYY-MM-DD) and treat this as immediately due for a re-check against the live site",
        )
    try:
        verified_date = date.fromisoformat(verified)
    except ValueError:
        return (
            "WARN",
            f"facts_last_verified {verified!r} is not a valid YYYY-MM-DD date",
        )
    age = (date.today() - verified_date).days
    if age < 0:
        return (
            "WARN",
            f"facts_last_verified {verified} is in the future — check for a typo",
        )
    if age > max_age_days:
        return (
            "WARN",
            f"verified_facts last confirmed {age} days ago (>{max_age_days}) — re-read the live site's source of truth and update facts_last_verified before publishing",
        )
    return "PASS", f"verified_facts confirmed {age} day(s) ago"


LEDGER_MAX_AGE_DAYS = 30


def ledger_path_for_config(config_path):
    base = os.path.basename(config_path)
    slug = base.replace("site-config.", "").replace(".json", "")
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), f"claim-verification.{slug}.json")


def load_claim_ledger(config_path):
    """Parse the claim-verification ledger next to the config, or None when it
    is missing, unreadable, or malformed. check_claim_ledger reports that state
    as a WARN — a broken ledger must not crash the whole gate.
    """
    path = ledger_path_for_config(config_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            ledger = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(ledger, dict) or not isinstance(ledger.get("results"), list):
        return None
    return ledger


def _ledger_entry_age_days(entry):
    checked_at = entry.get("checked_at")
    if not isinstance(checked_at, str):
        return None
    try:
        parsed = datetime.fromisoformat(checked_at)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).total_seconds() / 86400.0


def check_claim_ledger(
    config, config_path, max_age_days=LEDGER_MAX_AGE_DAYS, used_claim_ids=None
):
    """Turn the claim-verification ledger (scripts/verify_facts.py) into a gate.

    An unsupported claim is a HARD FAIL — the draft asserts something its own
    source contradicts, and the fix is to replace that sentence with
    `<!-- PLACEHOLDER: claim <id> not verifiable -->` or drop it. Everything
    else (no ledger yet, stale or inconclusive entries, claims never checked)
    is a WARN.
    """
    claims = [
        c
        for c in (config.get("claim_evidence") or [])
        if isinstance(c, dict)
        and c.get("claim_id")
        and (used_claim_ids is None or c["claim_id"] in used_claim_ids)
    ]
    path = ledger_path_for_config(config_path)
    if not claims:
        return (
            "PASS",
            "no registry claims selected — final-draft manifest coverage is checked separately",
        )

    ledger = load_claim_ledger(config_path)
    if ledger is None:
        return "WARN", (
            f"no usable claim-verification ledger at {path} — run "
            f"`python3 scripts/verify_facts.py --config {config_path}` before publishing"
        )

    ids = [
        r.get("claim_id")
        for r in ledger.get("results", [])
        if isinstance(r, dict) and r.get("claim_id") in {c["claim_id"] for c in claims}
    ]
    if len(ids) != len(set(ids)):
        return (
            "FAIL",
            "duplicate ledger results for used claim IDs; re-verify the evidence registry",
        )

    results_by_id = {
        r["claim_id"]: r
        for r in ledger.get("results", [])
        if isinstance(r, dict) and r.get("claim_id")
    }

    unsupported, inconclusive, stale, missing = [], [], [], []
    for claim in claims:
        claim_id = claim["claim_id"]
        result = results_by_id.get(claim_id)
        if result is None:
            missing.append(claim_id)
            continue
        status = result.get("status")
        age = age_days(result.get("checked_at"))
        if status == "unsupported":
            unsupported.append(claim_id)
        elif status != "verified":
            inconclusive.append(claim_id)
        elif age is None or age < 0 or age > max_age_days:
            stale.append(claim_id)
        elif binding_error(
            claim, result, ledger.get("evidence_root") or Path(config_path).parent
        ):
            missing.append(
                claim_id + " (legacy or changed binding/snapshot; re-verify)"
            )

    if unsupported:
        return "FAIL", (
            "unsupported claim(s): "
            + ", ".join(unsupported)
            + " — the source does not support the claim. Replace each with "
            "`<!-- PLACEHOLDER: claim <id> not verifiable -->` or remove the claim, "
            "then re-run scripts/verify_facts.py."
        )
    warnings = []
    if missing:
        warnings.append("never verified: " + ", ".join(missing))
    if inconclusive:
        warnings.append("inconclusive: " + ", ".join(inconclusive))
    if stale:
        warnings.append(f"stale (>{max_age_days}d): " + ", ".join(stale))
    if warnings:
        return "WARN", "; ".join(
            warnings
        ) + " — re-run scripts/verify_facts.py (see AUTONOMY.md)"
    return "PASS", f"all {len(claims)} claim(s) verified by the ledger"


def check_fabrication_placeholders(text):
    hits = []
    for pattern in PLACEHOLDER_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            line_no = text[: m.start()].count("\n") + 1
            hits.append(f"line {line_no}: /{pattern}/ -> {m.group(0)!r}")
    if hits:
        return "FAIL", "placeholder/fabrication patterns found:\n    " + "\n    ".join(
            hits
        )
    return "PASS", "no placeholder/fabrication patterns found"


def check_structured_element(text):
    has_table = "|" in text and re.search(r"^\s*\|.*\|.*\|\s*$", text, re.MULTILINE)
    has_numbered_list = re.search(r"^\s*\d+\.\s", text, re.MULTILINE)
    if has_table or has_numbered_list:
        kind = "table" if has_table else "numbered list"
        return "PASS", f"found a structured element ({kind})"
    return (
        "PASS",
        "no structured element; use tables or steps only when the reader task benefits",
    )


def check_bare_urls(text):
    """Catch a real generation bug: the model names a competitor's URL as bare
    parenthetical text — "YNAB (https://ynab.com)" — instead of a Markdown
    link. It reads fine to a human but registers as zero links to the linking
    scorer and to any real crawler looking for an anchor tag. See RULES.md §16/17.
    """
    markdown_link_spans = [
        m.span() for m in re.finditer(r"\[[^\]]+\]\(https?://[^)]+\)", text)
    ]

    def _inside_markdown_link(pos):
        return any(start <= pos < end for start, end in markdown_link_spans)

    bare = []
    for m in re.finditer(r"\(https?://[^)\s]+\)", text):
        if not _inside_markdown_link(m.start()):
            bare.append(m.group(0))
    if bare:
        return (
            "FAIL",
            f"{len(bare)} bare URL(s) in parentheses, not Markdown links: {bare[:3]}",
        )
    return "PASS", "no bare parenthetical URLs found"


def check_h1_present(text, target_query):
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if not m:
        return "FAIL", "no H1 (# heading) found"
    h1 = m.group(1).strip().lower()
    query_words = set(re.findall(r"\w+", target_query.lower()))
    h1_words = set(re.findall(r"\w+", h1))
    overlap = len(query_words & h1_words) / max(len(query_words), 1)
    if overlap < 0.5:
        return (
            "WARN",
            f"H1 ({h1!r}) overlaps only {overlap:.0%} with target query ({target_query!r})",
        )
    return "PASS", f"H1 matches target query closely ({overlap:.0%} word overlap)"


def check_visible_dateline(text):
    """Require the freshness signal the prompt asks the renderer to expose.

    A config date by itself is not visible to a reader or crawler. Keeping this
    check beside the H1 also catches a model that silently drops the dateline
    while leaving the rest of the draft intact.
    """
    h1 = re.search(r"^#\s+.+$", text, re.MULTILINE)
    if not h1:
        return "FAIL", "cannot verify dateline without an H1"
    after_h1 = text[h1.end() :].splitlines()[:5]
    if not any(
        re.search(r"\blast updated\b", line, re.IGNORECASE) for line in after_h1
    ):
        return (
            "FAIL",
            "missing visible 'Last updated' dateline immediately after the H1",
        )
    return "PASS", "visible 'Last updated' dateline is present after the H1"


PROCESS_INTENT = re.compile(
    r"\b(?:how to|book(?:ing)?|process|step(?:s)?|setup|install|plan)\b",
    re.IGNORECASE,
)


def check_process_structure(text, target_query):
    """Require numbered steps when the target query describes a process."""
    if not PROCESS_INTENT.search(target_query):
        return "PASS", "target query does not signal a process article"
    if re.search(r"^\s*\d+\.\s", text, re.MULTILINE):
        return "PASS", "process article contains a numbered step list"
    return "FAIL", "process-intent article must contain a numbered step list"


STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "up",
    "only",
    "not",
    "on",
    "for",
    "with",
}


def check_structural_repetition(text):
    """WARN-only signal for the flat-register failure mode (RULES.md §7/§12):
    every H2's opening paragraph using the same shape. This is a coarse
    proxy, not comprehension — per cross-model review (DeepSeek + Codex,
    2026-08-09), a simplistic variance/repetition threshold is gameable and
    must not be treated as a hard gate. Use it to flag sections worth a
    human's attention, not to auto-reject a draft.
    """
    sections = re.split(r"^##\s+.+$", text, flags=re.MULTILINE)[1:]
    headings = re.findall(r"^##\s+(.+)$", text, flags=re.MULTILINE)
    if len(sections) < 3:
        return "PASS", "too few H2 sections to assess repetition"

    first_words = []
    sentence_lengths_per_section = []
    for section in sections:
        para = section.strip().split("\n\n")[0].strip()
        words = re.findall(r"[A-Za-z']+", para)
        first_words.append(words[0].lower() if words else "")
        sentences = re.split(r"(?<=[.!?])\s+", para)
        lengths = [len(re.findall(r"\w+", s)) for s in sentences if s.strip()]
        sentence_lengths_per_section.append(lengths)

    repeats = []
    for i in range(1, len(first_words)):
        if first_words[i] and first_words[i] == first_words[i - 1]:
            repeats.append(
                f"'{headings[i - 1]}' and '{headings[i]}' both open with {first_words[i]!r}"
            )

    flat_sections = []
    for h, lengths in zip(headings, sentence_lengths_per_section):
        if len(lengths) >= 2:
            spread = max(lengths) - min(lengths)
            if spread <= 2:
                flat_sections.append(h)

    warnings = []
    if repeats:
        warnings.append(
            "adjacent sections share an opening word: " + "; ".join(repeats)
        )
    if len(flat_sections) >= max(2, len(headings) // 2):
        warnings.append(
            f"{len(flat_sections)}/{len(headings)} sections have near-uniform sentence length in their opening paragraph"
        )

    if warnings:
        return "WARN", "; ".join(warnings)
    return (
        "PASS",
        "no obvious structural repetition detected (coarse heuristic — still worth a human skim)",
    )


def _keywords(phrase):
    words = re.findall(r"[a-zA-Z-]+", phrase.lower())
    return {w for w in words if len(w) > 3 and w not in STOPWORDS}


def _contains_token(token, text):
    return (
        re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text, re.IGNORECASE)
        is not None
    )


def _segments(text):
    return [
        segment.strip()
        for segment in re.split(r"(?<=[.!?])\s+|\n+", text)
        if segment.strip()
    ]


def _mentions_feature(segment, feature):
    words = _keywords(feature)
    return bool(words) and sum(_contains_token(word, segment) for word in words) >= min(
        2, len(words)
    )


def check_coming_soon_mentions(text, coming_soon_features):
    hits = []
    for feature in coming_soon_features:
        if any(_mentions_feature(segment, feature) for segment in _segments(text)):
            hits.append(feature)
    if hits:
        return "FAIL", "coming-soon/roadmap feature mentioned in draft: " + ", ".join(
            repr(hit) for hit in hits
        )
    return "PASS", "no configured coming-soon features mentioned"


def check_tier_gated_mentions(text, real_differentiators):
    """Fail closed on unscoped or universal claims about tier-gated features.

    A feature mention must carry a tier in the same sentence or line. This is
    intentionally conservative; a human still reviews the final meaning.
    """
    failures = []
    universal_pattern = re.compile(
        r"\b(?:every|all|any|each)\s+(?:plan|tier|subscription)s?\b|"
        r"\b(?:on|for)\s+all\s+plans?\b",
        re.IGNORECASE,
    )
    for d in real_differentiators:
        if not isinstance(d, dict):
            continue
        feature = d.get("feature", "")
        tier = d.get("tier", "")
        if not feature or not tier:
            continue
        tier_kw = _keywords(tier)
        for segment in _segments(text):
            if not _mentions_feature(segment, feature):
                continue
            if universal_pattern.search(segment) and not re.search(
                r"\b(?:not|never|except|excluding)\b", segment, re.IGNORECASE
            ):
                failures.append(f"universal scope near {feature!r}: {segment[:180]!r}")
            if not any(_contains_token(word, segment) for word in tier_kw):
                failures.append(
                    f"{feature!r} needs nearby tier {tier!r}: {segment[:180]!r}"
                )
    if failures:
        return "FAIL", "tier-gated claim requires correction: " + "; ".join(failures)
    return "PASS", "tier-gated mentions carry nearby plan evidence"


def run_checks(
    text,
    article_type,
    target_query,
    config,
    config_path=None,
    use_ledger=True,
    manifest=None,
    snapshot=None,
    brief=None,
    brief_root=None,
):
    voice = config.get("voice", {})
    real_differentiators = config.get("verified_facts", {}).get(
        "real_differentiators", []
    )

    ids = used_ids(text, manifest, config)
    ledger = load_claim_ledger(config_path) if config_path else None
    root = (ledger or {}).get("evidence_root") or (
        Path(config_path).parent if config_path else Path(__file__).resolve().parents[1]
    )
    checks = [
        ("Config integrity", check_config_integrity(config)),
        ("Facts freshness", check_facts_freshness(config)),
        ("Claim evidence registry", check_claim_evidence(config, ids)),
        ("Dateline freshness", check_current_month_year(config)),
        ("Fabrication/placeholder gate", check_fabrication_placeholders(text)),
        ("Visible opening-function labels", check_visible_function_labels(text)),
        ("Internal planning artifacts", check_internal_planning_artifacts(text)),
        ("H1 matches target query", check_h1_present(text, target_query)),
        ("Visible dateline", check_visible_dateline(text)),
        ("Bare URLs (not Markdown links)", check_bare_urls(text)),
        (
            "Coming-soon features",
            check_coming_soon_mentions(
                text, config.get("verified_facts", {}).get("coming_soon_features", [])
            ),
        ),
        ("Word count", check_word_count(text, article_type)),
        ("Banned words", check_banned_words(text, voice.get("extra_ban_words", []))),
        ("Structured element present", check_structured_element(text)),
        (
            "Process structure",
            check_process_structure(text, target_query)
            if isinstance(brief, dict) and brief.get("requires_ordered_steps") is True
            else ("PASS", "ordered steps not required by the reviewed reader task"),
        ),
        ("Tier-gating mentions", check_tier_gated_mentions(text, real_differentiators)),
        ("Structural repetition (heuristic)", check_structural_repetition(text)),
    ]
    if use_ledger and config_path:
        checks.insert(
            2,
            (
                "Claim verification ledger",
                check_claim_ledger(config, config_path, used_claim_ids=ids),
            ),
        )
    elif use_ledger:
        checks.insert(
            2,
            (
                "Claim verification ledger",
                (
                    "WARN",
                    "config_path missing; ledger verification cannot be performed",
                ),
            ),
        )
    else:
        checks.insert(
            2,
            (
                "Claim verification ledger",
                ("WARN", "ledger verification disabled; diagnostic output only"),
            ),
        )
    checks.append(
        (
            "Evidence-led brief",
            check_brief(
                brief,
                target_query,
                brief_root or (Path(config_path).parent if config_path else root),
            ),
        )
    )
    checks.append(
        (
            "Final-draft claim coverage",
            check_manifest(text, manifest, config, ledger, root),
        )
    )
    if snapshot is not None:
        checks.append(
            ("SERP evidence contract", snapshot_gate(snapshot, target_query, config))
        )
    return checks


def main():
    parser = argparse.ArgumentParser(
        description="Run the automated compliance gate against an article draft"
    )
    parser.add_argument("--draft", required=True, help="Path to the markdown draft")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to your project's config, e.g. site-config.<project>.json",
    )
    parser.add_argument(
        "--type", default="standard", choices=["pillar", "standard", "supporting"]
    )
    parser.add_argument(
        "--query",
        required=True,
        help="The target query this article is meant to answer",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero for warnings as well as failures",
    )
    parser.add_argument(
        "--no-ledger",
        action="store_true",
        help="Diagnostic only: skipped verification stays WARN and blocks a passing exit",
    )
    parser.add_argument("--manifest", help="Reviewed claim-to-sentence manifest JSON")
    parser.add_argument("--brief", help="Evidence-led editorial brief JSON")
    parser.add_argument("--snapshot", help="Versioned SERP snapshot JSON")
    args = parser.parse_args()

    with open(args.draft, "r", encoding="utf-8") as f:
        text = f.read()
    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    manifest = json.loads(Path(args.manifest).read_text()) if args.manifest else None
    snapshot = json.loads(Path(args.snapshot).read_text()) if args.snapshot else None
    checks = run_checks(
        text,
        args.type,
        args.query,
        config,
        config_path=args.config,
        use_ledger=not args.no_ledger,
        manifest=manifest,
        snapshot=snapshot,
        brief=json.loads(Path(args.brief).read_text()) if args.brief else None,
        brief_root=Path(args.brief).parent if args.brief else None,
    )

    blocked = False
    for name, (status, detail) in checks:
        marker = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}[status]
        print(f"{marker} [{status}] {name}: {detail}")
        if status != "PASS":
            blocked = True

    print()
    if blocked and args.strict:
        print(
            "STRICT FAIL — resolve every warning/failure before generation or publishing."
        )
        sys.exit(1)
    if blocked:
        print("HARD FAIL — resolve the failures before publishing.")
        sys.exit(1)
    print(
        "All checks passed. Human publication approval and factual/visual review remain required."
    )


if __name__ == "__main__":
    main()
