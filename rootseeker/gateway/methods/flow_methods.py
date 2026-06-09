"""Gateway business methods for flow operations."""

from __future__ import annotations

from typing import Any

from rootseeker.bootstrap import DevRuntime
from rootseeker.contracts.case import CaseCreateRequest

__all__ = ["register_flow_methods"]


def register_flow_methods(registry: Any, runtime: DevRuntime) -> None:
    """Register flow.* gateway methods.

    Methods:
    - flow.run: Run default flow
    - flow.resume: Resume flow from checkpoint
    - flow.step: Execute single step from checkpoint
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

    def flow_resume(params: dict[str, Any]) -> dict[str, Any]:
        """Resume flow from checkpoint.

        Params:
            flow_run_id: Flow run ID
            force: Force replay
            case_request: Case request for resume
        """
        from rootseeker.flow_runtime import FlowRuntime

        flow_run_id = str(params.get("flow_run_id", ""))
        if not flow_run_id:
            return {"error": "flow_run_id is required"}

        force = bool(params.get("force", False))
        req_payload = params.get("case_request", {})

        flow_runtime = FlowRuntime(runtime)

        try:
            req = CaseCreateRequest.model_validate(req_payload)
        except Exception as e:
            return {"error": f"invalid case_request: {e}"}

        try:
            result = flow_runtime.resume_default(
                flow_run_id=flow_run_id,
                case_request=req,
                force=force,
            )
            if result is None:
                return {
                    "resumed": False,
                    "reason": "skipped_completed",
                    "flow_run_id": flow_run_id,
                }
            checkpoint = flow_runtime.checkpoints.get(flow_run_id) or {}
            return {
                "resumed": True,
                "resume_status": checkpoint.get("resume_status", "unknown"),
                "case_id": result.case_id,
                "flow_run_id": flow_run_id,
            }
        except ValueError as e:
            return {"error": str(e), "resumed": False}

    def flow_step(params: dict[str, Any]) -> dict[str, Any]:
        """Execute single step from checkpoint.

        Params:
            flow_run_id: Flow run ID
            step_index: Step index to execute from
            case_request: Case request
        """
        from rootseeker.flow_runtime import FlowRuntime
        from rootseeker.flow_runtime.flow_executor import FlowExecutor

        flow_run_id = str(params.get("flow_run_id", ""))
        step_index = int(params.get("step_index", 0))

        if not flow_run_id:
            return {"error": "flow_run_id is required"}

        flow_runtime = FlowRuntime(runtime)
        record = flow_runtime.checkpoints.get_record(flow_run_id)
        if record is None:
            return {"error": f"checkpoint not found: {flow_run_id}"}

        req_payload = params.get("case_request", {})
        try:
            req = CaseCreateRequest.model_validate(req_payload)
        except Exception as e:
            return {"error": f"invalid case_request: {e}"}

        prior_outputs: dict[str, dict[str, Any]] = {}
        for step_info in record.payload.get("steps", []):
            step_id = str(step_info.get("step_id", ""))
            outputs = step_info.get("outputs")
            if step_id and isinstance(outputs, dict):
                prior_outputs[step_id] = dict(outputs)

        prior_case_id = str(record.payload.get("case_id", ""))

        executor = FlowExecutor(runtime)
        result = executor.execute_from_checkpoint(
            req,
            start_from_step_index=step_index,
            prior_step_outputs=prior_outputs,
            prior_case_id=prior_case_id,
        )

        return {
            "executed": True,
            "case_id": result.case_id,
            "step_index": step_index,
            "flow_run_id": flow_run_id,
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
    registry.register("flow.resume", flow_resume)
    registry.register("flow.step", flow_step)
    registry.register("flow.checkpoints", flow_checkpoints)
