from __future__ import annotations

from rootseeker.contracts.common import utc_now
from rootseeker.contracts.evidence import ContextWindow, EvidencePack

__all__ = ["build_context_window"]


def build_context_window(pack: EvidencePack, *, max_tokens: int = 2048) -> ContextWindow:
    segments: list[str] = []
    for item in pack.items:
        segments.append(f"{item.type.value}:{item.source}:{str(item.content)[:200]}")
    used_tokens = min(max_tokens, sum(max(1, len(s) // 4) for s in segments))
    return ContextWindow(
        case_id=pack.case_id,
        max_tokens=max_tokens,
        used_tokens=used_tokens,
        segments=segments,
        notes=f"assembled_at={utc_now().isoformat()}",
    )
