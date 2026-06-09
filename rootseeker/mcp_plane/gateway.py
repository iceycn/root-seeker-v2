from __future__ import annotations

import time
import uuid
from typing import Any

from rootseeker.contracts.audit import AuditCategory, AuditEvent
from rootseeker.contracts.tool import ToolCallRequest, ToolCallResult, ToolError, ToolScope
from rootseeker.mcp_plane.external_client import McpExternalClient
from rootseeker.mcp_plane.policy import ApprovalRequiredError, PolicyDeniedError, PolicyGuard
from rootseeker.mcp_plane.registry import ToolRegistry
from rootseeker.observability.audit import InMemoryAuditLog

__all__ = ["McpGateway"]


class McpGateway:
    """Single entry for internal tool calls: policy → handler → audit."""

    def __init__(
        self,
        registry: ToolRegistry,
        policy: PolicyGuard,
        audit: InMemoryAuditLog,
        external_client: McpExternalClient | None = None,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._audit = audit
        self._external_client = external_client

    def invoke(
        self,
        request: ToolCallRequest,
        *,
        actor: str = "mcp-gateway",
        plugin_id: str | None = None,
        request_id: str | None = None,
    ) -> ToolCallResult:
        started = time.perf_counter()

        def _audit(ok: bool, err: ToolError | None, content: dict[str, Any]) -> None:
            latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            detail: dict[str, Any] = {
                "case_id": request.case_id,
                "step_id": request.step_id,
                "skill_name": request.skill_name,
                "tool_name": request.tool_name,
                "ok": ok,
                "latency_ms": latency_ms,
                "arguments_keys": sorted(request.arguments.keys()),
            }
            if plugin_id is not None:
                detail["plugin_id"] = plugin_id
            if err is not None:
                detail["error"] = err.model_dump(mode="json")
            if content:
                detail["content_preview"] = {k: content[k] for k in list(content)[:5]}
            self._audit.append(
                AuditEvent(
                    event_id=f"audit-{uuid.uuid4()}",
                    category=AuditCategory.TOOL_CALL,
                    action="mcp.invoke",
                    actor=actor,
                    target=request.tool_name,
                    request_id=request_id,
                    detail=detail,
                )
            )

        spec = self._registry.get_spec(request.tool_name)
        if spec is None:
            err = ToolError(
                code="TOOL_NOT_REGISTERED",
                message=f"Tool not registered: {request.tool_name}",
                retryable=False,
            )
            result = ToolCallResult(ok=False, tool_name=request.tool_name, error=err)
            _audit(False, err, {})
            return result

        try:
            self._policy.enforce(request, spec)
        except ApprovalRequiredError as e:
            err = ToolError(
                code="APPROVAL_REQUIRED",
                message=str(e),
                details=e.approval.to_payload(),
                retryable=True,
            )
            result = ToolCallResult(ok=False, tool_name=request.tool_name, error=err)
            _audit(False, err, {})
            return result
        except PolicyDeniedError as e:
            err = ToolError(code="POLICY_DENIED", message=str(e), retryable=False)
            result = ToolCallResult(ok=False, tool_name=request.tool_name, error=err)
            _audit(False, err, {})
            return result

        try:
            if spec.scope == ToolScope.EXTERNAL:
                if self._external_client is None:
                    raise RuntimeError("external client not configured")
                content = self._external_client.invoke(spec, dict(request.arguments))
            else:
                handler = self._registry.get_handler(request.tool_name)
                if handler is None:
                    raise RuntimeError("No handler for internal tool")
                content = handler(dict(request.arguments))
        except Exception as e:  # noqa: BLE001
            err = ToolError(
                code="TOOL_EXEC_ERROR",
                message=str(e),
                details={"type": type(e).__name__},
                retryable=False,
            )
            result = ToolCallResult(ok=False, tool_name=request.tool_name, error=err)
            _audit(False, err, {})
            return result

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        result = ToolCallResult(ok=True, tool_name=request.tool_name, content=content, latency_ms=latency_ms)
        _audit(True, None, content)
        return result
