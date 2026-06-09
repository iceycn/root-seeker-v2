from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CaseStatus(StrEnum):
    PENDING = "pending"
    PLANNED = "planned"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class CaseCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    symptom: str = Field(min_length=1)
    service_name: str = Field(min_length=1)
    source: str = Field(min_length=1, description="alert source or replay source")
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseStep(BaseModel):
    step_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    skill_name: str = Field(min_length=1)
    action: str = Field(min_length=1)
    status: StepStatus = StepStatus.PENDING
    tool_name: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False


class CaseRecord(BaseModel):
    case_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    symptom: str = Field(min_length=1)
    service_name: str = Field(min_length=1)
    source: str = Field(min_length=1)
    status: CaseStatus = CaseStatus.PENDING
    selected_skills: list[str] = Field(default_factory=list)
    steps: list[CaseStep] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CasePlanSnapshot(BaseModel):
    case_id: str = Field(min_length=1)
    status: CaseStatus
    selected_skill: str = Field(min_length=1)
    planned_steps: list[CaseStep] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
