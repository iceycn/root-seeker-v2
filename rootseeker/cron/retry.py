from __future__ import annotations

from datetime import datetime, timedelta

from rootseeker.cron.jobs import CronJobSpec, CronJobState

__all__ = ["can_retry", "next_retry_at"]


def can_retry(job: CronJobSpec, state: CronJobState) -> bool:
    return state.consecutive_failures < job.retry_policy.max_attempts


def next_retry_at(job: CronJobSpec, state: CronJobState, failed_at: datetime) -> datetime:
    failures = max(1, state.consecutive_failures)
    delay = job.retry_policy.base_delay_seconds * (
        job.retry_policy.backoff_multiplier ** (failures - 1)
    )
    delay = min(delay, job.retry_policy.max_delay_seconds)
    return failed_at + timedelta(seconds=delay)
