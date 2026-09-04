from pathlib import Path

from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.skill import SkillStepDefinition
from rootseeker.skill_runtime.llm_step_argument_planner import parse_step_argument_content
from rootseeker.skill_runtime.rule_step_argument_resolver import RuleStepArgumentResolver
from rootseeker.skill_system.composer import SkillComposer
from rootseeker.skill_system.content_loader import SkillContentLoader
from rootseeker.skill_system.registry import (
    DEFAULT_FLOW_SKILL_SLUG,
    build_registry_from_builtin_skills,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_registry_loads_flow_and_tool_skills() -> None:
    registry = build_registry_from_builtin_skills(_repo_root() / "skills" / "builtin")
    flow = registry.get(DEFAULT_FLOW_SKILL_SLUG)
    assert flow is not None
    assert flow.name == "default-log-triage"
    assert flow.metadata.get("role") == "playbook"
    assert flow.steps == []
    assert "incident.normalize" in flow.bound_tools
    tool = registry.get("code-lookup")
    assert tool is not None
    assert tool.slug == "code-lookup"
    assert "code.search" in tool.bound_tools


def test_composer_selects_default_flow() -> None:
    registry = build_registry_from_builtin_skills(_repo_root() / "skills" / "builtin")
    composer = SkillComposer(registry)
    plan = composer.compose(
        CaseCreateRequest(
            title="t",
            symptom="s",
            service_name="svc",
            source="aliyun-webhook",
            metadata={"preferred_skill": DEFAULT_FLOW_SKILL_SLUG},
        )
    )
    assert plan.skill_slug == DEFAULT_FLOW_SKILL_SLUG


def test_content_loader_includes_skill_body() -> None:
    registry = build_registry_from_builtin_skills(_repo_root() / "skills" / "builtin")
    flow = registry.get(DEFAULT_FLOW_SKILL_SLUG)
    assert flow is not None
    tool_skill = registry.get("incident-normalize")
    assert tool_skill is not None
    step = SkillStepDefinition(
        step_id="normalize-incident",
        name="Normalize incident input",
        action="incident.normalize",
        tool_skill_slug="incident-normalize",
    )
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


def test_rule_resolver_find_callers_reads_call_chain_from_any_normalize_step() -> None:
    resolver = RuleStepArgumentResolver()
    args = resolver.resolve(
        "code.find_callers",
        CaseCreateRequest(
            title="t",
            symptom="AES decrypt failed",
            service_name="training-manage-api",
            source="x",
        ),
        step_outputs={
            "llm-1-incident-normalize": {
                "extracted": {
                    "call_chain": [
                        "AesTypeHandler.decryptField (AesTypeHandler.java:53)",
                    ]
                }
            }
        },
    )
    assert args["call_chain"][0].startswith("AesTypeHandler.decryptField")
    assert "_skip_reason" not in args


def test_rule_resolver_graph_prefers_inferred_service_over_code_search() -> None:
    resolver = RuleStepArgumentResolver()
    args = resolver.resolve(
        "graph.impact",
        CaseCreateRequest(
            title="t",
            symptom="DuplicateKey in PopRecordService.insertPopRecordLogic",
            service_name="unknown-service",
            source="x",
        ),
        step_outputs={
            "normalize-incident": {
                "case_request": {"service_name": "training-manage-api", "symptom": "boom"},
                "extracted": {
                    "call_chain": ["PopRecordService.insertPopRecordLogic (PopRecordService.java:60)"]
                },
            },
            "code-search": {
                "hits": [{"repo": "6183__bs-integration", "path": "Foo.java"}],
            },
        },
    )
    assert args["repo"] == "training-manage-api"
    assert args["symbol"] == "PopRecordService.insertPopRecordLogic"


def test_build_notify_args_uses_resolved_service_name() -> None:
    from rootseeker.contracts.report import CaseReport
    from rootseeker.skill_runtime.rule_step_argument_resolver import build_notify_args

    message = build_notify_args(
        case_request=CaseCreateRequest(
            title="错误排查请求",
            symptom="2026-07-14 13:49:24.473 [training-manage-api] boom",
            service_name="unknown-service",
            source="admin-error-chat",
        ),
        report=CaseReport(case_id="c1", title="t", summary="s", evidence_item_ids=[]),
    )["message"]
    assert "training-manage-api" in message
    assert "unknown-service" not in message


def test_build_notify_args_formats_readable_incident_card() -> None:
    from rootseeker.contracts.evidence import RootCauseConclusion
    from rootseeker.contracts.report import CaseReport
    from rootseeker.skill_runtime.rule_step_argument_resolver import build_notify_args

    message = build_notify_args(
        case_request=CaseCreateRequest(
            title="错误排查请求",
            symptom=(
                "NOTIFY_SMOKE\n"
                "java.lang.NullPointerException: cannot invoke because is null\n"
                "\tat com.example.NotifySmoke.run(NotifySmoke.java:12)\n"
            ),
            service_name="unknown-service",
            source="admin-error-chat",
        ),
        report=CaseReport(
            case_id="case-9ecbac85",
            title="错误排查请求",
            summary="Collected 5 evidence item(s); generated 2 hypothesis(es).",
            evidence_item_ids=["a", "b", "c", "d", "e"],
            root_cause=RootCauseConclusion(
                title="日志中发现错误: java.lang.NullPointerException: cannot invoke because is null; zoekt",
                narrative="调用链停在 NotifySmoke.run，空指针未做空值保护。",
                confidence=0.62,
            ),
        ),
    )["message"]
    assert "root_cause=" not in message
    assert "evidence=" not in message
    assert "unknown-service" not in message
    assert "错误排查请求" not in message
    assert "; zoekt" not in message
    assert "Collected 5 evidence" not in message
    assert "NullPointerException" in message
    assert "NotifySmoke.run" in message
    assert "case-9ecbac85" in message
    assert "【RootSeeker】" in message
