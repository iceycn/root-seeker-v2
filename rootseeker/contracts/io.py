from __future__ import annotations

from typing import Any

from pydantic import Field

from rootseeker.contracts.case import CaseStatus
from rootseeker.contracts.common import RootSeekerModel
from rootseeker.contracts.evidence import EvidenceType
from rootseeker.contracts.skill import SkillSourceKind

__all__ = ["CaseAccepted", "EvidenceCollectRequest", "SkillFilterRequest"]


class SkillFilterRequest(RootSeekerModel):
    """Select or rank skills for a Case (registry query contract)."""

    tags: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    text_query: str = ""
    source_kind: SkillSourceKind | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceCollectRequest(RootSeekerModel):
    """Ask evidence layer to gather items for a Case (or step); execution still via Skill/Plugin/MCP."""

    case_id: str = Field(min_length=1)
    step_id: str | None = None
    kinds: list[EvidenceType] = Field(default_factory=list)
    hints: dict[str, Any] = Field(default_factory=dict)


class CaseAccepted(RootSeekerModel):
    """Response after Case is accepted for processing (e.g. from API or channel)."""

    case_id: str = Field(min_length=1)
    status: CaseStatus = CaseStatus.PENDING
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
