"""Unwrap nested log / alert shells so stack traces become parseable text."""

from __future__ import annotations

import json
from typing import Any

__all__ = ["unwrap_embedded_log_text"]

_EMBEDDED_KEYS = ("content", "message", "log", "log_content", "body", "text")
_MAX_DEPTH = 6


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
    if "\\n" in text or "\\t" in text:
        unescaped = text.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
        if unescaped != text:
            return unescaped
    return value


def _try_parse_json(text: str) -> Any:
    if not text or text[0] not in "{[\"":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
