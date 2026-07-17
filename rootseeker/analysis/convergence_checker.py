"""Convergence checking for root cause analysis."""

from __future__ import annotations

from dataclasses import dataclass

from rootseeker.analysis.hypothesis_validator import ValidationResult
from rootseeker.contracts.evidence import EvidencePack, Hypothesis

__all__ = ["ConvergenceChecker", "ConvergenceStatus"]


@dataclass
class ConvergenceStatus:
    """Status of convergence check."""

    is_converged: bool
    confidence_threshold_met: bool
    sufficient_evidence: bool
    top_hypothesis_gap: float  # Gap between top 2 hypotheses
    recommendation: str
    iterations_remaining: int


class ConvergenceChecker:
    """Check if root cause analysis has converged.

    Convergence criteria:
    - Confidence threshold: Top hypothesis has sufficient confidence
    - Evidence sufficiency: Enough evidence has been collected
    - Hypothesis separation: Clear winner among hypotheses
    - Iteration limit: Maximum iterations reached
    """

    def __init__(
        self,
        *,
        confidence_threshold: float = 0.7,
        min_evidence_count: int = 3,
        min_hypothesis_gap: float = 0.2,
        max_iterations: int = 5,
    ) -> None:
        self._confidence_threshold = confidence_threshold
        self._min_evidence = min_evidence_count
        self._min_gap = min_hypothesis_gap
        self._max_iterations = max_iterations

    def check(
        self,
        hypotheses: list[Hypothesis],
        validations: list[ValidationResult],
        pack: EvidencePack,
        current_iteration: int = 1,
    ) -> ConvergenceStatus:
        """Check if analysis has converged."""
        confidence_met = self._check_confidence(validations)
        evidence_sufficient = self._check_evidence(pack)
        gap = self._calculate_hypothesis_gap(validations)
        iterations_remaining = max(0, self._max_iterations - current_iteration)

        is_converged = (
            confidence_met and evidence_sufficient and gap >= self._min_gap
        ) or current_iteration >= self._max_iterations

        recommendation = self._build_recommendation(
            is_converged,
            confidence_met,
            evidence_sufficient,
            gap,
            iterations_remaining,
        )

        return ConvergenceStatus(
            is_converged=is_converged,
            confidence_threshold_met=confidence_met,
            sufficient_evidence=evidence_sufficient,
            top_hypothesis_gap=gap,
            recommendation=recommendation,
            iterations_remaining=iterations_remaining,
        )

    def _check_confidence(self, validations: list[ValidationResult]) -> bool:
        """Check if top hypothesis meets confidence threshold."""
        if not validations:
            return False
        top_confidence = validations[0].confidence if validations else 0.0
        return top_confidence >= self._confidence_threshold

    def _check_evidence(self, pack: EvidencePack) -> bool:
        """Check if sufficient evidence has been collected."""
        return len(pack.items) >= self._min_evidence

    def _calculate_hypothesis_gap(self, validations: list[ValidationResult]) -> float:
        """Calculate gap between top 2 hypotheses."""
        if len(validations) < 2:
            return 1.0 if validations else 0.0

        sorted_validations = sorted(validations, key=lambda v: v.confidence, reverse=True)
        return sorted_validations[0].confidence - sorted_validations[1].confidence

    def _build_recommendation(
        self,
        is_converged: bool,
        confidence_met: bool,
        evidence_sufficient: bool,
        gap: float,
        iterations_remaining: int,
    ) -> str:
        """Build recommendation for next steps."""
        if is_converged:
            return "分析已收敛，可以得出结论"

        recommendations: list[str] = []

        if not confidence_met:
            recommendations.append("需要更多证据提高置信度")
        if not evidence_sufficient:
            recommendations.append(f"证据数量不足（当前需要至少 {self._min_evidence} 条）")
        if gap < self._min_gap:
            recommendations.append("假设区分度不够，需要更多差异化证据")

        if iterations_remaining > 0:
            recommendations.append(f"剩余 {iterations_remaining} 轮迭代")
        else:
            recommendations.append("已达最大迭代次数，强制收敛")

        return "; ".join(recommendations)
