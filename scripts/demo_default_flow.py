from __future__ import annotations

from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime


def main() -> int:
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
    result = runtime.run_default_flow_from_payload(payload)

    print("=== RootSeeker V2 Demo ===")
    print(f"case_id: {result.case.case_id}")
    print(f"status: {result.case.status.value}")
    print(f"selected_skill: {result.case.selected_skills[0] if result.case.selected_skills else 'N/A'}")
    print(f"steps: {len(result.case.steps)}")
    print(f"evidence_count: {len(result.evidence_pack.items)}")
    print(f"report_summary: {result.report.summary}")
    print(f"audit_events: {runtime.audit_log.count()}")
    return 0 if result.case.status.value == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
