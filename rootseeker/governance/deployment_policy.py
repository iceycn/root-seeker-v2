from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from rootseeker.evaluation import EvaluationReport
from rootseeker.policies import ApprovalStatus, ApprovalStore

__all__ = ["DeploymentDecisionStatus", "DeploymentPolicyDecision", "DeploymentPolicyOrchestrator"]


class DeploymentDecisionStatus(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    NEEDS_APPROVAL = "needs_approval"


@dataclass(frozen=True)
class DeploymentPolicyDecision:
    status: DeploymentDecisionStatus
    release_allowed: bool
    reasons: list[str] = field(default_factory=list)
    approval_ids: list[str] = field(default_factory=list)
    gate_passed: bool = False
    gate_policy_name: str = "default-release"

    def to_payload(self) -> dict:
        return {
            "status": self.status.value,
            "release_allowed": self.release_allowed,
            "reasons": list(self.reasons),
            "approval_ids": list(self.approval_ids),
            "gate_passed": self.gate_passed,
            "gate_policy_name": self.gate_policy_name,
        }


class DeploymentPolicyOrchestrator:
    def __init__(
        self,
        approval_store: ApprovalStore,
        *,
        allow_manual_override: bool = True,
    ) -> None:
        self._approval_store = approval_store
        self._allow_manual_override = allow_manual_override

    def evaluate(
        self,
        report: EvaluationReport,
        *,
        approval_id: str | None = None,
    ) -> DeploymentPolicyDecision:
        if report.release_allowed:
            return DeploymentPolicyDecision(
                status=DeploymentDecisionStatus.ALLOWED,
                release_allowed=True,
                gate_passed=report.gate_passed,
                gate_policy_name=report.gate_policy_name,
            )

        reasons = list(report.gate_reasons) or ["release gate did not allow deployment"]
        if not self._allow_manual_override:
            return DeploymentPolicyDecision(
                status=DeploymentDecisionStatus.BLOCKED,
                release_allowed=False,
                reasons=reasons,
                gate_passed=report.gate_passed,
                gate_policy_name=report.gate_policy_name,
            )

        if approval_id:
            approval = self._approval_store.get(approval_id)
            if approval is not None and approval.status == ApprovalStatus.APPROVED:
                return DeploymentPolicyDecision(
                    status=DeploymentDecisionStatus.ALLOWED,
                    release_allowed=True,
                    reasons=["manual release override approved"],
                    approval_ids=[approval_id],
                    gate_passed=report.gate_passed,
                    gate_policy_name=report.gate_policy_name,
                )
            if approval is not None and approval.status == ApprovalStatus.REJECTED:
                return DeploymentPolicyDecision(
                    status=DeploymentDecisionStatus.BLOCKED,
                    release_allowed=False,
                    reasons=[*reasons, "manual release override rejected"],
                    approval_ids=[approval_id],
                    gate_passed=report.gate_passed,
                    gate_policy_name=report.gate_policy_name,
                )

        approval = self._approval_store.create_manual(
            case_id=report.report_id,
            step_id="release-gate",
            tool_name="release.deploy",
            permission_level="admin",
            reason="deployment requires manual override because quality gate blocked release",
            metadata={
                "suite_name": report.suite_name,
                "gate_policy_name": report.gate_policy_name,
                "gate_reasons": list(report.gate_reasons),
            },
        )
        return DeploymentPolicyDecision(
            status=DeploymentDecisionStatus.NEEDS_APPROVAL,
            release_allowed=False,
            reasons=reasons,
            approval_ids=[approval.approval_id],
            gate_passed=report.gate_passed,
            gate_policy_name=report.gate_policy_name,
        )
