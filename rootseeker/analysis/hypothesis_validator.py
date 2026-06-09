"""Hypothesis validation and elimination for root cause analysis."""

from __future__ import annotations

from dataclasses import dataclass

from rootseeker.contracts.evidence import EvidenceItem, EvidencePack, Hypothesis

__all__ = ["HypothesisValidator", "ValidationResult"]


@dataclass
class ValidationResult:
    """Result of validating a hypothesis."""

    hypothesis_id: str
    is_valid: bool
    confidence: float
    supporting_count: int
    contradicting_count: int
    reasons: list[str]


class HypothesisValidator:
    """Validate and rank hypotheses based on evidence.

    Validation strategies:
    - Support counting: Count evidence items supporting the hypothesis
    - Contradiction detection: Find evidence that contradicts
    - Confidence scoring: Calculate confidence based on support/contradiction ratio
    """

    def __init__(
        self,
        *,
        min_support_threshold: int = 1,
        contradiction_penalty: float = 0.3,
    ) -> None:
        self._min_support = min_support_threshold
        self._contradiction_penalty = contradiction_penalty

    def validate(self, hypothesis: Hypothesis, pack: EvidencePack) -> ValidationResult:
        """Validate a single hypothesis against evidence pack."""
        supporting = self._count_supporting(hypothesis, pack)
        contradicting = self._count_contradicting(hypothesis, pack)

        confidence = self._calculate_confidence(supporting, contradicting)
        is_valid = supporting >= self._min_support and confidence > 0.1

        reasons: list[str] = []
        if supporting >= 2:
            reasons.append(f"有 {supporting} 条证据支持")
        if contradicting > 0:
            reasons.append(f"有 {contradicting} 条证据可能矛盾")
        if not is_valid:
            reasons.append("支持证据不足或矛盾过多")

        return ValidationResult(
            hypothesis_id=hypothesis.hypothesis_id,
            is_valid=is_valid,
            confidence=confidence,
            supporting_count=supporting,
            contradicting_count=contradicting,
            reasons=reasons,
        )

    def validate_all(
        self,
        hypotheses: list[Hypothesis],
        pack: EvidencePack,
    ) -> list[ValidationResult]:
        """Validate all hypotheses and return sorted by confidence."""
        results = [self.validate(h, pack) for h in hypotheses]
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def filter_valid(
        self,
        hypotheses: list[Hypothesis],
        pack: EvidencePack,
    ) -> list[tuple[Hypothesis, ValidationResult]]:
        """Filter to only valid hypotheses with their validation results."""
        results = []
        for h in hypotheses:
            vr = self.validate(h, pack)
            if vr.is_valid:
                results.append((h, vr))
        results.sort(key=lambda x: x[1].confidence, reverse=True)
        return results

    def _count_supporting(self, hypothesis: Hypothesis, pack: EvidencePack) -> int:
        """Count evidence items supporting the hypothesis."""
        # Evidence items listed in hypothesis are considered supporting
        supporting_ids = set(hypothesis.evidence_item_ids)

        # Also count items with matching keywords
        hypothesis_keywords = self._extract_keywords(hypothesis.statement)
        for item in pack.items:
            if item.item_id in supporting_ids:
                continue
            content = self._get_item_content(item).lower()
            if any(kw in content for kw in hypothesis_keywords):
                supporting_ids.add(item.item_id)

        return len(supporting_ids)

    def _count_contradicting(self, hypothesis: Hypothesis, pack: EvidencePack) -> int:
        """Count evidence items that might contradict the hypothesis."""
        contradiction_keywords = ["success", "ok", "normal", "healthy", "resolved"]

        contradicting = 0
        for item in pack.items:
            if item.item_id in hypothesis.evidence_item_ids:
                continue
            content = self._get_item_content(item).lower()
            # Check if item indicates success but hypothesis suggests failure
            if any(ck in content for ck in contradiction_keywords):
                if any(hk in hypothesis.statement.lower() for hk in ["error", "fail", "异常", "故障"]):
                    contradicting += 1

        return contradicting

    def _calculate_confidence(self, supporting: int, contradicting: int) -> float:
        """Calculate confidence score based on support and contradiction."""
        if supporting == 0:
            return 0.0

        base_confidence = min(0.9, 0.3 + 0.15 * supporting)
        penalty = contradicting * self._contradiction_penalty
        return max(0.0, min(1.0, base_confidence - penalty))

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful keywords from text."""
        # Simple keyword extraction - in production would use NLP
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "by", "for", "to", "of", "and", "or"}
        words = text.lower().split()
        return [w for w in words if w not in stop_words and len(w) > 2]

    def _get_item_content(self, item: EvidenceItem) -> str:
        """Get searchable content from evidence item."""
        parts: list[str] = []
        content = item.content
        if content:
            for v in content.values():
                if isinstance(v, str):
                    parts.append(v)
                elif isinstance(v, dict):
                    parts.append(str(v))
        return " ".join(parts)
