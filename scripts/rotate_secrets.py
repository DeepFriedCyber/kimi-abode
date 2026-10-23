"""Rotate local secrets in-place, with a backup and masked output.

Usage:
    python scripts/rotate_secrets.py            # rotate
    python scripts/rotate_secrets.py --dry-run  # show what would change

Rotates POSTGRES_PASSWORD, JWT_SECRET and POI_INJECTION_SECRET in the given
.env files (defaults to the repo root and api/.env). If DATABASE_URL points at
PostgreSQL, the embedded password is rewritten to match.

What this does NOT do: change the password of a running PostgreSQL role. An
existing database keeps its old password until you run ALTER ROLE — see
docs/SECURITY-NOTICE.md.
"""

from __future__ import annotations

import argparse
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROTATE = {
    "POSTGRES_PASSWORD": lambda: secrets.token_urlsafe(32),
    "JWT_SECRET": lambda: secrets.token_hex(32),
    "POI_INJECTION_SECRET": lambda: secrets.token_hex(32),
}


def rewrite(path: Path, values: dict[str, str], dry_run: bool) -> list[str]:
    """Replace `KEY=value` lines in place, preserving comments and ordering."""
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    changed: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, _rest = stripped.partition("=")
        key = key.strip()
        if key not in values:
            continue
        if key == "DATABASE_URL":
            continue
        newline = line[len(line.rstrip("\r\n")) :]
        lines[index] = f"{key}={values[key]}{newline}"
        changed.append(key)
    if changed and not dry_run:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        path.write_text("".join(lines), encoding="utf-8")
    return changed


def rotate_database_url(path: Path, password: str, dry_run: bool) -> bool:
    """Keep DATABASE_URL consistent when it embeds PostgreSQL credentials."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    touched = False
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("DATABASE_URL="):
            continue
        value = line.partition("=")[2].strip()
        if not value.startswith(("postgres://", "postgresql://")):
            continue
        scheme, _, rest = value.partition("://")
        creds, _, hostpart = rest.rpartition("@")
        user = creds.partition(":")[0]
        newline = line[len(line.rstrip("\r\n")) :]
        lines[index] = f"DATABASE_URL={scheme}://{user}:{password}@{hostpart}{newline}"
        touched = True
    if touched and not dry_run:
        path.write_text("".join(lines), encoding="utf-8")
    return touched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        action="append",
        default=None,
        help="env file to rotate (repeatable); defaults to .env and api/.env",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    paths = [Path(p) for p in (args.env_file or [".env", "api/.env"])]
    values = {key: factory() for key, factory in ROTATE.items()}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    print(f"rotation started {stamp} (dry_run={args.dry_run})")
    rotated_any = False
    for path in paths:
        if not path.exists():
            print(f"  {path}: missing, skipped")
            continue
        changed = rewrite(path, values, args.dry_run)
        print(f"  {path}: rotated {', '.join(changed) if changed else 'nothing'}")
        rotated_any = rotated_any or bool(changed)
        if "POSTGRES_PASSWORD" in changed and rotate_database_url(
            path, values["POSTGRES_PASSWORD"], args.dry_run
        ):
            print(f"  {path}: rewrote DATABASE_URL credentials")

    if not rotated_any:
        print("  nothing rotated — check the keys exist in the env files")
        return 1

    if not args.dry_run:
        print("  backups written as <file>.bak (git-ignored)")
        print("  next: update the PostgreSQL role password, then restart services")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
