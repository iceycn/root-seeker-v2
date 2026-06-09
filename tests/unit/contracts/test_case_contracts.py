from rootseeker.contracts.case import (
    CaseCreateRequest,
    CasePlanSnapshot,
    CaseRecord,
    CaseStatus,
    CaseStep,
    StepStatus,
)


def test_case_create_request_can_build() -> None:
    request = CaseCreateRequest(
        title="API 5xx alarm",
        symptom="gateway timeout spikes",
        service_name="api-gateway",
        source="webhook",
        metadata={"tenant": "demo"},
    )
    assert request.title == "API 5xx alarm"
    assert request.metadata["tenant"] == "demo"


def test_case_record_serialization_contains_status_and_steps() -> None:
    step = CaseStep(
        step_id="step-1",
        name="resolve service",
        skill_name="base/default-log-triage",
        action="catalog.resolve_service",
        status=StepStatus.PENDING,
    )
    case = CaseRecord(
        case_id="case-1",
        title="alarm title",
        symptom="error ratio high",
        service_name="order-service",
        source="webhook",
        status=CaseStatus.PLANNED,
        selected_skills=["base/default-log-triage"],
        steps=[step],
    )
    payload = case.model_dump(mode="json")
    assert payload["status"] == "planned"
    assert payload["steps"][0]["status"] == "pending"


def test_case_plan_snapshot_can_build() -> None:
    snapshot = CasePlanSnapshot(
        case_id="case-2",
        status=CaseStatus.PLANNED,
        selected_skill="base/default-log-triage",
    )
    assert snapshot.case_id == "case-2"
    assert snapshot.status == CaseStatus.PLANNED
