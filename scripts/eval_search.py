"""Search eval harness — measures precision, recall and ranking on real data.

Why this exists: "semantic search" is only a claim until it has a number. This
runs a labelled query set through the same API the UI uses and reports:

  precision@k  of the rows returned, how many satisfy the stated constraints
  recall@k     of the rows that match, how many appear in the top k
  MRR          for exact-address queries, the rank of the intended property
  latency      p50 / p95 across the set

Ground truth is computed directly in SQL from each case's constraints, so the
harness validates the parser and ranker rather than trusting them.

    python scripts/eval_search.py
    python scripts/eval_search.py --json eval.json --k 10 --limit 200
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ai-service"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Case:
    name: str
    query: str
    kind: str  # "constraint" | "address" | "empty"
    spec: dict[str, Any] = field(default_factory=dict)
    expected_id: int | None = None


CASES: list[Case] = [
    # --- structured constraints -------------------------------------------
    Case("3bed crewe", "3 bed houses in Crewe", "constraint", {"town": "Crewe", "min_beds": 3}),
    Case("2bed crewe under 150k", "2 bed in Crewe under 150000", "constraint", {"town": "Crewe", "max_beds": 2, "max_price": 150000}),
    Case("4bed sandbach", "4 bed in Sandbach", "constraint", {"town": "Sandbach", "min_beds": 4}),
    Case("detached sandbach", "detached houses in Sandbach", "constraint", {"town": "Sandbach", "types": ["detached"]}),
    Case("bungalow alsager", "bungalows in Alsager", "constraint", {"town": "Alsager", "types": ["bungalow"]}),
    Case("bungalow middlewich", "bungalow in Middlewich", "constraint", {"town": "Middlewich", "types": ["bungalow"]}),
    Case("terraced middlewich", "terraced in Middlewich", "constraint", {"town": "Middlewich", "types": ["terraced"]}),
    Case("semi haslington", "semi-detached in Haslington", "constraint", {"town": "Haslington", "types": ["semi-detached"]}),
    Case("4bed detached sandbach", "4 bed detached in Sandbach", "constraint", {"town": "Sandbach", "min_beds": 4, "types": ["detached"]}),
    Case("flat crewe", "flats in Crewe", "constraint", {"town": "Crewe", "types": ["flat"]}),
    Case("price cap 200k crewe", "houses in Crewe under 200k", "constraint", {"town": "Crewe", "max_price": 200000}),
    Case("price range", "Crewe between 150000 and 250000", "constraint", {"town": "Crewe", "min_price": 150000, "max_price": 250000}),
    Case("cw11 detached", "detached in CW11", "constraint", {"outcode": "CW11", "types": ["detached"]}),
    Case("cw10 terraced", "terraced in CW10", "constraint", {"outcode": "CW10", "types": ["terraced"]}),
    Case("cw1 3bed", "3 bed in CW1", "constraint", {"outcode": "CW1", "min_beds": 3}),
    Case("st7 bungalow", "bungalow in ST7", "constraint", {"outcode": "ST7", "types": ["bungalow"]}),
    Case("5bed anywhere", "5 bedroom houses", "constraint", {"min_beds": 5, "max_beds": 5}),
    Case("4bed under 250k", "4 bed under 250000", "constraint", {"min_beds": 4, "max_price": 250000}),
    Case("2bed semi crewe", "2 bed semi in Crewe", "constraint", {"town": "Crewe", "max_beds": 2, "types": ["semi-detached"]}),
    Case("detached under 300k", "detached under 300k", "constraint", {"max_price": 300000, "types": ["detached"]}),

    # --- exact address (ranking) -------------------------------------------
    Case("addr cloverfields", "51 Cloverfields", "address", {}, expected_id=1),
    Case("addr middlewich road", "164 Middlewich Road", "address", {}, expected_id=2),
    Case("addr waterloo road", "126 Waterloo Road", "address", {}, expected_id=3),
    Case("addr newton bank", "19 Newton Bank", "address", {}, expected_id=4),
    Case("addr beechfield drive", "37 Beechfield Drive", "address", {}, expected_id=5),
    Case("addr with town", "51 Cloverfields Haslington", "address", {}, expected_id=1),
    Case("addr postcode", "51 Cloverfields CW1 5AL", "address", {}, expected_id=1),

    # --- no matches (must be empty, not an error) ---------------------------
    Case("nonexistent price", "houses in Crewe under 5000", "empty", {"town": "Crewe", "max_price": 5000}),
    Case("nonexistent town", "3 bed in Edinburgh", "empty", {"town": "Edinburgh"}),
    Case("nonexistent outcode", "houses in AB1", "empty", {"outcode": "AB1"}),
]


def where_from_spec(spec: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    def push(value: Any) -> str:
        params.append(value)
        return f"${len(params)}"

    if spec.get("town"):
        clauses.append(f"town ILIKE {push('%' + spec['town'] + '%')}")
    if spec.get("outcode"):
        clauses.append(f"outcode ILIKE {push('%' + spec['outcode'] + '%')}")
    if spec.get("min_beds") is not None:
        clauses.append(f"num_beds >= {push(spec['min_beds'])}")
    if spec.get("max_beds") is not None:
        clauses.append(f"num_beds <= {push(spec['max_beds'])}")
    if spec.get("min_price") is not None:
        clauses.append(f"price_paid >= {push(spec['min_price'])}")
    if spec.get("max_price") is not None:
        clauses.append(f"price_paid <= {push(spec['max_price'])}")
    if spec.get("types"):
        clauses.append(f"property_type = ANY({push(spec['types'])}::text[])")
    return (" AND ".join(clauses) if clauses else "TRUE"), params


def satisfies(row: dict[str, Any], spec: dict[str, Any]) -> bool:
    if spec.get("town") and spec["town"].lower() not in (row.get("town") or "").lower():
        return False
    if spec.get("outcode") and spec["outcode"].upper() not in (row.get("outcode") or "").upper():
        return False
    beds = row.get("num_beds")
    if spec.get("min_beds") is not None and (beds is None or beds < spec["min_beds"]):
        return False
    if spec.get("max_beds") is not None and (beds is None or beds > spec["max_beds"]):
        return False
    price = row.get("price_paid") if row.get("price_paid") is not None else row.get("asking_price")
    if spec.get("min_price") is not None and (price is None or float(price) < spec["min_price"]):
        return False
    if spec.get("max_price") is not None and (price is None or float(price) > spec["max_price"]):
        return False
    if spec.get("types") and row.get("property_type") not in spec["types"]:
        return False
    return True


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None, help="only run the first N cases")
    parser.add_argument("--json", default=None, help="write per-case results to this path")
    args = parser.parse_args()

    if not args.dsn or not str(args.dsn).startswith("postgres"):
        print("DATABASE_URL must be a postgres:// or postgresql:// URL")
        return 2
    os.environ["DATABASE_URL"] = args.dsn

    import asyncpg
    from fastapi.testclient import TestClient

    from app.main import app

    cases = CASES[: args.limit] if args.limit else CASES
    pool = await asyncpg.create_pool(args.dsn, min_size=1, max_size=3)

    results: list[dict[str, Any]] = []
    ground_truth: dict[str, list[int]] = {}
    try:
        async with pool.acquire() as conn:
            for case in cases:
                where_sql, params = where_from_spec(case.spec)
                ground_truth[case.name] = [
                    row["id"]
                    for row in await conn.fetch(
                        f"SELECT id FROM properties WHERE {where_sql} ORDER BY id", *params
                    )
                ]
    finally:
        await pool.close()

    with TestClient(app) as client:
        for case in cases:
            started = time.perf_counter()
            response = client.get(
                "/search", params={"query": case.query, "limit": args.k}
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            body = response.json() if response.status_code == 200 else {}
            rows = body.get("properties", [])
            ids = [row["id"] for row in rows]

            matching_ids: list[int] = ground_truth.get(case.name, [])
            if case.kind == "empty":
                precision = 1.0 if not rows else 0.0
                recall = 1.0 if not rows else 0.0
            else:
                precision = (
                    sum(1 for row in rows if satisfies(row, case.spec)) / len(rows)
                    if rows
                    else 0.0
                )
                denominator = min(args.k, len(matching_ids)) or 1
                recall = len(set(ids) & set(matching_ids)) / denominator

            reciprocal_rank = 0.0
            if case.expected_id is not None:
                reciprocal_rank = (
                    0.0 if case.expected_id not in ids else 1.0 / (ids.index(case.expected_id) + 1)
                )

            results.append(
                {
                    "name": case.name,
                    "kind": case.kind,
                    "query": case.query,
                    "status": response.status_code,
                    "returned": len(rows),
                    "matching": len(matching_ids),
                    "precision": round(precision, 3),
                    "recall": round(recall, 3),
                    "mrr": round(reciprocal_rank, 3),
                    "latency_ms": round(elapsed_ms, 1),
                    "top3": ids[:3],
                }
            )

    print(f"{'case':26} {'n':>3} {'match':>5} {'P@k':>5} {'R@k':>5} {'MRR':>5} {'ms':>7}")
    for row in results:
        print(
            f"{row['name']:26} {row['returned']:>3} {row['matching']:>5} "
            f"{row['precision']:>5.2f} {row['recall']:>5.2f} {row['mrr']:>5.2f} "
            f"{row['latency_ms']:>7.1f}"
        )

    def mean(values: list[float]) -> float:
        return round(statistics.fmean(values), 3) if values else 0.0

    constraint = [r for r in results if r["kind"] == "constraint"]
    address = [r for r in results if r["kind"] == "address"]
    empty = [r for r in results if r["kind"] == "empty"]
    latencies = [r["latency_ms"] for r in results]

    summary = {
        "cases": len(results),
        "constraint_precision": mean([r["precision"] for r in constraint]),
        "constraint_recall": mean([r["recall"] for r in constraint]),
        "address_mrr": mean([r["mrr"] for r in address]),
        "empty_ok": mean([r["precision"] for r in empty]),
        "latency_p50": round(statistics.median(latencies), 1),
        "latency_p95": round(
            sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 1
        ),
    }
    print("\nsummary")
    for key, value in summary.items():
        print(f"  {key:22} {value}")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"summary": summary, "results": results}, indent=2),
            encoding="utf-8",
        )
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
