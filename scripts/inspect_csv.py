"""Inspect a listings CSV using only the standard library."""

from __future__ import annotations

import csv
import io
import sys
from collections import Counter
from pathlib import Path


def decode(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise RuntimeError("could not decode CSV")


def main(path: str) -> None:
    text, encoding = decode(Path(path))
    reader = csv.DictReader(io.StringIO(text))
    rows = [row for row in reader]
    columns = reader.fieldnames or []

    print(f"file={path}")
    print(f"encoding={encoding} rows={len(rows)} cols={len(columns)}")
    print(f"columns={columns}\n")

    print("empty rate:")
    for column in columns:
        values = [(row.get(column) or "").strip() for row in rows]
        empty = sum(1 for value in values if not value)
        unique = len(set(values))
        print(f"  {column:30} empty={empty:4} ({empty / max(1, len(rows)):5.1%})  unique={unique}")
    print()

    print("first 3 rows:")
    for row in rows[:3]:
        print("  ", {key: (value or "")[:60] for key, value in row.items()})
    print()

    for column in columns:
        values = [(row.get(column) or "").strip() for row in rows]
        populated = [value for value in values if value]
        if not populated:
            continue
        unique = len(set(populated))
        if unique <= 12:
            print(f"{column}: {dict(Counter(populated).most_common(12))}")
        elif unique > len(rows) * 0.9:
            print(f"{column}: high-cardinality sample={populated[:3]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "search_results(4).csv")
