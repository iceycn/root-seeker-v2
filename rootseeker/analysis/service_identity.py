"""Infer service identity from free-form logs / alert payloads."""

from __future__ import annotations

import re

__all__ = [
    "PLACEHOLDER_SERVICE_NAMES",
    "extract_service_name_from_text",
    "is_placeholder_service_name",
    "resolve_service_name",
]

PLACEHOLDER_SERVICE_NAMES = frozenset(
    {
        "",
        "unknown",
        "unknown-service",
        "n/a",
        "na",
        "null",
        "none",
        "-",
    }
)

# Timestamp + [service] + [thread]  (common Spring / Logback style)
_BRACKET_AFTER_TS_RE = re.compile(
    r"(?m)^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\s+"
    r"\[([A-Za-z][\w.-]{1,96})\]"
)

# Explicit key=value / key: value forms
_KV_RE = re.compile(
    r"(?i)\b(?:service_name|serviceName|service|app(?:lication)?(?:[_-]?name)?|appName|app_id)\b"
    r"\s*[:=]\s*[\"']?([A-Za-z][\w.-]{1,96})"
)

# Prefer bracket tokens that look like deployable services
_SERVICE_LIKE_BRACKET_RE = re.compile(
    r"\[([A-Za-z][\w.-]*(?:-api|-service|-svc|-server|-web|-gateway|-admin|-worker|-job)[\w.-]*)\]"
)

_REJECT_PREFIXES = (
    "http-nio",
    "http-exec",
    "tid",
    "trace",
    "span",
    "thread",
    "pool-",
    "nio-",
)
_REJECT_EXACT = frozenset(
    {
        "error",
        "warn",
        "warning",
        "info",
        "debug",
        "trace",
        "main",
        "stdout",
        "stderr",
    }
)


def is_placeholder_service_name(value: str | None) -> bool:
    text = str(value or "").strip().lower()
    return text in PLACEHOLDER_SERVICE_NAMES


def extract_service_name_from_text(text: str | None) -> str | None:
    """Best-effort parse of a service name from log / stack / alert text."""
    raw = str(text or "")
    if not raw.strip():
        return None

    for match in _BRACKET_AFTER_TS_RE.finditer(raw):
        candidate = _clean_candidate(match.group(1))
        if candidate:
            return candidate

    for match in _KV_RE.finditer(raw):
        candidate = _clean_candidate(match.group(1))
        if candidate:
            return candidate

    for match in _SERVICE_LIKE_BRACKET_RE.finditer(raw):
        candidate = _clean_candidate(match.group(1))
        if candidate:
            return candidate
    return None


def resolve_service_name(
    *candidates: str | None,
    text: str | None = None,
    default: str = "unknown-service",
) -> str:
    """Pick the first non-placeholder candidate, else extract from text, else default."""
    for value in candidates:
        if not is_placeholder_service_name(value):
            return str(value).strip()
    extracted = extract_service_name_from_text(text)
    if extracted:
        return extracted
    return default


def _clean_candidate(value: str) -> str | None:
    candidate = str(value or "").strip().strip("\"'")
    if len(candidate) < 3 or len(candidate) > 96:
        return None
    lowered = candidate.lower()
    if lowered in _REJECT_EXACT or is_placeholder_service_name(lowered):
        return None
    if any(lowered.startswith(prefix) for prefix in _REJECT_PREFIXES):
        return None
    if not re.search(r"[A-Za-z]", candidate):
        return None
    # Thread pools / executor labels
    if re.search(r"exec-\d+$", lowered) or re.search(r"thread-\d+$", lowered):
        return None
    return candidate
