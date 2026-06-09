from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from rootseeker.contracts.evidence import RootCauseConclusion


class CaseReport(BaseModel):
    case_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = ""
    root_cause: RootCauseConclusion | None = None
    evidence_item_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
