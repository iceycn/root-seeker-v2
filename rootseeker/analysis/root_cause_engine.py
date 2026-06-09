"""Enhanced Root Cause Engine with multi-hypothesis reasoning."""

from __future__ import annotations

from dataclasses import dataclass

from rootseeker.analysis.convergence_checker import ConvergenceChecker
from rootseeker.analysis.evidence_weighting import EvidenceWeighting
from rootseeker.analysis.hypothesis_generator import HypothesisGenerator
from rootseeker.analysis.hypothesis_validator import HypothesisValidator
from rootseeker.contracts.common import new_id
from rootseeker.contracts.evidence import (
    ContextWindow,
    EvidencePack,
    Hypothesis,
    RootCauseConclusion,
)

__all__ = ["RootCauseAnalysisResult", "RootCauseEngine"]


@dataclass
class RootCauseAnalysisResult:
    """Result of root cause analysis."""

    hypotheses: list[Hypothesis]
    conclusion: RootCauseConclusion
    is_converged: bool = True
    iteration_count: int = 1
    recommendation: str = ""


class RootCauseEngine:
    """Enhanced root cause analysis engine.

    Features:
    - Multi-hypothesis generation
    - Hypothesis validation and ranking
    - Evidence weighting
    - Convergence checking

    The engine is read-only: it only consumes EvidencePack/ContextWindow,
    never makes MCP calls.
    """

    def __init__(
        self,
        *,
        confidence_threshold: float = 0.7,
        min_evidence_count: int = 3,
    ) -> None:
        self._generator = HypothesisGenerator()
        self._validator = HypothesisValidator()
        self._weighting = EvidenceWeighting()
        self._convergence = ConvergenceChecker(
            confidence_threshold=confidence_threshold,
            min_evidence_count=min_evidence_count,
        )

    def analyze(
        self,
        *,
        pack: EvidencePack,
        context: ContextWindow | None = None,
        max_iterations: int = 3,
    ) -> RootCauseAnalysisResult:
        """Perform root cause analysis with multi-hypothesis reasoning.

        Args:
            pack: Evidence pack containing collected evidence
            context: Optional context window for additional context
            max_iterations: Maximum analysis iterations

        Returns:
            RootCauseAnalysisResult with hypotheses and conclusion
        """
        if not pack.items:
            return self._empty_result()

        # Step 1: Generate multiple hypotheses
        hypotheses = self._generator.generate(pack)

        # Step 2: Validate hypotheses
        validations = self._validator.validate_all(hypotheses, pack)

        # Step 3: Weight evidence
        weighted_evidence = self._weighting.weight(pack)

        # Step 4: Check convergence
        convergence = self._convergence.check(hypotheses, validations, pack)

        # Step 5: Build conclusion from top hypothesis
        conclusion = self._build_conclusion(
            hypotheses=hypotheses,
            validations=validations,
            weighted_evidence=weighted_evidence,
            pack=pack,
            context=context,
            convergence=convergence,
        )

        return RootCauseAnalysisResult(
            hypotheses=hypotheses,
            conclusion=conclusion,
            is_converged=convergence.is_converged,
            iteration_count=1,
            recommendation=convergence.recommendation,
        )

    def _empty_result(self) -> RootCauseAnalysisResult:
        """Return result for empty evidence pack."""
        h = Hypothesis(
            hypothesis_id=new_id("hyp-"),
            statement="证据不足，需上游补证",
            evidence_item_ids=[],
        )
        c = RootCauseConclusion(
            title="证据不足",
            narrative="未收集到可用于推断根因的证据项",
            confidence=0.0,
        )
        return RootCauseAnalysisResult(
            hypotheses=[h],
            conclusion=c,
            is_converged=False,
            recommendation="需要收集更多证据",
        )

    def _build_conclusion(
        self,
        *,
        hypotheses: list[Hypothesis],
        validations: list,
        weighted_evidence: list,
        pack: EvidencePack,
        context: ContextWindow | None,
        convergence,
    ) -> RootCauseConclusion:
        """Build conclusion from analysis results."""
        # Get top hypothesis
        if validations:
            top_validation = validations[0]
            top_hypothesis = next(
                (h for h in hypotheses if h.hypothesis_id == top_validation.hypothesis_id),
                hypotheses[0] if hypotheses else None,
            )
        else:
            top_hypothesis = hypotheses[0] if hypotheses else None

        if top_hypothesis is None:
            return RootCauseConclusion(
                title="无法确定根因",
                narrative="分析未能生成有效假设",
                confidence=0.0,
            )

        # Calculate confidence
        confidence = top_validation.confidence if validations else 0.5

        # Build narrative
        evidence_count = len(pack.items)
        context_count = len(context.segments) if context else 0
        hypothesis_count = len(hypotheses)

        narrative = f"共分析 {evidence_count} 条证据，生成 {hypothesis_count} 个假设。"
        if context_count > 0:
            narrative += f" 上下文片段 {context_count} 条。"

        if convergence.is_converged:
            narrative += " 分析已收敛。"
        else:
            narrative += f" {convergence.recommendation}"

        # Extract contributing factors
        contributing_factors = []
        for item in pack.items[:5]:
            if item.type.value not in contributing_factors:
                contributing_factors.append(item.type.value)

        return RootCauseConclusion(
            title=top_hypothesis.statement[:100] if top_hypothesis.statement else "初步结论",
            narrative=narrative,
            confidence=confidence,
            contributing_factors=contributing_factors,
        )
