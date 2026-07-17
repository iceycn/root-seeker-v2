from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "QualityGatePolicy",
    "QualityGateResult",
    "default_quality_gate_policy",
    "evaluate_quality_gate",
]


@dataclass
class QualityGatePolicy:
    name: str = "default-release"
    min_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "service_accuracy": 0.95,
            "trace_id_accuracy": 0.8,
            "audit_completeness": 0.99,
            "stability_score": 0.95,
        }
    )
    max_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "tool_fail_rate": 0.05,
            "sensitive_leak_count": 0.0,
        }
    )
    blocking: bool = True


@dataclass
class QualityGateResult:
    passed: bool
    reasons: list[str]
    policy_name: str = "default-release"
    blocking: bool = True

    @property
    def release_allowed(self) -> bool:
        return self.passed or not self.blocking


def default_quality_gate_policy() -> QualityGatePolicy:
    return QualityGatePolicy()


def evaluate_quality_gate(
    aggregate_metrics: dict[str, float],
    policy: QualityGatePolicy | None = None,
) -> QualityGateResult:
    gate_policy = policy or default_quality_gate_policy()
    reasons: list[str] = []
    for metric, threshold in sorted(gate_policy.min_thresholds.items()):
        value = aggregate_metrics.get(metric, 0.0)
        if value < threshold:
            reasons.append(f"{metric} too low: {value:.3f} < {threshold:.3f}")
    for metric, threshold in sorted(gate_policy.max_thresholds.items()):
        value = aggregate_metrics.get(metric, 1.0)
        if value > threshold:
            reasons.append(f"{metric} too high: {value:.3f} > {threshold:.3f}")
    return QualityGateResult(
        passed=(len(reasons) == 0),
        reasons=reasons,
        policy_name=gate_policy.name,
        blocking=gate_policy.blocking,
    )
