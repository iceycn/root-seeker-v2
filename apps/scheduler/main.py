from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from apps.admin.config_store import (
    ALLOWED_CRON_HANDLERS,
    BUILTIN_CRON_JOBS,
    DEFAULT_FLOW_REPLAY_JOB_ID,
    AdminConfigStore,
    build_admin_config_store,
)
from rootseeker.bootstrap import create_dev_runtime
from rootseeker.code_index.git_auth import GitCredentials
from rootseeker.code_index.internal_repo_tools import repo_sync_all_tool, repo_sync_changed_tool
from rootseeker.code_index.repo_sync import RepoSyncService
from rootseeker.contracts.common import utc_now
from rootseeker.contracts.repository import RepositoryRef
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
from rootseeker.cron.state_store import CronStateStore, build_cron_state_store
from rootseeker.infra_core import RootSeekerSettings
from rootseeker.task_runtime import TaskRuntime

DEFAULT_JOB_ID = DEFAULT_FLOW_REPLAY_JOB_ID
DEFAULT_HANDLER = "replay.default_flow"
REPO_SYNC_CHANGED_HANDLER = "repo.sync_changed"
REPO_SYNC_ALL_HANDLER = "repo.sync_all"


def run_once(
    *,
    suite_name: str = "cron-default-flow",
    repeat_each: int = 1,
    schedule: str = "@hourly",
    timezone: str = "UTC",
    state_path: Path | None = None,
    run_immediately: bool = True,
    config_path: Path | None = None,
) -> int:
    results = _run_scheduler_tick(
        repo_root=Path.cwd(),
        suite_name=suite_name,
        repeat_each=repeat_each,
        schedule=schedule,
        timezone=timezone,
        state_path=state_path,
        run_immediately=run_immediately,
        config_path=config_path,
    )
    if not results:
        print("no cron job due")
        return 1
    for result in results:
        _print_run_result(result)
    if any(result.status != JobRunStatus.SUCCEEDED for result in results):
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
    config_path: Path | None = None,
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
                    config_path=config_path,
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


def run_job_now(
    *,
    job_id: str,
    repo_root: Path | None = None,
    state_path: Path | None = None,
    config_path: Path | None = None,
) -> JobRunResult:
    """Execute a single configured cron job immediately (used by Admin run API)."""
    root = repo_root or Path.cwd()
    admin_store = build_admin_config_store(root, path=config_path)
    job_cfg = admin_store.get_cron_job(job_id)
    if job_cfg is None:
        return JobRunResult(
            job_id=job_id,
            status=JobRunStatus.FAILED,
            message=f"cron job not found: {job_id}",
        )
    job = _config_to_spec(
        job_cfg,
        suite_name=str(job_cfg.get("metadata", {}).get("suite_name") or "cron-default-flow"),
        repeat_each=int(job_cfg.get("metadata", {}).get("repeat_each") or 1),
        retries=1,
        retry_delay_seconds=30.0,
    )
    # Manual run must execute even if the job is currently disabled in config.
    job = job.model_copy(update={"enabled": True})
    cron_store = build_cron_state_store(root, state_path=state_path)
    now = utc_now()

    state = cron_store.get_state(job_id) or CronJobState(job_id=job_id)
    if state.status == CronJobStatus.RUNNING:
        started = state.last_started_at
        age_seconds = (now - started).total_seconds() if started is not None else 10_000.0
        # Another request/process just started this job; do not double-run.
        if age_seconds < 5:
            result = JobRunResult(
                job_id=job_id,
                status=JobRunStatus.SKIPPED,
                started_at=now,
                finished_at=now,
                message="任务正在执行中，请稍后再查看运行记录",
            )
            cron_store.append_run(result)
            return result
        # Stuck running (crashed worker / abandoned long job): clear and continue.
        state.status = CronJobStatus.IDLE
        state.running_count = 0
        state.last_error = "cleared stuck running state before manual run"
        state.updated_at = now
        cron_store.save_state(state)

    _mark_job_due(cron_store, job, now)
    scheduler = CronScheduler(
        jobs=[job],
        executor=_build_executor(root, admin_store=admin_store),
        state_store=cron_store,
    )
    results = scheduler.tick(now)
    if not results:
        result = JobRunResult(
            job_id=job_id,
            status=JobRunStatus.SKIPPED,
            started_at=now,
            finished_at=utc_now(),
            message="job was not due / skipped by concurrency guard",
        )
        cron_store.append_run(result)
        return result
    return results[0]


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
    config_path: Path | None = None,
) -> list[JobRunResult]:
    now = utc_now()
    admin_store = build_admin_config_store(repo_root, path=config_path)
    jobs = _load_jobs_from_config(
        admin_store,
        suite_name=suite_name,
        repeat_each=repeat_each,
        cli_schedule=schedule,
        cli_timezone=timezone,
        retries=max(1, retries),
        retry_delay_seconds=retry_delay_seconds,
    )
    store = build_cron_state_store(repo_root, state_path=state_path)
    if run_immediately:
        for job in jobs:
            if job.enabled:
                _mark_job_due(store, job, now)
    scheduler = CronScheduler(
        jobs=jobs,
        executor=_build_executor(repo_root, admin_store=admin_store),
        state_store=store,
    )
    return scheduler.tick(now)


def _resolve_admin_config_path(repo_root: Path, config_path: Path | None) -> Path:
    if config_path is not None:
        return config_path if config_path.is_absolute() else repo_root / config_path
    return repo_root / "data" / "admin" / "config.json"


def _load_jobs_from_config(
    admin_store: AdminConfigStore,
    *,
    suite_name: str,
    repeat_each: int,
    cli_schedule: str,
    cli_timezone: str,
    retries: int,
    retry_delay_seconds: float,
) -> list[CronJobSpec]:
    configs = admin_store.list_cron_jobs()
    if not configs:
        configs = [dict(item) for item in BUILTIN_CRON_JOBS]
    jobs: list[CronJobSpec] = []
    for item in configs:
        job_id = str(item.get("job_id") or "")
        # CLI suite/schedule overrides apply to the legacy replay job for backward compatibility.
        if job_id == DEFAULT_FLOW_REPLAY_JOB_ID:
            metadata = dict(item.get("metadata") or {})
            metadata["suite_name"] = suite_name
            metadata["repeat_each"] = max(1, repeat_each)
            item = dict(item)
            item["metadata"] = metadata
            # Keep config schedule unless still default and CLI provided a custom one.
            if not str(item.get("schedule") or "").strip():
                item["schedule"] = cli_schedule
            if not str(item.get("timezone") or "").strip():
                item["timezone"] = cli_timezone
        jobs.append(
            _config_to_spec(
                item,
                suite_name=suite_name,
                repeat_each=repeat_each,
                retries=retries,
                retry_delay_seconds=retry_delay_seconds,
            )
        )
    return jobs


def _config_to_spec(
    item: dict[str, Any],
    *,
    suite_name: str,
    repeat_each: int,
    retries: int,
    retry_delay_seconds: float,
) -> CronJobSpec:
    handler = str(item.get("handler") or "").strip()
    metadata = dict(item.get("metadata") or {})
    if handler == DEFAULT_HANDLER:
        metadata.setdefault("suite_name", suite_name)
        metadata.setdefault("repeat_each", max(1, repeat_each))
    return CronJobSpec(
        job_id=str(item.get("job_id") or "").strip(),
        name=str(item.get("name") or item.get("job_id") or ""),
        schedule=str(item.get("schedule") or "@hourly"),
        timezone=str(item.get("timezone") or "UTC"),
        enabled=bool(item.get("enabled", True)),
        handler=handler,
        retry_policy=RetryPolicy(
            max_attempts=max(1, retries),
            base_delay_seconds=max(0.0, retry_delay_seconds),
            max_delay_seconds=max(0.0, retry_delay_seconds),
        ),
        metadata=metadata,
    )


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


def _admin_repo_credential_resolver(store: AdminConfigStore):
    def resolve(repo: RepositoryRef) -> GitCredentials | None:
        metadata = dict(repo.metadata or {})
        remote_name = str(metadata.get("remote_name") or "").strip()
        if not remote_name:
            return None
        remote = next(
            (item for item in store.list_repo_remotes() if item.get("name") == remote_name), None
        )
        if remote is None:
            return None
        token = str(remote.get("token") or "").strip()
        if not token:
            return None
        provider = str(remote.get("provider") or metadata.get("provider") or "custom")
        username = str(remote.get("git_username") or metadata.get("git_username") or "").strip()
        return GitCredentials(username=username, token=token, provider=provider)

    return resolve


def _build_repo_sync_service(repo_root: Path, admin_store: AdminConfigStore) -> RepoSyncService:
    settings = RootSeekerSettings()
    service = RepoSyncService(
        base_path=settings.repo_base_path,
        zoekt_endpoint=settings.zoekt_endpoint,
        qdrant_endpoint=settings.qdrant_endpoint,
        qdrant_collection_name=settings.qdrant_collection_name,
        qdrant_api_key=settings.qdrant_api_key,
        zoekt_timeout_seconds=settings.zoekt_timeout_seconds,
        qdrant_timeout_seconds=settings.qdrant_timeout_seconds,
        enable_zoekt=settings.repo_enable_zoekt,
        enable_qdrant=settings.repo_enable_qdrant,
        credential_resolver=_admin_repo_credential_resolver(admin_store),
    )
    for repo in admin_store.list_repos():
        service.register(repo)
    return service


def _build_executor(repo_root: Path, *, admin_store: AdminConfigStore | None = None):
    store = admin_store or build_admin_config_store(repo_root)

    def execute(job: CronJobSpec) -> JobRunResult:
        handler = str(job.handler or "").strip()
        if handler not in ALLOWED_CRON_HANDLERS:
            return JobRunResult(
                job_id=job.job_id,
                status=JobRunStatus.FAILED,
                message=f"unsupported cron handler: {job.handler}",
            )
        started_at = utc_now()
        if handler == REPO_SYNC_CHANGED_HANDLER:
            service = _build_repo_sync_service(repo_root, store)
            payload = repo_sync_changed_tool(service, {"trigger_index": True})
            ok = bool(payload.get("ok", False))
            failed_checks = payload.get("failed_checks") or []
            if ok and failed_checks:
                message = f"synced with {len(failed_checks)} check warning(s)"
            elif ok:
                message = ""
            else:
                message = "one or more changed repos failed to sync"
            return JobRunResult(
                job_id=job.job_id,
                status=JobRunStatus.SUCCEEDED if ok else JobRunStatus.FAILED,
                started_at=started_at,
                finished_at=utc_now(),
                message=message,
                payload=payload,
            )
        if handler == REPO_SYNC_ALL_HANDLER:
            service = _build_repo_sync_service(repo_root, store)
            payload = repo_sync_all_tool(service, {"trigger_index": True})
            results = payload.get("results") or []
            ok = bool(payload.get("ok", True)) and all(
                bool(item.get("success")) for item in results
            )
            return JobRunResult(
                job_id=job.job_id,
                status=JobRunStatus.SUCCEEDED if ok else JobRunStatus.FAILED,
                started_at=started_at,
                finished_at=utc_now(),
                message="" if ok else "one or more repos failed to sync",
                payload=payload,
            )

        # replay.default_flow
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
            message=""
            if status == JobRunStatus.SUCCEEDED
            else "deployment policy did not allow release",
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


def _mark_job_due(store: CronStateStore, job: CronJobSpec, now: datetime) -> None:
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
    if "task_id" in payload:
        print(f"task_id={payload.get('task_id', '-')}")
        print(f"suite_name={payload.get('suite_name', '-')}")
        print(f"gate_passed={bool(payload.get('gate_passed', False))}")
        print(f"case_count={int(payload.get('case_count', 0))}")
    if "changed" in payload:
        print(f"changed={payload.get('changed', [])}")
        print(f"synced={payload.get('synced', [])}")
        print(f"skipped={payload.get('skipped', [])}")
    if result.message:
        print(f"message={result.message}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rootseeker-scheduler", description="RootSeeker scheduler"
    )
    parser.add_argument("--loop", action="store_true", help="run scheduler loop")
    parser.add_argument("--suite-name", default="cron-default-flow")
    parser.add_argument("--repeat-each", type=int, default=1)
    parser.add_argument("--schedule", default="@hourly")
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--state-path", type=Path)
    parser.add_argument("--config-path", type=Path, help="admin config.json path for cron_jobs")
    parser.add_argument(
        "--run-immediately",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="mark enabled cron jobs due before the first tick",
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
            config_path=args.config_path,
        )
    return run_once(
        suite_name=args.suite_name,
        repeat_each=args.repeat_each,
        schedule=args.schedule,
        timezone=args.timezone,
        state_path=args.state_path,
        run_immediately=args.run_immediately,
        config_path=args.config_path,
    )


if __name__ == "__main__":
    raise SystemExit(main())
