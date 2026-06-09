from __future__ import annotations

import argparse
from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.cli_commands.commands.replay import run_replay_command
from rootseeker.contracts.task import TaskKind
from rootseeker.flow_runtime import FlowRuntime
from rootseeker.task_runtime import TaskRuntime


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rootseeker", description="RootSeeker V2 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("demo", help="run builtin default-flow demo once")
    sub.add_parser("replay", help="run replay suite once and evaluate gate")
    resume = sub.add_parser("resume", help="resume a flow run from checkpoint")
    resume.add_argument("--flow-run-id", required=True)
    resume.add_argument("--title", required=True)
    resume.add_argument("--symptom", required=True)
    resume.add_argument("--service-name", required=True)
    resume.add_argument("--source", default="cli-resume")
    resume.add_argument("--trace-id", default="trace-cli-resume-001")
    resume.add_argument("--force", action="store_true")
    list_resume = sub.add_parser("resume-list", help="list resumable flow checkpoints")
    list_resume.add_argument("--case-id")
    list_resume.add_argument("--status")
    list_resume.add_argument("--limit", type=int, default=50)
    return parser


def _run_demo(repo_root: Path) -> int:
    runtime = create_dev_runtime(repo_root)
    result = runtime.run_default_flow_from_payload(
        {
            "title": "CLI demo incident",
            "service_name": "order-service",
            "message": "error ratio high in prod",
            "source": "cli",
            "trace_id": "trace-cli-demo-001",
            "tenant": "demo",
            "environment": "prod",
        }
    )
    print(f"case_id={result.case.case_id}")
    print(f"status={result.case.status.value}")
    print(f"evidence_count={len(result.evidence_pack.items)}")
    return 0 if result.case.status.value == "completed" else 1


def _run_resume(repo_root: Path, args: argparse.Namespace) -> int:
    runtime = create_dev_runtime(repo_root)
    task_runtime = TaskRuntime(runtime)
    task = task_runtime.submit(
        kind=TaskKind.FLOW_RESUME,
        payload={
            "flow_run_id": args.flow_run_id,
            "force": bool(args.force),
            "case_request": {
                "title": args.title,
                "symptom": args.symptom,
                "service_name": args.service_name,
                "source": args.source,
                "metadata": {"trace_id": args.trace_id},
            },
        },
    )
    try:
        executed = task_runtime.run_once()
    except Exception as exc:  # noqa: BLE001
        print(f"resume_failed={exc}")
        return 2
    if executed is None:
        return 2
    print(f"task_id={task.task_id}")
    print(f"task_status={executed.status.value}")
    print(f"resume_status={executed.payload.get('resume_status', 'unknown')}")
    if executed.error:
        print(f"error={executed.error}")
        return 2
    return 0 if executed.status.value == "completed" else 2


def _run_resume_list(repo_root: Path, args: argparse.Namespace) -> int:
    runtime = create_dev_runtime(repo_root)
    flow_runtime = FlowRuntime(runtime)
    items = flow_runtime.list_checkpoints(case_id=args.case_id, status=args.status, limit=args.limit)
    print(f"checkpoint_count={len(items)}")
    for item in items:
        print(
            f"flow_run_id={item['flow_run_id']} revision={item['revision']} "
            f"status={item['payload'].get('status', 'unknown')}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    repo_root = Path.cwd()
    if args.command == "demo":
        return _run_demo(repo_root)
    if args.command == "replay":
        return run_replay_command(repo_root)
    if args.command == "resume":
        return _run_resume(repo_root, args)
    if args.command == "resume-list":
        return _run_resume_list(repo_root, args)
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
