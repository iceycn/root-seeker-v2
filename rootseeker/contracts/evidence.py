from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from rootseeker.contracts.common import RootSeekerModel


class EvidenceType(StrEnum):
    LOG = "log"
    TRACE = "trace"
    CODE = "code"
    METRIC = "metric"
    TOPOLOGY = "topology"
    SERVICE_CATALOG = "service_catalog"
    OTHER = "other"


class EvidenceItem(BaseModel):
    item_id: str = Field(min_length=1)
    type: EvidenceType
    source: str = Field(min_length=1, description="e.g. sls, zoekt, catalog tool name")
    content: dict[str, Any] = Field(default_factory=dict)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidencePack(BaseModel):
    case_id: str = Field(min_length=1)
    items: list[EvidenceItem] = Field(default_factory=list)
    summary: str = ""


class ContextWindow(BaseModel):
    """Token-budgeted view derived from evidence; not raw evidence store."""

    case_id: str = Field(min_length=1)
    max_tokens: int = Field(ge=1)
    used_tokens: int = Field(ge=0)
    segments: list[str] = Field(default_factory=list)
    notes: str = ""
    assembled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HypothesisStatus(StrEnum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class Hypothesis(BaseModel):
    hypothesis_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    status: HypothesisStatus = HypothesisStatus.OPEN
    evidence_item_ids: list[str] = Field(default_factory=list)


class RootCauseConclusion(BaseModel):
    title: str = Field(min_length=1)
    narrative: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    contributing_factors: list[str] = Field(default_factory=list)


class TraceSpanRef(RootSeekerModel):
    span_id: str = Field(min_length=1)
    parent_span_id: str | None = None
    service_name: str | None = None
    operation_name: str | None = None
    start_ms: int | None = None
    duration_ms: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class TraceChainEvidence(RootSeekerModel):
    """Structured trace chain; typically embedded in EvidenceItem.content or built from trace.get_chain."""

    trace_id: str = Field(min_length=1)
    spans: list[TraceSpanRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodeHit(RootSeekerModel):
    repository: str = ""
    path: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int | None = Field(default=None, ge=1)
    snippet: str = ""
    score: float | None = None


class CodeEvidence(RootSeekerModel):
    """Structured code search hits; maps to EvidenceType.CODE in EvidenceItem."""

    query: str = ""
    hits: list[CodeHit] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
