"""Autonomous claim verification for article-forge site configs.

For every `claim_evidence` entry in a site config this script:

1. Reads the source — `source_local` (path relative to this repo) wins over
   `source_url`, which is fetched over HTTP with a 1 req/sec throttle.
2. Snapshots the tag-stripped source (JSON-LD/microdata pulled out and
   prepended as a structured section) to
   `evidence/<project>/<claim_id>-<YYYYMMDD>.txt`.
3. Asks DeepSeek (temperature 0) whether the source supports the claim,
   requiring verbatim quotes for a `verified` verdict.
4. Writes `claim-verification.<project>.json` next to the config.

Entries younger than `--max-age-days` are carried forward without a new LLM
call; the ledger is merged by claim_id. Exit code is 0 even when claims come
back unsupported or inconclusive — check_article.py turns those into FAIL and
WARN. Exit code 2 covers config/ledger IO or parse errors, an unknown
--claim-id, and a missing DEEPSEEK_API_KEY.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from call_llm import call_llm

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

USER_AGENT = "article-forge-fact-checker"
FETCH_TIMEOUT = 10
MIN_FETCH_INTERVAL = 1.0
MAX_SOURCE_CHARS = 200_000
DEFAULT_MAX_AGE_DAYS = 30
VALID_STATUSES = ("verified", "unsupported", "inconclusive")
STATUS_MARKERS = {"verified": "✓", "unsupported": "✗", "inconclusive": "⚠"}

LD_JSON_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
ITEMPROP_RE = re.compile(r'itemprop=["\']([^"\']+)["\']([^>]*)>', re.IGNORECASE)
ITEMPROP_CONTENT_RE = re.compile(r'content=["\']([^"\']*)["\']')
TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^>\n]*?)?/?>")
BLOCK_TAG_RE = re.compile(
    r"</?(?:p|div|br|li|ul|ol|h[1-6]|tr|td|th|table|section|article|header|footer"
    r"|nav|main|aside|figure|figcaption|blockquote)\b[^>\n]*>",
    re.IGNORECASE,
)


class VerifyError(Exception):
    """A config/ledger problem that maps to exit code 2."""


def slug_for(config_path):
    base = os.path.basename(config_path)
    return base.replace("site-config.", "").replace(".json", "")


def ledger_path_for_config(config_path):
    return os.path.join(
        os.path.dirname(os.path.abspath(config_path)),
        f"claim-verification.{slug_for(config_path)}.json",
    )


def load_config(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise VerifyError(f"Config not found: {config_path}")
    except (OSError, json.JSONDecodeError) as exc:
        raise VerifyError(f"Could not read config {config_path}: {exc}")


def load_ledger(config_path):
    path = ledger_path_for_config(config_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            ledger = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise VerifyError(f"Could not read ledger {path}: {exc}")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("results"), list):
        raise VerifyError(f"Ledger {path} is malformed (expected an object with a results list)")
    return ledger


def write_ledger(path, ledger):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(ledger, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp_path, path)


def extract_structured_sections(raw_html):
    """JSON-LD blocks and microdata pairs found in the raw source, as text."""
    sections = []
    for match in LD_JSON_RE.finditer(raw_html):
        try:
            parsed = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue
        sections.append(json.dumps(parsed, indent=2, ensure_ascii=False))
    micro = []
    for match in ITEMPROP_RE.finditer(raw_html):
        prop = match.group(1).strip()
        content = ITEMPROP_CONTENT_RE.search(match.group(2) or "")
        if content:
            value = content.group(1).strip()
        else:
            tail = TAG_RE.sub(" ", raw_html[match.end(): match.end() + 200])
            value = " ".join(unescape(tail).split())[:200]
        if value:
            micro.append(f"{prop}: {value}")
    if micro:
        sections.append("\n".join(micro))
    return sections


def html_to_text(raw_html):
    """Tag-strip a source, prepending extracted JSON-LD/microdata as a section."""
    structured = extract_structured_sections(raw_html)
    body = LD_JSON_RE.sub(" ", raw_html)
    body = SCRIPT_STYLE_RE.sub(" ", body)
    body = BLOCK_TAG_RE.sub("\n", body)
    body = TAG_RE.sub(" ", body)
    body = unescape(body)
    body = re.sub(r"[ \t\f\v]+", " ", body)
    body = re.sub(r"[ \t]*\n[ \t]*", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if structured:
        body = (
            "=== STRUCTURED DATA (JSON-LD / microdata) ===\n"
            + "\n\n".join(structured)
            + "\n\n=== PAGE TEXT ===\n"
            + body
        )
    return body


def cap_source_text(text):
    if len(text) <= MAX_SOURCE_CHARS:
        return text
    return text[:MAX_SOURCE_CHARS] + f"\n\n[SOURCE TRUNCATED at {MAX_SOURCE_CHARS} characters]"


_last_fetch_at = [0.0]


def fetch_url(url):
    """Fetch `url` (throttled to >= 1s between requests); (None, status) on failure."""
    wait = MIN_FETCH_INTERVAL - (time.monotonic() - _last_fetch_at[0])
    if wait > 0:
        time.sleep(wait)
    _last_fetch_at[0] = time.monotonic()
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            return body.decode(charset, errors="replace"), response.status
    except HTTPError as exc:
        return None, exc.code
    except (URLError, OSError, ValueError) as exc:
        return None, str(exc)


def read_local_source(rel_path):
    full_path = os.path.normpath(os.path.join(REPO_ROOT, rel_path))
    with open(full_path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def acquire_source(entry):
    """Return (raw_text, source_label, http_status_or_local, error_note)."""
    local_rel = entry.get("source_local")
    if local_rel:
        try:
            raw = read_local_source(local_rel)
        except OSError as exc:
            return None, local_rel, local_rel, f"could not read source_local {local_rel}: {exc}"
        return raw, local_rel, local_rel, None
    url = entry.get("source_url")
    if not url:
        return None, "(no source)", None, "claim has neither source_local nor source_url"
    text, status = fetch_url(url)
    if text is None:
        return None, url, status, f"fetch failed ({status})"
    return text, url, status, None


def snapshot_rel_path(slug, claim_id, checked_at):
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", claim_id)
    day = checked_at[:10].replace("-", "")
    return f"evidence/{slug}/{safe_id}-{day}.txt"


def write_snapshot(slug, claim_id, checked_at, text):
    rel_path = snapshot_rel_path(slug, claim_id, checked_at)
    full_path = os.path.join(REPO_ROOT, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return rel_path


def build_prompt(claim, scope, source_label, source_text):
    scope_line = f"\nSCOPE: {scope}" if scope else ""
    return (
        "You are a strict fact-checker. Decide whether the SOURCE supports the CLAIM.\n\n"
        f"CLAIM: {claim}{scope_line}\n"
        f"SOURCE: {source_label}\n\n"
        "RULES\n"
        "- verified: the source supports every material part of the claim (numbers, prices, "
        "tiers, timeframes, product names). Include at least one short quote copied "
        "character-for-character from the source as proof.\n"
        "- unsupported: the source contradicts a material part of the claim.\n"
        "- inconclusive: the source is silent on a material part, or you are not certain.\n"
        "- Quotes must be verbatim (at most 3, no paraphrasing). Without a quote you cannot "
        "answer verified.\n\n"
        "Reply with ONLY this JSON object — no prose, no code fences:\n"
        '{"status": "verified|unsupported|inconclusive", "evidence_quotes": ["..."], '
        '"missing_aspects": ["..."]}\n\n'
        "SOURCE TEXT:\n"
        f"{source_text}"
    )


def parse_judgment(raw):
    """Normalize the LLM reply into a judgment dict, or None if unusable."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z0-9_+-]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start: end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("status") not in VALID_STATUSES:
        return None
    quotes = data.get("evidence_quotes")
    quotes = [q.strip() for q in quotes if isinstance(q, str) and q.strip()] if isinstance(quotes, list) else []
    missing = data.get("missing_aspects")
    missing = [m.strip() for m in missing if isinstance(m, str) and m.strip()] if isinstance(missing, list) else []
    return {"status": data["status"], "evidence_quotes": quotes[:3], "missing_aspects": missing}


def quotes_in_source(quotes, source_text):
    flat_source = " ".join(source_text.split())
    for quote in quotes:
        quote = quote.strip()
        if len(quote) < 4:
            continue
        if quote in source_text or " ".join(quote.split()) in flat_source:
            return True
    return False


def judge_claim(claim, scope, source_label, source_text):
    prompt = build_prompt(claim, scope, source_label, source_text)
    try:
        raw = call_llm(prompt, provider="deepseek", temperature=0.0, max_tokens=1500)
    except Exception as exc:  # an LLM/network failure is reported, not fatal
        return {
            "status": "inconclusive",
            "evidence_quotes": [],
            "missing_aspects": [f"LLM call failed: {exc}"],
        }
    judgment = parse_judgment(raw)
    if judgment is None:
        return {
            "status": "inconclusive",
            "evidence_quotes": [],
            "missing_aspects": ["verifier output was not strict JSON"],
        }
    if judgment["status"] == "verified" and not quotes_in_source(judgment["evidence_quotes"], source_text):
        judgment["status"] = "inconclusive"
        judgment["missing_aspects"].append("verified verdict had no quote matching the source")
    return judgment


def entry_age_days(entry, now):
    checked_at = entry.get("checked_at")
    if not isinstance(checked_at, str):
        return None
    try:
        parsed = datetime.fromisoformat(checked_at)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (now - parsed).total_seconds() / 86400.0


def is_fresh(entry, now, max_age_days):
    age = entry_age_days(entry, now)
    return age is not None and age < max_age_days


def make_result(claim_id, judgment, source_label, status_field, checked_at, snapshot_path):
    return {
        "claim_id": claim_id,
        "status": judgment["status"],
        "checked_at": checked_at,
        "source": source_label,
        "http_status_or_local": status_field,
        "evidence_quotes": judgment.get("evidence_quotes", []),
        "missing_aspects": judgment.get("missing_aspects", []),
        "snapshot_path": snapshot_path,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Verify claim_evidence entries against their sources and write a claim-verification ledger."
    )
    parser.add_argument("--config", required=True, help="Path to a site-config JSON file")
    parser.add_argument(
        "--claim-id",
        help="Verify only this claim (always re-checks it, ignoring the freshness window)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be checked without fetching, calling the LLM, or writing",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_MAX_AGE_DAYS,
        help="Carry forward ledger entries younger than this many days (default 30)",
    )
    args = parser.parse_args(argv)

    load_dotenv()

    try:
        config = load_config(args.config)
        ledger = load_ledger(args.config)
    except VerifyError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    entries = [
        entry
        for entry in (config.get("claim_evidence") or [])
        if isinstance(entry, dict) and entry.get("claim_id")
    ]
    if not entries:
        print(f"No claim_evidence entries in {args.config} — nothing to verify.")
        return 0

    if args.claim_id and args.claim_id not in {entry["claim_id"] for entry in entries}:
        sys.stderr.write(f"Unknown --claim-id: {args.claim_id}\n")
        return 2

    if not args.dry_run and not os.environ.get("DEEPSEEK_API_KEY"):
        sys.stderr.write("DEEPSEEK_API_KEY not set (check your .env file)\n")
        return 2

    previous_by_id = {}
    for item in (ledger or {}).get("results", []):
        if isinstance(item, dict) and item.get("claim_id"):
            previous_by_id[item["claim_id"]] = item

    slug = slug_for(args.config)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")

    results = []
    checked_now = 0
    carried = 0

    for entry in entries:
        claim_id = entry["claim_id"]
        previous = previous_by_id.get(claim_id)

        if args.claim_id and claim_id != args.claim_id:
            if previous is not None:
                results.append(previous)
                print(f"– {claim_id}: preserved (outside --claim-id scope)")
            else:
                print(f"– {claim_id}: skipped (outside --claim-id scope, no ledger entry yet)")
            continue

        forced = claim_id == args.claim_id
        if previous is not None and not forced and is_fresh(previous, now, args.max_age_days):
            carried_entry = dict(previous)
            carried_entry["carried_forward"] = True
            results.append(carried_entry)
            carried += 1
            print(f"↻ {claim_id}: carried forward (checked {previous.get('checked_at')})")
            continue

        planned = entry.get("source_local") or entry.get("source_url") or "(no source configured)"
        if args.dry_run:
            action = "re-verify" if previous is not None else "verify"
            print(f"• {claim_id}: would {action} against {planned}")
            continue

        raw_source, source_label, status_field, error_note = acquire_source(entry)
        if error_note:
            judgment = {
                "status": "inconclusive",
                "evidence_quotes": [],
                "missing_aspects": [error_note],
            }
            snapshot_path = None
        else:
            source_text = html_to_text(raw_source)
            try:
                snapshot_path = write_snapshot(slug, claim_id, now_iso, source_text)
            except OSError as exc:
                snapshot_path = None
                sys.stderr.write(f"Warning: could not write snapshot for {claim_id}: {exc}\n")
            judgment = judge_claim(
                entry.get("claim") or "",
                entry.get("verification_scope") or "",
                source_label,
                cap_source_text(source_text),
            )

        result = make_result(claim_id, judgment, source_label, status_field, now_iso, snapshot_path)
        results.append(result)
        checked_now += 1
        print(f"{STATUS_MARKERS.get(result['status'], '?')} {claim_id}: {result['status']} ({source_label})")
        for aspect in result["missing_aspects"]:
            print(f"    -> {aspect}")

    if args.dry_run:
        print("Dry run: no fetches, no LLM calls, nothing written.")
        return 0

    ledger_out = {
        "generated_at": now_iso,
        "project": slug,
        "verifier": "scripts/verify_facts.py (provider=deepseek)",
        "results": results,
    }
    try:
        write_ledger(ledger_path_for_config(args.config), ledger_out)
    except OSError as exc:
        sys.stderr.write(f"Could not write ledger: {exc}\n")
        return 2

    verified = sum(1 for item in results if item["status"] == "verified")
    unsupported = sum(1 for item in results if item["status"] == "unsupported")
    inconclusive = sum(1 for item in results if item["status"] == "inconclusive")
    print(
        f"\n{slug}: {len(results)} claim(s) in ledger — {verified} verified, "
        f"{unsupported} unsupported, {inconclusive} inconclusive "
        f"({checked_now} checked now, {carried} carried forward)"
    )
    print(f"Ledger: {ledger_path_for_config(args.config)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
