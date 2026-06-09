from __future__ import annotations

from typing import Any

from rootseeker.bootstrap import DevRuntime

__all__ = ["register_approval_methods"]


def register_approval_methods(registry: Any, runtime: DevRuntime) -> None:
    def approval_list(params: dict[str, Any]) -> dict[str, Any]:
        status = params.get("status")
        limit = int(params.get("limit", 200))
        items = runtime.approval_store.list(status=str(status) if status else None, limit=limit)
        return {"items": [item.to_payload() for item in items], "total": len(items)}

    def approval_get(params: dict[str, Any]) -> dict[str, Any]:
        approval_id = str(params.get("approval_id", ""))
        approval = runtime.approval_store.get(approval_id)
        return {
            "found": approval is not None,
            "approval": approval.to_payload() if approval is not None else None,
        }

    def approval_approve(params: dict[str, Any]) -> dict[str, Any]:
        approval_id = str(params.get("approval_id", ""))
        actor = str(params.get("actor", "gateway"))
        reason = str(params.get("reason", ""))
        approval = runtime.approval_store.approve(approval_id, actor=actor, reason=reason)
        return {"approval": approval.to_payload()}

    def approval_reject(params: dict[str, Any]) -> dict[str, Any]:
        approval_id = str(params.get("approval_id", ""))
        actor = str(params.get("actor", "gateway"))
        reason = str(params.get("reason", ""))
        approval = runtime.approval_store.reject(approval_id, actor=actor, reason=reason)
        return {"approval": approval.to_payload()}

    registry.register("approval.list", approval_list)
    registry.register("approval.get", approval_get)
    registry.register("approval.approve", approval_approve)
    registry.register("approval.reject", approval_reject)
