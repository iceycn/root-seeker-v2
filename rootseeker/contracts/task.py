from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel, utc_now

__all__ = ["TaskKind", "TaskStatus", "TaskRecord"]


class TaskKind(StrEnum):
    CASE_RUN = "case_run"
    FLOW_RESUME = "flow_resume"
    FLOW_STEP = "flow_step"
    CRON = "cron"
    REPLAY = "replay"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskRecord(RootSeekerModel):
    task_id: str = Field(min_length=1)
    kind: TaskKind
    case_id: str | None = None
    flow_id: str | None = None
    skill_slug: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    payload: dict[str, Any] = Field(default_factory=dict)
    result_ref: str | None = None
    error: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
