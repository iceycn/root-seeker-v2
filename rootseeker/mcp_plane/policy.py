from __future__ import annotations

from rootseeker.contracts.tool import ToolCallRequest, ToolPermissionLevel, ToolSpec
from rootseeker.policies import ApprovalRequest, ApprovalStore

__all__ = ["ApprovalRequiredError", "PolicyDeniedError", "PolicyGuard"]


class PolicyDeniedError(PermissionError):
    """Raised when PolicyGuard blocks a tool invocation."""


class ApprovalRequiredError(PolicyDeniedError):
    def __init__(self, approval: ApprovalRequest) -> None:
        self.approval = approval
        super().__init__(f"Approval required for tool: {approval.tool_name}")


class PolicyGuard:
    """Minimal guard: optional block on non-read tools (e.g. notify in dry-run)."""

    def __init__(
        self,
        *,
        deny_write: bool = False,
        approval_store: ApprovalStore | None = None,
        require_approval_for_write: bool = False,
    ) -> None:
        self._deny_write = deny_write
        self._approval_store = approval_store
        self._require_approval_for_write = require_approval_for_write

    def enforce(self, request: ToolCallRequest, spec: ToolSpec) -> None:
        if self._deny_write and spec.permission_level != ToolPermissionLevel.READ:
            raise PolicyDeniedError(f"Write tool blocked by policy: {request.tool_name}")
        if (
            not self._require_approval_for_write
            or spec.permission_level == ToolPermissionLevel.READ
        ):
            return
        if self._approval_store is None:
            raise PolicyDeniedError(f"Approval store not configured for tool: {request.tool_name}")
        approval_id = str(
            request.arguments.get("approval_id") or request.arguments.get("_approval_id") or ""
        )
        if approval_id and self._approval_store.is_approved_for(
            approval_id, request=request, spec=spec
        ):
            return
        approval = self._approval_store.create_for_tool(
            request=request,
            spec=spec,
            reason=f"{spec.permission_level.value} tool requires approval",
        )
        raise ApprovalRequiredError(approval)
