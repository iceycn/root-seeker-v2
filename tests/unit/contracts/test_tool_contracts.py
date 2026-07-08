from rootseeker.contracts.tool import (
    ToolCallRequest,
    ToolCallResult,
    ToolError,
    ToolPermissionLevel,
    ToolScope,
    ToolSpec,
)


def test_tool_spec_supports_internal_and_external_mapping() -> None:
    internal_tool = ToolSpec(
        name="catalog.resolve_service",
        description="Resolve service metadata",
        permission_level=ToolPermissionLevel.READ,
        scope=ToolScope.INTERNAL,
        parameters_schema={"type": "object", "properties": {"service_name": {"type": "string"}}},
        server_name="internal-catalog",
    )
    external_tool = ToolSpec(
        name="thirdparty.ticket.create",
        permission_level=ToolPermissionLevel.WRITE,
        scope=ToolScope.EXTERNAL,
        parameters_schema={"type": "object"},
        server_name="external-ticketing",
        tags=["ticket"],
    )
    assert internal_tool.scope == ToolScope.INTERNAL
    assert external_tool.scope == ToolScope.EXTERNAL


def test_tool_call_request_and_result_can_serialize() -> None:
    request = ToolCallRequest(
        case_id="case-1",
        step_id="step-1",
        skill_name="flows/default-log-triage",
        tool_name="log.query_by_trace_id",
        arguments={"trace_id": "abc123"},
    )
    result = ToolCallResult(
        ok=True,
        tool_name=request.tool_name,
        content={"total": 2, "items": ["log1", "log2"]},
        latency_ms=35,
    )
    payload = result.model_dump(mode="json")
    assert request.arguments["trace_id"] == "abc123"
    assert payload["ok"] is True
    assert payload["latency_ms"] == 35


def test_tool_call_result_can_hold_tool_error() -> None:
    error = ToolError(
        code="TOOL_TIMEOUT",
        message="tool execution timeout",
        details={"timeout_ms": 5000},
        retryable=True,
    )
    result = ToolCallResult(
        ok=False,
        tool_name="code.search",
        error=error,
    )
    assert result.error is not None
    assert result.error.retryable is True
