from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel, utc_now

__all__ = ["IndexKind", "IndexStatus"]


class IndexKind(StrEnum):
    ZOEKT = "zoekt"
    QDRANT = "qdrant"
    OTHER = "other"


class IndexStatus(RootSeekerModel):
    index_name: str = Field(min_length=1)
    kind: IndexKind
    ready: bool = False
    last_full_sync_at: datetime | None = None
    last_incremental_at: datetime | None = None
    lag_seconds: int | None = Field(default=None, ge=0)
    detail: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=utc_now)
