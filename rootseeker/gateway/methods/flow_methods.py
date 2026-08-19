"""Gateway business methods for flow operations."""

from __future__ import annotations

from typing import Any

from rootseeker.bootstrap import DevRuntime
from rootseeker.contracts.case import CaseCreateRequest

__all__ = ["register_flow_methods"]


def register_flow_methods(registry: Any, runtime: DevRuntime) -> None:
    """Register flow.* gateway methods.

    Methods:
    - flow.run: Run default Agent playbook
    - flow.checkpoints: List checkpoints
    """

    def flow_run(params: dict[str, Any]) -> dict[str, Any]:
        """Run default flow.

        Params:
            title: Case title
            symptom: Symptom description
            service_name: Service name
            source: Source identifier
            metadata: Optional metadata
        """
        from rootseeker.flow_runtime import FlowRuntime

        req = CaseCreateRequest(
            title=str(params.get("title", "Untitled Flow")),
            symptom=str(params.get("symptom", "")),
            service_name=str(params.get("service_name", "unknown-service")),
            source=str(params.get("source", "gateway")),
            metadata=dict(params.get("metadata", {})),
        )

        flow_runtime = FlowRuntime(runtime)
        result = flow_runtime.run_default(req)

        return {
            "case_id": result.case_id,
            "flow_run_id": result.trace.execution_id,
            "status": "completed",
            "step_count": len(result.trace.steps),
        }

    def flow_checkpoints(params: dict[str, Any]) -> dict[str, Any]:
        """List flow checkpoints.

        Params:
            case_id: Optional case ID filter
            status: Optional status filter
            limit: Max results
        """
        from rootseeker.flow_runtime import FlowRuntime

        flow_runtime = FlowRuntime(runtime)
        items = flow_runtime.list_checkpoints(
            case_id=params.get("case_id"),
            status=params.get("status"),
            limit=int(params.get("limit", 50)),
        )

        return {
            "items": items,
            "total": len(items),
        }

    registry.register("flow.run", flow_run)
    registry.register("flow.checkpoints", flow_checkpoints)
