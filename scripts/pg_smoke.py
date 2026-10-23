"""Smoke-test the AI service against a real PostgreSQL database.

Runs the FastAPI app in-process (lifespan opens the pool) and exercises the
paths that unit tests only cover with fakes: SQL search, live listings, property
detail, photo joins and the POI endpoint.

    python scripts/pg_smoke.py --dsn postgresql://abode:...@127.0.0.1:5544/abode
    python scripts/pg_smoke.py            # uses DATABASE_URL from .env

Exit code is non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ai-service"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

CHECKS = 0
FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {label}{(' — ' + detail) if detail else ''}")
    if not condition:
        FAILURES.append(label)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()

    if not args.dsn or not str(args.dsn).startswith("postgres"):
        print("DATABASE_URL must be a postgres:// or postgresql:// URL")
        return 2
    os.environ["DATABASE_URL"] = args.dsn
    os.environ.setdefault("DEMO_DATA", "true")

    from fastapi.testclient import TestClient  # noqa: E402

    from app.main import app  # noqa: E402

    with TestClient(app) as client:
        print("health")
        health = client.get("/health").json()
        check("health db reachable", health.get("db") is True, f"mode={health.get('mode')}")

        print("db info")
        info = client.get("/db/info")
        check("db/info returns 200", info.status_code == 200, str(info.status_code))
        if info.status_code == 200:
            payload = info.json()
            check("db/info connected", payload.get("connected") is True, str(payload.get("database")))

        print("search: natural language")
        started = time.perf_counter()
        nl = client.get("/search", params={"query": "3 bed semi-detached in Sandbach under 250000"})
        nl_ms = (time.perf_counter() - started) * 1000
        check("nl search 200", nl.status_code == 200, str(nl.status_code))
        nl_body = nl.json() if nl.status_code == 200 else {}
        check("nl search has matches", nl_body.get("total_matches", 0) > 0, f"total={nl_body.get('total_matches')}")
        check("nl search tier set", bool(nl_body.get("tier_used")), str(nl_body.get("tier_used")))
        check("nl search under 2s", nl_ms < 2000, f"{nl_ms:.0f} ms")
        rows = nl_body.get("properties", [])
        if rows:
            first = rows[0]
            check("row has id and address", bool(first.get("id")) and bool(first.get("address_line1")), first.get("address_line1", ""))
            check("row has comparison price", first.get("price_paid") is not None or first.get("asking_price") is not None)

        print("search: structured filters")
        filtered = client.get(
            "/search",
            params={"query": "", "location": "Sandbach", "min_beds": 3, "max_price": 250000},
        )
        check("filtered search 200", filtered.status_code == 200, str(filtered.status_code))
        filtered_body = filtered.json() if filtered.status_code == 200 else {}
        check("filtered search has matches", filtered_body.get("total_matches", 0) > 0, f"total={filtered_body.get('total_matches')}")
        wrong = [
            row
            for row in filtered_body.get("properties", [])
            if (row.get("num_beds") or 0) < 3
            or (row.get("price_paid") or row.get("asking_price") or 0) > 250000
        ]
        check("filters respected", not wrong, f"{len(wrong)} out-of-range rows")

        print("search: outcode")
        outcode = client.get("/search", params={"query": "", "outcode": "CW11", "limit": 5})
        check("outcode search 200", outcode.status_code == 200, str(outcode.status_code))
        outcode_rows = outcode.json().get("properties", []) if outcode.status_code == 200 else []
        check("outcode rows match", all((row.get("outcode") or "") == "CW11" for row in outcode_rows), f"{len(outcode_rows)} rows")

        print("search: type filter")
        typed = client.get("/search", params={"query": "", "property_types": "detached", "limit": 10})
        typed_rows = typed.json().get("properties", []) if typed.status_code == 200 else []
        check("type rows match", all(row.get("property_type") == "detached" for row in typed_rows), f"{len(typed_rows)} rows")

        print("property detail")
        if rows:
            prop_id = rows[0]["id"]
            detail = client.get("/property", params={"id": prop_id})
            check("property 200", detail.status_code == 200, str(detail.status_code))
            body = detail.json() if detail.status_code == 200 else {}
            check("property has address", bool(body.get("address_line1")), body.get("address_line1", ""))
            check("property has photos key", "photos" in body)

            nearby = client.get(f"/property/{prop_id}/nearby", params={"q": "nearest supermarket"})
            check("nearby 200", nearby.status_code == 200, str(nearby.status_code))
            if nearby.status_code == 200:
                answer = nearby.json().get("answer", "")
                check("nearby answer is imperial", " mile" in answer or "yards" in answer, answer[:60])

        missing = client.get("/property", params={"id": 99_999_999})
        check("unknown property 404", missing.status_code == 404, str(missing.status_code))

    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
    for failure in FAILURES:
        print(f"  failed: {failure}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
