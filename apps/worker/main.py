from __future__ import annotations

import argparse
import time
from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.task import TaskKind
from rootseeker.task_runtime import TaskRuntime


def _seed_demo_task(task_runtime: TaskRuntime) -> None:
    task_runtime.submit(
        kind=TaskKind.CASE_RUN,
        payload={
            "title": "worker demo incident",
            "symptom": "error ratio high in prod",
            "service_name": "order-service",
            "source": "worker",
            "metadata": {"trace_id": "trace-worker-001"},
        },
    )


def run_once(repo_root: Path | None = None, *, seed_demo: bool = False) -> int:
    runtime = create_dev_runtime(repo_root or Path.cwd())
    task_runtime = TaskRuntime(runtime)
    if seed_demo:
        _seed_demo_task(task_runtime)
    task = task_runtime.run_once()
    if task is None:
        print("no task executed")
        return 1
    print(f"task_id={task.task_id}")
    print(f"task_status={task.status.value}")
    print(f"result_ref={task.result_ref}")
    return 0 if task.status.value == "completed" else 1


def run_loop(
    *,
    repo_root: Path | None = None,
    interval_seconds: float = 2.0,
    max_empty_polls: int = 5,
    max_runs: int = 100,
    seed_demo: bool = False,
) -> int:
    runtime = create_dev_runtime(repo_root or Path.cwd())
    task_runtime = TaskRuntime(runtime)
    if seed_demo:
        _seed_demo_task(task_runtime)

    empty_polls = 0
    runs = 0
    while max_runs <= 0 or runs < max_runs:
        task = task_runtime.run_once()
        if task is None:
            empty_polls += 1
            print(f"worker idle: empty_polls={empty_polls}/{max_empty_polls}")
            if max_empty_polls > 0 and empty_polls >= max_empty_polls:
                print("worker stopped: queue empty for too long")
                return 0
        else:
            runs += 1
            empty_polls = 0
            print(f"task_id={task.task_id} status={task.status.value} result_ref={task.result_ref}")
            if task.status.value != "completed":
                return 1
        time.sleep(max(0.1, interval_seconds))
    print(f"worker stopped: reached max_runs={max_runs}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rootseeker-worker", description="RootSeeker worker")
    parser.add_argument("--loop", action="store_true", help="run worker polling loop")
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    parser.add_argument(
        "--max-empty-polls", type=int, default=5, help="0 means unlimited idle polls"
    )
    parser.add_argument("--max-runs", type=int, default=100, help="0 means unlimited task runs")
    parser.add_argument(
        "--seed-demo", action="store_true", help="submit one demo task before polling"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.loop:
        return run_loop(
            repo_root=Path.cwd(),
            interval_seconds=args.interval_seconds,
            max_empty_polls=args.max_empty_polls,
            max_runs=args.max_runs,
            seed_demo=args.seed_demo,
        )
    return run_once(Path.cwd(), seed_demo=args.seed_demo)


if __name__ == "__main__":
    raise SystemExit(main())
