from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.common import utc_now
from rootseeker.contracts.task import TaskKind
from rootseeker.cron import (
    CronJobSpec,
    CronJobState,
    CronJobStatus,
    CronScheduler,
    JobRunResult,
    JobRunStatus,
    RetryPolicy,
)
from rootseeker.cron.state_store import FileCronStateStore
from rootseeker.infra_core import RootSeekerSettings
from rootseeker.task_runtime import TaskRuntime

DEFAULT_JOB_ID = "cron.default-flow-replay"
DEFAULT_HANDLER = "replay.default_flow"


def run_once(
    *,
    suite_name: str = "cron-default-flow",
    repeat_each: int = 1,
    schedule: str = "@hourly",
    timezone: str = "UTC",
    state_path: Path | None = None,
    run_immediately: bool = True,
) -> int:
    results = _run_scheduler_tick(
        repo_root=Path.cwd(),
        suite_name=suite_name,
        repeat_each=repeat_each,
        schedule=schedule,
        timezone=timezone,
        state_path=state_path,
        run_immediately=run_immediately,
    )
    if not results:
        print("no cron job due")
        return 1
    result = results[0]
    _print_run_result(result)
    if result.status != JobRunStatus.SUCCEEDED:
        return 2
    return 0


def run_loop(
    *,
    suite_name: str = "cron-default-flow",
    repeat_each: int = 1,
    interval_seconds: float = 60.0,
    max_runs: int = 0,
    retries: int = 2,
    retry_delay_seconds: float = 5.0,
    schedule: str = "@hourly",
    timezone: str = "UTC",
    state_path: Path | None = None,
    run_immediately: bool = True,
) -> int:
    run_count = 0
    first_tick = True
    while max_runs <= 0 or run_count < max_runs:
        attempt = 0
        while True:
            attempt += 1
            try:
                results = _run_scheduler_tick(
                    repo_root=Path.cwd(),
                    suite_name=suite_name,
                    repeat_each=repeat_each,
                    schedule=schedule,
                    timezone=timezone,
                    state_path=state_path,
                    run_immediately=run_immediately and first_tick,
                    retries=retries,
                    retry_delay_seconds=retry_delay_seconds,
                )
                first_tick = False
                break
            except Exception as exc:  # noqa: BLE001
                print(f"scheduler run failed (attempt={attempt}): {exc}")
                if attempt > retries:
                    return 2
                time.sleep(max(0.1, retry_delay_seconds))
        if results:
            for result in results:
                _print_run_result(result)
                if result.status != JobRunStatus.SUCCEEDED:
                    print("scheduler quality gate not passed")
            run_count += len(results)
        if max_runs > 0 and run_count >= max_runs:
            break
        time.sleep(max(0.1, interval_seconds))
    return 0


def _run_scheduler_tick(
    *,
    repo_root: Path,
    suite_name: str,
    repeat_each: int,
    schedule: str,
    timezone: str,
    state_path: Path | None,
    run_immediately: bool,
    retries: int = 1,
    retry_delay_seconds: float = 30.0,
) -> list[JobRunResult]:
    now = utc_now()
    job = _build_default_job(
        suite_name=suite_name,
        repeat_each=repeat_each,
        schedule=schedule,
        timezone=timezone,
        retries=max(1, retries),
        retry_delay_seconds=retry_delay_seconds,
    )
    store = FileCronStateStore(_resolve_state_path(repo_root, state_path))
    if run_immediately:
        _mark_job_due(store, job, now)
    scheduler = CronScheduler(
        jobs=[job],
        executor=_build_executor(repo_root),
        state_store=store,
    )
    return scheduler.tick(now)


def _build_default_job(
    *,
    suite_name: str,
    repeat_each: int,
    schedule: str,
    timezone: str,
    retries: int,
    retry_delay_seconds: float,
) -> CronJobSpec:
    return CronJobSpec(
        job_id=DEFAULT_JOB_ID,
        name="Default flow replay evaluation",
        schedule=schedule,
        timezone=timezone,
        handler=DEFAULT_HANDLER,
        retry_policy=RetryPolicy(
            max_attempts=max(1, retries),
            base_delay_seconds=max(0.0, retry_delay_seconds),
            max_delay_seconds=max(0.0, retry_delay_seconds),
        ),
        metadata={"suite_name": suite_name, "repeat_each": max(1, repeat_each)},
    )


def _build_executor(repo_root: Path):
    def execute(job: CronJobSpec) -> JobRunResult:
        if job.handler != DEFAULT_HANDLER:
            return JobRunResult(
                job_id=job.job_id,
                status=JobRunStatus.FAILED,
                message=f"unsupported cron handler: {job.handler}",
            )
        started_at = utc_now()
        runtime = create_dev_runtime(repo_root)
        task_runtime = TaskRuntime(runtime)
        suite_name = str(job.metadata.get("suite_name") or "cron-default-flow")
        repeat_each = int(job.metadata.get("repeat_each") or 1)
        task = task_runtime.submit(
            kind=TaskKind.CRON,
            payload={"suite_name": suite_name, "repeat_each": repeat_each},
        )
        executed = task_runtime.run_once()
        if executed is None:
            return JobRunResult(
                job_id=job.job_id,
                status=JobRunStatus.FAILED,
                started_at=started_at,
                finished_at=utc_now(),
                message="no task executed",
                payload={"task_id": task.task_id},
            )
        gate_passed = bool(executed.payload.get("report_gate_passed", False))
        release_allowed = bool(executed.payload.get("report_release_allowed", gate_passed))
        completed = executed.status.value == "completed"
        status = JobRunStatus.SUCCEEDED if completed and release_allowed else JobRunStatus.FAILED
        return JobRunResult(
            job_id=job.job_id,
            status=status,
            started_at=started_at,
            finished_at=utc_now(),
            message="" if status == JobRunStatus.SUCCEEDED else "deployment policy did not allow release",
            payload={
                "task_id": executed.task_id,
                "task_status": executed.status.value,
                "task_result_ref": executed.result_ref,
                "suite_name": executed.payload.get("report_suite_name", suite_name),
                "gate_passed": gate_passed,
                "release_allowed": release_allowed,
                "deployment_decision": executed.payload.get("deployment_decision", {}),
                "case_count": int(executed.payload.get("report_case_count", 0)),
            },
        )

    return execute


def _mark_job_due(store: FileCronStateStore, job: CronJobSpec, now: datetime) -> None:
    state = store.get_state(job.job_id) or CronJobState(job_id=job.job_id)
    if state.status != CronJobStatus.RUNNING:
        state.status = CronJobStatus.IDLE
    state.next_run_at = now
    state.updated_at = now
    store.save_state(state)


def _resolve_state_path(repo_root: Path, state_path: Path | None) -> Path:
    configured = state_path or Path(RootSeekerSettings().cron_state_path)
    if configured.is_absolute():
        return configured
    return repo_root / configured


def _print_run_result(result: JobRunResult) -> None:
    payload = result.payload
    print(f"job_id={result.job_id}")
    print(f"job_status={result.status.value}")
    print(f"task_id={payload.get('task_id', '-')}")
    print(f"suite_name={payload.get('suite_name', '-')}")
    print(f"gate_passed={bool(payload.get('gate_passed', False))}")
    print(f"case_count={int(payload.get('case_count', 0))}")
    if result.message:
        print(f"message={result.message}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rootseeker-scheduler", description="RootSeeker scheduler")
    parser.add_argument("--loop", action="store_true", help="run scheduler loop")
    parser.add_argument("--suite-name", default="cron-default-flow")
    parser.add_argument("--repeat-each", type=int, default=1)
    parser.add_argument("--schedule", default="@hourly")
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--state-path", type=Path)
    parser.add_argument(
        "--run-immediately",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="mark the default cron job due before the first tick",
    )
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--max-runs", type=int, default=0, help="0 means unlimited")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=float, default=5.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.loop:
        return run_loop(
            suite_name=args.suite_name,
            repeat_each=args.repeat_each,
            interval_seconds=args.interval_seconds,
            max_runs=args.max_runs,
            retries=args.retries,
            retry_delay_seconds=args.retry_delay_seconds,
            schedule=args.schedule,
            timezone=args.timezone,
            state_path=args.state_path,
            run_immediately=args.run_immediately,
        )
    return run_once(
        suite_name=args.suite_name,
        repeat_each=args.repeat_each,
        schedule=args.schedule,
        timezone=args.timezone,
        state_path=args.state_path,
        run_immediately=args.run_immediately,
    )


if __name__ == "__main__":
    raise SystemExit(main())
