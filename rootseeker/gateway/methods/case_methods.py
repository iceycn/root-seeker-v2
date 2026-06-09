"""Gateway business methods for case operations."""

from __future__ import annotations

from typing import Any

from rootseeker.bootstrap import DevRuntime
from rootseeker.contracts.case import CaseCreateRequest

__all__ = ["register_case_methods"]


def register_case_methods(registry: Any, runtime: DevRuntime) -> None:
    """Register case.* gateway methods.

    Methods:
    - case.create: Create a new case and run default flow
    - case.get: Get case by ID
    - case.list: List cases (with optional filters)
    - case.resume: Resume a case from checkpoint
    """

    def case_create(params: dict[str, Any]) -> dict[str, Any]:
        """Create a case and run default flow.

        Params:
            title: Case title
            symptom: Symptom description
            service_name: Service name
            source: Source identifier (default: "gateway")
            metadata: Optional metadata dict
        """
        req = CaseCreateRequest(
            title=str(params.get("title", "Untitled Case")),
            symptom=str(params.get("symptom", "")),
            service_name=str(params.get("service_name", "unknown-service")),
            source=str(params.get("source", "gateway")),
            metadata=dict(params.get("metadata", {})),
        )
        result = runtime.run_default_flow_from_case_request(req)
        return {
            "case_id": result.case.case_id,
            "status": result.case.status.value,
            "evidence_count": len(result.evidence_pack.items),
        }

    def case_get(params: dict[str, Any]) -> dict[str, Any]:
        """Get case by ID.

        Params:
            case_id: Case ID
        """
        case_id = str(params.get("case_id", ""))
        if not case_id:
            return {"error": "case_id is required"}

        case = runtime.case_store.get(case_id)
        if case is None:
            return {"error": f"case not found: {case_id}", "found": False}

        return {
            "found": True,
            "case": case.model_dump(mode="json"),
        }

    def case_list(params: dict[str, Any]) -> dict[str, Any]:
        """List cases.

        Params:
            status: Optional status filter
            limit: Max results (default: 50)
        """
        limit = int(params.get("limit", 50))
        status = str(params.get("status") or "").strip()
        cases = runtime.case_store.list_all()
        if status:
            cases = [case for case in cases if case.status.value == status]
        cases.sort(key=lambda case: case.updated_at, reverse=True)
        limited = cases[: max(0, limit)]
        return {
            "items": [case.model_dump(mode="json") for case in limited],
            "total": len(cases),
            "limit": limit,
        }

    def case_resume(params: dict[str, Any]) -> dict[str, Any]:
        """Resume a case from checkpoint.

        Params:
            flow_run_id: Flow run ID to resume from
            force: Force replay even if completed
            case_request: Case request payload for resume
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
            return {
                "resumed": True,
                "case_id": result.case_id,
                "flow_run_id": flow_run_id,
            }
        except ValueError as e:
            return {"error": str(e), "resumed": False}

    registry.register("case.create", case_create)
    registry.register("case.get", case_get)
    registry.register("case.list", case_list)
    registry.register("case.resume", case_resume)
