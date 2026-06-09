from __future__ import annotations

from typing import Any

__all__ = ["extract_trace_id"]


def extract_trace_id(payload: dict[str, Any]) -> str | None:
    for key in ("trace_id", "traceId", "x_trace_id", "trace"):
        value = payload.get(key)
        if value:
            return str(value)
    return None
