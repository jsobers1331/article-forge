"""Collect Google Ads Keyword Planner market-demand evidence.

This is a direct Google Ads API adapter. It records approximate average
monthly searches and paid advertiser competition as market-demand evidence;
the paid competition field is intentionally never treated as organic SEO
difficulty by Article Forge's opportunity scorer.

Required project environment variables (load them in ``.env``; never commit
their values):

* ``GOOGLE_ADS_DEVELOPER_TOKEN``
* ``GOOGLE_ADS_CLIENT_ID``
* ``GOOGLE_ADS_CLIENT_SECRET``
* ``GOOGLE_ADS_REFRESH_TOKEN``
* ``GOOGLE_ADS_CUSTOMER_ID``

``GOOGLE_ADS_LOGIN_CUSTOMER_ID`` is optional and is needed when authenticating
through a Google Ads manager account. The API also requires a Google Ads
developer token approved for the account's access level.
"""

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_prompt import load_config  # noqa: E402
from import_demand import build_demand_document  # noqa: E402
from collect_search_console import (  # noqa: E402
    _atomic_write_json,
    _check_output_paths,
)

SCHEMA_VERSION = "article-forge.keyword-planner.v1"
REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
REQUIRED_ENV = (
    "GOOGLE_ADS_DEVELOPER_TOKEN",
    "GOOGLE_ADS_CLIENT_ID",
    "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN",
    "GOOGLE_ADS_CUSTOMER_ID",
)
API_VERSION = "v22"


def _required_environment():
    load_dotenv(str(ENV_PATH))
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing Google Ads environment variable(s): "
            + ", ".join(missing)
            + ". Keyword Planner access is not configured."
        )
    values = {name: os.environ[name] for name in REQUIRED_ENV}
    login_customer_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    if login_customer_id:
        values["GOOGLE_ADS_LOGIN_CUSTOMER_ID"] = login_customer_id
    return values


def load_google_ads_client(environment=None):
    environment = environment or _required_environment()
    client_config = {
        "developer_token": environment["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": environment["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": environment["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": environment["GOOGLE_ADS_REFRESH_TOKEN"],
        "use_proto_plus": True,
    }
    if environment.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID"):
        client_config["login_customer_id"] = environment["GOOGLE_ADS_LOGIN_CUSTOMER_ID"]
    return GoogleAdsClient.load_from_dict(client_config, version=API_VERSION)


def build_request(client, customer_id, geo_target_id, language_id, network, seeds, url):
    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id.replace("-", "")
    request.language = f"languageConstants/{language_id}"
    request.geo_target_constants.append(f"geoTargetConstants/{geo_target_id}")
    request.include_adult_keywords = False
    request.keyword_plan_network = getattr(client.enums.KeywordPlanNetworkEnum, network)
    if seeds and url:
        request.keyword_and_url_seed.keywords.extend(seeds)
        request.keyword_and_url_seed.url = url
    elif seeds:
        request.keyword_seed.keywords.extend(seeds)
    elif url:
        request.url_seed.url = url
    else:
        raise ValueError("at least one --seed or --url is required")
    return request


def _enum_name(value):
    name = getattr(value, "name", None)
    return name if name else str(value)


def normalize_results(results):
    rows = []
    for idea in results:
        metrics = idea.keyword_idea_metrics
        keyword = str(getattr(idea, "text", "")).strip()
        if not keyword:
            continue
        row = {
            "keyword": keyword,
            "avg_monthly_searches": int(
                getattr(metrics, "avg_monthly_searches", 0) or 0
            ),
            "competition": _enum_name(getattr(metrics, "competition", "UNSPECIFIED")),
            "competition_index": int(getattr(metrics, "competition_index", 0) or 0),
        }
        for field in ("low_top_of_page_bid_micros", "high_top_of_page_bid_micros"):
            value = getattr(metrics, field, None)
            if value is not None:
                row[field] = int(value)
        rows.append(row)
    return rows


def _validate_inputs(geo_target_id, language_id, seeds, urls):
    if not geo_target_id.isdigit() or int(geo_target_id) < 1:
        raise ValueError("--geo-target-id must be a numeric Google Ads geo target ID")
    if not language_id.isdigit() or int(language_id) < 1:
        raise ValueError("--language-id must be a numeric Google Ads language ID")
    if len(urls) > 1:
        raise ValueError("provide at most one --url")
    if not seeds and not urls:
        raise ValueError("at least one --seed or --url is required")
    if any(not seed.strip() for seed in seeds):
        raise ValueError("--seed values must not be empty")


def main():
    parser = argparse.ArgumentParser(
        description="Pull Google Ads Keyword Planner market-demand evidence"
    )
    parser.add_argument(
        "--config",
        help="Optional site config used for the output slug and provenance context",
    )
    parser.add_argument(
        "--seed",
        action="append",
        default=[],
        help="Keyword seed; repeat for related seeds",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="Optional URL seed (provide at most one)",
    )
    parser.add_argument(
        "--geo-target-id",
        required=True,
        help="Numeric Google Ads geo target constant ID",
    )
    parser.add_argument(
        "--language-id",
        default="1000",
        help="Numeric Google Ads language constant ID (default: 1000 / English)",
    )
    parser.add_argument(
        "--network",
        choices=["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"],
        default="GOOGLE_SEARCH",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=12,
        help="Months represented by average monthly searches (default: 12)",
    )
    parser.add_argument("--out", help="Raw Keyword Planner artifact path")
    parser.add_argument(
        "--demand-out", help="Optional normalized article-forge.demand.v1 path"
    )
    parser.add_argument(
        "--force", action="store_true", help="Allow replacing existing output files"
    )
    args = parser.parse_args()

    try:
        _validate_inputs(args.geo_target_id, args.language_id, args.seed, args.url)
        if args.sample_size < 1:
            raise ValueError("--sample-size must be at least 1")
        environment = _required_environment()
        customer_id = environment["GOOGLE_ADS_CUSTOMER_ID"].replace("-", "")
        if not customer_id.isdigit() or len(customer_id) < 3:
            raise ValueError(
                "GOOGLE_ADS_CUSTOMER_ID must contain a numeric customer ID"
            )
        client = load_google_ads_client(environment)
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    except Exception as exc:
        parser.error(f"Google Ads credentials/client initialization failed: {exc}")

    project_slug = "site"
    if args.config:
        load_config(args.config)
        project_slug = (
            Path(args.config).name.replace("site-config.", "").replace(".json", "")
        )
    request = build_request(
        client,
        environment["GOOGLE_ADS_CUSTOMER_ID"],
        args.geo_target_id,
        args.language_id,
        args.network,
        args.seed,
        args.url[0] if args.url else None,
    )
    service = client.get_service("KeywordPlanIdeaService")
    try:
        results = service.generate_keyword_ideas(request=request)
        rows = normalize_results(results)
    except Exception as exc:  # GoogleAdsException includes provider diagnostics.
        raise SystemExit(f"Google Ads Keyword Planner request failed: {exc}") from exc

    retrieved_at = datetime.now(timezone.utc).isoformat()
    raw_output = {
        "schema_version": SCHEMA_VERSION,
        "source": "google_keyword_planner",
        "retrieved_at": retrieved_at,
        "customer_id": environment["GOOGLE_ADS_CUSTOMER_ID"].replace("-", ""),
        "request": {
            "geo_target_id": args.geo_target_id,
            "language_id": args.language_id,
            "network": args.network,
            "keyword_seeds": args.seed,
            "url_seeds": args.url,
            "include_adult_keywords": False,
        },
        "row_count": len(rows),
        "rows": rows,
    }
    out_path = (
        Path(args.out)
        if args.out
        else Path.cwd() / f"keyword-planner-snapshot.{project_slug}.json"
    )
    demand_path = Path(args.demand_out) if args.demand_out else None
    _check_output_paths([out_path, demand_path], force=args.force)
    _atomic_write_json(out_path, raw_output, force=args.force)
    if demand_path:
        demand = build_demand_document(
            rows,
            source="keyword_planner",
            observed_at=date.today().isoformat(),
            sample_size=args.sample_size,
            metric="avg_monthly_searches",
        )
        _atomic_write_json(demand_path, demand, force=args.force)
        print(
            f"{len(demand['records'])} market-demand record(s) written to {demand_path}"
        )
    print(f"{len(rows)} Keyword Planner ideas written to {out_path}")


if __name__ == "__main__":
    main()
