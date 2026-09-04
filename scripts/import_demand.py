"""Normalize Keyword Planner or Search Console exports into demand evidence.

The importer preserves source semantics. Keyword Planner searches describe an
approximate market signal; Search Console clicks/impressions describe the
configured site's observed visibility. Neither is organic ranking difficulty.
"""

import argparse
import csv
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "article-forge.demand.v1"
SOURCES = {"keyword_planner", "search_console"}


def _header(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        raise ValueError(f"not a number: {value!r}")
    cleaned = value.strip().replace(",", "").replace("%", "")
    if not cleaned:
        raise ValueError("empty numeric value")
    return float(cleaned)


def _query_from_row(row, source):
    keys = list(row)
    aliases = (
        ("keyword", "search_term", "query")
        if source == "keyword_planner"
        else ("top_queries", "query", "search_query", "keyword")
    )
    for alias in aliases:
        if alias in row and str(row[alias]).strip():
            return str(row[alias]).strip()
    raise ValueError(f"row is missing a query column; found {keys}")


def _keyword_planner_value(row):
    for name in ("avg_monthly_searches", "average_monthly_searches"):
        if name in row:
            return _number(row[name])
    raise ValueError("Keyword Planner row is missing Avg. monthly searches")


def _search_console_value(row, metric):
    if metric not in row:
        raise ValueError(f"Search Console row is missing {metric}")
    return _number(row[metric])


def _json_rows(payload, source):
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("rows") or payload.get("records")
        if not isinstance(rows, list):
            raise ValueError("JSON input must contain a rows or records list")
    else:
        raise ValueError("JSON input must be a list or object")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("JSON rows must be objects")
    if source != "search_console":
        return rows
    normalized = []
    for row in rows:
        keys = row.get("keys")
        query = keys[0] if isinstance(keys, list) and keys else row.get("query")
        normalized.append({**row, "query": query})
    return normalized


def read_rows(path, source):
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = _json_rows(payload, source)
        return [{_header(k): value for k, value in row.items()} for row in rows]
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [
            {_header(k): value for k, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def build_demand_document(rows, *, source, observed_at, sample_size, metric):
    if source not in SOURCES:
        raise ValueError(f"source must be one of {sorted(SOURCES)}")
    if sample_size < 1:
        raise ValueError("sample_size must be positive")
    records = []
    for row in rows:
        query = _query_from_row(row, source)
        if source == "keyword_planner":
            value = _keyword_planner_value(row)
            unit = "searches"
            role = "market_demand"
            raw = {
                "avg_monthly_searches": value,
                "paid_competition": row.get("competition"),
                "paid_competition_index": row.get("competition_indexed_value")
                or row.get("competition_index"),
            }
        else:
            value = _search_console_value(row, metric)
            unit = metric
            role = "site_opportunity"
            raw = {
                "clicks": row.get("clicks"),
                "impressions": row.get("impressions"),
                "ctr": row.get("ctr"),
                "position": row.get("position"),
            }
        records.append(
            {"query": query, "value": value, "unit": unit, "role": role, "raw": raw}
        )

    maximum = max((record["value"] for record in records), default=0)
    normalization = "max-value-within-imported-candidate-set"
    for record in records:
        record["demand"] = {
            "source": source,
            "role": record.pop("role"),
            "value": record["value"],
            "unit": record["unit"],
            "score": round(record["value"] / maximum * 100, 1) if maximum else 0.0,
            "normalization": normalization,
            "observed_at": observed_at,
            "sample_size": sample_size,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "observed_at": observed_at,
        "sample_size": sample_size,
        "metric": metric if source == "search_console" else "avg_monthly_searches",
        "normalization": normalization,
        "records": records,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Import demand evidence from a CSV or JSON export"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Keyword Planner or Search Console CSV/JSON export",
    )
    parser.add_argument("--source", required=True, choices=sorted(SOURCES))
    parser.add_argument(
        "--observed-at", required=True, help="YYYY-MM-DD or ISO-8601 date"
    )
    parser.add_argument(
        "--sample-size",
        required=True,
        type=int,
        help="months or days represented by this export",
    )
    parser.add_argument(
        "--metric", choices=["clicks", "impressions"], default="impressions"
    )
    parser.add_argument("--out", required=True, help="normalized demand JSON path")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        date.fromisoformat(args.observed_at[:10])
    except ValueError as exc:
        parser.error("--observed-at must begin with YYYY-MM-DD")
        raise AssertionError from exc
    out = Path(args.out)
    if out.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite existing output; pass --force: {out}")
    document = build_demand_document(
        read_rows(Path(args.input), args.source),
        source=args.source,
        observed_at=args.observed_at,
        sample_size=args.sample_size,
        metric=args.metric,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(
        f"Imported {len(document['records'])} {args.source} demand record(s); wrote {out}"
    )


if __name__ == "__main__":
    main()
