"""Unwrap nested log / alert shells so stack traces become parseable text."""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = ["unwrap_embedded_log_text"]

_EMBEDDED_KEYS = (
    "content",
    "message",
    "log",
    "log_content",
    "body",
    "text",
    "stackTrace",
    "stack_trace",
    "exception",
    "error",
    "err_msg",
)
_MAX_DEPTH = 6
_EMBEDDED_KEY_RE = re.compile(
    r'"(?:' + "|".join(re.escape(k) for k in _EMBEDDED_KEYS) + r')"\s*:\s*"(.*)',
    re.DOTALL,
)


def unwrap_embedded_log_text(value: Any, *, depth: int = 0) -> str:
    """Recursively peel SLS/alert JSON wrappers such as ``{"content": "...stack..."}``."""
    if value is None:
        return ""
    if depth > _MAX_DEPTH:
        return str(value)
    if isinstance(value, dict):
        for key in _EMBEDDED_KEYS:
            inner = value.get(key)
            if inner is None or inner == "":
                continue
            unwrapped = unwrap_embedded_log_text(inner, depth=depth + 1)
            if str(unwrapped).strip():
                return unwrapped
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:
            unwrapped = unwrap_embedded_log_text(item, depth=depth + 1)
            if str(unwrapped).strip():
                return unwrapped
        return ""
    if not isinstance(value, str):
        return str(value)
    text = value.strip()
    if not text:
        return ""
    parsed = _try_parse_json(text)
    if parsed is not None and parsed != text:
        inner = unwrap_embedded_log_text(parsed, depth=depth + 1)
        if inner.strip() and inner != text:
            return inner
        if isinstance(parsed, str) and parsed.strip():
            return _unescape_log_escapes(parsed)
    if "\\n" in text or "\\t" in text:
        unescaped = _unescape_log_escapes(text)
        if unescaped != text:
            return unescaped
    return value


def _unescape_log_escapes(text: str) -> str:
    return text.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\\\", "\\")


def _try_parse_json(text: str) -> Any:
    if not text or text[0] not in "{[\"":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _salvage_truncated_embedded(text)


def _salvage_truncated_embedded(text: str) -> str | None:
    """Recover log body from truncated JSON that still embeds stack text."""
    match = _EMBEDDED_KEY_RE.search(text)
    if not match:
        return None
    raw = match.group(1)
    if raw.endswith('"'):
        raw = raw[:-1]
    unescaped = _unescape_log_escapes(raw)
    lowered = unescaped.lower()
    if "at " in unescaped or "exception" in lowered or "\n" in unescaped:
        return unescaped
    return None
