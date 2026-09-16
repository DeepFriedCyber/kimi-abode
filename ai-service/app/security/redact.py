"""Security — redact sensitive information from logs and responses."""

from __future__ import annotations

import re


# Patterns for sensitive data types
SENSITIVE_PATTERNS = [
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "CREDIT_CARD"),  # credit card
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "EMAIL"),
    (re.compile(r"Bearer\s+\S+"), "AUTH_TOKEN"),
    (re.compile(r"(?i)(api[_-]?key|secret_key)\s+(?:is\s+)?\S{8,}", re.I), "SECRET"),  # API key <value>
    (re.compile(r"(api[_-]?key|secret|password)\s*[:=]\s*\S+", re.I), "API_KEY"),
]


def redact(text: str) -> str:
    """Redact sensitive information from text."""
    result = text
    for pattern, _label in SENSITIVE_PATTERNS:
        result = pattern.sub(lambda m: f"[REDACTED_{_label}]", result)
    return result


def redact_dict(d: dict, keys_to_redact: set[str] | None = None) -> dict:
    """Recursively redact sensitive keys in a dictionary."""
    redact_keys = keys_to_redact or {"password", "api_key", "secret", "token", "authorization"}
    result = {}
    for k, v in d.items():
        if k.lower() in redact_keys:
            result[k] = "[REDACTED]"
        elif isinstance(v, dict):
            result[k] = redact_dict(v, redact_keys)
        elif isinstance(v, str):
            result[k] = redact(v)
        else:
            result[k] = v
    return result


def log_safe(msg: str) -> str:
    """Redact a log message for safe output."""
    return redact(msg)
