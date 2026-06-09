from __future__ import annotations

from datetime import datetime, timedelta

from rootseeker.contracts.common import utc_now
from rootseeker.cron.jobs import CronJobSpec, CronJobState, CronJobStatus

__all__ = ["recover_stale_running"]


def recover_stale_running(job: CronJobSpec, state: CronJobState, now: datetime | None = None) -> CronJobState:
    current = now or utc_now()
    if state.status != CronJobStatus.RUNNING or state.last_started_at is None:
        return state
    stale_at = state.last_started_at + timedelta(seconds=job.stale_after_seconds)
    if current < stale_at:
        return state
    state.status = CronJobStatus.FAILED
    state.running_count = 0
    state.last_error = "stale running state recovered"
    state.consecutive_failures += 1
    state.updated_at = current
    return state
