"""Enhanced Root Cause Engine with multi-hypothesis reasoning."""

from __future__ import annotations

from dataclasses import dataclass

from rootseeker.analysis.convergence_checker import ConvergenceChecker, ConvergenceStatus
from rootseeker.analysis.evidence_expander import EvidenceExpander
from rootseeker.analysis.evidence_weighting import EvidenceWeighting, WeightedEvidence
from rootseeker.analysis.hypothesis_generator import HypothesisGenerator
from rootseeker.analysis.hypothesis_validator import HypothesisValidator
from rootseeker.contracts.common import new_id
from rootseeker.contracts.evidence import (
    ContextWindow,
    EvidenceItem,
    EvidencePack,
    EvidenceType,
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
        min_hypothesis_gap: float = 0.2,
    ) -> None:
        self._confidence_threshold = confidence_threshold
        self._min_evidence_count = min_evidence_count
        self._min_hypothesis_gap = min_hypothesis_gap
        self._generator = HypothesisGenerator()
        self._validator = HypothesisValidator()
        self._weighting = EvidenceWeighting()

    def analyze(
        self,
        *,
        pack: EvidencePack,
        context: ContextWindow | None = None,
        max_iterations: int = 3,
        evidence_expander: EvidenceExpander | None = None,
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

        max_iters = max(1, max_iterations)
        convergence_checker = ConvergenceChecker(
            confidence_threshold=self._confidence_threshold,
            min_evidence_count=self._min_evidence_count,
            min_hypothesis_gap=self._min_hypothesis_gap,
            max_iterations=max_iters,
        )

        hypotheses: list[Hypothesis] = []
        validations: list = []
        weighted_evidence: list = []
        convergence = None
        iteration = 0

        for iteration in range(1, max_iters + 1):
            analysis_pack = pack
            if iteration > 1 and weighted_evidence:
                analysis_pack = self._focus_pack(pack, weighted_evidence, iteration)
            hypotheses = self._generator.generate(analysis_pack)
            validations = self._validator.validate_all(hypotheses, pack)
            weighted_evidence = self._weighting.weight(pack)
            convergence = convergence_checker.check(
                hypotheses,
                validations,
                pack,
                current_iteration=iteration,
            )
            if not convergence.is_converged and iteration < max_iters:
                pack = self._synthesize_iteration_evidence(
                    pack,
                    weighted_evidence=weighted_evidence,
                    validations=validations,
                    iteration=iteration,
                )
                if evidence_expander is not None:
                    pack = evidence_expander.expand(
                        pack,
                        iteration=iteration,
                        convergence=convergence,
                    )
            if convergence.is_converged:
                break

        assert convergence is not None
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
            iteration_count=iteration,
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

    def _focus_pack(
        self,
        pack: EvidencePack,
        weighted_evidence: list[WeightedEvidence],
        iteration: int,
    ) -> EvidencePack:
        """Narrow later iterations to higher-weight evidence subsets."""
        ranked = sorted(weighted_evidence, key=lambda w: w.weight, reverse=True)
        keep_count = max(1, min(len(ranked), self._min_evidence_count + iteration - 1))
        kept_ids = {w.item.item_id for w in ranked[:keep_count]}
        focused_items = [item for item in pack.items if item.item_id in kept_ids]
        if not focused_items:
            return pack
        return EvidencePack(
            case_id=pack.case_id,
            summary=pack.summary,
            items=focused_items,
        )

    def _synthesize_iteration_evidence(
        self,
        pack: EvidencePack,
        *,
        weighted_evidence: list[WeightedEvidence],
        validations: list,
        iteration: int,
    ) -> EvidencePack:
        """Add derived correlation evidence between iterations (no external I/O)."""
        if not weighted_evidence:
            return pack
        if any(
            item.source == "root_cause_iteration"
            and item.content.get("iteration") == iteration
            for item in pack.items
        ):
            return pack

        ranked = sorted(weighted_evidence, key=lambda w: w.weight, reverse=True)
        top = ranked[0]
        top_hypothesis_id = validations[0].hypothesis_id if validations else ""
        derived = EvidenceItem(
            item_id=new_id("ev-derived-"),
            type=EvidenceType.OTHER,
            source="root_cause_iteration",
            content={
                "iteration": iteration,
                "summary": (
                    f"第 {iteration} 轮分析：高权重证据来自 {top.item.source} "
                    f"({top.item.type.value})，权重 {top.weight:.2f}"
                ),
                "top_hypothesis_id": top_hypothesis_id,
                "top_weight": top.weight,
            },
        )
        return EvidencePack(
            case_id=pack.case_id,
            summary=pack.summary,
            items=[*pack.items, derived],
        )

    def _build_conclusion(
        self,
        *,
        hypotheses: list[Hypothesis],
        validations: list,
        weighted_evidence: list[WeightedEvidence],
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

        # Calculate confidence, optionally boosted by weighted evidence support
        confidence = top_validation.confidence if validations else 0.5
        if weighted_evidence and validations and top_hypothesis:
            evidence_weight = self._weighting.aggregate_weight(
                top_hypothesis.evidence_item_ids,
                weighted_evidence,
            )
            if evidence_weight > 0:
                confidence = min(0.95, confidence * (0.75 + 0.25 * evidence_weight))

        # Contributing factors from highest-weighted evidence types
        contributing_factors: list[str] = []
        if weighted_evidence:
            ranked = sorted(weighted_evidence, key=lambda w: w.weight, reverse=True)
            for weighted in ranked[:5]:
                if weighted.item.source == "root_cause_iteration":
                    continue
                type_val = weighted.item.type.value
                if type_val not in contributing_factors:
                    contributing_factors.append(type_val)
        else:
            for item in pack.items[:5]:
                if item.type.value not in contributing_factors:
                    contributing_factors.append(item.type.value)

        return RootCauseConclusion(
            title=_conclusion_title(pack=pack, top_hypothesis=top_hypothesis),
            narrative=_conclusion_narrative(
                pack=pack,
                top_hypothesis=top_hypothesis,
                convergence=convergence,
            ),
            confidence=confidence,
            contributing_factors=contributing_factors,
        )


_HYPOTHESIS_PREFIXES = (
    "日志中发现错误:",
    "调用链异常:",
    "代码缺陷:",
    "资源耗尽:",
    "配置错误:",
    "依赖服务故障:",
)


def _extracted_field(pack: EvidencePack, key: str) -> str:
    for item in pack.items:
        extracted = (item.content or {}).get("extracted")
        if not isinstance(extracted, dict):
            continue
        value = extracted.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if key == "call_chain" and isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str) and first.strip():
                return first.strip()
    return ""


def _strip_hypothesis_prefix(statement: str) -> str:
    text = statement.strip()
    for prefix in _HYPOTHESIS_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def _conclusion_title(*, pack: EvidencePack, top_hypothesis: Hypothesis) -> str:
    exception = _extracted_field(pack, "exception_summary")
    if exception:
        return exception[:100]
    cleaned = _strip_hypothesis_prefix(top_hypothesis.statement or "")
    if cleaned:
        return cleaned[:100]
    return "初步结论"


def _conclusion_narrative(
    *,
    pack: EvidencePack,
    top_hypothesis: Hypothesis,
    convergence,
) -> str:
    parts: list[str] = []
    exception = _extracted_field(pack, "exception_summary")
    if exception:
        parts.append(exception[:240])
    fault = _extracted_field(pack, "call_chain")
    if fault and fault not in "".join(parts):
        parts.append(f"故障点：{fault[:160]}")
    if not parts:
        cleaned = _strip_hypothesis_prefix(top_hypothesis.statement or "")
        if cleaned:
            parts.append(cleaned[:240])
    if not getattr(convergence, "is_converged", True):
        recommendation = str(getattr(convergence, "recommendation", "") or "").strip()
        if recommendation:
            parts.append(recommendation)
    return " ".join(parts) if parts else "分析未能生成有效假设"
