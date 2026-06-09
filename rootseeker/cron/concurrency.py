from __future__ import annotations

from rootseeker.cron.jobs import CronJobSpec, CronJobState

__all__ = ["ConcurrencyGuard"]


class ConcurrencyGuard:
    def can_start(self, job: CronJobSpec, state: CronJobState) -> bool:
        return state.running_count < job.max_concurrent_runs

    def mark_started(self, state: CronJobState) -> CronJobState:
        state.running_count += 1
        return state

    def mark_finished(self, state: CronJobState) -> CronJobState:
        state.running_count = max(0, state.running_count - 1)
        return state
