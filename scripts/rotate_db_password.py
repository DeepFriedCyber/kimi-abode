"""Rotate the password of the `abode` PostgreSQL role on local instances.

Reads the new password from `.env` and the previous one from `.env.bak`
(written by scripts/rotate_secrets.py), then runs ALTER ROLE on each reachable
port. Uses libpq via psql so it works without extra Python dependencies.

    python scripts/rotate_db_password.py --ports 5432,5433
    python scripts/rotate_db_password.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

ROLE = "abode"


def read_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            return stripped.partition("=")[2].strip().strip('"').strip("'")
    return None


def connect(port: int, password: str | None, database: str = "postgres") -> bool:
    url = f"postgresql://{ROLE}:{quote(password or '')}@localhost:{port}/{database}"
    env = {**os.environ, "PGCONNECT_TIMEOUT": "5"}
    result = subprocess.run(
        ["psql", url, "-tAc", "SELECT current_user"],
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode == 0 and ROLE in result.stdout


def alter(port: int, current_password: str, new_password: str) -> tuple[bool, str]:
    url = f"postgresql://{ROLE}:{quote(current_password)}@localhost:{port}/postgres"
    sql = f"ALTER ROLE {ROLE} WITH PASSWORD '{new_password}'"
    result = subprocess.run(
        ["psql", url, "-tAc", sql],
        capture_output=True,
        text=True,
        env={**os.environ, "PGCONNECT_TIMEOUT": "5"},
    )
    detail = (result.stderr or result.stdout).strip().splitlines()
    return result.returncode == 0, (detail[0] if detail else "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ports", default="5432,5433")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--backup-file", default=".env.bak")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not shutil.which("psql"):
        print("psql not found on PATH; install the PostgreSQL client tools")
        return 2

    new_password = read_value(Path(args.env_file), "POSTGRES_PASSWORD")
    old_password = read_value(Path(args.backup_file), "POSTGRES_PASSWORD")
    if not new_password:
        print(f"POSTGRES_PASSWORD missing from {args.env_file}")
        return 2

    rotated = 0
    for port_text in args.ports.split(","):
        port = int(port_text.strip())
        if connect(port, new_password):
            print(f"  port {port}: already using the new password, skipping")
            continue
        if not old_password or not connect(port, old_password):
            print(f"  port {port}: cannot authenticate as {ROLE}, skipping")
            continue
        if args.dry_run:
            print(f"  port {port}: would run ALTER ROLE {ROLE}")
            rotated += 1
            continue
        ok, detail = alter(port, old_password, new_password)
        if not ok:
            print(f"  port {port}: ALTER ROLE failed - {detail}")
            continue
        if connect(port, new_password):
            print(f"  port {port}: password rotated and verified")
            rotated += 1
        else:
            print(f"  port {port}: ALTER ROLE ran but verification failed")

    print(f"instances rotated: {rotated}")
    return 0 if rotated else 1


if __name__ == "__main__":
    raise SystemExit(main())
