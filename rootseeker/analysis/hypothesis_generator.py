"""Multi-hypothesis generation strategies for root cause analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from rootseeker.contracts.common import new_id
from rootseeker.contracts.evidence import EvidenceItem, EvidencePack, Hypothesis

__all__ = ["HypothesisGenerator", "HypothesisTemplate", "HypothesisType"]


class HypothesisType(StrEnum):
    """Types of hypotheses based on evidence patterns."""

    LOG_ERROR = "log_error"
    TRACE_ANOMALY = "trace_anomaly"
    CODE_DEFECT = "code_defect"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    CONFIG_ERROR = "config_error"
    DEPENDENCY_FAILURE = "dependency_failure"
    UNKNOWN = "unknown"


@dataclass
class HypothesisTemplate:
    """Template for generating hypotheses."""

    hypothesis_type: HypothesisType
    pattern: str  # Pattern to match in evidence
    statement_template: str  # Template for hypothesis statement
    weight: float = 1.0  # Base weight for this hypothesis type
    keywords: list[str] = field(default_factory=list)


class HypothesisGenerator:
    """Generate multiple hypotheses from evidence pack.

    Strategies:
    - Pattern-based: Match keywords/patterns in evidence content
    - Type-based: Generate hypotheses based on evidence types
    - Correlation-based: Find related evidence items
    """

    def __init__(self) -> None:
        self._templates = self._build_default_templates()

    def _build_default_templates(self) -> list[HypothesisTemplate]:
        """Build default hypothesis templates."""
        return [
            HypothesisTemplate(
                hypothesis_type=HypothesisType.LOG_ERROR,
                pattern="error",
                statement_template="日志中发现错误: {summary}",
                weight=1.2,
                keywords=["error", "exception", "fail", "timeout"],
            ),
            HypothesisTemplate(
                hypothesis_type=HypothesisType.TRACE_ANOMALY,
                pattern="trace",
                statement_template="调用链异常: {summary}",
                weight=1.1,
                keywords=["latency", "slow", "timeout", "retry"],
            ),
            HypothesisTemplate(
                hypothesis_type=HypothesisType.CODE_DEFECT,
                pattern="code",
                statement_template="代码缺陷: {summary}",
                weight=1.0,
                keywords=["null", "nil", "panic", "index out of range"],
            ),
            HypothesisTemplate(
                hypothesis_type=HypothesisType.RESOURCE_EXHAUSTION,
                pattern="resource",
                statement_template="资源耗尽: {summary}",
                weight=1.3,
                keywords=["oom", "memory", "cpu", "disk", "connection pool"],
            ),
            HypothesisTemplate(
                hypothesis_type=HypothesisType.CONFIG_ERROR,
                pattern="config",
                statement_template="配置错误: {summary}",
                weight=0.9,
                keywords=["config", "env", "missing", "invalid"],
            ),
            HypothesisTemplate(
                hypothesis_type=HypothesisType.DEPENDENCY_FAILURE,
                pattern="dependency",
                statement_template="依赖服务故障: {summary}",
                weight=1.2,
                keywords=["downstream", "upstream", "service", "dependency", "unavailable"],
            ),
        ]

    def generate(self, pack: EvidencePack) -> list[Hypothesis]:
        """Generate multiple hypotheses from evidence pack.

        Returns a list of hypotheses sorted by weight (descending).
        """
        if not pack.items:
            return [
                Hypothesis(
                    hypothesis_id=new_id("hyp-"),
                    statement="证据不足，需上游补证",
                    evidence_item_ids=[],
                )
            ]

        hypotheses: list[Hypothesis] = []
        used_items: set[str] = set()

        # Generate hypotheses based on templates
        for template in self._templates:
            matching_items = self._find_matching_items(pack, template)
            if matching_items:
                hypothesis = self._build_hypothesis(template, matching_items, used_items)
                if hypothesis:
                    hypotheses.append(hypothesis)
                    used_items.update(hypothesis.evidence_item_ids)

        # Generate type-based hypotheses for remaining items
        type_hypotheses = self._generate_type_hypotheses(pack, used_items)
        hypotheses.extend(type_hypotheses)

        # Generate a catch-all hypothesis if needed
        if not hypotheses:
            hypotheses.append(self._build_catch_all_hypothesis(pack))

        # Sort by weight (approximated by evidence count and template weight)
        hypotheses.sort(key=lambda h: len(h.evidence_item_ids), reverse=True)

        return hypotheses[:5]  # Return top 5 hypotheses

    def _find_matching_items(
        self, pack: EvidencePack, template: HypothesisTemplate
    ) -> list[EvidenceItem]:
        """Find evidence items matching a template's keywords."""
        matching: list[EvidenceItem] = []
        for item in pack.items:
            content = self._extract_content(item)
            content_lower = content.lower()
            if any(kw in content_lower for kw in template.keywords):
                matching.append(item)
        return matching

    def _extract_content(self, item: EvidenceItem) -> str:
        """Extract searchable content from evidence item."""
        parts: list[str] = []
        content = item.content
        if content:
            for v in content.values():
                if isinstance(v, str):
                    parts.append(v)
                elif isinstance(v, dict):
                    parts.append(str(v))
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            parts.append(str(item))
                        else:
                            parts.append(str(item))
        return " ".join(parts)

    def _build_hypothesis(
        self,
        template: HypothesisTemplate,
        items: list[EvidenceItem],
        used_items: set[str],
    ) -> Hypothesis | None:
        """Build a hypothesis from matching items."""
        new_items = [i for i in items if i.item_id not in used_items]
        if not new_items:
            return None

        # Build summary from top items' content
        summaries: list[str] = []
        for item in new_items[:3]:
            content = item.content
            if content:
                # Extract first meaningful value from content
                for v in content.values():
                    if isinstance(v, str) and len(v) > 0:
                        summaries.append(v[:50])
                        break
        summary = "; ".join(summaries[:2]) if summaries else f"证据 {new_items[0].item_id}"

        statement = template.statement_template.format(summary=summary)

        return Hypothesis(
            hypothesis_id=new_id("hyp-"),
            statement=statement,
            evidence_item_ids=[i.item_id for i in new_items[:5]],
            metadata={
                "type": template.hypothesis_type.value,
                "weight": template.weight,
                "match_count": len(new_items),
            },
        )

    def _generate_type_hypotheses(
        self, pack: EvidencePack, used_items: set[str]
    ) -> list[Hypothesis]:
        """Generate hypotheses based on evidence types."""
        type_groups: dict[str, list[EvidenceItem]] = {}
        for item in pack.items:
            if item.item_id not in used_items:
                type_groups.setdefault(item.type.value, []).append(item)

        hypotheses: list[Hypothesis] = []
        for evidence_type, items in type_groups.items():
            if len(items) >= 2:  # Only if we have multiple items of same type
                h = Hypothesis(
                    hypothesis_id=new_id("hyp-"),
                    statement=f"基于 {evidence_type} 类型证据的假设",
                    evidence_item_ids=[i.item_id for i in items[:5]],
                    metadata={"type": evidence_type, "weight": 0.8},
                )
                hypotheses.append(h)

        return hypotheses

    def _build_catch_all_hypothesis(self, pack: EvidencePack) -> Hypothesis:
        """Build a catch-all hypothesis when no patterns match."""
        first = pack.items[0]
        return Hypothesis(
            hypothesis_id=new_id("hyp-"),
            statement=f"疑似由 {first.source} 相关异常导致",
            evidence_item_ids=[i.item_id for i in pack.items[:3]],
        )
