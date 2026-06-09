"""Evidence weighting and relevance scoring for root cause analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rootseeker.contracts.evidence import EvidenceItem, EvidencePack

__all__ = ["EvidenceWeighting", "WeightedEvidence", "WeightingStrategy"]


class WeightingStrategy(StrEnum):
    """Strategies for weighting evidence."""

    UNIFORM = "uniform"  # All evidence equal weight
    TYPE_BASED = "type_based"  # Weight by evidence type
    RECENCY_BASED = "recency_based"  # Weight by recency
    COMBINED = "combined"  # Combine multiple strategies


@dataclass
class WeightedEvidence:
    """Evidence item with computed weight."""

    item: EvidenceItem
    weight: float
    relevance_score: float
    factors: dict[str, float]


class EvidenceWeighting:
    """Calculate weights and relevance scores for evidence items.

    Weighting factors:
    - Evidence type: Some types are more reliable indicators
    - Source reliability: Some sources are more trustworthy
    - Recency: More recent evidence may be more relevant
    - Correlation: Evidence correlated with other evidence gets higher weight
    """

    # Default weights by evidence type
    DEFAULT_TYPE_WEIGHTS: dict[str, float] = {
        "log": 1.0,
        "trace": 1.1,
        "code": 0.9,
        "metric": 1.0,
        "service_catalog": 0.8,
        "other": 0.7,
    }

    def __init__(
        self,
        *,
        strategy: WeightingStrategy = WeightingStrategy.COMBINED,
        type_weights: dict[str, float] | None = None,
    ) -> None:
        self._strategy = strategy
        self._type_weights = type_weights or self.DEFAULT_TYPE_WEIGHTS

    def weight(self, pack: EvidencePack) -> list[WeightedEvidence]:
        """Calculate weights for all evidence items in pack."""
        weighted: list[WeightedEvidence] = []

        for item in pack.items:
            factors: dict[str, float] = {}

            if self._strategy in {WeightingStrategy.TYPE_BASED, WeightingStrategy.COMBINED}:
                factors["type"] = self._type_weights.get(item.type.value, 0.7)

            if self._strategy in {WeightingStrategy.RECENCY_BASED, WeightingStrategy.COMBINED}:
                factors["recency"] = self._calculate_recency_weight(item, pack)

            if self._strategy == WeightingStrategy.UNIFORM:
                factors["uniform"] = 1.0

            # Combine factors
            if factors:
                weight = sum(factors.values()) / len(factors)
            else:
                weight = 1.0

            relevance = self._calculate_relevance(item, pack)

            weighted.append(
                WeightedEvidence(
                    item=item,
                    weight=weight,
                    relevance_score=relevance,
                    factors=factors,
                )
            )

        # Normalize weights to sum to 1.0
        total_weight = sum(w.weight for w in weighted)
        if total_weight > 0:
            for w in weighted:
                w.weight = w.weight / total_weight

        return weighted

    def rank(self, pack: EvidencePack) -> list[EvidenceItem]:
        """Rank evidence items by weight (descending)."""
        weighted = self.weight(pack)
        weighted.sort(key=lambda w: w.weight, reverse=True)
        return [w.item for w in weighted]

    def top_k(self, pack: EvidencePack, k: int = 5) -> list[EvidenceItem]:
        """Get top K evidence items by weight."""
        return self.rank(pack)[:k]

    def _calculate_recency_weight(self, item: EvidenceItem, pack: EvidencePack) -> float:
        """Score by how close ``item.collected_at`` is to the newest timestamp in the pack."""
        items = pack.items
        if not items:
            return 1.0
        times = [it.collected_at for it in items]
        newest = max(times)
        oldest = min(times)
        span_seconds = (newest - oldest).total_seconds()
        if span_seconds <= 0:
            return 1.0
        age_seconds = max(0.0, (newest - item.collected_at).total_seconds())
        fresher = max(0.0, min(1.0, 1.0 - age_seconds / span_seconds))
        return 0.5 + 0.5 * fresher

    def _calculate_relevance(self, item: EvidenceItem, pack: EvidencePack) -> float:
        """Calculate relevance score based on correlation with other evidence."""
        # Count how many other items share similar characteristics
        score = 0.0

        for other in pack.items:
            if other.item_id == item.item_id:
                continue

            # Same type increases relevance
            if other.type == item.type:
                score += 0.1

            # Same source increases relevance
            if other.source == item.source:
                score += 0.1

            # Overlapping content keys increases relevance
            if item.content and other.content:
                common_keys = set(item.content.keys()) & set(other.content.keys())
                score += 0.05 * len(common_keys)

        return min(1.0, score)

    def aggregate_weight(self, item_ids: list[str], weighted: list[WeightedEvidence]) -> float:
        """Calculate aggregate weight for a set of evidence items."""
        id_to_weight = {w.item.item_id: w.weight for w in weighted}
        return sum(id_to_weight.get(iid, 0.0) for iid in item_ids)
