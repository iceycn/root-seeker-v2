from pathlib import Path

import pytest

from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.skill import SkillKind
from rootseeker.skill_system.composer import SkillComposer
from rootseeker.skill_system.content_loader import SkillContentLoader
from rootseeker.skill_system.registry import (
    DEFAULT_FLOW_SKILL_SLUG,
    LEGACY_SKILL_SLUG_ALIAS,
    build_registry_from_builtin_skills,
)
from rootseeker.skill_runtime.llm_step_argument_planner import parse_step_argument_content
from rootseeker.skill_runtime.rule_step_argument_resolver import RuleStepArgumentResolver


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_registry_loads_flow_and_tool_skills() -> None:
    registry = build_registry_from_builtin_skills(_repo_root() / "skills" / "builtin")
    flow = registry.get(DEFAULT_FLOW_SKILL_SLUG)
    assert flow is not None
    assert flow.skill_kind == SkillKind.FLOW
    assert len(flow.steps) == 11
    assert registry.get(LEGACY_SKILL_SLUG_ALIAS) is not None
    assert registry.get(LEGACY_SKILL_SLUG_ALIAS).slug == LEGACY_SKILL_SLUG_ALIAS
    tool = registry.resolve_tool_skill("code.search")
    assert tool is not None
    assert tool.slug == "tools/code-lookup"


def test_composer_selects_default_flow() -> None:
    registry = build_registry_from_builtin_skills(_repo_root() / "skills" / "builtin")
    composer = SkillComposer(registry)
    plan = composer.compose(
        CaseCreateRequest(
            title="t",
            symptom="s",
            service_name="svc",
            source="aliyun-webhook",
        )
    )
    assert plan.skill_slug == DEFAULT_FLOW_SKILL_SLUG


def test_content_loader_includes_skill_body() -> None:
    registry = build_registry_from_builtin_skills(_repo_root() / "skills" / "builtin")
    flow = registry.get(DEFAULT_FLOW_SKILL_SLUG)
    assert flow is not None
    step = flow.steps[0]
    tool_skill = registry.get(step.tool_skill_slug)
    assert tool_skill is not None
    loader = SkillContentLoader()
    ctx = loader.load_step_context(flow_skill=flow, step=step, tool_skill=tool_skill)
    assert "incident.normalize" in ctx.to_prompt_text()
    assert ctx.reference_paths


def test_parse_step_argument_content() -> None:
    plan = parse_step_argument_content(
        '{"skip": false, "rationale": "ok", "arguments": {"trace_id": "t1"}}'
    )
    assert plan is not None
    assert plan.arguments["trace_id"] == "t1"
    assert plan.argument_source == "llm"


def test_rule_resolver_semantic_search_defaults() -> None:
    resolver = RuleStepArgumentResolver()
    args = resolver.resolve(
        "code.semantic_search",
        CaseCreateRequest(title="t", symptom="handler timeout", service_name="svc", source="x"),
        step_outputs={},
    )
    assert args["query"] == "handler timeout"
    assert args["limit"] == 10


def test_rule_resolver_code_read_skip_without_path() -> None:
    resolver = RuleStepArgumentResolver()
    args = resolver.resolve(
        "code.read",
        CaseCreateRequest(title="t", symptom="generic error", service_name="svc", source="x"),
        step_outputs={},
    )
    assert args.get("_skip_reason")
