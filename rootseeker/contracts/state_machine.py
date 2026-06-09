from __future__ import annotations

from rootseeker.contracts.case import CaseStatus, StepStatus

__all__ = [
    "ALLOWED_CASE_TRANSITIONS",
    "ALLOWED_STEP_TRANSITIONS",
    "StateTransitionError",
    "validate_case_transition",
    "validate_step_transition",
]


class StateTransitionError(ValueError):
    """Raised when a Case or Step status change is not allowed by the frozen state machine."""


# Responsibility (T1): Case transitions are initiated by supervisor/orchestrator only.
ALLOWED_CASE_TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.PENDING: frozenset({CaseStatus.PLANNED, CaseStatus.FAILED}),
    CaseStatus.PLANNED: frozenset({CaseStatus.RUNNING, CaseStatus.FAILED}),
    CaseStatus.RUNNING: frozenset(
        {CaseStatus.WAITING_APPROVAL, CaseStatus.COMPLETED, CaseStatus.FAILED}
    ),
    CaseStatus.WAITING_APPROVAL: frozenset(
        {CaseStatus.RUNNING, CaseStatus.COMPLETED, CaseStatus.FAILED}
    ),
    CaseStatus.COMPLETED: frozenset(),
    CaseStatus.FAILED: frozenset(),
}

# Step transitions: executor or approval engine; tools must not flip Case top-level status.
ALLOWED_STEP_TRANSITIONS: dict[StepStatus, frozenset[StepStatus]] = {
    StepStatus.PENDING: frozenset({StepStatus.RUNNING, StepStatus.SKIPPED, StepStatus.FAILED}),
    StepStatus.RUNNING: frozenset({StepStatus.COMPLETED, StepStatus.FAILED}),
    StepStatus.COMPLETED: frozenset(),
    StepStatus.FAILED: frozenset(),
    StepStatus.SKIPPED: frozenset(),
}


def validate_case_transition(current: CaseStatus, new: CaseStatus) -> None:
    allowed = ALLOWED_CASE_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise StateTransitionError(
            f"Illegal Case transition: {current.value} -> {new.value}. "
            f"Allowed: {sorted(s.value for s in allowed)}"
        )


def validate_step_transition(current: StepStatus, new: StepStatus) -> None:
    allowed = ALLOWED_STEP_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise StateTransitionError(
            f"Illegal Step transition: {current.value} -> {new.value}. "
            f"Allowed: {sorted(s.value for s in allowed)}"
        )
