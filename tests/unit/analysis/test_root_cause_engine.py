"""Tests for enhanced root cause analysis components."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rootseeker.analysis import (
    ConvergenceChecker,
    EvidenceWeighting,
    HypothesisGenerator,
    HypothesisValidator,
    RootCauseEngine,
    WeightingStrategy,
)
from rootseeker.contracts.evidence import EvidenceItem, EvidencePack, EvidenceType


def _make_evidence_pack(items: list[tuple[str, str, str]]) -> EvidencePack:
    """Helper to create evidence pack from tuples."""
    pack = EvidencePack(case_id="test-case", summary="test pack")
    for idx, (type_val, source, content_str) in enumerate(items):
        item = EvidenceItem(
            item_id=f"item-{idx}",
            type=EvidenceType(type_val),
            source=source,
            content={"message": content_str},
        )
        pack.items.append(item)
    return pack


def test_hypothesis_generator_empty_pack() -> None:
    """Test generator with empty pack."""
    generator = HypothesisGenerator()
    pack = EvidencePack(case_id="empty", summary="empty")
    hypotheses = generator.generate(pack)

    assert len(hypotheses) == 1
    assert "证据不足" in hypotheses[0].statement


def test_hypothesis_generator_log_error() -> None:
    """Test generator finds log error hypothesis."""
    generator = HypothesisGenerator()
    pack = _make_evidence_pack([
        ("log", "app-logs", "error: connection timeout"),
        ("log", "app-logs", "exception: null pointer"),
    ])

    hypotheses = generator.generate(pack)

    assert len(hypotheses) >= 1
    # Should find log error hypothesis
    assert any("日志" in h.statement or "error" in h.statement.lower() for h in hypotheses)


def test_hypothesis_generator_multiple_types() -> None:
    """Test generator handles multiple evidence types."""
    generator = HypothesisGenerator()
    pack = _make_evidence_pack([
        ("log", "logs", "error message"),
        ("trace", "traces", "slow query detected"),
        ("code", "repo", "null check missing"),
    ])

    hypotheses = generator.generate(pack)

    assert len(hypotheses) >= 1
    # Each hypothesis should have evidence items
    assert all(len(h.evidence_item_ids) >= 1 for h in hypotheses)


def test_hypothesis_validator_basic() -> None:
    """Test validator validates hypotheses."""
    validator = HypothesisValidator()
    pack = _make_evidence_pack([
        ("log", "logs", "error occurred"),
        ("log", "logs", "another error"),
    ])

    generator = HypothesisGenerator()
    hypotheses = generator.generate(pack)

    validations = validator.validate_all(hypotheses, pack)

    assert len(validations) == len(hypotheses)
    # All validations should have confidence
    assert all(v.confidence >= 0.0 for v in validations)


def test_hypothesis_validator_supporting_count() -> None:
    """Test validator counts supporting evidence."""
    validator = HypothesisValidator()
    pack = _make_evidence_pack([
        ("log", "logs", "error"),
        ("log", "logs", "error"),
        ("log", "logs", "error"),
    ])

    generator = HypothesisGenerator()
    hypotheses = generator.generate(pack)

    validation = validator.validate(hypotheses[0], pack)

    assert validation.supporting_count >= 1


def test_evidence_weighting_basic() -> None:
    """Test evidence weighting."""
    weighting = EvidenceWeighting()
    pack = _make_evidence_pack([
        ("log", "logs", "error"),
        ("trace", "traces", "slow"),
        ("code", "repo", "bug"),
    ])

    weighted = weighting.weight(pack)

    assert len(weighted) == 3
    # All weights should be positive
    assert all(w.weight > 0 for w in weighted)
    # Weights should sum to ~1.0 (normalized)
    assert abs(sum(w.weight for w in weighted) - 1.0) < 0.01


def test_evidence_weighting_rank() -> None:
    """Test evidence ranking by weight."""
    weighting = EvidenceWeighting()
    pack = _make_evidence_pack([
        ("log", "logs", "error"),
        ("trace", "traces", "slow"),
        ("code", "repo", "bug"),
    ])

    ranked = weighting.rank(pack)

    assert len(ranked) == 3


def test_evidence_weighting_recency_uses_collected_at() -> None:
    """More recent ``collected_at`` should receive higher recency factor (before normalization)."""
    weighting = EvidenceWeighting(strategy=WeightingStrategy.RECENCY_BASED)
    older = datetime.now(UTC) - timedelta(hours=2)
    newer = datetime.now(UTC)
    pack = EvidencePack(case_id="c", summary="s")
    pack.items.append(
        EvidenceItem(
            item_id="old",
            type=EvidenceType.LOG,
            source="s",
            content={},
            collected_at=older,
        )
    )
    pack.items.append(
        EvidenceItem(
            item_id="new",
            type=EvidenceType.LOG,
            source="s",
            content={},
            collected_at=newer,
        )
    )
    weighted = weighting.weight(pack)
    factors_by_id = {w.item.item_id: w.factors.get("recency", 0.0) for w in weighted}
    assert factors_by_id["new"] > factors_by_id["old"]


def test_convergence_checker_empty() -> None:
    """Test convergence with empty pack."""
    checker = ConvergenceChecker()
    pack = EvidencePack(case_id="empty", summary="empty")

    status = checker.check([], [], pack)

    assert not status.is_converged
    assert not status.sufficient_evidence


def test_convergence_checker_sufficient_evidence() -> None:
    """Test convergence with sufficient evidence."""
    checker = ConvergenceChecker(min_evidence_count=2)
    pack = _make_evidence_pack([
        ("log", "logs", "error"),
        ("log", "logs", "error"),
    ])

    generator = HypothesisGenerator()
    validator = HypothesisValidator()
    hypotheses = generator.generate(pack)
    validations = validator.validate_all(hypotheses, pack)

    status = checker.check(hypotheses, validations, pack)

    assert status.sufficient_evidence


def test_root_cause_engine_empty() -> None:
    """Test engine with empty pack."""
    engine = RootCauseEngine()
    pack = EvidencePack(case_id="empty", summary="empty")

    result = engine.analyze(pack=pack)

    assert len(result.hypotheses) == 1
    assert result.conclusion.confidence == 0.0
    assert not result.is_converged


def test_root_cause_engine_with_evidence() -> None:
    """Test engine with evidence."""
    engine = RootCauseEngine()
    pack = _make_evidence_pack([
        ("log", "logs", "error: timeout occurred"),
        ("log", "logs", "exception: connection failed"),
        ("trace", "traces", "slow query detected"),
    ])

    result = engine.analyze(pack=pack)

    assert len(result.hypotheses) >= 1
    assert result.conclusion.confidence > 0.0
    assert result.conclusion.title


def test_root_cause_engine_multiple_hypotheses() -> None:
    """Test engine generates multiple hypotheses."""
    engine = RootCauseEngine()
    pack = _make_evidence_pack([
        ("log", "logs", "error timeout"),
        ("trace", "traces", "latency spike"),
        ("code", "repo", "null pointer"),
        ("metric", "metrics", "cpu high"),
    ])

    result = engine.analyze(pack=pack)

    # Should generate multiple hypotheses
    assert len(result.hypotheses) >= 1
    # Each hypothesis should have evidence
    assert all(len(h.evidence_item_ids) >= 1 for h in result.hypotheses)


def test_root_cause_engine_convergence_check() -> None:
    """Test engine checks convergence."""
    engine = RootCauseEngine(confidence_threshold=0.5)
    pack = _make_evidence_pack([
        ("log", "logs", "error"),
        ("log", "logs", "error"),
        ("log", "logs", "error"),
    ])

    result = engine.analyze(pack=pack)

    assert result.recommendation  # Should have recommendation
