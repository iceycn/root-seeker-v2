from rootseeker.contracts.skill import (
    GeneratedSkillDraft,
    SkillCondition,
    SkillExecutionPlan,
    SkillSourceKind,
    SkillSpec,
    SkillStepDefinition,
)


def test_skill_spec_can_build_from_skill_md_shape() -> None:
    step = SkillStepDefinition(
        step_id="step-1",
        name="resolve service",
        action="catalog.resolve_service",
        requires_tools=["catalog.resolve_service"],
        conditions=[
            SkillCondition(field="service_name", operator="exists", value=True),
        ],
    )
    spec = SkillSpec(
        name="Default Log Triage",
        slug="flows/default-log-triage",
        description="Builtin troubleshooting skill",
        tags=["builtin", "triage"],
        triggers=["webhook_alarm"],
        required_tools=["catalog.resolve_service", "log.query_by_trace_id"],
        steps=[step],
        source_kind=SkillSourceKind.BUILTIN,
        version="1.0.0",
    )
    payload = spec.model_dump(mode="json")
    assert payload["slug"] == "flows/default-log-triage"
    assert payload["steps"][0]["action"] == "catalog.resolve_service"


def test_skill_execution_plan_and_generated_draft_can_serialize() -> None:
    step = SkillStepDefinition(
        step_id="step-2",
        name="query logs",
        action="log.query_by_trace_id",
    )
    plan = SkillExecutionPlan(
        skill_slug="flows/default-log-triage",
        steps=[step],
    )
    spec = SkillSpec(
        name="Generated Skill",
        slug="custom/generated-triage",
        steps=[step],
        source_kind=SkillSourceKind.GENERATED,
    )
    draft = GeneratedSkillDraft(
        draft_id="draft-1",
        title="Generated from high-quality cases",
        spec=spec,
        source_case_ids=["case-a", "case-b"],
        generated_reason="Repeated incident pattern",
    )
    assert plan.skill_slug == "flows/default-log-triage"
    assert draft.spec.source_kind == SkillSourceKind.GENERATED
