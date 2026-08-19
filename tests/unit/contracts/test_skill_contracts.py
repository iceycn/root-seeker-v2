from rootseeker.contracts.skill import (
    GeneratedSkillDraft,
    SkillExecutionPlan,
    SkillSourceKind,
    SkillSpec,
    SkillStepDefinition,
)


def test_skill_spec_can_build_from_skill_md_shape() -> None:
    spec = SkillSpec(
        name="default-log-triage",
        slug="default-log-triage",
        description="Builtin troubleshooting skill",
        tags=["builtin", "triage"],
        triggers=["webhook_alarm"],
        required_tools=["catalog.resolve_service", "log.query_by_trace_id"],
        source_kind=SkillSourceKind.BUILTIN,
        version="1.0.0",
    )
    payload = spec.model_dump(mode="json")
    assert payload["slug"] == "default-log-triage"
    assert payload["steps"] == []


def test_skill_execution_plan_and_generated_draft_can_serialize() -> None:
    step = SkillStepDefinition(
        step_id="step-2",
        name="query logs",
        action="log.query_by_trace_id",
    )
    plan = SkillExecutionPlan(
        skill_slug="default-log-triage",
        steps=[step],
    )
    spec = SkillSpec(
        name="Generated Skill",
        slug="generated-triage",
        source_kind=SkillSourceKind.GENERATED,
    )
    draft = GeneratedSkillDraft(
        draft_id="draft-1",
        title="Generated from high-quality cases",
        spec=spec,
        source_case_ids=["case-a", "case-b"],
        generated_reason="Repeated incident pattern",
    )
    assert plan.skill_slug == "default-log-triage"
    assert draft.spec.source_kind == SkillSourceKind.GENERATED
    assert draft.spec.steps == []


def test_skill_source_kind_includes_external() -> None:
    assert SkillSourceKind.EXTERNAL.value == "external"
