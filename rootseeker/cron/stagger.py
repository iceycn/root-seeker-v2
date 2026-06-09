from __future__ import annotations

import hashlib

__all__ = ["stable_stagger_seconds"]


def stable_stagger_seconds(job_id: str, *, max_offset_seconds: int) -> int:
    if max_offset_seconds <= 0:
        return 0
    digest = hashlib.sha256(job_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % (max_offset_seconds + 1)
