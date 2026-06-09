from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rootseeker.cron import CronJobSpec, CronScheduler, JobRunResult, JobRunStatus, parse_schedule
from rootseeker.cron.jobs import CronJobState, CronJobStatus, RetryPolicy
from rootseeker.cron.recovery import recover_stale_running
from rootseeker.cron.stagger import stable_stagger_seconds
from rootseeker.cron.state_store import FileCronStateStore, InMemoryCronStateStore


def test_schedule_parser_returns_next_run() -> None:
    schedule = parse_schedule("*/5 * * * *")
    now = datetime(2026, 4, 28, 10, 1, tzinfo=UTC)

    assert schedule.next_after(now) == datetime(2026, 4, 28, 10, 5, tzinfo=UTC)


def test_stagger_is_stable() -> None:
    first = stable_stagger_seconds("job-a", max_offset_seconds=60)
    second = stable_stagger_seconds("job-a", max_offset_seconds=60)

    assert first == second
    assert 0 <= first <= 60


def test_file_state_store_persists_state_and_history(tmp_path) -> None:
    path = tmp_path / "cron-state.json"
    store = FileCronStateStore(path)
    now = datetime(2026, 4, 28, 10, 0, tzinfo=UTC)

    store.save_state(CronJobState(job_id="job-a", next_run_at=now))
    store.append_run(
        JobRunResult(
            job_id="job-a",
            status=JobRunStatus.SUCCEEDED,
            started_at=now,
            finished_at=now,
        )
    )

    restored = FileCronStateStore(path)
    assert restored.get_state("job-a") is not None
    assert len(restored.list_runs("job-a")) == 1


def test_scheduler_runs_due_job_and_updates_state() -> None:
    now = datetime(2026, 4, 28, 10, 0, tzinfo=UTC)
    job = CronJobSpec(job_id="job-a", schedule="*/5 * * * *", handler="test")
    store = InMemoryCronStateStore()
    store.save_state(CronJobState(job_id=job.job_id, next_run_at=now))

    def executor(spec: CronJobSpec) -> JobRunResult:
        return JobRunResult(
            job_id=spec.job_id,
            status=JobRunStatus.SUCCEEDED,
            started_at=now,
            finished_at=now,
        )

    results = CronScheduler(jobs=[job], executor=executor, state_store=store).tick(now)
    state = store.get_state(job.job_id)

    assert [result.status for result in results] == [JobRunStatus.SUCCEEDED]
    assert state is not None
    assert state.status == CronJobStatus.SUCCEEDED
    assert state.last_success_at == now
    assert state.next_run_at == datetime(2026, 4, 28, 10, 5, tzinfo=UTC)


def test_scheduler_applies_retry_delay_after_failure() -> None:
    now = datetime(2026, 4, 28, 10, 0, tzinfo=UTC)
    job = CronJobSpec(
        job_id="job-a",
        schedule="*/5 * * * *",
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=10, max_delay_seconds=60),
    )
    store = InMemoryCronStateStore()
    store.save_state(CronJobState(job_id=job.job_id, next_run_at=now))

    def executor(spec: CronJobSpec) -> JobRunResult:
        return JobRunResult(
            job_id=spec.job_id,
            status=JobRunStatus.FAILED,
            started_at=now,
            finished_at=now,
            message="boom",
        )

    CronScheduler(jobs=[job], executor=executor, state_store=store).tick(now)
    state = store.get_state(job.job_id)

    assert state is not None
    assert state.status == CronJobStatus.FAILED
    assert state.consecutive_failures == 1
    assert state.next_run_at == now + timedelta(seconds=10)


def test_recovery_clears_stale_running_state() -> None:
    now = datetime(2026, 4, 28, 10, 0, tzinfo=UTC)
    job = CronJobSpec(job_id="job-a", schedule="@hourly", stale_after_seconds=30)
    state = CronJobState(
        job_id=job.job_id,
        status=CronJobStatus.RUNNING,
        last_started_at=now - timedelta(seconds=60),
        running_count=1,
    )

    recovered = recover_stale_running(job, state, now)

    assert recovered.status == CronJobStatus.FAILED
    assert recovered.running_count == 0
    assert recovered.consecutive_failures == 1
