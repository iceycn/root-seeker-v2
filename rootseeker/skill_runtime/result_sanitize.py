from __future__ import annotations

from copy import deepcopy
from typing import Any

__all__ = [
    "DEFAULT_MAX_CODE_HITS",
    "DEFAULT_MAX_LIST_ITEMS",
    "DEFAULT_MAX_TEXT_CHARS",
    "EVIDENCE_MAX_CODE_HITS",
    "sanitize_tool_result_for_evidence",
    "sanitize_tool_result_for_persistence",
]

# Step outputs / checkpoints keep enough hits for downstream code.read / find_callers.
DEFAULT_MAX_CODE_HITS = 50
DEFAULT_MAX_LIST_ITEMS = 100
DEFAULT_MAX_TEXT_CHARS = 100_000

# Evidence only needs a compact preview for root-cause / LLM context.
EVIDENCE_MAX_CODE_HITS = 20
EVIDENCE_MAX_LIST_ITEMS = 50
EVIDENCE_MAX_TEXT_CHARS = 32_000

_LIST_KEYS = ("hits", "records", "spans", "repos", "sources", "indexes", "items", "results")


def sanitize_tool_result_for_persistence(
    content: dict[str, Any],
    *,
    max_code_hits: int = DEFAULT_MAX_CODE_HITS,
    max_list_items: int = DEFAULT_MAX_LIST_ITEMS,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
) -> dict[str, Any]:
    """Trim oversized tool payloads before writing case steps / checkpoints."""
    return _sanitize(
        content,
        max_code_hits=max_code_hits,
        max_list_items=max_list_items,
        max_text_chars=max_text_chars,
    )


def sanitize_tool_result_for_evidence(
    action: str,
    content: dict[str, Any],
) -> dict[str, Any]:
    """Evidence packs do not need full search corpora — keep a small preview."""
    max_hits = EVIDENCE_MAX_CODE_HITS if action.startswith("code.") else EVIDENCE_MAX_LIST_ITEMS
    return _sanitize(
        content,
        max_code_hits=max_hits,
        max_list_items=EVIDENCE_MAX_LIST_ITEMS,
        max_text_chars=EVIDENCE_MAX_TEXT_CHARS,
    )


def _sanitize(
    content: dict[str, Any],
    *,
    max_code_hits: int,
    max_list_items: int,
    max_text_chars: int,
) -> dict[str, Any]:
    sanitized = deepcopy(content)

    hits = sanitized.get("hits")
    if isinstance(hits, list):
        total = sanitized.get("total")
        if not isinstance(total, int):
            total = len(hits)
        if len(hits) > max_code_hits:
            sanitized["hits"] = hits[:max_code_hits]
            sanitized["truncated"] = True
            sanitized["truncated_from"] = total
        sanitized["total"] = total

    for key in _LIST_KEYS:
        if key == "hits":
            continue
        value = sanitized.get(key)
        if isinstance(value, list) and len(value) > max_list_items:
            sanitized[key] = value[:max_list_items]
            sanitized[f"{key}_truncated"] = True
            sanitized[f"{key}_total"] = len(value)

    content_text = sanitized.get("content")
    if isinstance(content_text, str) and len(content_text) > max_text_chars:
        sanitized["content"] = content_text[:max_text_chars]
        sanitized["content_truncated"] = True
        sanitized["content_total_chars"] = len(content_text)

    return sanitized
