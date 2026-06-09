import pytest

from rootseeker.contracts.case import CaseStatus, StepStatus
from rootseeker.contracts.evidence import EvidenceType
from rootseeker.contracts.io import CaseAccepted, EvidenceCollectRequest, SkillFilterRequest
from rootseeker.contracts.skill import SkillSourceKind
from rootseeker.contracts.state_machine import (
    StateTransitionError,
    validate_case_transition,
    validate_step_transition,
)


def test_skill_filter_request_and_case_accepted_json() -> None:
    filt = SkillFilterRequest(
        tags=["triage"],
        triggers=["webhook"],
        text_query="timeout",
        source_kind=SkillSourceKind.BUILTIN,
    )
    acc = CaseAccepted(case_id="c1", status=CaseStatus.PENDING, message="queued")
    assert filt.model_dump(mode="json")["source_kind"] == "builtin"
    assert acc.case_id == "c1"


def test_evidence_collect_request() -> None:
    req = EvidenceCollectRequest(
        case_id="c1",
        step_id="s1",
        kinds=[EvidenceType.LOG, EvidenceType.TRACE],
    )
    assert EvidenceType.LOG in req.kinds


def test_validate_case_transition_happy_path() -> None:
    validate_case_transition(CaseStatus.PENDING, CaseStatus.PLANNED)
    validate_case_transition(CaseStatus.PLANNED, CaseStatus.RUNNING)
    validate_case_transition(CaseStatus.RUNNING, CaseStatus.COMPLETED)


def test_validate_case_transition_terminal_blocked() -> None:
    with pytest.raises(StateTransitionError):
        validate_case_transition(CaseStatus.COMPLETED, CaseStatus.RUNNING)


def test_validate_step_transition() -> None:
    validate_step_transition(StepStatus.PENDING, StepStatus.RUNNING)
    validate_step_transition(StepStatus.RUNNING, StepStatus.COMPLETED)
    with pytest.raises(StateTransitionError):
        validate_step_transition(StepStatus.COMPLETED, StepStatus.RUNNING)
