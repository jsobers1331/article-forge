"""Generate one article and fail closed before it reaches the output folder.

Non-PASS drafts are retained in ``output/.quarantine`` with a JSON receipt so
they can be fixed without being mistaken for publishable material.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from call_llm import PROVIDERS, call_llm
from check_article import check_fabrication_placeholders, run_checks
from generate_prompt import REPO_ROOT, load_config, pick_topic, render
from score_article import build_article_report, render_report_markdown


def run_fabrication_gate(text):
    """Keep the legacy helper while sharing the canonical checker."""
    status, detail = check_fabrication_placeholders(text)
    return [] if status == "PASS" else [detail]


def slugify(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "article"


def _atomic_write(path, content):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _safe_output_dir(out_dir, config_path):
    out_dir = Path(out_dir).expanduser()
    if out_dir.exists() and out_dir.is_symlink():
        raise RuntimeError(f"refusing symlink output directory: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    resolved = out_dir.resolve()
    protected_roots = {
        Path(REPO_ROOT).resolve(),
        (Path(REPO_ROOT) / "scripts").resolve(),
        (Path(REPO_ROOT) / "prompts").resolve(),
    }
    if any(root == resolved or root in resolved.parents for root in protected_roots):
        raise RuntimeError(f"refusing protected output directory: {resolved}")
    config_file = Path(config_path).expanduser().resolve()
    if resolved == config_file or config_file.parent == resolved:
        raise RuntimeError(
            f"refusing output directory containing config file: {resolved}"
        )
    return resolved


def _target_path(out_dir, slug, force=False):
    target = out_dir / f"{slug}.md"
    if target.is_symlink():
        raise RuntimeError(f"refusing symlink output target: {target}")
    if target.exists() and not force:
        raise FileExistsError(
            f"draft already exists: {target}; use --force only to replace a passing draft"
        )
    return target


def _unique_quarantine_path(out_dir, slug):
    quarantine = out_dir / ".quarantine"
    if quarantine.exists() and quarantine.is_symlink():
        raise RuntimeError(f"refusing symlink quarantine directory: {quarantine}")
    quarantine.mkdir(exist_ok=True)
    candidate = quarantine / f"{slug}.md"
    index = 1
    while candidate.exists() or candidate.is_symlink():
        candidate = quarantine / f"{slug}-{index}.md"
        index += 1
    return candidate


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _checks_payload(checks):
    return [
        {"name": name, "status": status, "detail": detail}
        for name, (status, detail) in checks
    ]


def _persist_report(draft_path, report):
    """Write JSON and Markdown report companions beside the draft."""
    if report is None:
        return None
    report_path, markdown_path = _report_paths(draft_path)
    _atomic_write(report_path, json.dumps(report, indent=2) + "\n")
    _atomic_write(markdown_path, render_report_markdown(report))
    return report_path, markdown_path


def _report_paths(draft_path):
    """Keep persisted and displayed report paths on one naming contract."""
    draft_path = Path(draft_path)
    return draft_path.with_suffix(".report.json"), draft_path.with_suffix(".report.md")


def persist_checked_article(
    article,
    out_dir,
    slug,
    checks,
    prompt,
    config_path,
    force=False,
    report=None,
):
    """Persist only an all-PASS article to normal output.

    A blocked draft and a receipt are written to quarantine. The receipt makes
    the failure reproducible without retaining credentials or the API request.
    """
    out_dir = _safe_output_dir(out_dir, config_path)
    payload = _checks_payload(checks)
    # WARN is intentionally held in quarantine too: only an all-PASS draft may
    # enter normal output, matching the repo's fail-closed publication contract.
    non_pass = [item for item in payload if item["status"] != "PASS"]
    if non_pass:
        draft_path = _unique_quarantine_path(out_dir, slug)
        _atomic_write(draft_path, article)
        receipt = {
            "schema_version": "article-forge.quarantine.v1",
            "quarantined_at": datetime.now(timezone.utc).isoformat(),
            "draft_sha256": _sha256_text(article),
            "prompt_sha256": _sha256_text(prompt),
            "config_sha256": hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),
            "checks": payload,
            "normal_output_blocked": True,
        }
        _atomic_write(
            draft_path.with_suffix(".json"), json.dumps(receipt, indent=2) + "\n"
        )
        _persist_report(draft_path, report)
        return False, draft_path, payload

    target = _target_path(out_dir, slug, force=force)
    _persist_report(target, report)
    _atomic_write(target, article)
    return True, target, payload


def main():
    parser = argparse.ArgumentParser(
        description="Generate one article and gate it before normal output"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to your project's config, e.g. site-config.<project>.json",
    )
    parser.add_argument("--topic-index", type=int)
    parser.add_argument("--title")
    parser.add_argument("--query")
    parser.add_argument("--type", choices=["pillar", "standard", "supporting"])
    parser.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    parser.add_argument("--model")
    parser.add_argument(
        "--snapshot", help="Optional serp_snapshot.json for SERP-parity reporting"
    )
    parser.add_argument("--out-dir", default=os.path.join(REPO_ROOT, "output"))
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing passing draft; never bypass checks",
    )
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv()

    config = load_config(args.config)
    snapshot = None
    if args.snapshot:
        with open(args.snapshot, "r", encoding="utf-8") as stream:
            snapshot = json.load(stream)
    topic = pick_topic(config, args.topic_index, args.title, args.query, args.type)
    prompt = render(config, topic)
    slug = slugify(topic.get("target_query", topic.get("title", "article")))
    out_dir = _safe_output_dir(args.out_dir, args.config)
    _target_path(out_dir, slug, force=args.force)

    print(f"Calling {args.provider}...", file=sys.stderr)
    article = call_llm(prompt, provider=args.provider, model=args.model)
    checks = run_checks(
        article, topic.get("type", "standard"), topic.get("target_query", ""), config
    )
    report = build_article_report(
        article,
        config,
        topic,
        checks,
        snapshot=snapshot,
        snapshot_source=args.snapshot,
    )
    passed, saved_path, payload = persist_checked_article(
        article,
        out_dir,
        slug,
        checks,
        prompt,
        args.config,
        force=args.force,
        report=report,
    )
    report_json, report_markdown = _report_paths(saved_path)
    print(
        f"Article score: {report['score']['total_score']}/100 "
        f"[{report['score']['score_kind']}; {report['score']['evidence_status']}]",
        file=sys.stderr,
    )
    print(f"Article report: {report_json} and {report_markdown}", file=sys.stderr)
    if not passed:
        print(f"Draft blocked and quarantined at {saved_path}", file=sys.stderr)
        for item in payload:
            if item["status"] != "PASS":
                print(
                    f"  - [{item['status']}] {item['name']}: {item['detail']}",
                    file=sys.stderr,
                )
        sys.exit(1)
    print(f"Saved passing draft to {saved_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
