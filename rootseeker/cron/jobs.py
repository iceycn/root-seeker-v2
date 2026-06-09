from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from rootseeker.contracts.common import RootSeekerModel, utc_now

__all__ = [
    "CronJobSpec",
    "CronJobState",
    "CronJobStatus",
    "JobRunResult",
    "JobRunStatus",
    "RetryPolicy",
]


class CronJobStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DISABLED = "disabled"


class JobRunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class RetryPolicy(RootSeekerModel):
    max_attempts: int = Field(default=1, ge=1)
    base_delay_seconds: float = Field(default=30.0, ge=0.0)
    max_delay_seconds: float = Field(default=300.0, ge=0.0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)


class CronJobSpec(RootSeekerModel):
    """Stable cron job contract for scheduler and app entrypoints."""

    job_id: str = Field(min_length=1)
    name: str = Field(default="", description="Human readable job name")
    schedule: str = Field(min_length=1, description="Cron expression or named schedule")
    timezone: str = Field(default="UTC")
    enabled: bool = True
    handler: str = Field(default="", description="Registered handler id")
    max_concurrent_runs: int = Field(default=1, ge=1)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    stale_after_seconds: float = Field(default=900.0, ge=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobRunResult(RootSeekerModel):
    job_id: str = Field(min_length=1)
    status: JobRunStatus
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime = Field(default_factory=utc_now)
    attempt: int = Field(default=1, ge=1)
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class CronJobState(RootSeekerModel):
    job_id: str = Field(min_length=1)
    status: CronJobStatus = CronJobStatus.IDLE
    next_run_at: datetime | None = None
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = Field(default=0, ge=0)
    running_count: int = Field(default=0, ge=0)
    run_count: int = Field(default=0, ge=0)
    updated_at: datetime = Field(default_factory=utc_now)
