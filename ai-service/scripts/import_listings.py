"""Import a HouseMetric CSV into the demo fixture used by the AI service.

Usage (from ai-service/):
    python -m scripts.import_listings --input "../search_results(4).csv"
    python -m scripts.import_listings --input ... --no-enrich --limit 50

Writes JSON consumed by app.router.DeterministicSearchProvider.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.ingestion.housemetric import import_csv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="HouseMetric CSV path")
    parser.add_argument(
        "--output",
        default="data/demo_listings.json",
        help="Output fixture path (default: data/demo_listings.json)",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip postcodes.io enrichment (no coordinates)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Import only the first N rows")
    args = parser.parse_args()

    records, report = import_csv(
        args.input,
        enrich=not args.no_enrich,
        limit=args.limit,
    )

    if not records:
        print("No records imported", file=sys.stderr)
        return 1

    for index, record in enumerate(records, start=1):
        record["id"] = index

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": Path(args.input).name,
        "count": len(records),
        "report": report.as_dict(),
        "records": records,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report.as_dict(), indent=2))
    print(f"wrote {len(records)} records to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
