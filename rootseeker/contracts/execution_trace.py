from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from rootseeker.contracts.case import StepStatus
from rootseeker.contracts.common import RootSeekerModel, utc_now
from rootseeker.contracts.errors import ErrorShape

__all__ = [
    "StepExecutionRecord",
    "ExecutionTrace",
    "SkillExecutionTrace",
    "CaseExecutionTrace",
]


class StepExecutionRecord(RootSeekerModel):
    step_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    status: StepStatus = StepStatus.PENDING
    capability: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: ErrorShape | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class ExecutionTrace(RootSeekerModel):
    """Runtime trace for a Case/Flow run (not distributed APM trace)."""

    execution_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    skill_slug: str = Field(min_length=1)
    flow_id: str | None = None
    steps: list[StepExecutionRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class SkillExecutionTrace(RootSeekerModel):
    skill_name: str = Field(min_length=1)
    skill_version: str = Field(min_length=1)
    step_name: str = Field(min_length=1)
    tool_calls: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class CaseExecutionTrace(RootSeekerModel):
    case_id: str = Field(min_length=1)
    skill_name: str = Field(min_length=1)
    flow_plugin_id: str = Field(min_length=1)
    step_traces: list[SkillExecutionTrace] = Field(default_factory=list)
    mcp_call_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    report_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
