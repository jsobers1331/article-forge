"""Search Console demand collector — Phase 1 of the GSC/Keyword Planner
integration described in DISCOVERY.md's "validate against Google Search
Console / Keyword Planner" caveat.

Pulls real clicks/impressions/CTR/position data for a site's own domain so
discover_gaps.py candidates can be checked against actual signal instead of
lexical overlap alone. This is the one script in article-forge that talks to
a live API directly — every other script (score_article.py, discover_gaps.py)
deliberately has no API access and expects an orchestrating agent to hand it
structured JSON. GSC needs its own OAuth-authenticated client with a
refreshable token, which doesn't fit the "agent fetches, script computes"
pattern, so it gets a real integration instead.

One-time setup (see README.md):
    1. Create an OAuth client (Desktop app) in Google Cloud Console and
       enable the Search Console API.
    2. Put GSC_CLIENT_ID / GSC_CLIENT_SECRET in .env.
    3. Run: python scripts/collect_search_console.py --authorize
       This opens your browser once to grant read-only access and saves
       GSC_REFRESH_TOKEN back into .env.

Normal use (--config is required on every run, same as every other script
here — no shared default property, so pulling one site's data can never
silently land on another's):
    python scripts/collect_search_console.py --config site-config.shootmuse.json --days 90
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv, set_key
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_prompt import load_config  # noqa: E402
from import_demand import build_demand_document  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
SCHEMA_VERSION = "article-forge.gsc.v1"
REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
MAX_ROW_LIMIT = 25_000
ALLOWED_DIMENSIONS = {
    "country",
    "date",
    "device",
    "page",
    "query",
    "searchAppearance",
}


def _atomic_write_json(path, payload, *, force=False):
    """Write JSON atomically and refuse accidental evidence replacement."""
    destination = Path(path)
    if destination.exists() and not force:
        raise SystemExit(
            f"refusing to overwrite existing output; pass --force: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _check_output_paths(paths, *, force=False):
    if force:
        return
    existing = [str(Path(path)) for path in paths if path and Path(path).exists()]
    if existing:
        raise SystemExit(
            "refusing to overwrite existing output; pass --force: "
            + ", ".join(existing)
        )


def parse_dimensions(value):
    dimensions = [item.strip() for item in value.split(",") if item.strip()]
    if not dimensions:
        raise ValueError("at least one Search Console dimension is required")
    unknown = sorted(set(dimensions) - ALLOWED_DIMENSIONS)
    if unknown:
        raise ValueError(
            f"unsupported Search Console dimension(s): {', '.join(unknown)}; "
            f"choose from {', '.join(sorted(ALLOWED_DIMENSIONS))}"
        )
    if len(dimensions) != len(set(dimensions)):
        raise ValueError("Search Console dimensions must not repeat")
    return dimensions


def validate_window(days, row_limit):
    if days < 1:
        raise ValueError("--days must be at least 1")
    if not 1 <= row_limit <= MAX_ROW_LIMIT:
        raise ValueError(f"--row-limit must be between 1 and {MAX_ROW_LIMIT}")


def authorize():
    load_dotenv(str(ENV_PATH))
    client_id = os.environ.get("GSC_CLIENT_ID")
    client_secret = os.environ.get("GSC_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit(
            "Set GSC_CLIENT_ID and GSC_CLIENT_SECRET in .env first, then re-run --authorize."
        )

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    # prompt="consent" forces Google to reissue a refresh_token even on a repeat
    # authorization — without it, a second run (e.g. after revoking access) can
    # return refresh_token=None, since Google only issues one on first consent.
    creds = flow.run_local_server(port=0, prompt="consent")
    if not creds.refresh_token:
        sys.exit(
            "Google did not return a refresh token. Revoke this app's access at "
            "https://myaccount.google.com/permissions and re-run --authorize."
        )
    set_key(str(ENV_PATH), "GSC_REFRESH_TOKEN", creds.refresh_token)
    os.chmod(ENV_PATH, 0o600)
    print(
        "Authorized — GSC_REFRESH_TOKEN saved to .env. You won't need --authorize again unless access is revoked."
    )


def get_credentials():
    load_dotenv(str(ENV_PATH))
    client_id = os.environ.get("GSC_CLIENT_ID")
    client_secret = os.environ.get("GSC_CLIENT_SECRET")
    refresh_token = os.environ.get("GSC_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        sys.exit(
            "Missing GSC_CLIENT_ID/GSC_CLIENT_SECRET/GSC_REFRESH_TOKEN in .env — run --authorize first."
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def query_search_analytics(
    service, property_url, start_date, end_date, dimensions, row_limit
):
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "type": "web",
        "dataState": "final",
        "rowLimit": row_limit,
    }
    response = (
        service.searchanalytics().query(siteUrl=property_url, body=body).execute()
    )
    return response.get("rows", [])


def normalize_rows(rows, dimensions):
    normalized = []
    for row in rows:
        keys = row.get("keys", [])
        if len(keys) != len(dimensions):
            raise ValueError(
                f"GSC returned {len(keys)} dimension values but {len(dimensions)} "
                f"were requested ({dimensions}) — refusing to write mismatched data."
            )
        entry = dict(zip(dimensions, keys))
        entry.update(
            {
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": row.get("ctr", 0),
                "position": row.get("position", 0),
            }
        )
        normalized.append(entry)
    return normalized


def _query_demand_rows(rows, dimensions):
    """Aggregate query+dimension rows into one row per query for demand."""
    if "query" not in dimensions:
        raise ValueError("--demand-out requires the query dimension")
    grouped = {}
    for row in rows:
        query = row.get("query", "").strip()
        if not query:
            continue
        item = grouped.setdefault(
            query,
            {"query": query, "clicks": 0, "impressions": 0, "position_weight": 0},
        )
        clicks = float(row.get("clicks", 0) or 0)
        impressions = float(row.get("impressions", 0) or 0)
        item["clicks"] += clicks
        item["impressions"] += impressions
        item["position_weight"] += float(row.get("position", 0) or 0) * impressions
    demand_rows = []
    for item in grouped.values():
        impressions = item["impressions"]
        demand_rows.append(
            {
                "query": item["query"],
                "clicks": item["clicks"],
                "impressions": impressions,
                "ctr": item["clicks"] / impressions if impressions else 0,
                "position": item["position_weight"] / impressions if impressions else 0,
            }
        )
    return demand_rows


def _property_from_config(config):
    search_console = config.get("research", {}).get("search_console", {})
    return search_console.get("property") or f"sc-domain:{config['domain']}"


def main():
    parser = argparse.ArgumentParser(
        description="Pull final Search Console evidence for one site — see DISCOVERY.md"
    )
    parser.add_argument(
        "--authorize",
        action="store_true",
        help="One-time OAuth setup: opens your browser and saves the refresh token to .env",
    )
    parser.add_argument(
        "--config",
        help="Path to site-config.<project>.json — required unless --authorize or --property is given",
    )
    parser.add_argument(
        "--property", help="Search Console property, e.g. sc-domain:shootmuse.com"
    )
    parser.add_argument(
        "--days", type=int, default=90, help="Trailing days to pull (default: 90)"
    )
    parser.add_argument(
        "--dimensions",
        default="query",
        help="Comma-separated dimensions (default: query; query,page is also supported)",
    )
    parser.add_argument(
        "--row-limit", type=int, default=1000, help=f"Maximum rows (1-{MAX_ROW_LIMIT})"
    )
    parser.add_argument(
        "--metric",
        choices=["clicks", "impressions"],
        default="impressions",
        help="Metric used for optional demand output (default: impressions)",
    )
    parser.add_argument(
        "--out",
        help="GSC artifact path (default: gsc-snapshot.<project>.json next to config)",
    )
    parser.add_argument(
        "--demand-out",
        help="Optional normalized article-forge.demand.v1 path, aggregated by query",
    )
    parser.add_argument(
        "--force", action="store_true", help="Allow replacing existing output files"
    )
    args = parser.parse_args()

    if args.authorize:
        authorize()
        return

    if not args.property and not args.config:
        parser.error("--config or --property is required")

    try:
        validate_window(args.days, args.row_limit)
        dimensions = parse_dimensions(args.dimensions)
        if args.demand_out and "query" not in dimensions:
            raise ValueError("--demand-out requires the query dimension")
    except ValueError as exc:
        parser.error(str(exc))

    property_url = args.property
    project_slug = "site"
    config_dir = Path.cwd()
    if args.config:
        config = load_config(args.config)
        project_slug = (
            Path(args.config).name.replace("site-config.", "").replace(".json", "")
        )
        config_dir = Path(args.config).resolve().parent
        if not property_url:
            property_url = _property_from_config(config)

    creds = get_credentials()
    service = build("searchconsole", "v1", credentials=creds)

    end = date.today() - timedelta(days=2)  # GSC data lags ~2 days
    start = end - timedelta(
        days=args.days - 1
    )  # GSC's range is inclusive of both endpoints

    rows = query_search_analytics(
        service,
        property_url,
        start.isoformat(),
        end.isoformat(),
        dimensions,
        args.row_limit,
    )
    normalized = normalize_rows(rows, dimensions)

    out_path = (
        Path(args.out) if args.out else config_dir / f"gsc-snapshot.{project_slug}.json"
    )
    demand_path = Path(args.demand_out) if args.demand_out else None
    _check_output_paths([out_path, demand_path], force=args.force)
    output = {
        "schema_version": SCHEMA_VERSION,
        "source": "google_search_console",
        "property": property_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "type": "web",
        "data_state": "final",
        "dimensions": dimensions,
        "row_limit": args.row_limit,
        "row_count": len(normalized),
        "rows": normalized,
    }
    _atomic_write_json(out_path, output, force=args.force)

    if demand_path:
        demand_document = build_demand_document(
            _query_demand_rows(normalized, dimensions),
            source="search_console",
            observed_at=end.isoformat(),
            sample_size=args.days,
            metric=args.metric,
        )
        _atomic_write_json(demand_path, demand_document, force=args.force)
        print(
            f"{len(demand_document['records'])} query demand record(s) written to {demand_path}"
        )

    print(
        f"{len(normalized)} rows for {property_url} ({start.isoformat()} to {end.isoformat()}) written to {out_path}"
    )


if __name__ == "__main__":
    main()
