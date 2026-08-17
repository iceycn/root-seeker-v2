from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from rootseeker.contracts.common import utc_now
from rootseeker.cron.concurrency import ConcurrencyGuard
from rootseeker.cron.jobs import (
    CronJobSpec,
    CronJobState,
    CronJobStatus,
    JobRunResult,
    JobRunStatus,
)
from rootseeker.cron.recovery import recover_stale_running
from rootseeker.cron.retry import can_retry, next_retry_at
from rootseeker.cron.schedule import parse_schedule
from rootseeker.cron.stagger import stable_stagger_seconds
from rootseeker.cron.state_store import CronStateStore, InMemoryCronStateStore

__all__ = ["CronExecutor", "CronScheduler"]

CronExecutor = Callable[[CronJobSpec], JobRunResult]


class CronScheduler:
    def __init__(
        self,
        *,
        jobs: list[CronJobSpec],
        executor: CronExecutor,
        state_store: CronStateStore | None = None,
        concurrency: ConcurrencyGuard | None = None,
    ) -> None:
        self.jobs = {job.job_id: job for job in jobs}
        self.executor = executor
        self.state_store = state_store or InMemoryCronStateStore()
        self.concurrency = concurrency or ConcurrencyGuard()

    def tick(self, now: datetime | None = None) -> list[JobRunResult]:
        current = now or utc_now()
        results: list[JobRunResult] = []
        for job in self.jobs.values():
            state = self._state_for(job, current)
            recover_stale_running(job, state, current)
            if not job.enabled:
                state.status = CronJobStatus.DISABLED
                self.state_store.save_state(state)
                continue
            if not self._is_due(state, current):
                self.state_store.save_state(state)
                continue
            if not self.concurrency.can_start(job, state):
                self.state_store.save_state(state)
                continue
            results.append(self._run_job(job, state, current))
        return results

    def next_wake_at(self, now: datetime | None = None) -> datetime | None:
        current = now or utc_now()
        next_values: list[datetime] = []
        for job in self.jobs.values():
            if not job.enabled:
                continue
            state = self._state_for(job, current)
            if state.next_run_at is not None:
                next_values.append(state.next_run_at)
        return min(next_values) if next_values else None

    def _run_job(
        self,
        job: CronJobSpec,
        state: CronJobState,
        started_at: datetime,
    ) -> JobRunResult:
        state.status = CronJobStatus.RUNNING
        state.last_started_at = started_at
        state.updated_at = started_at
        self.concurrency.mark_started(state)
        self.state_store.save_state(state)

        try:
            result = self.executor(job)
        except Exception as exc:  # noqa: BLE001
            result = JobRunResult(
                job_id=job.job_id,
                status=JobRunStatus.FAILED,
                started_at=started_at,
                finished_at=utc_now(),
                attempt=state.consecutive_failures + 1,
                message=str(exc),
            )

        finished_at = result.finished_at
        self.concurrency.mark_finished(state)
        state.last_finished_at = finished_at
        state.run_count += 1
        if result.status == JobRunStatus.SUCCEEDED:
            state.status = CronJobStatus.SUCCEEDED
            state.last_success_at = finished_at
            state.last_error = None
            state.consecutive_failures = 0
            state.next_run_at = _schedule_next_run(job, finished_at)
        elif result.status == JobRunStatus.FAILED:
            state.status = CronJobStatus.FAILED
            state.last_error = result.message
            state.consecutive_failures += 1
            state.next_run_at = (
                next_retry_at(job, state, finished_at)
                if can_retry(job, state)
                else _schedule_next_run(job, finished_at)
            )
        else:
            state.status = CronJobStatus.IDLE
            state.next_run_at = _schedule_next_run(job, finished_at)
        state.updated_at = finished_at
        self.state_store.save_state(state)
        self.state_store.append_run(result)
        return result

    def _state_for(self, job: CronJobSpec, now: datetime) -> CronJobState:
        state = self.state_store.get_state(job.job_id)
        if state is None:
            state = CronJobState(
                job_id=job.job_id,
                next_run_at=_schedule_next_run(job, now),
                status=CronJobStatus.IDLE,
            )
            self.state_store.save_state(state)
        return state

    @staticmethod
    def _is_due(state: CronJobState, now: datetime) -> bool:
        return state.next_run_at is not None and state.next_run_at <= now


def _schedule_next_run(job: CronJobSpec, after: datetime) -> datetime:
    next_at = parse_schedule(job.schedule, job.timezone).next_after(after)
    stagger_max = int(job.metadata.get("stagger_max_offset_seconds", 0) or 0)
    if stagger_max > 0:
        offset = stable_stagger_seconds(job.job_id, max_offset_seconds=stagger_max)
        next_at = next_at + timedelta(seconds=offset)
    return next_at
