from __future__ import annotations

import argparse
from pathlib import Path

from rootseeker.agent_runtime.result import AgentRunResult
from rootseeker.bootstrap import create_dev_runtime


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RootSeeker default-flow demo")
    parser.add_argument(
        "--use-agent",
        action="store_true",
        help="run through AgentRuntime (LLM tool plan with default-flow fallback)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    runtime = create_dev_runtime(repo_root)
    payload = {
        "title": "Order service 5xx spike",
        "service_name": "order-service",
        "message": "error ratio high in prod",
        "source": "demo-script",
        "trace_id": "trace-demo-001",
        "tenant": "demo",
        "environment": "prod",
    }
    if args.use_agent:
        payload["use_agent"] = True

    flow_result = runtime.run_flow_from_payload(payload)

    print("=== RootSeeker V2 Demo ===")
    if isinstance(flow_result, AgentRunResult):
        case = runtime.case_store.get(flow_result.case_id)
        report = runtime.report_store.get(flow_result.case_id)
        pack = runtime.evidence_store.get_pack(flow_result.case_id)
        print(f"case_id: {flow_result.case_id}")
        print(f"status: {flow_result.status}")
        print(f"runner: agent")
        print(f"attempt_count: {len(flow_result.attempts)}")
        print(f"evidence_count: {len(pack.items) if pack else 0}")
        if report is not None:
            print(f"report_summary: {report.summary}")
        print(f"audit_events: {runtime.audit_log.count()}")
        return 0 if flow_result.status == "completed" else 1

    result = flow_result
    print(f"case_id: {result.case.case_id}")
    print(f"status: {result.case.status.value}")
    print(f"runner: default_flow")
    print(f"selected_skill: {result.case.selected_skills[0] if result.case.selected_skills else 'N/A'}")
    print(f"steps: {len(result.case.steps)}")
    print(f"evidence_count: {len(result.evidence_pack.items)}")
    print(f"report_summary: {result.report.summary}")
    print(f"audit_events: {runtime.audit_log.count()}")
    return 0 if result.case.status.value == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
