"""Scrub secrets from log text before it is handed to a model."""

import re

_PATTERNS = (
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)\b(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@"), r"\1[REDACTED]@"),
    (
        re.compile(
            r"(?i)\b((?:access_|refresh_|api_|auth_)?token|password|passwd|pwd|"
            r"api[_-]?key|secret|client_secret)(\"?\s*[:=]\s*\"?)([^\s\"',&}]+)"
        ),
        r"\1\2[REDACTED]",
    ),
)

DEFAULT_MAX_CHARS = 20_000


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def tail(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[-max_chars:]
    newline = cut.find("\n")
    if 0 <= newline < 500:
        cut = cut[newline + 1 :]
    return f"[... truncated {len(text) - len(cut)} earlier characters ...]\n{cut}"
