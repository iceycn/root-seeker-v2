from __future__ import annotations

from pathlib import Path

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.gateway import GatewayServer


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_gateway_server_registers_business_methods() -> None:
    """Test that GatewayServer registers business methods when runtime is provided."""
    runtime = create_dev_runtime(_repo_root())
    server = GatewayServer(runtime=runtime)

    methods = server.methods.list_methods()

    # Check system methods
    assert "system.ping" in methods
    assert "system.list_methods" in methods

    # Check approval methods
    assert "approval.list" in methods
    assert "approval.get" in methods
    assert "approval.approve" in methods
    assert "approval.reject" in methods

    # Check case methods
    assert "case.create" in methods
    assert "case.get" in methods
    assert "case.list" in methods
    assert "case.resume" in methods

    # Check flow methods
    assert "flow.run" in methods
    assert "flow.resume" in methods
    assert "flow.step" in methods
    assert "flow.checkpoints" in methods

    # Check skill methods
    assert "skill.list" in methods
    assert "skill.get" in methods

    # Check tool methods
    assert "tool.invoke" in methods
    assert "tool.list" in methods


def test_gateway_case_create() -> None:
    """Test case.create method."""
    runtime = create_dev_runtime(_repo_root())
    server = GatewayServer(runtime=runtime)

    result = server.methods.invoke("case.create", {
        "title": "Test Case",
        "symptom": "Test symptom",
        "service_name": "test-service",
        "source": "test",
    })

    assert result.get("case_id")
    assert result.get("status") == "completed"
    assert result.get("evidence_count", 0) >= 0


def test_gateway_case_get() -> None:
    """Test case.get method."""
    runtime = create_dev_runtime(_repo_root())
    server = GatewayServer(runtime=runtime)

    # Create a case first
    create_result = server.methods.invoke("case.create", {
        "title": "Test Case for Get",
        "symptom": "Test symptom",
        "service_name": "test-service",
    })
    case_id = create_result["case_id"]

    # Get the case
    result = server.methods.invoke("case.get", {"case_id": case_id})

    assert result.get("found") is True
    assert result.get("case", {}).get("case_id") == case_id


def test_gateway_case_list_returns_created_cases() -> None:
    """Test case.list returns cases from the runtime store."""
    runtime = create_dev_runtime(_repo_root())
    server = GatewayServer(runtime=runtime)

    create_result = server.methods.invoke("case.create", {
        "title": "Test Case for List",
        "symptom": "Test symptom",
        "service_name": "test-service",
    })

    result = server.methods.invoke("case.list", {"status": "completed", "limit": 10})

    assert result["total"] >= 1
    assert any(item["case_id"] == create_result["case_id"] for item in result["items"])


def test_gateway_skill_list() -> None:
    """Test skill.list method."""
    runtime = create_dev_runtime(_repo_root())
    server = GatewayServer(runtime=runtime)

    result = server.methods.invoke("skill.list", {})

    assert "items" in result
    assert result["total"] >= 1
    slugs = [s["slug"] for s in result["items"]]
    assert "flows/default-log-triage" in slugs


def test_gateway_skill_get() -> None:
    """Test skill.get method."""
    runtime = create_dev_runtime(_repo_root())
    server = GatewayServer(runtime=runtime)

    result = server.methods.invoke("skill.get", {"slug": "flows/default-log-triage"})

    assert result.get("found") is True
    assert result.get("skill", {}).get("slug") == "flows/default-log-triage"


def test_gateway_tool_list() -> None:
    """Test tool.list method."""
    runtime = create_dev_runtime(_repo_root())
    server = GatewayServer(runtime=runtime)

    result = server.methods.invoke("tool.list", {})

    assert "items" in result
    assert result["total"] >= 1
    names = [t["name"] for t in result["items"]]
    assert "catalog.resolve_service" in names


def test_gateway_flow_run() -> None:
    """Test flow.run method."""
    runtime = create_dev_runtime(_repo_root())
    server = GatewayServer(runtime=runtime)

    result = server.methods.invoke("flow.run", {
        "title": "Flow Test",
        "symptom": "Test symptom",
        "service_name": "test-service",
    })

    assert result.get("case_id")
    assert result.get("flow_run_id")
    assert result.get("status") == "completed"


def test_gateway_flow_checkpoints() -> None:
    """Test flow.checkpoints method."""
    runtime = create_dev_runtime(_repo_root())
    server = GatewayServer(runtime=runtime)

    # Run a flow first; the gateway methods should share one checkpoint store.
    run_result = server.methods.invoke("flow.run", {
        "title": "Checkpoint Test",
        "symptom": "Test",
        "service_name": "test-service",
    })

    # List checkpoints filtered by case_id
    result = server.methods.invoke("flow.checkpoints", {
        "case_id": run_result["case_id"],
        "limit": 10,
    })

    assert "items" in result
    assert any(item["flow_run_id"] == run_result["flow_run_id"] for item in result["items"])


def test_gateway_flow_resume_sees_checkpoint_from_flow_run() -> None:
    """Test flow.resume can see a checkpoint created by flow.run."""
    runtime = create_dev_runtime(_repo_root())
    server = GatewayServer(runtime=runtime)

    run_result = server.methods.invoke("flow.run", {
        "title": "Resume Checkpoint Test",
        "symptom": "Test",
        "service_name": "test-service",
    })

    result = server.methods.invoke("flow.resume", {
        "flow_run_id": run_result["flow_run_id"],
        "case_request": {
            "title": "Resume Checkpoint Test",
            "symptom": "Test",
            "service_name": "test-service",
            "source": "gateway-test",
            "metadata": {},
        },
    })

    assert result["resumed"] is False
    assert result["reason"] == "skipped_completed"


def test_gateway_tool_invoke() -> None:
    """Test tool.invoke method."""
    runtime = create_dev_runtime(_repo_root())
    server = GatewayServer(runtime=runtime)

    result = server.methods.invoke("tool.invoke", {
        "tool_name": "catalog.resolve_service",
        "arguments": {
            "tenant": "demo",
            "environment": "prod",
            "service_name": "order-service",
        },
    })

    assert result.get("ok") is True
    assert "content" in result


def test_gateway_approval_methods_can_approve_pending_tool(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_LLM_ENABLED", "false")
    monkeypatch.setenv("ROOTSEEKER_APPROVAL_REQUIRED_FOR_WRITE_TOOLS", "true")
    runtime = create_dev_runtime(_repo_root())
    server = GatewayServer(runtime=runtime)

    first = server.methods.invoke("tool.invoke", {
        "tool_name": "repo.register",
        "case_id": "approval-case",
        "step_id": "repo-register",
        "arguments": {"name": "approval-repo", "url": "/tmp/approval-repo", "branch": "main"},
    })
    assert first["ok"] is False
    assert first["error"].code == "APPROVAL_REQUIRED"
    approval_id = first["error"].details["approval_id"]

    pending = server.methods.invoke("approval.list", {"status": "pending"})
    assert any(item["approval_id"] == approval_id for item in pending["items"])

    approved = server.methods.invoke("approval.approve", {
        "approval_id": approval_id,
        "actor": "unit-test",
        "reason": "safe notification",
    })
    assert approved["approval"]["status"] == "approved"

    retry = server.methods.invoke("tool.invoke", {
        "tool_name": "repo.register",
        "case_id": "approval-case",
        "step_id": "repo-register",
        "arguments": {
            "name": "approval-repo",
            "url": "/tmp/approval-repo",
            "branch": "main",
            "approval_id": approval_id,
        },
    })
    assert retry["ok"] is True
