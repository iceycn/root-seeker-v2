from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from rootseeker.contracts.common import utc_now
from rootseeker.evaluation.quality_gate import QualityGateResult

__all__ = ["EvaluationReport", "build_evaluation_report"]


@dataclass
class EvaluationReport:
    report_id: str
    suite_name: str
    generated_at: datetime = field(default_factory=utc_now)
    case_count: int = 0
    aggregate_metrics: dict[str, float] = field(default_factory=dict)
    gate_passed: bool = False
    gate_policy_name: str = "default-release"
    release_allowed: bool = False
    gate_reasons: list[str] = field(default_factory=list)
    case_summaries: list[dict[str, Any]] = field(default_factory=list)


def build_evaluation_report(
    *,
    report_id: str,
    suite_name: str,
    case_count: int,
    aggregate_metrics: dict[str, float],
    gate_result: QualityGateResult,
    case_summaries: list[dict[str, Any]],
) -> EvaluationReport:
    return EvaluationReport(
        report_id=report_id,
        suite_name=suite_name,
        case_count=case_count,
        aggregate_metrics=dict(aggregate_metrics),
        gate_passed=gate_result.passed,
        gate_policy_name=gate_result.policy_name,
        release_allowed=gate_result.release_allowed,
        gate_reasons=list(gate_result.reasons),
        case_summaries=list(case_summaries),
    )
