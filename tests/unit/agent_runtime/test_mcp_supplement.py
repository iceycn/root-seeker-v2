"""Tests for external MCP supplement after default flow."""

from __future__ import annotations

from rootseeker.agent_runtime.mcp_supplement import run_external_mcp_supplement
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.evidence import EvidencePack
from rootseeker.contracts.skill import SkillKind, SkillSpec
from rootseeker.contracts.tool import ToolPermissionLevel, ToolScope, ToolSpec
from rootseeker.mcp_plane.registry import ToolRegistry


def test_run_external_mcp_supplement_skips_without_flag() -> None:
    registry = ToolRegistry()
    skill = SkillSpec(name="flow", slug="flows/test", skill_kind=SkillKind.FLOW)
    results = run_external_mcp_supplement(
        case_request=CaseCreateRequest(
            title="t",
            symptom="s",
            service_name="svc",
            source="error-chat",
        ),
        flow_case_id="case-1",
        evidence_pack=EvidencePack(case_id="case-1", summary=""),
        step_outputs={},
        skill=skill,
        gateway=None,
        tool_registry=registry,
    )
    assert results == []


def test_run_external_mcp_supplement_skips_without_external_tools() -> None:
    registry = ToolRegistry()
    skill = SkillSpec(
        name="flow",
        slug="flows/test",
        skill_kind=SkillKind.FLOW,
        metadata={"allow_external_mcp": True},
    )
    results = run_external_mcp_supplement(
        case_request=CaseCreateRequest(
            title="t",
            symptom="s",
            service_name="svc",
            source="error-chat",
        ),
        flow_case_id="case-1",
        evidence_pack=EvidencePack(case_id="case-1", summary=""),
        step_outputs={},
        skill=skill,
        gateway=None,
        tool_registry=registry,
    )
    assert results == []


def test_run_external_mcp_supplement_registers_external_tools_present() -> None:
    registry = ToolRegistry()
    registry.register_external(
        ToolSpec(
            name="ext.server.echo",
            description="",
            permission_level=ToolPermissionLevel.READ,
            scope=ToolScope.EXTERNAL,
            server_name="server",
        )
    )
    skill = SkillSpec(
        name="flow",
        slug="flows/test",
        skill_kind=SkillKind.FLOW,
        metadata={"allow_external_mcp": True},
    )
    results = run_external_mcp_supplement(
        case_request=CaseCreateRequest(
            title="t",
            symptom="s",
            service_name="svc",
            source="error-chat",
        ),
        flow_case_id="case-1",
        evidence_pack=EvidencePack(case_id="case-1", summary=""),
        step_outputs={},
        skill=skill,
        gateway=None,
        tool_registry=registry,
        tool_planner=None,
    )
    assert results == []
