"""Pre-commit secret scan over tracked + untracked (non-ignored) files.

Deliberately conservative: flags high-signal patterns only, so the output is
short enough to actually read before every commit.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PATTERNS = [
    ("password-assignment", re.compile(r"(?i)\b(password|passwd|pwd)\b\s*[:=]\s*['\"]?[^\s'\"]{6,}")),
    ("secret-assignment", re.compile(r"(?i)\b(secret|token|api[_-]?key)\b\s*[:=]\s*['\"]?[^\s'\"]{8,}")),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}")),
    ("openai-key", re.compile(r"sk-[A-Za-z0-9]{32,}")),
    ("aws-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("postgres-url-with-creds", re.compile(r"postgres(?:ql)?://[^\s'\"]+:[^\s'\"]+@")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]

# Placeholders and test fixtures are expected; do not flag them.
ALLOW = re.compile(
    r"(?i)(change-?me|rotate-?me|example|placeholder|your-|xxx+|\*\*\*|dummy|test-?secret|"
    r"<[a-z-]+>|\$\{|process\.env|os\.getenv|os\.environ)"
)

SKIP_SUFFIXES = {".json", ".csv", ".pbf", ".png", ".jpg", ".webp", ".lock"}
SKIP_DIRS = {"node_modules", ".next", "__pycache__", ".git", "data/media", "data/cache"}


def files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-o", "-c", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [f for f in out if Path(f).is_file()]


def main() -> int:
    hits: list[tuple[str, int, str, str]] = []
    scanned = 0
    for name in files():
        if Path(name).suffix.lower() in SKIP_SUFFIXES:
            continue
        if any(part in name.replace("\\", "/") for part in SKIP_DIRS):
            continue
        try:
            text = Path(name).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        for lineno, line in enumerate(text.splitlines(), start=1):
            if ALLOW.search(line):
                continue
            for label, pattern in PATTERNS:
                match = pattern.search(line)
                if match:
                    hits.append((name, lineno, label, match.group(0)[:72]))

    for name, lineno, label, snippet in hits:
        print(f"{name}:{lineno}: [{label}] {snippet}")
    print(f"scanned={scanned} files, hits={len(hits)}")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
