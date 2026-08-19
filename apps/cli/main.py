from __future__ import annotations

import argparse
from pathlib import Path

from rootseeker.agent_runtime.result import AgentRunResult
from rootseeker.bootstrap import create_dev_runtime
from rootseeker.cli_commands.commands.replay import run_replay_command
from rootseeker.flow_runtime import FlowRuntime


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rootseeker", description="RootSeeker V2 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="run builtin default-flow demo once")
    demo.add_argument(
        "--use-agent",
        action="store_true",
        help="run through AgentRuntime (LLM tool plan)",
    )
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


def _run_demo(repo_root: Path, *, use_agent: bool = False) -> int:
    runtime = create_dev_runtime(repo_root, node_role="cli")
    payload = {
        "title": "CLI demo incident",
        "service_name": "order-service",
        "message": "error ratio high in prod",
        "source": "cli",
        "trace_id": "trace-cli-demo-001",
        "tenant": "demo",
        "environment": "prod",
    }
    if use_agent:
        payload["use_agent"] = True
    flow_result = runtime.run_flow_from_payload(payload)
    if isinstance(flow_result, AgentRunResult):
        case = runtime.case_store.get(flow_result.case_id)
        pack = runtime.evidence_store.get_pack(flow_result.case_id)
        report = runtime.report_store.get(flow_result.case_id)
        print(f"case_id={flow_result.case_id}")
        print(f"status={flow_result.status}")
        print(f"runner=agent")
        print(f"attempt_count={len(flow_result.attempts)}")
        print(f"evidence_count={len(pack.items) if pack else 0}")
        if report is not None:
            print(f"report_summary={report.summary}")
        return 0 if flow_result.status == "completed" else 1

    result = flow_result
    print(f"case_id={result.case.case_id}")
    print(f"status={result.case.status.value}")
    print(f"runner=default_flow")
    print(f"evidence_count={len(result.evidence_pack.items)}")
    return 0 if result.case.status.value == "completed" else 1


def _run_resume(repo_root: Path, args: argparse.Namespace) -> int:
    del repo_root
    print("resume_failed=FLOW_STEP_UNSUPPORTED")
    print(f"flow_run_id={args.flow_run_id}")
    return 2


def _run_resume_list(repo_root: Path, args: argparse.Namespace) -> int:
    runtime = create_dev_runtime(repo_root, node_role="cli")
    flow_runtime = FlowRuntime(runtime)
    items = flow_runtime.list_checkpoints(
        case_id=args.case_id, status=args.status, limit=args.limit
    )
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
        return _run_demo(repo_root, use_agent=bool(args.use_agent))
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
