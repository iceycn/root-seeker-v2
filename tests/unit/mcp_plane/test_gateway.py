from mcp_servers.internal.handlers import register_internal_tools
from rootseeker.contracts.tool import ToolCallRequest, ToolPermissionLevel, ToolScope, ToolSpec
from rootseeker.mcp_plane import McpExternalClient, McpGateway, PolicyGuard, ToolRegistry
from rootseeker.observability.audit import InMemoryAuditLog
from rootseeker.policies import ApprovalStore
from rootseeker.service_catalog.memory_catalog import MemoryServiceCatalog
from tests.support.stub_internal_adapter import StubInternalToolAdapter


def _gateway() -> tuple[McpGateway, InMemoryAuditLog]:
    reg = ToolRegistry()
    register_internal_tools(
        reg,
        adapter=StubInternalToolAdapter(catalog=MemoryServiceCatalog.seeded_default()),
    )
    audit = InMemoryAuditLog()
    policy = PolicyGuard()
    return McpGateway(reg, policy, audit), audit


def test_gateway_invoke_success_appends_audit() -> None:
    gw, audit = _gateway()
    req = ToolCallRequest(
        case_id="c1",
        step_id="s1",
        skill_name="flows/default-log-triage",
        tool_name="catalog.resolve_service",
        arguments={"service_name": "order-service", "tenant": "t1"},
    )
    res = gw.invoke(req, plugin_id="builtin.service_catalog")
    assert res.ok is True
    assert res.content.get("entry", {}).get("service_name") == "order-service"
    assert audit.count() == 1
    events = audit.list_events(case_id="c1")
    assert len(events) == 1
    assert events[0].detail["tool_name"] == "catalog.resolve_service"
    assert events[0].detail["plugin_id"] == "builtin.service_catalog"


def test_gateway_unknown_tool_audits_failure() -> None:
    gw, audit = _gateway()
    req = ToolCallRequest(
        case_id="c1",
        step_id="s1",
        skill_name="flows/default-log-triage",
        tool_name="does.not.exist",
        arguments={},
    )
    res = gw.invoke(req)
    assert res.ok is False
    assert res.error is not None
    assert res.error.code == "TOOL_NOT_REGISTERED"
    assert audit.count() == 1


def test_policy_deny_write_blocks_notify() -> None:
    reg = ToolRegistry()
    register_internal_tools(
        reg,
        adapter=StubInternalToolAdapter(catalog=MemoryServiceCatalog.seeded_default()),
    )
    audit = InMemoryAuditLog()
    policy = PolicyGuard(deny_write=True)
    gw = McpGateway(reg, policy, audit)
    req = ToolCallRequest(
        case_id="c1",
        step_id="s1",
        skill_name="flows/default-log-triage",
        tool_name="notify.send",
        arguments={"channel": "x"},
    )
    res = gw.invoke(req)
    assert res.ok is False
    assert res.error is not None
    assert res.error.code == "POLICY_DENIED"
    assert audit.count() == 1


def test_policy_requires_approval_for_write_tool_then_allows_retry() -> None:
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="internal.write",
            permission_level=ToolPermissionLevel.WRITE,
            server_name="internal",
        ),
        lambda args: {"ok": True, "value": args.get("value")},
    )
    audit = InMemoryAuditLog()
    approvals = ApprovalStore()
    policy = PolicyGuard(approval_store=approvals, require_approval_for_write=True)
    gw = McpGateway(reg, policy, audit)
    req = ToolCallRequest(
        case_id="c1",
        step_id="write",
        skill_name="flows/default-log-triage",
        tool_name="internal.write",
        arguments={"value": "hello"},
    )

    first = gw.invoke(req)
    assert first.ok is False
    assert first.error is not None
    assert first.error.code == "APPROVAL_REQUIRED"
    approval_id = first.error.details["approval_id"]
    approvals.approve(approval_id, actor="unit-test")

    retry = gw.invoke(
        req.model_copy(update={"arguments": {**req.arguments, "approval_id": approval_id}})
    )
    assert retry.ok is True
    assert retry.content["ok"] is True


def test_gateway_invoke_external_tool_via_external_client() -> None:
    reg = ToolRegistry()
    reg.register_external(
        ToolSpec(
            name="external.demo.echo",
            description="echo from external mcp",
            scope=ToolScope.EXTERNAL,
            server_name="demo-server",
            tags=["external"],
        )
    )
    client = McpExternalClient()
    client.register_server("demo-server", lambda tool, args: {"tool": tool, "echo": args.get("x")})
    audit = InMemoryAuditLog()
    gw = McpGateway(reg, PolicyGuard(), audit, external_client=client)
    req = ToolCallRequest(
        case_id="c-ext",
        step_id="s-ext",
        skill_name="flows/default-log-triage",
        tool_name="external.demo.echo",
        arguments={"x": "ok"},
    )
    res = gw.invoke(req, plugin_id="builtin.external")
    assert res.ok is True
    assert res.content["tool"] == "external.demo.echo"
    assert res.content["echo"] == "ok"
    assert audit.count() == 1
