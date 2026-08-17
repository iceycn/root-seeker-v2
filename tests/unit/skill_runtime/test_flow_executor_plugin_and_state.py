from pathlib import Path
from unittest.mock import MagicMock

from rootseeker.bootstrap import create_dev_runtime
from rootseeker.contracts.case import CaseCreateRequest, CaseStatus, StepStatus
from rootseeker.contracts.skill import SkillKind, SkillSpec, SkillStepDefinition
from rootseeker.skill_runtime.flow_executor import (
    DEFAULT_FLOW_PLUGIN_ID,
    _resolve_flow_plugin_id,
    execute_skill_flow,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_resolve_flow_plugin_id_prefers_skill_metadata() -> None:
    skill = SkillSpec(
        name="Custom Flow",
        slug="flows/custom",
        skill_kind=SkillKind.FLOW,
        version="1.0.0",
        steps=[],
        metadata={"flow_plugin_id": "builtin.custom_flow"},
    )
    assert _resolve_flow_plugin_id(skill, None) == "builtin.custom_flow"
    assert _resolve_flow_plugin_id(skill, "explicit.plugin") == "explicit.plugin"


def test_resolve_flow_plugin_id_falls_back_to_default() -> None:
    skill = SkillSpec(name="X", slug="flows/x", skill_kind=SkillKind.FLOW, version="1.0.0", steps=[])
    assert _resolve_flow_plugin_id(skill, None) == DEFAULT_FLOW_PLUGIN_ID


def test_execute_skill_flow_uses_metadata_flow_plugin_id() -> None:
    runtime = create_dev_runtime(_repo_root())
    custom_plugin_id = "builtin.default_log_triage_flow"
    flow_skill = SkillSpec(
        name="Test Plugin Flow",
        slug="flows/test-plugin-id",
        skill_kind=SkillKind.FLOW,
        version="1.0.0",
        metadata={"flow_plugin_id": custom_plugin_id},
        steps=[
            SkillStepDefinition(
                step_id="noop",
                name="noop",
                action="incident.normalize",
                tool_skill_slug="tools/incident-normalize",
            )
        ],
    )
    gateway = runtime.gateway
    original_invoke = gateway.invoke
    seen_plugin_ids: list[str] = []

    def tracking_invoke(req, *, plugin_id, actor=""):
        seen_plugin_ids.append(plugin_id)
        return original_invoke(req, plugin_id=plugin_id, actor=actor)

    gateway.invoke = MagicMock(side_effect=tracking_invoke)

    result = execute_skill_flow(
        case_request=CaseCreateRequest(
            title="t",
            symptom="s",
            service_name="order-service",
            source="test",
        ),
        skill_registry=runtime.skill_registry,
        tool_registry=runtime.tool_registry,
        gateway=gateway,
        flow_skill=flow_skill,
    )

    assert seen_plugin_ids
    assert all(pid == custom_plugin_id for pid in seen_plugin_ids)
    assert result.case.status == CaseStatus.COMPLETED
    assert all(step.status == StepStatus.COMPLETED for step in result.case.steps)
