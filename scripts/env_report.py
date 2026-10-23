"""Report which secret-bearing keys are set in local env files (values masked)."""

from __future__ import annotations

import re
from pathlib import Path

SECRET_HINTS = ("SECRET", "PASSWORD", "API_KEY", "TOKEN", "DATABASE_URL", "AGENT_API_KEY")


def mask(value: str) -> str:
    value = value.strip().strip('"').strip("'")
    if not value:
        return "(empty)"
    if len(value) <= 8:
        return f"set (len={len(value)})"
    return f"set (len={len(value)}, {value[:3]}...)"


for name in (".env", "api/.env", "ai-service/.env", "frontend/.env.local"):
    path = Path(name)
    if not path.exists():
        print(f"{name}: missing")
        continue
    print(f"{name}:")
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if any(hint in key.upper() for hint in SECRET_HINTS):
            extra = ""
            if key.upper() == "DATABASE_URL":
                extra = " host=" + (re.sub(r"://[^@]*@", "://***@", value.strip()) or "")
            print(f"  {key}: {mask(value)}{extra}")
    print()
