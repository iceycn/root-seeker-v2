from rootseeker.evaluation import EvaluationReport
from rootseeker.governance import DeploymentDecisionStatus, DeploymentPolicyOrchestrator
from rootseeker.policies import ApprovalEvent, ApprovalStore, InMemoryApprovalEventSink


def test_deployment_policy_allows_passing_release() -> None:
    decision = DeploymentPolicyOrchestrator(ApprovalStore()).evaluate(
        EvaluationReport(
            report_id="eval-pass",
            suite_name="default",
            gate_passed=True,
            release_allowed=True,
        )
    )
    assert decision.status == DeploymentDecisionStatus.ALLOWED
    assert decision.release_allowed is True
    assert not decision.approval_ids


def test_deployment_policy_creates_manual_override_request() -> None:
    approvals = ApprovalStore()
    decision = DeploymentPolicyOrchestrator(approvals).evaluate(
        EvaluationReport(
            report_id="eval-fail",
            suite_name="default",
            gate_passed=False,
            release_allowed=False,
            gate_reasons=["tool_fail_rate too high"],
        )
    )
    assert decision.status == DeploymentDecisionStatus.NEEDS_APPROVAL
    assert decision.release_allowed is False
    approval = approvals.get(decision.approval_ids[0])
    assert approval is not None
    assert approval.tool_name == "release.deploy"


def test_deployment_policy_allows_after_manual_override() -> None:
    approvals = ApprovalStore()
    report = EvaluationReport(
        report_id="eval-override",
        suite_name="default",
        gate_passed=False,
        release_allowed=False,
        gate_reasons=["service_accuracy too low"],
    )
    first = DeploymentPolicyOrchestrator(approvals).evaluate(report)
    approval_id = first.approval_ids[0]
    approvals.approve(approval_id, actor="release-manager")

    second = DeploymentPolicyOrchestrator(approvals).evaluate(report, approval_id=approval_id)
    assert second.status == DeploymentDecisionStatus.ALLOWED
    assert second.release_allowed is True
    assert second.approval_ids == [approval_id]


def test_deployment_policy_blocks_after_rejection() -> None:
    approvals = ApprovalStore()
    report = EvaluationReport(
        report_id="eval-reject",
        suite_name="default",
        gate_passed=False,
        release_allowed=False,
        gate_reasons=["sensitive_leak_count too high"],
    )
    first = DeploymentPolicyOrchestrator(approvals).evaluate(report)
    approval_id = first.approval_ids[0]
    approvals.reject(approval_id, actor="release-manager")

    second = DeploymentPolicyOrchestrator(approvals).evaluate(report, approval_id=approval_id)
    assert second.status == DeploymentDecisionStatus.BLOCKED
    assert second.release_allowed is False


def test_approval_store_emits_request_and_decision_events() -> None:
    sink = InMemoryApprovalEventSink()
    approvals = ApprovalStore(event_sink=sink)

    approval = approvals.create_manual(
        case_id="eval-fail",
        step_id="release-gate",
        tool_name="release.deploy",
        permission_level="admin",
        reason="quality gate blocked release",
    )
    approvals.approve(approval.approval_id, actor="release-manager", reason="override accepted")

    assert [event.event_type for event in sink.events] == [
        "approval.requested",
        "approval.approved",
    ]
    assert sink.events[0].approval.approval_id == approval.approval_id
    assert sink.events[1].actor == "release-manager"
    assert sink.events[1].to_payload()["approval"]["status"] == "approved"


def test_approval_store_keeps_state_when_event_sink_fails() -> None:
    class FailingSink:
        def emit(self, event: ApprovalEvent) -> None:
            raise RuntimeError(f"cannot publish {event.event_type}")

    approvals = ApprovalStore(event_sink=FailingSink())

    approval = approvals.create_manual(
        case_id="eval-fail",
        step_id="release-gate",
        tool_name="release.deploy",
        permission_level="admin",
        reason="quality gate blocked release",
    )
    approvals.reject(approval.approval_id, actor="release-manager", reason="too risky")

    stored = approvals.get(approval.approval_id)
    assert stored is not None
    assert stored.status == "rejected"
    assert approvals.last_event_error == "cannot publish approval.rejected"
