"""Print a quality report for the demo fixture."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def main(path: str) -> None:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("records", payload)
    print(f"count={len(records)} generated_at={payload.get('generated_at')}")
    print(f"report={payload.get('report')}\n")

    for field in ("town", "property_type", "tenure", "district", "geo_precision"):
        counter = Counter(record.get(field) for record in records)
        print(f"{field}: {dict(counter.most_common(15))}")

    missing = {
        field: sum(1 for record in records if record.get(field) is None)
        for field in ("num_beds", "floor_area_sqm", "plot_size_sqm", "price_per_sqm",
                      "latitude", "longitude", "ward")
    }
    print(f"\nmissing: {missing}")

    prices = [record["price_paid"] for record in records if record.get("price_paid")]
    floors = [record["floor_area_sqm"] for record in records if record.get("floor_area_sqm")]
    psm = [record["price_per_sqm"] for record in records if record.get("price_per_sqm")]
    print(f"\nprice: min={min(prices):,.0f} max={max(prices):,.0f}")
    print(f"floor: min={min(floors):,.0f} max={max(floors):,.0f}")
    print(f"£/m²:  min={min(psm):,.0f} max={max(psm):,.0f}")

    print("\ncheapest 5:")
    for record in sorted(records, key=lambda r: r.get("price_paid") or 0)[:5]:
        print(f"  £{record['price_paid']:>9,.0f} | {record.get('property_type'):14} | "
              f"{record.get('floor_area_sqm')} m² | {record['address_line1']}, {record.get('postcode')}")

    print("\nhighest £/m² 5:")
    for record in sorted(records, key=lambda r: r.get("price_per_sqm") or 0, reverse=True)[:5]:
        print(f"  {record['price_per_sqm']:>9,.0f} | £{record.get('price_paid'):,.0f} / "
              f"{record.get('floor_area_sqm')} m² | {record['address_line1']}")

    print("\nlowest £/m² 5:")
    for record in sorted(records, key=lambda r: r.get("price_per_sqm") or 1e9)[:5]:
        print(f"  {record['price_per_sqm']:>9,.0f} | £{record.get('price_paid'):,.0f} / "
              f"{record.get('floor_area_sqm')} m² | {record['address_line1']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ai-service/data/demo_listings.json")
