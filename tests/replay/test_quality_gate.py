from rootseeker.evaluation.quality_gate import QualityGatePolicy, evaluate_quality_gate


def test_quality_gate_pass() -> None:
    gate = evaluate_quality_gate(
        {
            "service_accuracy": 1.0,
            "trace_id_accuracy": 1.0,
            "tool_fail_rate": 0.0,
            "sensitive_leak_count": 0.0,
            "audit_completeness": 1.0,
            "stability_score": 1.0,
        }
    )
    assert gate.passed is True
    assert gate.release_allowed is True
    assert not gate.reasons


def test_quality_gate_fail_reasoning() -> None:
    gate = evaluate_quality_gate(
        {
            "service_accuracy": 0.5,
            "trace_id_accuracy": 0.2,
            "tool_fail_rate": 0.8,
            "sensitive_leak_count": 1.0,
            "audit_completeness": 0.4,
            "stability_score": 0.3,
        }
    )
    assert gate.passed is False
    assert gate.release_allowed is False
    assert len(gate.reasons) >= 3


def test_quality_gate_policy_can_be_advisory() -> None:
    gate = evaluate_quality_gate(
        {"service_accuracy": 0.0},
        policy=QualityGatePolicy(
            name="advisory",
            min_thresholds={"service_accuracy": 0.95},
            max_thresholds={},
            blocking=False,
        ),
    )
    assert gate.passed is False
    assert gate.policy_name == "advisory"
    assert gate.release_allowed is True
